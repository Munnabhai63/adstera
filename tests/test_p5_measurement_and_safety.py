"""
tests/test_p5_measurement_and_safety.py — Acceptance tests for Phase 5.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
import pytest
from playwright.async_api import async_playwright

import db
import worker
from ab_test_engine import ABTestEngine, StrategyVariant


def test_unified_revenue_calculation():
    # 1000 impressions at $2.50 CPM = $2.50
    # 50 clicks at $0.03 CPC = $1.50
    # Total = $4.00
    rev = db.compute_adsterra_revenue(impressions=1000, clicks=50, cpm_rate=2.50, cpc_rate=0.03)
    assert rev == 4.00

    # Zero values
    assert db.compute_adsterra_revenue(0, 0) == 0.0


def test_circuit_breaker_persistence_and_hysteresis(tmp_path, monkeypatch):
    test_cb_file = tmp_path / "circuit_breaker.json"
    monkeypatch.setattr(db, "_CIRCUIT_BREAKER_FILE", test_cb_file)

    # Mock domain_today to return high CTR (6.0%)
    monkeypatch.setattr(
        db,
        "domain_today",
        lambda domain: {
            "domain": domain,
            "sessions": 50,
            "clicks": 6,
            "impressions": 100,
            "ctr": 0.06,
            "ctr_ratio": 0.06,
            "ctr_pct": 6.0,
        },
    )

    safety = db.check_domain_safety("testloan.com")
    assert safety["status"] == "PAUSED"
    assert safety["allow_click"] is False
    assert test_cb_file.exists()

    # Verify persisted in JSON
    data = json.loads(test_cb_file.read_text(encoding="utf-8"))
    assert data["testloan.com"]["paused"] is True

    # CTR drops slightly to 4.5% (above 3.5% resume threshold) -> MUST STAY PAUSED
    monkeypatch.setattr(
        db,
        "domain_today",
        lambda domain: {
            "domain": domain,
            "sessions": 60,
            "clicks": 9,
            "impressions": 200,
            "ctr": 0.045,
            "ctr_ratio": 0.045,
            "ctr_pct": 4.5,
        },
    )
    safety_hysteresis = db.check_domain_safety("testloan.com")
    assert safety_hysteresis["status"] == "PAUSED"
    assert safety_hysteresis["allow_click"] is False

    # CTR drops to 2.5% (below 3.5% resume threshold) -> UNPAUSES
    monkeypatch.setattr(
        db,
        "domain_today",
        lambda domain: {
            "domain": domain,
            "sessions": 100,
            "clicks": 10,
            "impressions": 400,
            "ctr": 0.025,
            "ctr_ratio": 0.025,
            "ctr_pct": 2.5,
        },
    )
    safety_resumed = db.check_domain_safety("testloan.com")
    assert safety_resumed["status"] == "OPTIMAL"
    assert safety_resumed["allow_click"] is True

    # Check updated persistence
    data_resumed = json.loads(test_cb_file.read_text(encoding="utf-8"))
    assert data_resumed["testloan.com"]["paused"] is False


def test_ab_test_epsilon_greedy_and_ttl_expiry(tmp_path, monkeypatch):
    test_state_file = tmp_path / "ab_test_state.json"
    monkeypatch.setattr("ab_test_engine.STATE_PATH", test_state_file)

    engine = ABTestEngine(enabled=True)
    engine.winning_variant_id = "balanced"
    engine.promoted_at = time.time()
    engine.promotion_ttl_seconds = 100.0

    # Test epsilon-greedy: across 200 draws, at least some non-winning variants chosen
    rng = random.Random(42)
    choices = [engine.select_variant(rng).variant_id for _ in range(200)]
    assert "balanced" in choices
    # Non-winner should be chosen occasionally (~10%)
    non_winners = [c for c in choices if c != "balanced"]
    assert len(non_winners) > 5

    # Test TTL expiry
    engine.promoted_at = time.time() - 200.0  # Expired
    engine.select_variant(rng)
    assert engine.winning_variant_id is None


def test_impression_deduplication():
    # Test on a temporary HTML fixture with 2 ad containers wrapping 2 iframes
    html_content = """<!DOCTYPE html>
    <html><body>
    <div class="ad-unit" style="padding: 10px; width: 320px; height: 270px;">
        <iframe class="ad-frame" src="about:blank" width="300" height="250"></iframe>
    </div>
    <div class="ad-unit" style="padding: 10px; width: 748px; height: 110px;">
        <iframe class="ad-frame" src="about:blank" width="728" height="90"></iframe>
    </div>
    </body></html>
    """
    import asyncio
    async def _run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True)
            p = await b.new_page()
            await p.set_content(html_content)
            cnt = await worker._count_impressions(p)
            await b.close()
            return cnt

    cnt = asyncio.run(_run())
    # Exactly 2 ad units, NOT 4!
    assert cnt == 2
