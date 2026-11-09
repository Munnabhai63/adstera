"""
tests/test_font_spoofing.py — Comprehensive tests for Step 3.1: Font Enumeration Spoofing.
Verifies platform catalogs, seeded generation, determinism, and Playwright execution.
"""
import asyncio
import pytest
from pool import Proxy, GeoInfo
import fingerprint as fp_mod


def test_font_catalogs_exist():
    assert len(fp_mod._WINDOWS_FONTS) > 20
    assert len(fp_mod._MACOS_FONTS) > 15
    assert len(fp_mod._ANDROID_FONTS) > 5
    assert len(fp_mod._LINUX_FONTS) > 5


def test_font_generation_coherence():
    proxy = Proxy(host="10.0.0.1", port=8080)
    proxy.geo = GeoInfo(country="US", region="NY", city="New York", timezone="America/New_York", locale="en-US")

    # Desktop
    fp_desk = fp_mod.build(proxy, force_mobile=False)
    assert len(fp_desk.fonts) >= 10
    plat_low = fp_desk.platform.lower()
    if "linux" in plat_low:
        assert any("Liberation" in f or "Ubuntu" in f or "DejaVu" in f for f in fp_desk.fonts)
    elif "mac" in plat_low:
        assert any("San Francisco" in f or "Helvetica" in f or "Arial" in f for f in fp_desk.fonts)
    else:
        assert any("Segoe" in f or "Calibri" in f or "Arial" in f for f in fp_desk.fonts)

    # Mobile
    fp_mob = fp_mod.build(proxy, force_mobile=True)
    assert len(fp_mob.fonts) >= 5
    assert any("Roboto" in f or "Noto" in f for f in fp_mob.fonts)


def test_font_determinism():
    proxy = Proxy(host="192.168.1.100", port=9000)
    proxy.geo = GeoInfo(country="US", region="CA", city="Los Angeles", timezone="America/Los_Angeles", locale="en-US")

    fp1 = fp_mod.build(proxy)
    fp2 = fp_mod.build(proxy)
    assert fp1.fonts == fp2.fonts


def test_font_js_injection():
    from playwright.async_api import async_playwright

    async def _run():
        proxy = Proxy(host="192.168.1.50", port=8080)
        proxy.geo = GeoInfo(country="US", region="IL", city="Chicago", timezone="America/Chicago", locale="en-US")
        fp = fp_mod.build(proxy)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_init_script(fp_mod.init_script(fp))
            page = await context.new_page()

            res = await page.evaluate("""async () => {
                const fonts = await window.queryLocalFonts();
                return {
                    checkNative: document.fonts.check.toString().includes('[native code]'),
                    qlfNative: window.queryLocalFonts.toString().includes('[native code]'),
                    count: fonts.length,
                    hasFirst: fonts.length > 0 && typeof fonts[0].family === 'string',
                };
            }""")

            assert res["checkNative"] is True
            assert res["qlfNative"] is True
            assert res["count"] == len(fp.fonts)
            assert res["hasFirst"] is True

            await context.close()
            await browser.close()

    asyncio.run(_run())
