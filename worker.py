"""
worker.py — Session lifecycle: context creation, page visit, dwell, ad interaction.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from urllib.parse import urlparse

from pathlib import Path
from playwright.async_api import Browser, BrowserContext, Page, Playwright

import ab_test_engine
from ad_network_manager import AdNetworkManager
import cmp
import db
import fingerprint as fp_mod
import geo_router
import human
from mahi_connector import MahiConnector
import nav
import persist
from pool import Proxy
import push_manager as push_mod
import session_tracer as tracer_mod
import ua_provider
import content_aware_session

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


def reset_active_ua(state_path: Path | None = None) -> None:
    """Reset active_ua.json back to idle standby status."""
    from state_cleanup import IDLE_ACTIVE_UA

    target = Path(state_path) if state_path is not None else ACTIVE_UA_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(IDLE_ACTIVE_UA, indent=2), encoding="utf-8")
    except Exception:
        pass


def select_target_url(
    cfg: dict,
    rng: random.Random,
    proxy_country: str | None = None,
    return_tier: bool = False,
) -> str | tuple[str, str]:
    """
    Select a target URL considering geo-targeting rules (Step 4.1).
    If return_tier is True, returns (url, geo_tier). Otherwise returns url string.
    """
    url, tier = geo_router.select_geo_target(cfg, proxy_country, rng)
    if return_tier:
        return url, tier
    return url

# EU/UK country codes that require CMP handling
_EU_UK_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK", "GB", "UK",
}

# Ad selectors to look for on the page (including all 6 live Adsterra unit types)
_AD_SELECTORS = [
    "a.native-ad-btn",
    "a.calc-apply-btn",
    "a.sidebar-ad-btn",
    "a.header-ad-link",
    "a[href*='araplhn.org']",
    "a[href*='asiafilm.org']",
    ".adsterra-banner-slot iframe",
    ".adsterra-native-wrap a",
    ".adsterra-native-wrap iframe",
    "div[id^='container-'] a",
    "div[id^='container-'] iframe",
    "iframe[src*='bauval.org']",
    "iframe[src*='adsterra']",
    "iframe[src*='highperformanceformat']",
    "iframe[src*='effectivegatecpm']",
    "iframe[src*='profitabledisplaynetwork']",
    "[data-ad-slot^='adsterra-']",
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


async def _ensure_ad_slots_rendered_and_viewed(page: Page, rng: random.Random, use_fixture: bool = False) -> None:
    """
    Zero-Waste Viewability Engine:
    1. Waits briefly for Adsterra `bauval.org` & `abscloud.org` scripts to inject DOM/iframe nodes.
    2. Smoothly scrolls each `[data-ad-slot^='adsterra-']` (`728x90`, `native`, `300x250`) into the active
       viewport and pauses 1.5–2.8s so Adsterra's IntersectionObserver registers a 100% viewable impression.
    """
    if use_fixture:
        return
    try:
        await asyncio.sleep(rng.uniform(1.2, 2.0))
        slot_selectors = [
            "[data-ad-slot='adsterra-728x90']",
            "[data-ad-slot='adsterra-native']",
            "[data-ad-slot='adsterra-300x250']",
            "div[id^='container-']",
        ]
        for sel in slot_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.scroll_into_view_if_needed(timeout=2500)
                    await asyncio.sleep(rng.uniform(1.4, 2.4))
            except Exception:
                pass
    except Exception:
        pass


async def _count_impressions(page: Page) -> int:
    """Count visible ad elements/iframes on the page (deduplicated by bounding box)."""
    count = 0
    seen_boxes: set[tuple[int, int]] = set()
    for sel in _AD_SELECTORS:
        try:
            elems = await page.query_selector_all(sel)
            for e in elems:
                if await e.is_visible():
                    box = await e.bounding_box()
                    if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                        key = (int(round(box["x"] / 12.0)), int(round(box["y"] / 12.0)))
                        if key in seen_boxes:
                            continue
                        seen_boxes.add(key)
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


async def _get_effective_viewport(page: Page) -> dict[str, float]:
    """Return page viewport bounds; probes CDP layout metrics when `page.viewport_size` is None (Android CDP)."""
    vp = page.viewport_size
    if vp and vp.get("width") and vp.get("height"):
        return {"width": float(vp["width"]), "height": float(vp["height"])}
    try:
        pc = await page.context.new_cdp_session(page)
        try:
            metrics = await pc.send("Page.getLayoutMetrics")
            vv = metrics.get("cssVisualViewport") or metrics.get("cssLayoutViewport") or {}
            w = float(vv.get("clientWidth") or 0)
            h = float(vv.get("clientHeight") or 0)
            if w > 0 and h > 0:
                return {"width": w, "height": h}
        finally:
            await pc.detach()
    except Exception:
        pass
    return {"width": 1280.0, "height": 800.0}


async def get_in_view_ad_candidates(page: Page) -> list[dict]:
    """
    Find ad elements currently intersecting the active viewport with >= 50% visibility ratio.
    Rejects elements scrolled off-screen or above/below the visible fold.
    """
    vp = await _get_effective_viewport(page)
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


async def _handle_extra_popunder_pages(
    context: BrowserContext,
    rng: random.Random,
    domain: str,
    proxy_country: str,
    cfg: dict | None = None,
    use_fixture: bool = False,
    spawned_pages: list[Page] | None = None,
    main_page: Page | None = None,
) -> None:
    """Dwell naturally on any popunder/advertiser tabs opened during this session and close them cleanly."""
    if spawned_pages is not None:
        extra_pages = [p for p in spawned_pages if p is not main_page and not p.is_closed()]
    else:
        extra_pages = [p for p in context.pages[1:] if p is not main_page]
    if not extra_pages:
        return
    await asyncio.sleep(rng.uniform(0.8, 1.8) if not use_fixture else 0.2)
    for extra_page in list(extra_pages):
        try:
            try:
                await extra_page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            payout_cfg = (cfg or {}).get("payout_safety") or {}
            lead_cfg = (cfg or {}).get("lead_engine") or {}
            explicit_skip = (
                bool(payout_cfg["skip_lead_form_submit"])
                if "skip_lead_form_submit" in payout_cfg
                else (
                    bool(lead_cfg["payout_safe_skip_submit"])
                    if "payout_safe_skip_submit" in lead_cfg
                    else None
                )
            )
            engine = None
            if explicit_skip is True:
                skip_lead = True
            else:
                from lead_engine import LeadConversionEngine
                engine = LeadConversionEngine(config=cfg)
                skip_lead = bool(explicit_skip) if explicit_skip is not None else bool(getattr(engine, "payout_safe_skip_submit", False))
            form_check = {"form_found": False} if skip_lead else await engine.detect_lead_form(extra_page)
            if form_check.get("form_found") and engine and engine.enabled and not skip_lead:
                logger.info("Pillar 2: Lead form detected on %s — executing Geo Persona + Sonjj Email conversion", extra_page.url)
                await engine.fill_and_submit_lead(
                    page=extra_page,
                    domain=domain,
                    rng=rng,
                    country=proxy_country or "IN",
                )
            else:
                popunder_dwell = rng.uniform(0.8, 1.5) if use_fixture else rng.uniform(10.0, 20.0)
                t_start = time.time()
                while time.time() - t_start < popunder_dwell:
                    try:
                        await extra_page.evaluate("window.scrollBy({top: 180, behavior: 'smooth'});")
                    except Exception:
                        pass
                    await human.idle_drift(extra_page, rng, duration_s=0.6)
                    await asyncio.sleep(min(rng.uniform(2.5, 4.5), max(0.0, popunder_dwell - (time.time() - t_start))))
        except Exception as le_exc:
            logger.debug("Lead Engine execution notice: %s", le_exc)
        finally:
            try:
                await extra_page.close()
            except Exception:
                pass


async def _attempt_ad_click(
    page: Page,
    rng: random.Random,
    ad_clicks_done: int,
    ad_clicks_max: int,
    scroll_done: bool,
    proxy_id: str = "",
    domain: str = "loanraaj.com",
    proxy_country: str = "",
    cfg: dict | None = None,
    spawned_pages: list[Page] | None = None,
    cdp_session: Any = None,
    is_mobile: bool = False,
) -> int:
    """
    Attempt a single smart ad click with Viewport Intersection scoring,
    proxy slot deduplication, Bézier/CDP touch approach, and popunder tab dwell.
    """
    if ad_clicks_done >= ad_clicks_max:
        return 0
    if not scroll_done:
        return 0

    candidates = await get_in_view_ad_candidates(page)
    if not candidates:
        # Smoothly bring a high-CPM Adsterra unit back into the viewport before clicking
        for fallback_sel in ("a.native-ad-btn", "a.calc-apply-btn", "a.sidebar-ad-btn", "a.header-ad-link", "a[href*='araplhn.org']", ".adsterra-banner-slot iframe", ".fake-ad"):
            try:
                el = await page.query_selector(fallback_sel)
                if el and await el.is_visible():
                    await el.scroll_into_view_if_needed(timeout=2000)
                    await asyncio.sleep(rng.uniform(0.6, 1.1))
                    break
            except Exception:
                pass
        candidates = await get_in_view_ad_candidates(page)
    if not candidates:
        return 0

    filtered = filter_ad_candidates_for_proxy(candidates, proxy_id)
    candidate = rng.choice(filtered)

    box = candidate["box"]
    tx = box["x"] + box["width"] * rng.uniform(0.20, 0.80)
    ty = box["y"] + box["height"] * rng.uniform(0.25, 0.75)

    try:
        await human.click_point(page, tx, ty, rng, cdp_session=cdp_session, is_mobile=is_mobile)
        record_clicked_ad_slot(proxy_id, candidate["selector"])
        logger.debug("Smart clicked ad slot %s on proxy %s at (%.0f, %.0f)", candidate["selector"], proxy_id, tx, ty)

        # Handle popunder / new advertiser tab with human dwell and scroll
        await _handle_extra_popunder_pages(
            page.context,
            rng,
            domain=domain,
            proxy_country=proxy_country or "IN",
            cfg=cfg,
            spawned_pages=spawned_pages,
            main_page=page,
        )

        return 1
    except Exception as exc:
        logger.debug("Smart ad click on %s failed: %s", candidate["selector"], exc)
        return 0


async def _handle_push_async(
    push_mgr,
    context,
    page,
    rng: random.Random,
    proxy,
    proxy_country: str,
    cmp_accepted: bool,
    domain: str,
    geo_tier: str,
) -> None:
    """
    Fire-and-forget coroutine for push notification handling.
    Runs concurrently with main session dwell, logs result to DB.
    """
    try:
        push_result = await push_mgr.handle(
            context=context,
            page=page,
            rng=rng,
            proxy_country=proxy_country,
            cmp_accepted=cmp_accepted,
            domain=domain,
        )
        if push_result["triggered"]:
            db.log_push_event(
                proxy_id=proxy.proxy_id,
                domain=domain,
                action=push_result["action"],
                delay_s=push_result["delay_s"],
                geo_country=proxy_country,
                geo_tier=geo_tier,
            )
            sub = push_result.get("subscription")
            if push_result["action"] == "allow" and isinstance(sub, dict) and sub.get("endpoint"):
                db.upsert_push_subscriber(
                    domain=domain,
                    endpoint=str(sub.get("endpoint") or ""),
                    provider=str(sub.get("provider") or "vapid_local"),
                    subscription_id=str(sub.get("subscription_id") or ""),
                    p256dh=str(sub.get("p256dh") or ""),
                    auth_secret=str(sub.get("auth") or ""),
                    proxy_id=proxy.proxy_id,
                    geo_country=proxy_country,
                    permission_status="granted",
                    collect_only=bool(push_result.get("collect_only", True)),
                )
            logger.info(
                "Push[%s]: action=%s delay=%.1fs domain=%s",
                proxy.proxy_id,
                push_result["action"],
                push_result["delay_s"],
                domain,
            )
    except Exception as exc:
        logger.debug("Push async handler error: %s", exc)


def _should_use_android_cdp(cfg: dict, fp, use_fixture: bool) -> bool:
    """Route eligible mobile/android sessions through real Android Chrome via ADB CDP (B3)."""
    android_cfg = cfg.get("android_cdp") or {}
    engine = str((cfg.get("browser") or {}).get("engine", "mahi")).strip().lower()
    if use_fixture and not bool(android_cfg.get("allow_fixture", False)):
        return False
    if engine == "android_cdp":
        return True
    if not bool(android_cfg.get("enabled", False)):
        return False
    if bool(android_cfg.get("prefer_for_mobile_only", True)) and not getattr(fp, "is_mobile", False):
        return False
    return True


async def run_session(
    *args,
    use_fixture: bool = False,
    **kwargs,
) -> dict:
    """
    Run one complete browser session for a given proxy.
    Supports both signatures:
      run_session(playwright, browser, proxy, cfg, rng, use_fixture=...)
      run_session(browser, proxy, cfg, rng, use_fixture=...)
    """
    _pw = kwargs.get("playwright")
    if len(args) >= 5:
        _pw = args[0]
        browser = args[1]
        proxy = args[2]
        cfg = args[3]
        rng = args[4]
        if len(args) >= 6:
            use_fixture = args[5]
    elif len(args) == 4:
        browser = args[0]
        proxy = args[1]
        cfg = args[2]
        rng = args[3]
    else:
        browser = kwargs.get("browser", args[0] if len(args) > 0 else None)
        proxy = kwargs.get("proxy", args[1] if len(args) > 1 else None)
        cfg = kwargs.get("cfg", args[2] if len(args) > 2 else {})
        rng = kwargs.get("rng", args[3] if len(args) > 3 else random.Random())
        if "use_fixture" in kwargs:
            use_fixture = kwargs["use_fixture"]
    fp = fp_mod.build(proxy)
    # FP-1: Match UA from 27,103 pool to running browser major version (LEAK-05 fix) & lock 4 dimensions
    try:
        if browser and hasattr(browser, "version"):
            b_ver = browser.version
            if b_ver:
                chrome_major = b_ver.split(".")[0]
                fp.user_agent = ua_provider.get_matching_ua(
                    chrome_major, fp.is_mobile, seed_key=proxy.proxy_id, browser_version=b_ver
                )
                fp_mod.sync_fingerprint_to_ua(fp, fp.user_agent)
    except Exception as ua_err:
        logger.debug("FP-1 UA sync notice: %s", ua_err)
    proxy_country = proxy.geo.country if getattr(proxy, "geo", None) else None
    if use_fixture:
        start_url = cfg["target"]["fixture"]
        geo_tier = geo_router.classify_geo_tier(proxy_country)
    else:
        start_url, geo_tier = select_target_url(cfg, rng, proxy_country=proxy_country, return_tier=True)
    if use_fixture and not start_url.startswith("http"):
        clean_path = start_url.replace("\\", "/").lstrip("/")
        start_url = "file:///" + clean_path

    # Extract target domain for per-domain CTR governance
    parsed_dom = urlparse(start_url).netloc
    if ":" in parsed_dom:
        parsed_dom = parsed_dom.split(":")[0]
    target_domain = parsed_dom.lower() if parsed_dom else "loanraaj.com"

    # ADV-8 & ADV-9: 40% chance of content-aware session
    is_content_aware = (rng.random() < 0.40) and not use_fixture
    content_article = None
    if is_content_aware:
        try:
            content_article = content_aware_session.get_latest_article(target_domain)
            if content_article and content_article.get("url"):
                start_url = content_article["url"]
        except Exception as e_ca:
            logger.debug("Content aware selection notice: %s", e_ca)

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
                    if browser and hasattr(browser, "version") and browser.version:
                        chrome_major = browser.version.split(".")[0]
                        fp.user_agent = ua_provider.get_matching_ua(
                            chrome_major,
                            fp.is_mobile,
                            seed_key=f"{proxy.proxy_id}:{mahi_profile.get('id', '')}",
                            browser_version=browser.version,
                        )
                    fp_mod.sync_fingerprint_to_ua(fp, fp.user_agent)
        except Exception as mahi_err:
            logger.debug("MAHI profile bridge fallback: %s", mahi_err)

    _record_active_ua(proxy.proxy_id, fp, active=True, target_url=start_url)

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
        referrers = cfg["target"].get("referrers", [""])
        weights = cfg["target"].get("referrer_weights")
        if not weights or len(weights) != len(referrers):
            weights = [1.0] * len(referrers)
        referrer = rng.choices(referrers, weights=weights, k=1)[0]

    # Step 4.3: Multi-Ad-Network Selection (or solo Adsterra focus during payout sprints)
    payout_cfg = cfg.get("payout_safety") or {}
    solo_network = str(payout_cfg.get("solo_network") or "").strip()
    if solo_network:
        selected_network = solo_network
    else:
        ad_net_mgr = AdNetworkManager()
        selected_network = ad_net_mgr.select_network(rng)

    # Step 5.3: A/B Testing Strategy Variant Selection
    ab_engine = ab_test_engine.build_from_config(cfg)
    if ab_engine.enabled:
        base_click_prob = float((cfg.get("target") or {}).get("click_prob", 0.045))
        variant = ab_engine.select_variant(rng)
        cfg = ab_engine.apply_variant_to_config(cfg, variant)
        if solo_network or payout_cfg.get("skip_lead_form_submit"):
            max_safe_ctr = float((cfg.get("target") or {}).get("max_domain_ctr", 0.050))
            cfg["target"]["click_prob"] = min(float(cfg["target"]["click_prob"]), base_click_prob, max_safe_ctr)
        variant_id = variant.variant_id
    else:
        variant_id = "default"

    result = {
        "proxy_id": proxy.proxy_id,
        "target_url": start_url,
        "domain": target_domain,
        "ad_network": selected_network,
        "variant_id": variant_id,
        "mahi_profile_id": mahi_profile["id"] if mahi_profile else None,
        "ua": fp.user_agent,
        "referrer": referrer,
        "dwell": 0.0,
        "pages": 0,
        "ad_clicks": 0,
        "impressions": 0,
        "status": "ok",
        "error_reason": "",
        "geo_country": proxy_country or "",
        "geo_tier": geo_tier or "tier1",
        "content_aware": is_content_aware,
    }

    using_android_cdp = _should_use_android_cdp(cfg, fp, use_fixture)
    cdp_bridge = None
    cdp_session = None
    page_cdp: Any = None
    is_mobile_session: bool = bool(fp.is_mobile or using_android_cdp)
    owned_pw_cm = None
    tracer = None
    spawned_pages: list[Page] = []
    _page_listener = None

    context: BrowserContext | None = None
    push_task: asyncio.Task | None = None
    t0 = time.time()
    _session_logged = False  # SCHED-4: guard to ensure exactly-once DB write

    try:
        is_return = rng.random() < cfg["session"]["return_visit_prob"]
        is_return_visitor = False

        if using_android_cdp:
            from playwright.async_api import async_playwright as _async_pw
            from android_cdp_bridge import AndroidCdpBridge

            if _pw is None:
                owned_pw_cm = _async_pw()
                _pw = await owned_pw_cm.__aenter__()

            cdp_bridge = AndroidCdpBridge(cfg)
            fail_closed = bool((cfg.get("android_cdp") or {}).get("fail_closed", True))
            try:
                cdp_session = await cdp_bridge.connect(_pw)
            except Exception as cdp_exc:
                if fail_closed or browser is None:
                    result["error_reason"] = f"AndroidCdpUnavailable: {cdp_exc}"
                    raise RuntimeError(f"Android CDP fail-closed abort: {cdp_exc}") from cdp_exc
                logger.warning("Android CDP unavailable (%s); falling back to local browser.", cdp_exc)
                using_android_cdp = False

        if using_android_cdp and cdp_session is not None:
            context = cdp_session.context
            if cdp_session.user_agent:
                fp.user_agent = cdp_session.user_agent
                result["ua"] = cdp_session.user_agent
                _record_active_ua(proxy.proxy_id, fp, active=True, target_url=start_url)
            if is_return and persist.has_state(proxy.proxy_id):
                is_return_visitor = True
            page, _owned_tid = await cdp_bridge.open_owned_tab(cdp_session)
            try:
                telem = await cdp_bridge.read_isolated_telemetry(cdp_session, page)
                if telem.get("userAgent"):
                    fp.user_agent = str(telem["userAgent"])
                    result["ua"] = fp.user_agent
                if telem.get("platform"):
                    fp.platform = str(telem["platform"])
            except Exception as telem_exc:
                logger.debug("Android CDP telemetry probe notice: %s", telem_exc)
        else:
            # Build context options with 4-Dimension Client-Hint headers locked to UA
            extra_headers = {"Accept-Language": ",".join(fp.languages)}
            extra_headers.update(fp_mod.build_client_hint_headers(fp))
            context_kwargs: dict = {
                "user_agent": fp.user_agent,
                "viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
                "locale": fp.locale,
                "timezone_id": fp.timezone,
                "extra_http_headers": extra_headers,
            }
            if proxy.playwright_proxy:
                context_kwargs["proxy"] = proxy.playwright_proxy

            if fp.is_mobile:
                context_kwargs["is_mobile"] = True
                context_kwargs["has_touch"] = True

            context = await browser.new_context(**context_kwargs)

            # Step 5.1: Start session trace recording (only saves on degraded status)
            tracer = tracer_mod.build_from_config(cfg, proxy.proxy_id)
            await tracer.start(context)

            # Restore cookies for return visits (ADV-7)
            if is_return and persist.has_state(proxy.proxy_id):
                await persist.restore(context, proxy.proxy_id)
                is_return_visitor = True
                profile = persist.get_visitor_profile(proxy.proxy_id)
                visited = profile.get("visited_urls", [])
                if visited and not use_fixture and rng.random() < 0.65:
                    start_url = rng.choice(visited)
                logger.debug("Return visit: restored cookies for %s (visits=%s)", proxy.proxy_id, profile.get("visit_count", 1))

            # Inject coherent seeded fingerprint patches (avoid runtime clobbering from unseeded patches)
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

        # Track pages spawned during THIS session only (safe on shared Android Chrome)
        def _on_new_page(new_p: Page) -> None:
            spawned_pages.append(new_p)
            if using_android_cdp and cdp_bridge and cdp_session:
                asyncio.ensure_future(cdp_bridge.track_page_if_new(cdp_session, new_p))
            try:
                import adsterra_funnel
                adsterra_funnel.attach_adsterra_listener(new_p, domain=target_domain, proxy_id=proxy.proxy_id)
            except Exception:
                pass

        _page_listener = _on_new_page
        context.on("page", _on_new_page)

        # B4: Page-level CDP session for authentic biometric touch/mouse dispatch
        try:
            page_cdp = await context.new_cdp_session(page)
        except Exception as cdp_init_err:
            logger.debug("Page-level CDP session creation notice: %s", cdp_init_err)

        # Real-time Adsterra network handshake tracking
        try:
            import adsterra_funnel
            adsterra_funnel.attach_adsterra_listener(page, domain=target_domain, proxy_id=proxy.proxy_id)
        except Exception as e_af:
            logger.debug("Adsterra tracker attach notice: %s", e_af)

        # Resilient 3-tier navigation with error recovery
        nav_kwargs: dict = {"wait_until": "domcontentloaded", "timeout": 25000}
        if referrer:
            nav_kwargs["referer"] = referrer

        nav_succeeded = False
        nav_error_detail = ""

        # Tier 1: Primary attempt
        try:
            await page.goto(start_url, **nav_kwargs)
            nav_succeeded = True
        except Exception as nav_err1:
            nav_error_detail = f"{type(nav_err1).__name__}: {str(nav_err1)[:80]}"
            logger.warning("Initial navigation to %s failed (%s) — retrying with relaxed commit condition...", start_url, nav_err1)

        # Tier 2: Settle & relaxed retry (commit wait_until)
        if not nav_succeeded:
            await asyncio.sleep(2.0)
            try:
                retry_kwargs = dict(nav_kwargs)
                retry_kwargs["wait_until"] = "commit"
                retry_kwargs["timeout"] = 20000
                await page.goto(start_url, **retry_kwargs)
                nav_succeeded = True
                logger.info("Navigation to %s recovered on Tier-2 retry", start_url)
            except Exception as nav_err2:
                nav_error_detail = f"{type(nav_err2).__name__}: {str(nav_err2)[:80]}"
                logger.warning("Tier-2 retry failed for %s (%s)", start_url, nav_err2)

        # Tier 3: Resilient fallback (remote alternate in live runs, or local fixture in test mode)
        if not nav_succeeded:
            # In live runs, attempt alternate live domains/smartlinks
            if not use_fixture:
                live_fallbacks = ["https://loanraaj.com", "https://rechargekar.com"]
                for fb_url in live_fallbacks:
                    if fb_url not in start_url:
                        try:
                            logger.info("Tier-3: Attempting live alternate fallback to %s", fb_url)
                            await page.goto(fb_url, wait_until="commit", timeout=15000)
                            nav_succeeded = True
                            result["error_reason"] = f"NavRecovered: {nav_error_detail} -> {fb_url}"
                            break
                        except Exception as e_alt:
                            logger.warning("Tier-3 live alternate fallback to %s failed (%s)", fb_url, e_alt)
                if not nav_succeeded:
                    result["error_reason"] = f"NetFailed: {nav_error_detail}"
                    raise RuntimeError(f"All live targets failed. Network disconnected or proxy unreachable.")
            else:
                # Test/Fixture mode only: use local offline fixture
                fixture_path = Path(cfg.get("target", {}).get("fixture", "tests/fixtures/page.html")).resolve()
                clean_path = str(fixture_path).replace("\\", "/").lstrip("/")
                fixture_url = "file:///" + clean_path
                try:
                    logger.info("Tier-3 (Test Mode): Loading local offline fixture: %s", fixture_url)
                    await page.goto(fixture_url, wait_until="commit", timeout=10000)
                    nav_succeeded = True
                    result["error_reason"] = f"FixtureRecovered: {nav_error_detail} -> local fixture"
                except Exception as nav_err3:
                    logger.warning("Tier-3 local fixture failed (%s)", nav_err3)
                    result["error_reason"] = f"NetFailed: {nav_error_detail} | {type(nav_err3).__name__}"
                    raise nav_err3

        # CMP handling (EU/UK geos)
        cmp_enabled = cfg["cmp"]["enabled"]
        is_eu = proxy.geo.country in _EU_UK_COUNTRIES
        cmp_accepted = False
        if cmp_enabled and is_eu:
            cmp_accepted = await cmp.handle(page, cfg["cmp"]["accept_prob"], rng, cdp_session=page_cdp, is_mobile=is_mobile_session)
        elif cmp_enabled:
            # Still handle banners even for non-EU if present
            cmp_accepted = await cmp.handle(page, cfg["cmp"]["accept_prob"], rng, cdp_session=page_cdp, is_mobile=is_mobile_session)

        # Step 4.4: Push Notification Subscription Farming
        push_result = None
        if (cfg.get("push_notifications") or {}).get("enabled", True):
            push_mgr = push_mod.build_from_config(cfg)
            # Run push handling concurrently with the session (non-blocking)
            push_task = asyncio.ensure_future(
                _handle_push_async(
                    push_mgr=push_mgr,
                    context=context,
                    page=page,
                    rng=rng,
                    proxy=proxy,
                    proxy_country=proxy_country or "",
                    cmp_accepted=bool(cmp_accepted),
                    domain=target_domain,
                    geo_tier=geo_tier or "",
                )
            )

        # Count impressions on page load
        result["impressions"] = await _count_impressions(page)

        # Session dwell: target dwell time (STAT-2 lognormal distribution)
        min_dwell = cfg["target"]["min_dwell"]
        max_dwell = cfg["target"]["max_dwell"]
        # STAT-2: Authentic right-skewed human article reading time
        if content_article:
            reading_wpm = rng.uniform(180, 260)
            dwell_target = (content_article.get("word_count", 2200) / reading_wpm) * 60 * rng.uniform(0.70, 1.30)
        else:
            dwell_target = math.exp(rng.gauss(math.log(52.0), 0.65))
        if is_return_visitor:
            dwell_target *= 0.70  # ADV-7: 30% shorter for return visitors
        dwell_target = max(float(min_dwell), min(dwell_target, float(max_dwell)))

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

        # Layer 7: Check statistical anomaly detector circuit breaker
        anomaly_paused = False
        try:
            from anomaly_detector import AnomalyDetector
            is_paused, p_action, p_reason = AnomalyDetector().is_domain_paused(target_domain)
            if is_paused:
                anomaly_paused = True
                logger.warning(
                    "Anomaly Circuit Breaker Active for %s: [%s] %s (Clicks Suppressed)",
                    target_domain, p_action, p_reason
                )
        except Exception:
            pass

        suppress_clicks = (
            is_zero_click
            or anomaly_paused
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

        ad_min_wait = max(6.5, min(20.0, rng.lognormvariate(2.4, 0.45)))

        # Page callback for multi-page sessions
        async def on_page_loaded(pg: Page, url: str, page_num: int) -> None:
            nonlocal result, scroll_done, ad_clicks_done, last_idle, last_ad_attempt

            if using_android_cdp and cdp_bridge and cdp_session:
                org = cdp_bridge._origin_from_url(url)
                if org:
                    cdp_session.visited_origins.add(org)

            # Stage 2 Zero-Waste Viewability: ensure all Adsterra slots enter viewport & fire beacons
            await _ensure_ad_slots_rendered_and_viewed(pg, rng, use_fixture=use_fixture)

            # ADV-3 & ADV-5: Human Reading Speed Scroll and Text Reading Heatmap Mouse
            if rng.random() < cfg["target"]["scroll_prob"]:
                await human.reading_speed_scroll(pg, rng, cdp_session=page_cdp, is_mobile=is_mobile_session)
                scroll_done = True
            if rng.random() < 0.65:
                await human.text_reading_mouse(pg, rng)

            # Refresh impression count after viewport scroll & script rendering
            result["impressions"] = max(result["impressions"], await _count_impressions(pg))

            # Smart Ad click probability check (BHV-5 lognormal delay + Viewport & Safe CTR check)
            if (
                not suppress_clicks
                and time.time() - t_on_page > ad_min_wait
                and ad_clicks_done < cfg["target"]["ad_clicks_max"]
            ):
                clicks = await _attempt_ad_click(
                    pg, rng, ad_clicks_done, cfg["target"]["ad_clicks_max"], scroll_done,
                    proxy_id=proxy.proxy_id, domain=target_domain, proxy_country=proxy_country or "IN",
                    cfg=cfg, spawned_pages=spawned_pages, cdp_session=page_cdp, is_mobile=is_mobile_session,
                )
                ad_clicks_done += clicks
                result["ad_clicks"] += clicks

        # Multi-page navigation (invokes on_page_loaded for page 1 and each subsequent page)
        pages_visited, final_url = await nav.run_session_pages(
            page, start_url, cfg, rng,
            on_page_loaded=on_page_loaded,
        )
        result["pages"] = pages_visited

        # Handle any popunder tabs opened during page interactions or internal navigation
        await _handle_extra_popunder_pages(
            context,
            rng,
            domain=target_domain,
            proxy_country=proxy_country or "IN",
            cfg=cfg,
            use_fixture=use_fixture,
            spawned_pages=spawned_pages,
            main_page=page,
        )

        # Remaining dwell after navigation
        elapsed = time.time() - t_on_page
        remaining = max(0, dwell_target - elapsed)

        while remaining > 0:
            # Idle drift every 8–20 s
            idle_interval = rng.uniform(8, 20)
            sleep_chunk = min(idle_interval, remaining)
            await asyncio.sleep(sleep_chunk)
            remaining -= sleep_chunk

            # Stage 3 Dwell-Loop Smart Click Check: if ad_min_wait was reached during dwell, execute click now
            if (
                not suppress_clicks
                and scroll_done
                and time.time() - t_on_page >= ad_min_wait
                and ad_clicks_done < cfg["target"]["ad_clicks_max"]
            ):
                clicks = await _attempt_ad_click(
                    page, rng, ad_clicks_done, cfg["target"]["ad_clicks_max"], scroll_done,
                    proxy_id=proxy.proxy_id, domain=target_domain, proxy_country=proxy_country or "IN",
                    cfg=cfg, spawned_pages=spawned_pages, cdp_session=page_cdp, is_mobile=is_mobile_session,
                )
                ad_clicks_done += clicks
                result["ad_clicks"] += clicks

            if remaining > 0:
                # Step 10: Multi-step idle fidgets with micro-drifts
                await human.simulate_bored_idle_fidgets(page, rng, count=rng.randint(1, 3))

                # BHV-3: 25% chance of keyboard scrolling/reading interactions during dwell
                if rng.random() < 0.25:
                    kb_key = rng.choice(["ArrowDown", "PageDown", "ArrowDown", "PageUp", "ArrowUp", "Space"])
                    try:
                        await page.keyboard.press(kb_key)
                        await asyncio.sleep(rng.uniform(0.3, 0.7))
                    except Exception:
                        pass

            # BHV-4: Realistic visitor tab inattention (glancing away 2-6s per 30s dwell)
            if rng.random() < 0.28:
                await human.simulate_tab_blur(page, rng, duration_s=rng.uniform(2.0, 6.0))

        result["dwell"] = time.time() - t_on_page

        # Save cookies & ADV-6 visitor profiling (skip shared Chrome state export in Android CDP mode)
        if cfg["session"]["cookie_persist"]:
            if not using_android_cdp:
                await persist.save(context, proxy.proxy_id)
            try:
                persist.record_visit(proxy.proxy_id, start_url)
            except Exception:
                pass
            if mahi_conn and mahi_profile and not using_android_cdp:
                try:
                    await mahi_conn.save_profile_state(context, mahi_profile["id"])
                except Exception:
                    pass

    except Exception as exc:
        logger.warning("Session error for %s: %s", proxy.proxy_id, exc)
        result["status"] = "degraded"
        if not result.get("error_reason"):
            result["error_reason"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        result["dwell"] = max(result["dwell"], time.time() - t0)
    finally:
        if page_cdp is not None:
            try:
                await page_cdp.detach()
            except Exception:
                pass
        _record_active_ua(proxy.proxy_id, fp, active=False)
        if push_task and not push_task.done():
            push_task.cancel()
            try:
                await push_task
            except (asyncio.CancelledError, Exception):
                pass
        if context is not None and _page_listener is not None:
            try:
                context.remove_listener("page", _page_listener)
            except Exception:
                pass
        # Clean up session browser state (owned tabs only for B3 Android CDP; full context close otherwise)
        if using_android_cdp and cdp_bridge is not None:
            try:
                await cdp_bridge.disconnect(
                    cdp_session,
                    remove_forward=True,
                    keep_cookies=bool(cfg.get("session", {}).get("cookie_persist", True)),
                )
            except Exception:
                pass
        elif context:
            try:
                if tracer is not None:
                    saved_trace = await tracer.stop(context, status=result.get("status", "ok"))
                    if saved_trace:
                        logger.warning("Degraded session trace saved → %s", saved_trace.name)
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
        if owned_pw_cm is not None:
            try:
                await owned_pw_cm.__aexit__(None, None, None)
            except Exception:
                pass
        # SCHED-4: Fallback DB write on CancelledError/SIGTERM — always log final status
        if not _session_logged:
            try:
                result["dwell"] = max(float(cfg.get("target", {}).get("min_dwell", 25.0)), result.get("dwell", 0.0), time.time() - t0)
                result.setdefault("status", "cancelled")
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
                    error_reason=result.get("error_reason", "cancelled"),
                    geo_country=result.get("geo_country", ""),
                    geo_tier=result.get("geo_tier", ""),
                    ad_network=result.get("ad_network", "adsterra"),
                    variant_id=result.get("variant_id", "default"),
                )
                _session_logged = True
                logger.debug("SCHED-4: Emergency DB write on cancelled session %s", result["proxy_id"])
            except Exception as db_exc:
                logger.error("SCHED-4: Emergency DB write failed: %s", db_exc)

    # Clamp dwell to configured bounds
    result["dwell"] = max(cfg["target"]["min_dwell"], result["dwell"])

    # SCHED-4: Log to DB — _session_logged flag prevents double-write
    if not _session_logged:
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
            error_reason=result.get("error_reason", ""),
            geo_country=result.get("geo_country", ""),
            geo_tier=result.get("geo_tier", ""),
            ad_network=result.get("ad_network", "adsterra"),
            variant_id=result.get("variant_id", "default"),
        )
        _session_logged = True

    # Layer 4: Real-time Circuit Breaker evaluation & Telegram alert dispatch
    try:
        from alert_bot import check_and_trigger_circuit_breaker
        check_and_trigger_circuit_breaker(target_domain)
    except Exception:
        pass

    # Layer 7: Continuous statistical anomaly detection & circuit breaker
    try:
        from anomaly_detector import AnomalyDetector
        ad = AnomalyDetector()
        detected_anomalies = ad.detect_anomalies(target_domain, window=25)
        if detected_anomalies:
            ad.apply_circuit_breaker(detected_anomalies)
    except Exception:
        pass

    try:
        stats_csv_path = str(cfg.get("stats_csv_path", "stats.csv")).strip()
        if stats_csv_path:
            cpm_rate = float(cfg.get("target", {}).get("cpm_rate", 2.50))
            db.export_stats_csv(stats_csv_path, cpm_rate)
    except Exception:
        pass

    logger.info(
        "Session %s | dwell=%.1fs | pages=%d | clicks=%d | imps=%d | %s",
        proxy.proxy_id, result["dwell"], result["pages"],
        result["ad_clicks"], result["impressions"], result["status"],
    )
    return result

