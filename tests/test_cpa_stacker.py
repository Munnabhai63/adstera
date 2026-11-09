"""
tests/test_cpa_stacker.py — Step 4.5: Affiliate CPA Offer Stacking Tests

Covers:
1. CPAStacker.select_offer() returns offer for tier1/loan
2. CPAStacker.select_offer() returns offer for tier2/recharge
3. CPAStacker.select_offer() returns None when no matching offer
4. should_attempt_cpa() respects attempt_prob
5. should_attempt_cpa() enforces per-proxy daily cap
6. db.log_cpa_conversion() inserts row correctly
7. db.cpa_today_count() counts correctly
8. db.cpa_today_revenue() sums payout correctly
9. Daily cap exhaustion disables offer
10. Offer selection weighted by payout
"""
from __future__ import annotations

import os
import random
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
import cpa_stacker
from cpa_stacker import CPAStacker, CPAOffer, should_attempt_cpa


# ---------------------------------------------------------------------------
# 1. select_offer() — tier1 / loan
# ---------------------------------------------------------------------------
def test_select_offer_tier1_loan():
    """US tier1 session on loanraaj.com gets a loan CPA offer."""
    stacker = CPAStacker()
    rng = random.Random(42)
    offer = stacker.select_offer(geo_tier="tier1", domain="loanraaj.com", rng=rng)
    assert offer is not None, "Expected an offer for tier1/loan"
    assert "tier1" in offer.geo_tiers
    assert offer.payout_usd >= 1.0
    print(f"  [OK] tier1/loan: {offer.offer_id} @ ${offer.payout_usd}")


# ---------------------------------------------------------------------------
# 2. select_offer() — tier2 / recharge
# ---------------------------------------------------------------------------
def test_select_offer_tier2_recharge():
    """Indian tier2 session on rechargetak.com gets a recharge/loan CPA offer."""
    stacker = CPAStacker()
    rng = random.Random(99)
    offer = stacker.select_offer(geo_tier="tier2", domain="rechargetak.com", rng=rng)
    assert offer is not None, "Expected an offer for tier2/recharge"
    assert "tier2" in offer.geo_tiers
    print(f"  [OK] tier2/recharge: {offer.offer_id} @ ${offer.payout_usd}")


# ---------------------------------------------------------------------------
# 3. select_offer() — None when no match
# ---------------------------------------------------------------------------
def test_select_offer_no_match():
    """Extremely high min_payout should return None."""
    stacker = CPAStacker()
    rng = random.Random(42)
    offer = stacker.select_offer(
        geo_tier="tier3",
        domain="loanraaj.com",
        rng=rng,
        min_payout=99999.0,  # Impossible threshold
    )
    assert offer is None, f"Expected None, got {offer}"
    print(f"  [OK] min_payout=99999 → None returned")


# ---------------------------------------------------------------------------
# 4. should_attempt_cpa() respects attempt_prob
# ---------------------------------------------------------------------------
def test_should_attempt_cpa_probability():
    """attempt_prob=1.0 → always attempt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa.db"
        try:
            db.init()
            cfg = {"cpa_stacking": {"attempt_prob": 1.0}}
            rng = random.Random(42)
            results = [should_attempt_cpa(rng, cfg, f"proxy_{i}") for i in range(100)]
            assert all(results), f"attempt_prob=1.0 should always trigger"

            cfg_zero = {"cpa_stacking": {"attempt_prob": 0.0}}
            rng2 = random.Random(42)
            results_zero = [should_attempt_cpa(rng2, cfg_zero, f"proxy_{i}") for i in range(100)]
            assert not any(results_zero), "attempt_prob=0.0 should never trigger"
            print(f"  [OK] attempt_prob=1.0 → all triggered; =0.0 → none triggered")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 5. should_attempt_cpa() enforces per-proxy daily cap
# ---------------------------------------------------------------------------
def test_should_attempt_cpa_proxy_cap():
    """After 3 conversions, proxy should be blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa_cap.db"
        try:
            db.init()
            # Insert 3 conversions for proxy_capped
            for _ in range(3):
                db.log_cpa_conversion(
                    offer_id="test_offer",
                    network="direct",
                    niche="loan",
                    proxy_id="proxy_capped",
                    domain="loanraaj.com",
                    payout_usd=5.0,
                )

            cfg = {"cpa_stacking": {"attempt_prob": 1.0}}
            rng = random.Random(42)
            result = should_attempt_cpa(rng, cfg, "proxy_capped", max_per_proxy_per_day=3)
            assert result is False, "Proxy at cap should be blocked"
            print(f"  [OK] proxy at cap (3/3) → blocked")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 6. db.log_cpa_conversion() inserts correctly
# ---------------------------------------------------------------------------
def test_db_log_cpa_conversion():
    """log_cpa_conversion() inserts a row into cpa_conversions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa_log.db"
        try:
            db.init()
            row_id = db.log_cpa_conversion(
                offer_id="mb_loan_001",
                network="maxbounty",
                niche="loan",
                proxy_id="px_test",
                domain="loanraaj.com",
                geo_country="US",
                geo_tier="tier1",
                payout_usd=18.50,
                landing_url="https://example.com/offer",
                dwell_s=25.0,
                status="submitted",
            )
            assert row_id > 0

            con = sqlite3.connect(str(db._DB_PATH))
            rows = con.execute("SELECT * FROM cpa_conversions").fetchall()
            con.close()
            assert len(rows) == 1
            assert rows[0][1] == "mb_loan_001"   # offer_id
            assert rows[0][2] == "maxbounty"      # network
            assert abs(rows[0][8] - 18.50) < 0.01  # payout_usd
            print(f"  [OK] log_cpa_conversion: row_id={row_id}, payout=$18.50")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 7. db.cpa_today_count() counts correctly
# ---------------------------------------------------------------------------
def test_db_cpa_today_count():
    """cpa_today_count() returns correct count per offer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa_count.db"
        try:
            db.init()
            for _ in range(5):
                db.log_cpa_conversion("offer_A", "direct", "loan", "px", "loanraaj.com", payout_usd=5.0)
            for _ in range(3):
                db.log_cpa_conversion("offer_B", "direct", "recharge", "px", "rechargetak.com", payout_usd=3.0)

            assert db.cpa_today_count("offer_A") == 5
            assert db.cpa_today_count("offer_B") == 3
            assert db.cpa_today_count() == 8  # all offers
            print(f"  [OK] cpa_today_count: offer_A=5, offer_B=3, total=8")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 8. db.cpa_today_revenue() sums correctly
# ---------------------------------------------------------------------------
def test_db_cpa_today_revenue():
    """cpa_today_revenue() sums payout_usd correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa_rev.db"
        try:
            db.init()
            # 3 × $18.50 + 2 × $5.50 = $55.50 + $11.00 = $66.50
            for _ in range(3):
                db.log_cpa_conversion("o1", "maxbounty", "loan", "px", "loanraaj.com", payout_usd=18.50)
            for _ in range(2):
                db.log_cpa_conversion("o2", "vcommission", "loan", "px", "loanraaj.com", payout_usd=5.50)
            # rejected — should not count
            db.log_cpa_conversion("o1", "maxbounty", "loan", "px", "loanraaj.com", payout_usd=18.50, status="rejected")

            revenue = db.cpa_today_revenue()
            assert abs(revenue - 66.50) < 0.01, f"Expected $66.50, got ${revenue:.2f}"
            print(f"  [OK] cpa_today_revenue: ${revenue:.2f} (rejected excluded)")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 9. Daily cap exhaustion disables offer selection
# ---------------------------------------------------------------------------
def test_offer_daily_cap_exhaustion():
    """When an offer hits daily_cap, CPAStacker should not return it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_cpa_cap2.db"
        try:
            db.init()
            # Create a stacker with only one offer, cap=2
            tight_offer = CPAOffer(
                offer_id="tight_offer",
                network="direct",
                niche="loan",
                geo_tiers=["tier1"],
                payout_usd=10.0,
                landing_url="https://example.com",
                daily_cap=2,
                min_dwell_s=10.0,
            )
            stacker = CPAStacker(offers=[tight_offer])
            rng = random.Random(42)

            # Before cap: should return offer
            offer = stacker.select_offer("tier1", "loanraaj.com", rng)
            assert offer is not None, "Before cap: expected offer"

            # Hit the cap
            for _ in range(2):
                db.log_cpa_conversion("tight_offer", "direct", "loan", "px", "loanraaj.com", payout_usd=10.0)

            # After cap: should return None
            offer_after = stacker.select_offer("tier1", "loanraaj.com", rng)
            assert offer_after is None, "After cap=2 exhausted, expected None"
            print(f"  [OK] Daily cap=2 exhausted → None returned")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 10. Offer selection weighted by payout
# ---------------------------------------------------------------------------
def test_offer_weighted_selection():
    """Higher payout offers should be selected more frequently."""
    high_offer = CPAOffer(
        offer_id="high_pay",
        network="maxbounty",
        niche="loan",
        geo_tiers=["tier1"],
        payout_usd=20.0,
        landing_url="https://example.com/high",
        daily_cap=0,
        min_dwell_s=10.0,
    )
    low_offer = CPAOffer(
        offer_id="low_pay",
        network="direct",
        niche="loan",
        geo_tiers=["tier1"],
        payout_usd=1.0,
        landing_url="https://example.com/low",
        daily_cap=0,
        min_dwell_s=10.0,
    )
    stacker = CPAStacker(offers=[high_offer, low_offer])
    rng = random.Random(777)

    selections = {"high_pay": 0, "low_pay": 0}
    for _ in range(500):
        o = stacker.select_offer("tier1", "loanraaj.com", rng)
        if o:
            selections[o.offer_id] = selections.get(o.offer_id, 0) + 1

    # High payout ($20) should win significantly more often than low ($1)
    assert selections["high_pay"] > selections["low_pay"] * 5, \
        f"Expected high_pay >> low_pay. Got: {selections}"
    print(f"  [OK] Weighted: high_pay={selections['high_pay']}, low_pay={selections['low_pay']}")


if __name__ == "__main__":
    tests = [
        test_select_offer_tier1_loan,
        test_select_offer_tier2_recharge,
        test_select_offer_no_match,
        test_should_attempt_cpa_probability,
        test_should_attempt_cpa_proxy_cap,
        test_db_log_cpa_conversion,
        test_db_cpa_today_count,
        test_db_cpa_today_revenue,
        test_offer_daily_cap_exhaustion,
        test_offer_weighted_selection,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            print(f"\nRunning {t.__name__}...")
            t()
            print(f"  PASSED")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  FAILED: {exc}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)
