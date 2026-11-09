"""
tests/test_ab_test_engine.py — Step 5.3: A/B Test Engine for Click & Dwell Strategies Tests

Covers:
1. ABTestEngine selects variants based on weights
2. apply_variant_to_config overrides target parameters cleanly without mutating original cfg
3. db.get_ab_test_metrics aggregates variant metrics
4. evaluate_and_promote disqualifies variants with CTR > 5.0%
5. evaluate_and_promote promotes winning variant with lowest degradation rate
6. State persistence preserves and restores winning variant
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

import ab_test_engine
from ab_test_engine import ABTestEngine, StrategyVariant
import db


def test_ab_test_select_variant():
    """select_variant samples variants according to defined weights."""
    engine = ABTestEngine()
    rng = random.Random(42)

    counts = {"conservative": 0, "balanced": 0, "high_engagement": 0}
    for _ in range(300):
        v = engine.select_variant(rng)
        counts[v.variant_id] += 1

    # Balanced has weight 0.45, so it should be the most frequently selected
    assert counts["balanced"] > counts["high_engagement"]
    assert counts["conservative"] > 0
    print(f"  [OK] select_variant distribution: {counts}")


def test_ab_test_apply_variant_to_config():
    """apply_variant_to_config overrides click_prob and dwell cleanly."""
    engine = ABTestEngine()
    base_cfg = {
        "target": {
            "click_prob": 0.05,
            "min_dwell": 20.0,
            "max_dwell": 60.0,
            "scroll_prob": 0.70,
        }
    }
    variant = StrategyVariant(
        variant_id="test_custom",
        click_prob=0.08,
        min_dwell=45.0,
        max_dwell=120.0,
        scroll_prob=0.95,
        weight=1.0,
        description="custom test variant",
    )

    scoped_cfg = engine.apply_variant_to_config(base_cfg, variant)
    assert scoped_cfg["target"]["click_prob"] == 0.08
    assert scoped_cfg["target"]["min_dwell"] == 45.0
    assert scoped_cfg["target"]["max_dwell"] == 120.0
    assert scoped_cfg["target"]["scroll_prob"] == 0.95
    # Ensure original config untouched
    assert base_cfg["target"]["click_prob"] == 0.05
    print("  [OK] apply_variant_to_config correctly applied overrides")


def test_db_get_ab_test_metrics():
    """db.get_ab_test_metrics returns accurate aggregated metrics per variant."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_db = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_ab.db"
        try:
            db.init()
            # Insert 10 sessions for 'conservative' (0 degraded, 2 clicks, 100 imps -> 2% CTR)
            for _ in range(10):
                db.log_session(
                    proxy_id="p1",
                    ua="UA",
                    referrer="",
                    dwell=30.0,
                    pages=1,
                    ad_clicks=0,
                    impressions=10,
                    status="ok",
                    variant_id="conservative",
                )
            # Add 2 clicks
            db.log_session(
                proxy_id="p1",
                ua="UA",
                referrer="",
                dwell=30.0,
                pages=1,
                ad_clicks=2,
                impressions=10,
                status="ok",
                variant_id="conservative",
            )

            # Insert 5 sessions for 'aggressive' (2 degraded, 8 clicks, 50 imps -> 16% CTR)
            for _ in range(3):
                db.log_session(
                    proxy_id="p2",
                    ua="UA",
                    referrer="",
                    dwell=50.0,
                    pages=2,
                    ad_clicks=0,
                    impressions=10,
                    status="ok",
                    variant_id="aggressive",
                )
            for _ in range(2):
                db.log_session(
                    proxy_id="p2",
                    ua="UA",
                    referrer="",
                    dwell=50.0,
                    pages=1,
                    ad_clicks=4,
                    impressions=10,
                    status="degraded",
                    variant_id="aggressive",
                )

            metrics = db.get_ab_test_metrics(last_n=100)
            assert "conservative" in metrics
            assert metrics["conservative"]["sessions"] == 11
            assert metrics["conservative"]["degraded"] == 0
            assert metrics["conservative"]["clicks"] == 2

            assert "aggressive" in metrics
            assert metrics["aggressive"]["sessions"] == 5
            assert metrics["aggressive"]["degraded"] == 2
            assert metrics["aggressive"]["clicks"] == 8
            print("  [OK] db.get_ab_test_metrics aggregated variants accurately")
        finally:
            db._DB_PATH = orig_db


def test_ab_test_evaluate_and_promote():
    """evaluate_and_promote disqualifies CTR > 5% and promotes safest high performer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_db = db._DB_PATH
        orig_state = ab_test_engine.STATE_PATH
        db._DB_PATH = Path(tmpdir) / "test_ab2.db"
        ab_test_engine.STATE_PATH = Path(tmpdir) / "ab_state.json"
        try:
            db.init()
            # Populate 'conservative' (50 sessions, 0 degraded, CTR 3.5%)
            for i in range(50):
                db.log_session(
                    proxy_id=f"p_{i}",
                    ua="UA",
                    referrer="",
                    dwell=35.0,
                    pages=1,
                    ad_clicks=1 if i < 35 else 0,
                    impressions=20,
                    status="ok",
                    variant_id="conservative",
                )

            # Populate 'high_engagement' (50 sessions, 10 degraded, CTR 7.5% - over safety limit)
            for i in range(50):
                db.log_session(
                    proxy_id=f"p_{i}",
                    ua="UA",
                    referrer="",
                    dwell=55.0,
                    pages=2,
                    ad_clicks=3 if i < 25 else 0,
                    impressions=20,
                    status="degraded" if i < 10 else "ok",
                    variant_id="high_engagement",
                )

            engine = ABTestEngine()
            eval_result = engine.evaluate_and_promote(min_samples=40)

            # 'high_engagement' has CTR > 5%, so it must be disqualified
            assert "high_engagement" in eval_result["disqualified"]
            assert eval_result["winner"] == "conservative"
            assert engine.winning_variant_id == "conservative"
            print(f"  [OK] evaluate_and_promote promoted winner: {eval_result['winner']}")
        finally:
            db._DB_PATH = orig_db
            ab_test_engine.STATE_PATH = orig_state


def test_ab_test_state_persistence():
    """ABTestEngine persists winning variant to json and restores on restart."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = ab_test_engine.STATE_PATH
        test_state_file = Path(tmpdir) / "ab_test_state.json"
        ab_test_engine.STATE_PATH = test_state_file
        try:
            engine = ABTestEngine()
            engine.winning_variant_id = "conservative"
            engine._save_state()

            assert test_state_file.exists()

            # Second engine instance should load winner automatically
            engine2 = ABTestEngine()
            assert engine2.winning_variant_id == "conservative"

            # Selection should always return winner
            v = engine2.select_variant(random.Random(123))
            assert v.variant_id == "conservative"
            print("  [OK] ABTestEngine state persistence verified")
        finally:
            ab_test_engine.STATE_PATH = orig_state


if __name__ == "__main__":
    test_ab_test_select_variant()
    test_ab_test_apply_variant_to_config()
    test_db_get_ab_test_metrics()
    test_ab_test_evaluate_and_promote()
    test_ab_test_state_persistence()
    print("\nAll A/B test engine tests PASSED!")
