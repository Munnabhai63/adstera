"""
tests/test_extension_emulation.py — Tests for Step 3.3: Browser Extension Emulation.
Verifies extension seeding, desktop vs mobile handling, and runtime API behavior in Chromium.
"""
import asyncio
import pytest
from pool import Proxy, GeoInfo
import fingerprint as fp_mod


def test_extension_generation_desktop_vs_mobile():
    proxy = Proxy(host="10.0.0.1", port=8080)
    proxy.geo = GeoInfo(country="US", region="NY", city="New York", timezone="America/New_York", locale="en-US")

    # Desktop
    fp_desk = fp_mod.build(proxy, force_mobile=False)
    assert len(fp_desk.extensions) >= 2
    assert any(e["id"] == "ghbmnnjldmmeejimcflloakocagkodme" for e in fp_desk.extensions)

    # Mobile
    fp_mob = fp_mod.build(proxy, force_mobile=True)
    assert len(fp_mob.extensions) == 0


def test_extension_determinism():
    proxy = Proxy(host="192.168.1.100", port=9000)
    proxy.geo = GeoInfo(country="US", region="CA", city="Los Angeles", timezone="America/Los_Angeles", locale="en-US")

    fp1 = fp_mod.build(proxy, force_mobile=False)
    fp2 = fp_mod.build(proxy, force_mobile=False)
    assert fp1.extensions == fp2.extensions


@pytest.mark.browser
def test_extension_runtime_apis():
    from playwright.async_api import async_playwright

    async def _run():
        proxy = Proxy(host="192.168.1.50", port=8080)
        proxy.geo = GeoInfo(country="US", region="IL", city="Chicago", timezone="America/Chicago", locale="en-US")
        fp = fp_mod.build(proxy, force_mobile=False)
        installed_id = fp.extensions[0]["id"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_init_script(fp_mod.init_script(fp))
            page = await context.new_page()

            res = await page.evaluate(f"""async () => {{
                const results = {{}};
                results.hasRuntime = typeof window.chrome !== 'undefined' && typeof window.chrome.runtime !== 'undefined';
                results.sendMsgNative = window.chrome.runtime.sendMessage.toString().includes('[native code]');
                results.getURLNative = window.chrome.runtime.getURL.toString().includes('[native code]');

                // Test installed extension
                try {{
                    const ack = await window.chrome.runtime.sendMessage('{installed_id}', {{ cmd: 'ping' }});
                    results.installedAck = ack && ack.status === 'ok';
                }} catch (e) {{
                    results.installedErr = e.toString();
                }}

                // Test bogus extension
                try {{
                    await window.chrome.runtime.sendMessage('bogusnonexistentextensionid12345', {{ cmd: 'ping' }});
                    results.bogusAck = true;
                }} catch (e) {{
                    results.bogusRejected = true;
                }}

                // Test getURL
                const url = window.chrome.runtime.getURL('manifest.json');
                results.urlValid = url.startsWith('chrome-extension://');

                // Test getManifest
                const manifest = window.chrome.runtime.getManifest();
                results.manifestValid = manifest && manifest.manifest_version === 3;

                return results;
            }}""")

            assert res.get("hasRuntime") is True
            assert res.get("sendMsgNative") is True
            assert res.get("getURLNative") is True
            assert res.get("installedAck") is True
            assert res.get("bogusRejected") is True
            assert res.get("urlValid") is True
            assert res.get("manifestValid") is True

            await context.close()
            await browser.close()

    asyncio.run(_run())
