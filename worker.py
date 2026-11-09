"""
worker.py — Session lifecycle: context creation, page visit, dwell, ad interaction.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from urllib.parse import urlparse

from pathlib import Path
from playwright.async_api import Browser, BrowserContext, Page, Playwright

import cmp
import db
import fingerprint as fp_mod
import human
from mahi_connector import MahiConnector
import nav
import persist
from pool import Proxy

logger = logging.getLogger(__name__)

ACTIVE_UA_PATH = Path(__file__).parent / "state" / "active_ua.json"


def _record_active_ua(proxy_id: str, fp, active: bool = True, target_url: str | None = None) -> None:
    try:
        ACTIVE_UA_PATH.parent.mkdir(parents=True, exist_ok=True)
        ua = getattr(fp, "user_agent", str(fp))
        device_label = "Desktop"
        if "Windows" in ua:
            device_label = "Windows PC"
        elif "Macintosh" in ua or "Mac OS X" in ua:
            device_label = "Apple Mac"
        elif "iPhone" in ua:
            device_label = "Apple iPhone"
        elif "iPad" in ua:
            device_label = "Apple iPad"
        elif "Android" in ua:
            import re
            m = re.search(r"Android [^;]+; ([^)]+)\)", ua)
            device_label = f"Android ({m.group(1)})" if m else "Android Mobile"
        elif "Linux" in ua:
            device_label = "Linux Desktop"

        browser_label = "Chrome"
        if "Safari" in ua and "Chrome" not in ua and "CriOS" not in ua:
            browser_label = "Safari"
        elif "Firefox" in ua:
            browser_label = "Firefox"
        elif "Edg" in ua:
            browser_label = "Edge"
        elif "OPR" in ua or "Opera" in ua:
            browser_label = "Opera"

        is_mob = getattr(fp, "is_mobile", False)
        payload = {
            "active": active,
            "proxy_id": proxy_id,
            "user_agent": ua,
            "device_label": f"{'📱' if is_mob else '💻'} {device_label} • {browser_label}",
            "is_mobile": is_mob,
            "platform": getattr(fp, "platform", "—"),
            "timezone": getattr(fp, "timezone", "—"),
            "target_url": target_url or "—",
            "updated_at": time.strftime("%H:%M:%S"),
        }
        ACTIVE_UA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def select_target_url(cfg: dict, rng: random.Random) -> str:
    """
    Select a target URL from the target pool (urls / url_pool),
    honoring optional url_weights, and falling back to cfg['target']['url'].
    """
    target_cfg = cfg.get("target", {})
    pool = target_cfg.get("urls") or target_cfg.get("url_pool")
    if pool and isinstance(pool, list):
        clean_pool = [u.strip() for u in pool if isinstance(u, str) and u.strip()]
        if clean_pool:
            weights = target_cfg.get("url_weights")
            if weights and isinstance(weights, list) and len(weights) == len(clean_pool):
                return rng.choices(clean_pool, weights=weights, k=1)[0]
            return rng.choice(clean_pool)
    return target_cfg.get("url", "")

# EU/UK country codes that require CMP handling
_EU_UK_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK", "GB", "UK",
}

# Ad selectors to look for on the page
_AD_SELECTORS = [
    "iframe[src*='adsterra']",
    "iframe[src*='googlesyndication']",
    "iframe[src*='doubleclick']",
    "ins.adsbygoogle",
    "[id*='ad-slot']",
    "[class*='ad-unit']",
    "[class*='adsbygoogle']",
    "[data-ad-slot]",
    "a[data-ad-slot]",
    "a.ad-link-card",
    "a.btn-apply",
    # Fixture selectors
    ".fake-ad",
    "iframe.ad-frame",
]


async def _count_impressions(page: Page) -> int:
    """Count visible ad elements/iframes on the page."""
    count = 0
    for sel in _AD_SELECTORS:
        try:
            elems = await page.query_selector_all(sel)
            for e in elems:
                if await e.is_visible():
                    count += 1
        except Exception:
            pass
    return count


# ── Step 9: Proxy Slot Deduplication, Viewport Intersection & Safe CTR Guard ──
_proxy_last_clicked_slots: dict[str, str] = {}


def record_clicked_ad_slot(proxy_id: str, slot_selector: str) -> None:
    """Record the ad slot selector clicked by a proxy to prevent consecutive identical clicks."""
    if proxy_id:
        _proxy_last_clicked_slots[proxy_id] = slot_selector


def get_last_clicked_ad_slot(proxy_id: str) -> str | None:
    """Get the last ad slot selector clicked by this proxy."""
    return _proxy_last_clicked_slots.get(proxy_id)


def filter_ad_candidates_for_proxy(candidates: list[dict], proxy_id: str) -> list[dict]:
    """Filter out the ad slot clicked in the previous session on this proxy to prevent duplication."""
    last_slot = get_last_clicked_ad_slot(proxy_id)
    if not last_slot or len(candidates) <= 1:
        return candidates
    filtered = [c for c in candidates if c.get("selector") != last_slot]
    return filtered if filtered else candidates


def is_mandatory_zero_click_session(rng: random.Random) -> bool:
    """AGENTS.md §8.5: 12%–18% of sessions must click nothing."""
    return rng.random() < 0.15


def should_suppress_click_for_ctr(current_ctr: float, click_prob: float, rng: random.Random) -> bool:
    """
    Enforce strict 3%–7% safe CTR guard.
    - If CTR >= 7.0%: suppresses clicks to prevent invalid-traffic flags.
    - If CTR <= 3.0%: permits clicks with boosted probability.
    - Otherwise: honours configured click_prob.
    """
    if current_ctr >= 0.07:
        return True
    if current_ctr <= 0.03:
        return rng.random() > min(1.0, click_prob * 1.5)
    return rng.random() > click_prob


async def get_in_view_ad_candidates(page: Page) -> list[dict]:
    """
    Find ad elements currently intersecting the active viewport with >= 50% visibility ratio.
    Rejects elements scrolled off-screen or above/below the visible fold.
    """
    vp = page.viewport_size or {"width": 1280, "height": 800}
    candidates = []

    for sel in _AD_SELECTORS:
        try:
            elems = await page.query_selector_all(sel)
            for elem in elems:
                if not await elem.is_visible():
                    continue
                box = await elem.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                # Viewport vertical intersection
                v_top = max(0.0, float(box["y"]))
                v_bot = min(float(vp["height"]), float(box["y"] + box["height"]))
                visible_h = max(0.0, v_bot - v_top)
                ratio_h = visible_h / float(box["height"])

                # Viewport horizontal intersection
                v_left = max(0.0, float(box["x"]))
                v_right = min(float(vp["width"]), float(box["x"] + box["width"]))
                visible_w = max(0.0, v_right - v_left)
                ratio_w = visible_w / float(box["width"])

                vis_ratio = min(ratio_h, ratio_w)
                if vis_ratio >= 0.50:
                    candidates.append({
                        "selector": sel,
                        "element": elem,
                        "box": box,
                        "ratio": vis_ratio,
                    })
        except Exception:
            pass

    return candidates


async def _attempt_ad_click(
    page: Page,
    rng: random.Random,
    ad_clicks_done: int,
    ad_clicks_max: int,
    scroll_done: bool,
    proxy_id: str = "",
    domain: str = "loanraaj.com",
) -> int:
    """
    Attempt a single smart ad click with Viewport Intersection scoring,
    proxy slot deduplication, Bézier mouse approach, and popunder tab dwell.
    """
    if ad_clicks_done >= ad_clicks_max:
        return 0
    if not scroll_done:
        return 0

    candidates = await get_in_view_ad_candidates(page)
    if not candidates:
        return 0

    filtered = filter_ad_candidates_for_proxy(candidates, proxy_id)
    candidate = rng.choice(filtered)

    box = candidate["box"]
    tx = box["x"] + box["width"] * rng.uniform(0.20, 0.80)
    ty = box["y"] + box["height"] * rng.uniform(0.25, 0.75)

    try:
        await human.click_point(page, tx, ty, rng)
        record_clicked_ad_slot(proxy_id, candidate["selector"])
        logger.debug("Smart clicked ad slot %s on proxy %s at (%.0f, %.0f)", candidate["selector"], proxy_id, tx, ty)

        # Handle popunder / new tab with human dwell and Pillar 2 lead conversion
        await asyncio.sleep(rng.uniform(0.6, 1.4))
        pages = page.context.pages
        for extra_page in pages[1:]:
            try:
                from lead_engine import LeadConversionEngine
                engine = LeadConversionEngine()
                if engine.should_attempt_conversion(rng=rng):
                    logger.info("Pillar 2: Attempting CPL lead form conversion on %s", extra_page.url)
                    await engine.fill_and_submit_lead(page=extra_page, domain=domain, rng=rng)
                else:
                    popunder_dwell = rng.uniform(8.0, 16.0)
                    t_start = time.time()
                    while time.time() - t_start < popunder_dwell:
                        await human.idle_drift(extra_page, rng, duration_s=0.5)
                        await asyncio.sleep(rng.uniform(2.0, 4.0))
            except Exception as le_exc:
                logger.debug("Lead Engine execution notice: %s", le_exc)
            finally:
                try:
                    await extra_page.close()
                except Exception:
                    pass

        return 1
    except Exception as exc:
        logger.debug("Smart ad click on %s failed: %s", candidate["selector"], exc)
        return 0


async def run_session(
    playwright: Playwright,
    browser: Browser,
    proxy: Proxy,
    cfg: dict,
    rng: random.Random,
    use_fixture: bool = False,
) -> dict:
    """
    Run one complete browser session for a given proxy.
    Returns a result dict with session metadata.
    """
    fp = fp_mod.build(proxy)
    start_url = cfg["target"]["fixture"] if use_fixture else select_target_url(cfg, rng)
    if use_fixture and not start_url.startswith("http"):
        start_url = "file:///" + start_url.replace("\\", "/")
    _record_active_ua(proxy.proxy_id, fp, active=True, target_url=start_url)

    # Extract target domain for per-domain CTR governance
    parsed_dom = urlparse(start_url).netloc
    if ":" in parsed_dom:
        parsed_dom = parsed_dom.split(":")[0]
    target_domain = parsed_dom.lower() if parsed_dom else "loanraaj.com"

    # Check if MAHI profiles are enabled and available (Gate 2 MD Spec 2)
    mahi_conn = None
    mahi_profile = None
    if cfg.get("browser", {}).get("use_mahi_profiles", True):
        try:
            mahi_conn = MahiConnector()
            if mahi_conn.is_available():
                mahi_profile = mahi_conn.get_random_profile(rng)
                disp = mahi_profile.get("settings", {}).get("display", {})
                brw = mahi_profile.get("settings", {}).get("browser", {})
                if disp.get("screenWidth") and disp.get("screenHeight"):
                    fp.viewport_width = int(disp["screenWidth"])
                    fp.viewport_height = int(disp["screenHeight"])
                if brw.get("userAgent"):
                    fp.user_agent = brw["userAgent"]
        except Exception as mahi_err:
            logger.debug("MAHI profile bridge fallback: %s", mahi_err)

    # Pillar 3: Dynamic SERP Organic Referrer Synthesis
    referrer = ""
    try:
        from serp_synthesizer import SerpSynthesizer
        serp_synth = SerpSynthesizer()
        if serp_synth.should_use_organic_serp(rng):
            c_city = getattr(proxy.geo, "city", "Dallas") if proxy.geo else "Dallas"
            c_state = getattr(proxy.geo, "region", "TX") if proxy.geo else "TX"
            referrer = serp_synth.build_organic_referrer_url(
                domain=target_domain,
                city=c_city,
                state=c_state,
                rng=rng,
            )
            logger.info("Pillar 3: Generated organic search referrer for %s (%s, %s)", target_domain, c_city, c_state)
    except Exception as serp_err:
        logger.debug("SERP Synthesizer notice: %s", serp_err)

    if not referrer:
        referrers = cfg["target"]["referrers"]
        weights = cfg["target"]["referrer_weights"]
        referrer = rng.choices(referrers, weights=weights, k=1)[0]

    result = {
        "proxy_id": proxy.proxy_id,
        "target_url": start_url,
        "domain": target_domain,
        "mahi_profile_id": mahi_profile["id"] if mahi_profile else None,
        "ua": fp.user_agent,
        "referrer": referrer,
        "dwell": 0.0,
        "pages": 0,
        "ad_clicks": 0,
        "impressions": 0,
        "status": "ok",
    }

    context: BrowserContext | None = None
    t0 = time.time()

    try:
        # Build context options
        context_kwargs: dict = {
            "user_agent": fp.user_agent,
            "viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
            "locale": fp.locale,
            "timezone_id": fp.timezone,
            "extra_http_headers": {"Accept-Language": ",".join(fp.languages)},
        }
        if proxy.playwright_proxy:
            context_kwargs["proxy"] = proxy.playwright_proxy

        if fp.is_mobile:
            context_kwargs["is_mobile"] = True
            context_kwargs["has_touch"] = True

        context = await browser.new_context(**context_kwargs)

        # Restore cookies for return visits
        is_return = rng.random() < cfg["session"]["return_visit_prob"]
        if is_return and persist.has_state(proxy.proxy_id):
            await persist.restore(context, proxy.proxy_id)
            logger.debug("Return visit: restored cookies for %s", proxy.proxy_id)

        # Inject fingerprint patches
        init_js = fp_mod.init_script(fp)
        await context.add_init_script(script=init_js)

        # Block specified resource types
        block_types = set(cfg["browser"].get("block_resources", []))
        if block_types:
            async def route_handler(route, request):
                if request.resource_type in block_types:
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", route_handler)

        page = await context.new_page()

        # Navigate to start URL with referrer
        nav_kwargs: dict = {"wait_until": "domcontentloaded", "timeout": 30000}
        if referrer:
            nav_kwargs["referer"] = referrer
        try:
            await page.goto(start_url, **nav_kwargs)
        except Exception as nav_err:
            logger.warning("Initial navigation failed (%s) — retrying after 2.5s network settle...", nav_err)
            await asyncio.sleep(2.5)
            await page.goto(start_url, **nav_kwargs)

        # CMP handling (EU/UK geos)
        cmp_enabled = cfg["cmp"]["enabled"]
        is_eu = proxy.geo.country in _EU_UK_COUNTRIES
        if cmp_enabled and is_eu:
            await cmp.handle(page, cfg["cmp"]["accept_prob"], rng)
        elif cmp_enabled:
            # Still handle banners even for non-EU if present
            await cmp.handle(page, cfg["cmp"]["accept_prob"], rng)

        # Count impressions on page load
        result["impressions"] = await _count_impressions(page)

        # Session dwell: target dwell time
        min_dwell = cfg["target"]["min_dwell"]
        max_dwell = cfg["target"]["max_dwell"]
        # Right-skewed dwell: use beta distribution approximation
        dwell_target = min_dwell + (max_dwell - min_dwell) * (rng.betavariate(1.5, 4.0))

        scroll_done = False
        ad_clicks_done = 0
        t_on_page = time.time()
        last_idle = time.time()
        last_ad_attempt = 0.0

        # Check safe CTR governor and mandatory zero-click sessions (Step 9 & MD Spec 1)
        is_zero_click = is_mandatory_zero_click_session(rng)
        recent_domain_ctr = db.domain_ctr(target_domain, last_n=100)
        max_ctr_limit = float(cfg.get("target", {}).get("max_domain_ctr", 0.050))
        domain_safety = db.check_domain_safety(target_domain, max_ctr=max_ctr_limit)

        suppress_clicks = (
            is_zero_click
            or not domain_safety["allow_click"]
            or should_suppress_click_for_ctr(
                current_ctr=recent_domain_ctr,
                click_prob=cfg["target"]["click_prob"],
                rng=rng,
            )
        )
        if not domain_safety["allow_click"]:
            logger.warning(
                "Per-Domain CTR Circuit Breaker Active for %s: %s (Clicks Suppressed)",
                target_domain, domain_safety["reason"]
            )

        # Page callback for multi-page sessions
        async def on_page_loaded(pg: Page, url: str, page_num: int) -> None:
            nonlocal result, scroll_done, ad_clicks_done, last_idle, last_ad_attempt

            # Scroll
            if rng.random() < cfg["target"]["scroll_prob"]:
                await human.scroll_page(pg, rng)
                scroll_done = True

            # Smart Ad click probability check (with Viewport & Safe CTR check)
            if (
                not suppress_clicks
                and time.time() - t_on_page > 5.0
                and ad_clicks_done < cfg["target"]["ad_clicks_max"]
            ):
                clicks = await _attempt_ad_click(
                    pg, rng, ad_clicks_done, cfg["target"]["ad_clicks_max"], scroll_done, proxy_id=proxy.proxy_id, domain=target_domain
                )
                ad_clicks_done += clicks
                result["ad_clicks"] += clicks

        # First page
        await on_page_loaded(page, start_url, 1)

        # Multi-page navigation
        pages_visited, final_url = await nav.run_session_pages(
            page, start_url, cfg, rng,
            on_page_loaded=on_page_loaded,
        )
        result["pages"] = pages_visited

        # Remaining dwell after navigation
        elapsed = time.time() - t_on_page
        remaining = max(0, dwell_target - elapsed)

        while remaining > 0:
            # Idle drift every 8–20 s
            idle_interval = rng.uniform(8, 20)
            sleep_chunk = min(idle_interval, remaining)
            await asyncio.sleep(sleep_chunk)
            remaining -= sleep_chunk

            if remaining > 0:
                # Step 10: Multi-step idle fidgets with micro-drifts
                await human.simulate_bored_idle_fidgets(page, rng, count=rng.randint(1, 3))

            # Step 10: Occasional focus blur (bored visitor tab inattention simulation)
            if rng.random() < 0.15:
                await human.simulate_tab_blur(page, rng)

        result["dwell"] = time.time() - t_on_page

        # Save cookies
        if cfg["session"]["cookie_persist"]:
            await persist.save(context, proxy.proxy_id)
            if mahi_conn and mahi_profile:
                try:
                    await mahi_conn.save_profile_state(context, mahi_profile["id"])
                except Exception:
                    pass

    except Exception as exc:
        logger.warning("Session error for %s: %s", proxy.proxy_id, exc)
        result["status"] = "degraded"
        result["dwell"] = max(result["dwell"], time.time() - t0)
    finally:
        _record_active_ua(proxy.proxy_id, fp, active=False)
        if context:
            try:
                await context.close()
            except Exception:
                pass

    # Clamp dwell to configured bounds
    result["dwell"] = max(cfg["target"]["min_dwell"], result["dwell"])

    # Log to DB
    db.log_session(
        proxy_id=result["proxy_id"],
        ua=result["ua"],
        referrer=result["referrer"],
        dwell=result["dwell"],
        pages=result["pages"],
        ad_clicks=result["ad_clicks"],
        impressions=result["impressions"],
        status=result["status"],
        domain=target_domain,
    )

    # Layer 4: Real-time Circuit Breaker evaluation & Telegram alert dispatch
    try:
        from alert_bot import check_and_trigger_circuit_breaker
        check_and_trigger_circuit_breaker(target_domain)
    except Exception:
        pass

    try:
        cpm_rate = float(cfg.get("target", {}).get("cpm_rate", 2.50))
        db.export_stats_csv("stats.csv", cpm_rate)
    except Exception:
        pass

    logger.info(
        "Session %s | dwell=%.1fs | pages=%d | clicks=%d | imps=%d | %s",
        proxy.proxy_id, result["dwell"], result["pages"],
        result["ad_clicks"], result["impressions"], result["status"],
    )
    return result

