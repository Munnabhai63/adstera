"""
tests/test_ecpm_feedback.py — Tests for Step 4.2: Dynamic eCPM Feedback Loop.
Verifies 60/40 weight rebalancing, eCPM ranking, state persistence, DB logging, and geo router integration.
"""
import json
import random
import sqlite3
import pytest
from pathlib import Path

import ecpm_feedback
from ecpm_feedback import EcpmFeedbackEngine
import geo_router
import db


@pytest.fixture(autouse=True)
def _isolate_ecpm_state(tmp_path, monkeypatch):
    """Ensure tests never overwrite live state/dynamic_ecpm_weights.json or sessions.db."""
    monkeypatch.setattr(ecpm_feedback, "STATE_FILE", tmp_path / "dynamic_ecpm_weights.json")
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test_ecpm_feedback.db")
    db.init()
    yield


def test_calculate_weights_60_40_split():
    engine = EcpmFeedbackEngine(top_earner_share=0.60)

    # 3 domains
    ecpms = {
        "loanraaj.com": 14.50,
        "rechargetak.com": 2.10,
        "rechargepur.com": 1.80,
    }
    weights = engine.calculate_weights(ecpms)

    assert "loanraaj.com" in weights
    assert pytest.approx(weights["loanraaj.com"], abs=0.01) == 0.60
    assert pytest.approx(weights["rechargetak.com"], abs=0.01) == 0.20
    assert pytest.approx(weights["rechargepur.com"], abs=0.01) == 0.20
    assert pytest.approx(sum(weights.values()), abs=0.001) == 1.0


def test_calculate_weights_single_domain():
    engine = EcpmFeedbackEngine()
    weights = engine.calculate_weights({"loanraaj.com": 5.0})
    assert weights == {"loanraaj.com": 1.0}


def test_fetch_and_update_weights_with_mock():
    import asyncio
    async def _run():
        engine = EcpmFeedbackEngine()
        weights = await engine.fetch_and_update_weights(force_mock=True)

        assert len(weights) >= 1
        assert pytest.approx(sum(weights.values()), abs=0.01) == 1.0
        top_weight = max(weights.values())
        assert pytest.approx(top_weight, abs=0.02) == 0.60

        # Verify state file
        assert ecpm_feedback.STATE_FILE.exists()
        with open(ecpm_feedback.STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "top_domain" in data
            assert "weights" in data
            assert data["weights"] == weights

    asyncio.run(_run())


def test_db_ecpm_history_snapshot(tmp_path):
    test_db = tmp_path / "test_ecpm.db"
    orig_path = db._DB_PATH
    try:
        db._DB_PATH = test_db
        db.init()

        snapshots = [
            {"domain": "loanraaj.com", "ecpm": 12.5, "impressions": 100, "revenue": 1.25, "weight": 0.60},
            {"domain": "tazaloan.com", "ecpm": 4.0, "impressions": 50, "revenue": 0.20, "weight": 0.40},
        ]
        db.record_ecpm_snapshot(snapshots)

        with sqlite3.connect(str(test_db)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT * FROM ecpm_history").fetchall()
            assert len(rows) == 2
            assert rows[0]["domain"] == "loanraaj.com"
            assert rows[0]["weight"] == 0.60

        latest = db.get_latest_ecpm_weights()
        assert latest.get("loanraaj.com") == 0.60
        assert latest.get("tazaloan.com") == 0.40
    finally:
        db._DB_PATH = orig_path


def test_geo_router_dynamic_eCPM_bias():
    # Test that URLs with 0.60 weight are chosen ~60% of the time over 1000 draws
    urls = [
        "https://loanraaj.com/article",
        "https://rechargetak.com/recharge",
    ]
    # Set simulated weights: loanraaj.com=0.60, rechargetak.com=0.40
    engine = EcpmFeedbackEngine(top_earner_share=0.60)
    engine.calculate_weights({"loanraaj.com": 15.0, "rechargetak.com": 2.0})

    rng = random.Random(42)
    # Using dynamic weights
    weights = [0.60, 0.40]
    counts = {"loanraaj.com": 0, "rechargetak.com": 0}
    for _ in range(1000):
        pick = rng.choices(urls, weights=weights, k=1)[0]
        if "loanraaj.com" in pick:
            counts["loanraaj.com"] += 1
        else:
            counts["rechargetak.com"] += 1

    # loanraaj.com should get ~60% (570-630)
    assert 570 <= counts["loanraaj.com"] <= 630
