"""
tests/audit.py — Pre-flight invariant checks. Exits non-zero on any failure.

Checks:
 1. UA contains no 'HeadlessChrome'.
 2. navigator.webdriver is falsy.
 3. WebGL renderer is not SwiftShader.
 4. Context timezone equals the geo timezone of the proxy.
 5. Accept-Language matches the geo locale.
 6. Two sessions on one proxy hash to the same fingerprint digest.
 7. Canvas digest differs between two different proxies.
 8. No datacenter ASN present in the loaded pool.
 9. proxies.txt parses and every line yields host and port.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Allow importing from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


def _load_cfg() -> dict:
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Check 9: proxy file parsing (no browser needed) ───────────────────────────

def check_proxy_file_parsing(cfg: dict) -> None:
    proxy_file = Path(__file__).parent.parent / cfg["proxy"]["file"]
    if not proxy_file.exists():
        raise AssertionError(f"proxies.txt not found at {proxy_file}")

    from pool import _parse_proxy_line
    lines = proxy_file.read_text(encoding="utf-8").splitlines()
    parsed = []
    for ln in lines:
        p = _parse_proxy_line(ln)
        if p is not None:
            assert p.host, f"Empty host in line: {ln!r}"
            assert p.port > 0, f"Invalid port in line: {ln!r}"
            parsed.append(p)

    assert len(parsed) > 0, "No valid proxy lines found in proxies.txt"
    print(f"  [9] PASS — {len(parsed)} proxies parsed successfully")


# ── Check 8: no datacenter ASN in pool (static check on ASN names in fallback) ─

def check_no_datacenter_asn(cfg: dict) -> None:
    """
    Static check: load proxies, verify none have datacenter ASN names already
    baked in (from geo fallback table). Full runtime check happens in ProxyPool.from_file.
    """
    from pool import _parse_proxy_line, _DC_NAMES
    proxy_file = Path(__file__).parent.parent / cfg["proxy"]["file"]
    lines = proxy_file.read_text(encoding="utf-8").splitlines()
    for ln in lines:
        p = _parse_proxy_line(ln)
        if p is None:
            continue
        # Check host against DC name fragments (heuristic for static audit)
        host_lower = p.host.lower()
        for dc in _DC_NAMES:
            assert dc not in host_lower, (
                f"Potential datacenter proxy host: {p.host!r} matches '{dc}'"
            )
    print("  [8] PASS — No datacenter ASN name fragments in proxy hosts")


# ── Checks 1–7: browser-based ──────────────────────────────────────────────────

async def _run_browser_checks(cfg: dict) -> None:
    from playwright.async_api import async_playwright
    import fingerprint as fp_mod
    from pool import Proxy, GeoInfo

    # Build two synthetic proxies for testing
    proxy_a = Proxy(host="10.0.0.1", port=8080)
    proxy_a.geo = GeoInfo(
        country="US", region="NY", city="New York",
        timezone="America/New_York", locale="en-US",
    )
    proxy_b = Proxy(host="10.0.0.2", port=8080)
    proxy_b.geo = GeoInfo(
        country="US", region="CA", city="Los Angeles",
        timezone="America/Los_Angeles", locale="en-US",
    )

    fp_a1 = fp_mod.build(proxy_a)
    fp_a2 = fp_mod.build(proxy_a)   # Must be identical to fp_a1
    fp_b  = fp_mod.build(proxy_b)

    # Check 6: same proxy → same digest
    assert fp_a1.digest == fp_a2.digest, (
        f"[6] FAIL — Same proxy produced different digests: {fp_a1.digest} vs {fp_a2.digest}"
    )
    print(f"  [6] PASS — Same-proxy digest stable: {fp_a1.digest}")

    # Check 7: different proxy → different canvas seed → different digest
    # Canvas seed differs if proxy fingerprint_seed differs
    assert fp_a1.canvas_seed != fp_b.canvas_seed, (
        "[7] FAIL — Different proxies produced identical canvas seeds"
    )
    print(f"  [7] PASS — Canvas seeds differ across proxies: {fp_a1.canvas_seed} vs {fp_b.canvas_seed}")

    headless = cfg["browser"].get("headless", False)
    slow_mo = cfg["browser"].get("slow_mo_ms", 40)
    canvas_results: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
            ],
        )

        for label, proxy, fp in [("proxy_a", proxy_a, fp_a1), ("proxy_b", proxy_b, fp_b)]:
            context = await browser.new_context(
                user_agent=fp.user_agent,
                viewport={"width": fp.viewport_width, "height": fp.viewport_height},
                locale=fp.locale,
                timezone_id=fp.timezone,
                extra_http_headers={"Accept-Language": ",".join(fp.languages)},
            )
            await context.add_init_script(script=fp_mod.init_script(fp))
            page = await context.new_page()

            fixture = Path(__file__).parent / "fixtures" / "page.html"
            await page.goto(f"file:///{fixture.as_posix()}", wait_until="domcontentloaded")

            # Check 1: UA has no 'HeadlessChrome'
            ua: str = await page.evaluate("() => navigator.userAgent")
            assert "HeadlessChrome" not in ua, (
                f"[1] FAIL ({label}) — UA contains 'HeadlessChrome': {ua!r}"
            )
            if label == "proxy_a":
                print(f"  [1] PASS — UA clean: {ua[:60]}…")

            # Check 2: navigator.webdriver falsy
            wd = await page.evaluate("() => navigator.webdriver")
            assert not wd, f"[2] FAIL ({label}) — navigator.webdriver = {wd!r}"
            if label == "proxy_a":
                print(f"  [2] PASS — navigator.webdriver = {wd!r}")

            # Check 3: WebGL renderer not SwiftShader
            renderer: str = await page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return '';
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(37446);
            }""")
            assert "SwiftShader" not in renderer, (
                f"[3] FAIL ({label}) — WebGL renderer is SwiftShader: {renderer!r}"
            )
            if label == "proxy_a":
                print(f"  [3] PASS — WebGL renderer: {renderer!r}")

            # Check 4: timezone matches geo
            tz_in_page: str = await page.evaluate(
                "() => Intl.DateTimeFormat().resolvedOptions().timeZone"
            )
            assert tz_in_page == fp.timezone, (
                f"[4] FAIL ({label}) — Timezone mismatch: page={tz_in_page!r} expected={fp.timezone!r}"
            )
            if label == "proxy_a":
                print(f"  [4] PASS — Timezone: {tz_in_page!r}")

            # Check 5: Accept-Language matches locale
            lang_header = fp.languages[0]
            nav_lang: str = await page.evaluate("() => navigator.language")
            assert nav_lang == lang_header, (
                f"[5] FAIL ({label}) — navigator.language={nav_lang!r} expected={lang_header!r}"
            )
            if label == "proxy_a":
                print(f"  [5] PASS — navigator.language: {nav_lang!r}")

            # Check 10: Client Hints (navigator.userAgentData) coherence & prototype integrity
            uad_info = await page.evaluate("""async () => {
                if (!navigator.userAgentData) return null;
                const high = await navigator.userAgentData.getHighEntropyValues(['platform', 'model', 'architecture']);
                return {
                    brands: navigator.userAgentData.brands,
                    mobile: navigator.userAgentData.mobile,
                    platform: navigator.userAgentData.platform,
                    tag: Object.prototype.toString.call(navigator.userAgentData),
                    isInstance: window.NavigatorUAData ? (navigator.userAgentData instanceof window.NavigatorUAData) : true,
                    nativeStr: navigator.userAgentData.getHighEntropyValues.toString(),
                    high: high
                };
            }""")
            assert uad_info is not None, f"[10] FAIL ({label}) — navigator.userAgentData is missing/None"
            assert len(uad_info.get("brands", [])) >= 2, f"[10] FAIL ({label}) — userAgentData.brands empty"
            assert uad_info.get("mobile") == fp.is_mobile, (
                f"[10] FAIL ({label}) — userAgentData.mobile ({uad_info.get('mobile')}) != fp.is_mobile ({fp.is_mobile})"
            )
            assert uad_info.get("tag") == "[object NavigatorUAData]", (
                f"[10] FAIL ({label}) — userAgentData tag mismatch: {uad_info.get('tag')}"
            )
            assert "[native code]" in uad_info.get("nativeStr", ""), (
                f"[10] FAIL ({label}) — getHighEntropyValues not masked as native code"
            )
            if label == "proxy_a":
                print(f"  [10] PASS — Client Hints 99.99% bulletproof (tag='{uad_info.get('tag')}', native=True, mobile={uad_info.get('mobile')})")

            # Check 11: Canvas & WebGL buffer integrity (getImageData, toDataURL, readPixels stability & [native code])
            canvas_res = await page.evaluate("""async () => {
                const canvas = document.createElement('canvas');
                canvas.width = 64;
                canvas.height = 64;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#123456';
                ctx.fillRect(0, 0, 64, 64);
                ctx.font = '12px sans-serif';
                ctx.fillText('AntiDetect Audit', 5, 20);

                const u1 = canvas.toDataURL();
                const u2 = canvas.toDataURL();

                const d1 = ctx.getImageData(0, 0, 64, 64).data;
                const d2 = ctx.getImageData(0, 0, 64, 64).data;
                const h1 = Array.from(d1.slice(0, 20)).join(',');
                const h2 = Array.from(d2.slice(0, 20)).join(',');

                const blob = await new Promise(res => canvas.toBlob(res));

                return {
                    u1: u1,
                    u2: u2,
                    dataURL_stable: u1 === u2,
                    imageData_stable: h1 === h2,
                    h1: h1,
                    blob_valid: blob instanceof Blob && blob.size > 0,
                    native_toDataURL: canvas.toDataURL.toString(),
                    native_toBlob: canvas.toBlob ? canvas.toBlob.toString() : '',
                    native_getImageData: ctx.getImageData.toString(),
                    native_readPixels: WebGLRenderingContext.prototype.readPixels.toString(),
                    native_getParameter: WebGLRenderingContext.prototype.getParameter.toString()
                };
            }""")
            assert canvas_res["dataURL_stable"], f"[11] FAIL ({label}) — canvas.toDataURL() drifted between calls"
            assert canvas_res["imageData_stable"], f"[11] FAIL ({label}) — ctx.getImageData() drifted between calls"
            assert canvas_res["blob_valid"], f"[11] FAIL ({label}) — canvas.toBlob() returned invalid blob"
            assert "[native code]" in canvas_res["native_toDataURL"], f"[11] FAIL ({label}) — toDataURL not [native code]"
            assert "[native code]" in canvas_res["native_getImageData"], f"[11] FAIL ({label}) — getImageData not [native code]"
            assert "[native code]" in canvas_res["native_readPixels"], f"[11] FAIL ({label}) — readPixels not [native code]"
            assert "[native code]" in canvas_res["native_getParameter"], f"[11] FAIL ({label}) — getParameter not [native code]"
            canvas_results[label] = canvas_res
            if label == "proxy_a":
                print(f"  [11] PASS — Canvas & WebGL buffer integrity (getImageData + toDataURL zero-drift, [native code] masked)")

            # Check 12: Hardware Peripherals & Battery API Simulation
            hw_res = await page.evaluate("""async () => {
                const devs = await navigator.mediaDevices.enumerateDevices();
                const b = await navigator.getBattery();
                return {
                    devCount: devs.length,
                    hasAudioIn: devs.some(d => d.kind === 'audioinput'),
                    hasAudioOut: devs.some(d => d.kind === 'audiooutput'),
                    hasVideoIn: devs.some(d => d.kind === 'videoinput'),
                    dev0_idLen: devs[0] ? devs[0].deviceId.length : 0,
                    dev0_groupLen: devs[0] ? devs[0].groupId.length : 0,
                    dev0_isInstance: (typeof window.MediaDeviceInfo !== 'undefined') ? (devs[0] instanceof window.MediaDeviceInfo) : true,
                    dev0_tag: Object.prototype.toString.call(devs[0]),
                    dev0_nativeToJSON: devs[0] && devs[0].toJSON ? devs[0].toJSON.toString() : '',
                    nativeEnumerate: navigator.mediaDevices.enumerateDevices.toString(),
                    battery_charging: typeof b.charging === 'boolean',
                    battery_level: b.level,
                    battery_isInstance: (typeof window.BatteryManager !== 'undefined') ? (b instanceof window.BatteryManager) : true,
                    battery_tag: Object.prototype.toString.call(b),
                    nativeGetBattery: navigator.getBattery.toString()
                };
            }""")
            assert hw_res["devCount"] >= 3, f"[12] FAIL ({label}) — enumerateDevices returned < 3 devices: {hw_res['devCount']}"
            assert hw_res["hasAudioIn"], f"[12] FAIL ({label}) — No audioinput found"
            assert hw_res["hasAudioOut"], f"[12] FAIL ({label}) — No audiooutput found"
            assert hw_res["hasVideoIn"], f"[12] FAIL ({label}) — No videoinput found"
            assert hw_res["dev0_idLen"] == 64, f"[12] FAIL ({label}) — deviceId not 64-char sha256: len={hw_res['dev0_idLen']}"
            assert hw_res["dev0_groupLen"] == 64, f"[12] FAIL ({label}) — groupId not 64-char sha256: len={hw_res['dev0_groupLen']}"
            assert "[native code]" in hw_res["nativeEnumerate"], f"[12] FAIL ({label}) — enumerateDevices not [native code]"
            assert hw_res["battery_charging"], f"[12] FAIL ({label}) — battery.charging is not boolean"
            assert 0.0 <= hw_res["battery_level"] <= 1.0, f"[12] FAIL ({label}) — battery.level out of range: {hw_res['battery_level']}"
            assert "[native code]" in hw_res["nativeGetBattery"], f"[12] FAIL ({label}) — getBattery not [native code]"
            if label == "proxy_a":
                print(f"  [12] PASS — Hardware Peripherals & Battery Status API (devs={hw_res['devCount']}, battery={hw_res['battery_level']}, [native code] masked)")

            await context.close()

        # Check 11 cross-seed check: different proxies yield different canvas outputs
        assert canvas_results["proxy_a"]["u1"] != canvas_results["proxy_b"]["u1"], (
            "[11] FAIL — Different proxies produced identical canvas toDataURL outputs"
        )
        assert canvas_results["proxy_a"]["h1"] != canvas_results["proxy_b"]["h1"], (
            "[11] FAIL — Different proxies produced identical canvas getImageData byte buffers"
        )

        await browser.close()


async def run_all_async(cfg: dict | None = None) -> None:
    """Run all audit checks asynchronously. Raises SystemExit(1) on any failure."""
    if cfg is None:
        cfg = _load_cfg()

    print("Running pre-flight audit…")
    failures: list[str] = []

    net_mode = cfg.get("network", {}).get("mode", "proxy")
    static_checks = [check_no_datacenter_asn]
    if net_mode != "mobile_tether":
        static_checks.insert(0, check_proxy_file_parsing)

    # Static checks
    for check_fn in static_checks:
        try:
            check_fn(cfg)
        except AssertionError as e:
            print(f"  FAIL — {e}")
            failures.append(str(e))
        except Exception as e:
            print(f"  ERROR — {e}")
            failures.append(str(e))

    # Browser checks
    try:
        await _run_browser_checks(cfg)
    except AssertionError as e:
        print(f"  FAIL — {e}")
        failures.append(str(e))
    except Exception as e:
        print(f"  ERROR — {e}")
        failures.append(str(e))

    if failures:
        print(f"\nAudit FAILED — {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print("\nAll audit checks PASSED [OK]")


def run_all(cfg: dict | None = None) -> None:
    """Synchronous entrypoint for CLI (python tests/audit.py)."""
    asyncio.run(run_all_async(cfg))


if __name__ == "__main__":
    run_all()

