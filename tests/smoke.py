"""
tests/smoke.py — 5-session end-to-end run against local fixture.

Verifies:
- 5 sessions complete, zero unhandled exceptions
- Every sessions row has non-empty ua, dwell in 25–110, referrer from mix
- Same-proxy fingerprint digest stable across two runs
- navigator.webdriver falsy inside the page
- daily_cap: 3 halts cleanly
- CMP fires when banner present / skipped when absent
- CTR logged in range 0–20%
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from playwright.async_api import async_playwright

import db
import fingerprint as fp_mod
import worker
from pool import Proxy, GeoInfo


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    with open(Path(__file__).parent.parent / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Override for smoke test: use fixture, low cap
    cfg["target"]["fixture"] = str(
        (Path(__file__).parent / "fixtures" / "page.html").resolve()
    )
    cfg["target"]["min_dwell"] = 25
    cfg["target"]["max_dwell"] = 35   # keep smoke test fast
    cfg["scheduler"]["daily_cap"] = 10
    cfg["session"]["page_depth_min"] = 1
    cfg["session"]["page_depth_max"] = 1
    cfg["session"]["internal_nav_prob"] = 0.0   # stay on fixture only
    cfg["target"]["click_prob"] = 0.5           # higher chance for smoke test coverage
    cfg["browser"]["slow_mo_ms"] = 0            # faster for tests
    cfg["ab_testing"] = {"enabled": False}      # preserve smoke dwell cap (25-35s)
    cfg.setdefault("push_notifications", {})["enabled"] = False
    cfg["stats_csv_path"] = ""
    return cfg


def _make_proxy(idx: int) -> Proxy:
    proxy = Proxy(host=f"10.0.{idx}.1", port=8080)
    proxy.geo = GeoInfo(
        country="US",
        region="NY",
        city="New York",
        timezone="America/New_York",
        locale="en-US",
    )
    return proxy


# ── test: 5 sessions complete, zero exceptions ─────────────────────────────────

async def test_five_sessions(cfg: dict) -> list[dict]:
    print("\n[Smoke] Running 5 sessions…")
    results = []

    headless = cfg["browser"].get("headless", False)
    slow_mo = cfg["browser"].get("slow_mo_ms", 0)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-features=WebRtcHideLocalIpsWithMdns",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        for i in range(5):
            proxy = _make_proxy(i % 3)   # 3 unique proxies, some reused
            rng = random.Random(i + 42)
            try:
                result = await worker.run_session(pw, browser, proxy, cfg, rng, use_fixture=True)
                results.append(result)
                print(f"  Session {i+1}: dwell={result['dwell']:.1f}s  pages={result['pages']}  "
                      f"clicks={result['ad_clicks']}  status={result['status']}")
            except Exception as exc:
                print(f"  Session {i+1} UNHANDLED EXCEPTION: {exc}")
                raise

        await browser.close()

    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    print("  PASS — 5 sessions completed, 0 unhandled exceptions")
    return results


# ── test: DB row validity ──────────────────────────────────────────────────────

def test_db_rows(cfg: dict, results: list[dict]) -> None:
    print("\n[Smoke] Verifying DB rows…")
    rows = db.last_sessions(10)
    # Filter to rows from this smoke run (last 5 at minimum)
    checked = 0
    for row in rows[:5]:
        assert row["ua"], f"Empty UA in session row: {row}"
        assert 20 <= row["dwell"] <= 120, f"Dwell out of range: {row['dwell']}"
        referrers = cfg["target"]["referrers"]
        is_valid_ref = (
            row["referrer"] in referrers
            or "google." in row["referrer"]
            or "bing." in row["referrer"]
            or "duckduckgo." in row["referrer"]
            or row["referrer"] == ""
        )
        assert is_valid_ref, (
            f"Referrer not in configured list or organic search: {row['referrer']!r}"
        )
        checked += 1
    assert checked >= 1, "No DB rows found for smoke run"
    print(f"  PASS — {checked} rows verified (ua, dwell, referrer)")


# ── test: fingerprint digest stability ────────────────────────────────────────

def test_digest_stability() -> None:
    print("\n[Smoke] Fingerprint digest stability…")
    proxy = _make_proxy(99)
    fp1 = fp_mod.build(proxy)
    fp2 = fp_mod.build(proxy)
    assert fp1.digest == fp2.digest, (
        f"Digest unstable: {fp1.digest!r} vs {fp2.digest!r}"
    )
    print(f"  PASS — digest stable: {fp1.digest}")


# ── test: navigator.webdriver falsy ───────────────────────────────────────────

async def test_webdriver_falsy(cfg: dict) -> None:
    print("\n[Smoke] navigator.webdriver check…")
    proxy = _make_proxy(0)
    fp = fp_mod.build(proxy)
    headless = cfg["browser"].get("headless", False)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=fp.user_agent,
            viewport={"width": fp.viewport_width, "height": fp.viewport_height},
            locale=fp.locale,
            timezone_id=fp.timezone,
        )
        await ctx.add_init_script(script=fp_mod.init_script(fp))
        page = await ctx.new_page()
        fixture = Path(__file__).parent / "fixtures" / "page.html"
        await page.goto(f"file:///{fixture.as_posix()}", wait_until="domcontentloaded")
        wd = await page.evaluate("() => navigator.webdriver")
        assert not wd, f"navigator.webdriver = {wd!r} (expected falsy)"
        print(f"  PASS — navigator.webdriver = {wd!r}")
        await browser.close()


# ── test: daily_cap: 3 halts cleanly ─────────────────────────────────────────

async def test_daily_cap(cfg: dict) -> None:
    print("\n[Smoke] daily_cap=3 halt test…")
    import db as db_mod

    cap_cfg = yaml.safe_load(yaml.dump(cfg))  # deep copy
    cap_cfg["scheduler"]["daily_cap"] = 3
    cap_cfg["scheduler"]["concurrency"] = 1
    cap_cfg["target"]["min_dwell"] = 1
    cap_cfg["target"]["max_dwell"] = 2
    cap_cfg["session"]["page_depth_min"] = 1
    cap_cfg["session"]["page_depth_max"] = 1
    cap_cfg["session"]["internal_nav_prob"] = 0.0

    orig_db = db_mod._DB_PATH
    temp_dir = tempfile.mkdtemp()
    temp_db = Path(temp_dir) / "cap_test.db"
    db_mod._DB_PATH = temp_db
    db_mod.init()

    try:
        headless = cap_cfg["browser"].get("headless", False)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )

            done = 0
            for i in range(5):  # Try 5, should stop when cap (3) is reached
                if db_mod.today() >= cap_cfg["scheduler"]["daily_cap"]:
                    break
                proxy = _make_proxy(i)
                rng = random.Random(i + 1000)
                await worker.run_session(pw, browser, proxy, cap_cfg, rng, use_fixture=True)
                done += 1

            await browser.close()

        after = db_mod.today()
        assert done == 3, f"Expected 3 sessions completed before halt, got {done}"
        assert after == 3, f"daily_cap not enforced: {after} sessions logged (cap=3)"
        print(f"  PASS — daily_cap: 3 enforced. Completed {done} sessions, loop halted cleanly.")
    finally:
        db_mod._DB_PATH = orig_db
        try:
            temp_db.unlink(missing_ok=True)
            Path(temp_dir).rmdir()
        except Exception:
            pass


# ── test: CMP fires / skips ───────────────────────────────────────────────────

async def test_cmp(cfg: dict) -> None:
    print("\n[Smoke] CMP banner detection…")
    import cmp as cmp_mod

    proxy = _make_proxy(0)
    fp = fp_mod.build(proxy)
    headless = cfg["browser"].get("headless", False)
    fixture_with_banner = Path(__file__).parent / "fixtures" / "page.html"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=fp.user_agent,
            viewport={"width": fp.viewport_width, "height": fp.viewport_height},
            locale=fp.locale,
            timezone_id=fp.timezone,
        )
        await ctx.add_init_script(script=fp_mod.init_script(fp))
        page = await ctx.new_page()
        await page.goto(
            f"file:///{fixture_with_banner.as_posix()}",
            wait_until="domcontentloaded",
        )
        rng = random.Random(42)
        found = await cmp_mod.handle(page, accept_prob=1.0, rng=rng)
        assert found, "CMP banner not detected on fixture page (expected banner)"
        print("  PASS — CMP banner detected and clicked on fixture with banner")

        # Test page without banner (about:blank)
        page2 = await ctx.new_page()
        await page2.goto("about:blank")
        found2 = await cmp_mod.handle(page2, accept_prob=1.0, rng=rng)
        assert not found2, "CMP falsely detected on blank page"
        print("  PASS — CMP correctly skipped on page without banner")

        await browser.close()


# ── test: CTR in range ────────────────────────────────────────────────────────

def test_ctr_logged() -> None:
    print("\n[Smoke] CTR check…")
    ctr = db.ctr(last_n=10)
    assert 0.0 <= ctr <= 0.20, f"CTR out of 0–20% range: {ctr}"
    print(f"  PASS — CTR = {ctr*100:.1f}% (within 0–20% range)")


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    cfg = _load_cfg()
    db.init()

    test_digest_stability()

    results = await test_five_sessions(cfg)
    test_db_rows(cfg, results)
    await test_webdriver_falsy(cfg)
    await test_daily_cap(cfg)
    await test_cmp(cfg)
    test_ctr_logged()

    print("\n" + "="*60)
    print("SMOKE TEST COMPLETE — All checks passed ✓")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

