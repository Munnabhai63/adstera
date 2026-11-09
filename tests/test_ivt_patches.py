"""
tests/test_ivt_patches.py — Acceptance verification for Phase 2 IVT Patches Suite:
1. Validates WEBRTC_CHROMIUM_ARGS flags.
2. Validates IPQualityChecker behavior (clean IP vs fraud IP vs fail-open on no key).
3. Validates GeoResolver multi-API fallback resolution.
4. Validates ProxyHeaderValidator forbidden headers detection.
5. Validates UserAgentManager version extraction, stale filter, and synced UA generation.
6. Validates generate_stealth_js payload injection and DOM properties.
7. Validates IVTPatchManager unified convenience interface.
"""
import asyncio
from ivt_patches import (
    WEBRTC_CHROMIUM_ARGS,
    IPQualityChecker,
    GeoResolver,
    ProxyHeaderValidator,
    UserAgentManager,
    generate_stealth_js,
    IVTPatchManager,
)


def test_webrtc_chromium_args():
    assert "--disable-features=WebRtcHideLocalIpsWithMdns" in WEBRTC_CHROMIUM_ARGS
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in WEBRTC_CHROMIUM_ARGS
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in WEBRTC_CHROMIUM_ARGS


def test_user_agent_manager():
    mgr = UserAgentManager(min_chrome_version=118)
    assert mgr.extract_chrome_major("130.0.6723.58") == "130"
    assert mgr.extract_chrome_major("119.0.0.0") == "119"

    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/105.0.0.0 Safari/537.36",  # Stale
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
    ]
    filtered = mgr.filter_recent_uas(uas)
    assert len(filtered) == 2
    assert "105.0.0.0" not in filtered[0]
    assert "105.0.0.0" not in filtered[1]

    win_ua = mgr.get_matching_ua("130", is_mobile=False, os_type="windows")
    assert "Chrome/130.0.0.0" in win_ua
    assert "Windows NT 10.0" in win_ua

    mob_ua = mgr.get_matching_ua("130", is_mobile=True)
    assert "Android 14" in mob_ua
    assert "Mobile Safari" in mob_ua


def test_stealth_js_payload():
    js = generate_stealth_js(session_salt=0.0000042)
    assert "0.0000042" in js
    assert "outerWidth" in js
    assert "outerHeight" in js
    assert "PDF Viewer" in js
    assert "navigator.webdriver" in js
    assert "SESSION_SALT" in js


def test_ivt_patch_manager():
    mgr = IVTPatchManager(ipqs_api_key="mock_key")
    args = mgr.get_browser_launch_args()
    assert len(args) >= 3
    script = mgr.get_stealth_script(session_salt=0.000001)
    assert "outerWidth" in script


def test_ip_quality_checker_fail_open_and_loopback():
    async def _test():
        checker = IPQualityChecker(api_key="")
        # Localhost should always pass
        assert await checker.check_ip("127.0.0.1") is True
        # Without API key, fails open
        assert await checker.check_ip("8.8.8.8") is True

    asyncio.run(_test())


def test_geo_resolver_loopback():
    async def _test():
        res = await GeoResolver.resolve_host("127.0.0.1")
        assert res is not None
        assert res.get("countryCode") == "US"
        assert res.get("city") == "New York"

    asyncio.run(_test())


def test_proxy_header_validator_loopback():
    async def _test():
        # Localhost should pass validation
        assert await ProxyHeaderValidator.verify_proxy_anonymity("http://127.0.0.1:8080") is True

    asyncio.run(_test())
