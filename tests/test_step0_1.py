"""
test_step0_1.py — Acceptance verification for Layer 0 Step 0.1:
1. Verifies db schema contains error_reason column
2. Verifies db.log_session handles error_reason parameter
3. Tests worker resilient navigation & recovery
"""
import pytest
import sqlite3
import random
from pathlib import Path
import db

def test_db_error_reason_schema():
    db.init()
    with db._conn() as con:
        cur = con.execute("PRAGMA table_info(sessions)")
        cols = [c[1] for c in cur.fetchall()]
        assert "error_reason" in cols, "error_reason column must exist in sessions table"

def test_db_log_session_with_error_reason():
    db.init()
    test_reason = "TestError: connection timeout after 25s"
    row_id = db.log_session(
        proxy_id="test:127.0.0.1",
        ua="TestUA/1.0",
        referrer="https://google.com",
        dwell=30.0,
        pages=1,
        ad_clicks=0,
        impressions=1,
        status="degraded",
        domain="loanraaj.com",
        error_reason=test_reason,
    )
    assert row_id > 0
    with db._conn() as con:
        row = con.execute("SELECT * FROM sessions WHERE id = ?", (row_id,)).fetchone()
        assert row["error_reason"] == test_reason
        assert row["status"] == "degraded"
        # Cleanup test row
        con.execute("DELETE FROM sessions WHERE id = ?", (row_id,))

def test_worker_resilient_navigation():
    import asyncio
    async def _run():
        from playwright.async_api import async_playwright
        import yaml
        from pool import Proxy
        import worker
        
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        
        # Run a test session with fixture (safe, offline)
        cfg["target"]["min_dwell"] = 1
        cfg["target"]["max_dwell"] = 2
        cfg["session"]["page_depth_max"] = 1
        cfg["session"]["internal_nav_prob"] = 0.0
        cfg["target"]["scroll_prob"] = 0.0
        rng = random.Random(42)
        proxy = Proxy(host="direct", port=0)
        
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                result = await worker.run_session(pw, browser, proxy, cfg, rng, use_fixture=True)
                assert result["status"] == "ok"
                assert result["pages"] >= 1
                assert "error_reason" in result
            finally:
                await browser.close()
    
    asyncio.run(_run())

def test_worker_fallback_recovery_on_bad_url():
    import asyncio
    async def _run():
        from playwright.async_api import async_playwright
        import yaml
        from pool import Proxy
        import worker
        
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        
        # Override target to an unresolvable bad URL to trigger Tier-3 fallback recovery
        cfg_bad = dict(cfg)
        cfg_bad["target"] = dict(cfg["target"])
        cfg_bad["target"]["url"] = "http://this-domain-definitely-does-not-exist-123456789.com"
        cfg_bad["target"]["urls"] = ["http://this-domain-definitely-does-not-exist-123456789.com"]
        cfg_bad["target"]["min_dwell"] = 1
        cfg_bad["target"]["max_dwell"] = 2
        cfg_bad["target"]["scroll_prob"] = 0.0
        cfg_bad["session"] = dict(cfg["session"])
        cfg_bad["session"]["page_depth_max"] = 1
        cfg_bad["session"]["internal_nav_prob"] = 0.0
        cfg_bad["geo_routing"] = {"enabled": False}
        
        rng = random.Random(99)
        proxy = Proxy(host="direct", port=0)
        
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                result = await worker.run_session(pw, browser, proxy, cfg_bad, rng, use_fixture=False)
                # Should have recovered via loanraaj or fixture, so pages >= 1 and error_reason notes recovery!
                assert result["pages"] >= 1
                assert "Recovered" in result["error_reason"]
            finally:
                await browser.close()
    
    asyncio.run(_run())

if __name__ == "__main__":
    test_db_error_reason_schema()
    test_db_log_session_with_error_reason()
    print("All synchronous Step 0.1 tests passed successfully!")
