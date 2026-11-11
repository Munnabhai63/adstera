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
import ivt_patches
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

# Ad selectors to look for on the page
_AD_SELECTORS = [
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
            logger.info(
                "Push[%s]: action=%s delay=%.1fs domain=%s",
                proxy.proxy_id,
                push_result["action"],
                push_result["delay_s"],
                domain,
            )
    except Exception as exc:
        logger.debug("Push async handler error: %s", exc)


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
    # FP-1: Match UA to running browser major version (LEAK-05 fix)
    try:
        if browser and hasattr(browser, "version"):
            b_ver = browser.version
            if b_ver:
                chrome_major = b_ver.split(".")[0]
                fp.user_agent = ua_provider.get_matching_ua(chrome_major, fp.is_mobile)
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
    _record_active_ua(proxy.proxy_id, fp, active=True, target_url=start_url)

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
        referrers = cfg["target"].get("referrers", [""])
        weights = cfg["target"].get("referrer_weights")
        if not weights or len(weights) != len(referrers):
            weights = [1.0] * len(referrers)
        referrer = rng.choices(referrers, weights=weights, k=1)[0]

    # Step 4.3: Multi-Ad-Network Selection
    ad_net_mgr = AdNetworkManager()
    selected_network = ad_net_mgr.select_network(rng)

    # Step 5.3: A/B Testing Strategy Variant Selection
    ab_engine = ab_test_engine.build_from_config(cfg)
    variant = ab_engine.select_variant(rng)
    cfg = ab_engine.apply_variant_to_config(cfg, variant)

    result = {
        "proxy_id": proxy.proxy_id,
        "target_url": start_url,
        "domain": target_domain,
        "ad_network": selected_network,
        "variant_id": variant.variant_id,
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

    context: BrowserContext | None = None
    t0 = time.time()
    _session_logged = False  # SCHED-4: guard to ensure exactly-once DB write

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

        # Step 5.1: Start session trace recording (only saves on degraded status)
        tracer = tracer_mod.build_from_config(cfg, proxy.proxy_id)
        await tracer.start(context)

        # Restore cookies for return visits (ADV-7)
        is_return = rng.random() < cfg["session"]["return_visit_prob"]
        is_return_visitor = False
        if is_return and persist.has_state(proxy.proxy_id):
            await persist.restore(context, proxy.proxy_id)
            is_return_visitor = True
            profile = persist.get_visitor_profile(proxy.proxy_id)
            visited = profile.get("visited_urls", [])
            if visited and not use_fixture and rng.random() < 0.65:
                start_url = rng.choice(visited)
            logger.debug("Return visit: restored cookies for %s (visits=%s)", proxy.proxy_id, profile.get("visit_count", 1))

        # Inject fingerprint patches (including unified IVT patches FP-3 to FP-6)
        init_js = fp_mod.init_script(fp)
        await context.add_init_script(script=init_js)
        await context.add_init_script(script=ivt_patches.generate_stealth_js(getattr(fp, "audio_jitter_seed", 0.000005)))

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

        # Real-time Adsterra network handshake tracking
        try:
            import adsterra_funnel
            adsterra_funnel.attach_adsterra_listener(page, domain=target_domain, proxy_id=proxy.proxy_id)
            context.on("page", lambda p: adsterra_funnel.attach_adsterra_listener(p, domain=target_domain, proxy_id=proxy.proxy_id))
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
            cmp_accepted = await cmp.handle(page, cfg["cmp"]["accept_prob"], rng)
        elif cmp_enabled:
            # Still handle banners even for non-EU if present
            cmp_accepted = await cmp.handle(page, cfg["cmp"]["accept_prob"], rng)

        # Step 4.4: Push Notification Subscription Farming
        push_result = None
        if cfg.get("push_notifications", {}).get("enabled", True):
            push_mgr = push_mod.build_from_config(cfg)
            # Run push handling concurrently with the session (non-blocking)
            asyncio.ensure_future(
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

        # Page callback for multi-page sessions
        async def on_page_loaded(pg: Page, url: str, page_num: int) -> None:
            nonlocal result, scroll_done, ad_clicks_done, last_idle, last_ad_attempt

            # ADV-3 & ADV-5: Human Reading Speed Scroll and Text Reading Heatmap Mouse
            if rng.random() < cfg["target"]["scroll_prob"]:
                await human.reading_speed_scroll(pg, rng)
                scroll_done = True
            if rng.random() < 0.65:
                await human.text_reading_mouse(pg, rng)

            # Smart Ad click probability check (BHV-5 lognormal delay + Viewport & Safe CTR check)
            ad_min_wait = max(6.5, rng.lognormvariate(2.8, 0.6))  # BHV-5 lognormal click delay (mean ~20-25s)
            if (
                not suppress_clicks
                and time.time() - t_on_page > ad_min_wait
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

        # Save cookies & ADV-6 visitor profiling
        if cfg["session"]["cookie_persist"]:
            await persist.save(context, proxy.proxy_id)
            try:
                persist.record_visit(proxy.proxy_id, start_url)
            except Exception:
                pass
            if mahi_conn and mahi_profile:
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
        _record_active_ua(proxy.proxy_id, fp, active=False)
        # Step 5.1: Stop trace — saves file only if session was degraded
        if context:
            try:
                saved_trace = await tracer.stop(context, status=result.get("status", "ok"))
                if saved_trace:
                    logger.warning("Degraded session trace saved → %s", saved_trace.name)
            except Exception:
                pass
            try:
                await context.close()
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

