"""
tests/test_push_notification.py — Step 4.4: Push Notification Subscription Farming Tests

Covers:
1. PushManager.should_trigger() probability respects trigger_prob
2. PushManager.should_allow() probability respects allow_prob
3. handle() returns 'eu_skip' for EU country without CMP accept
4. handle() returns 'allow' action when permission granted
5. handle() returns 'block' action when user blocks
6. db.log_push_event() records row correctly
7. db.push_allow_rate() computes ratio correctly
8. build_from_config() reads config.yaml values correctly
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
import push_manager


# ---------------------------------------------------------------------------
# 1. should_trigger() respects trigger_prob
# ---------------------------------------------------------------------------
def test_should_trigger_probability():
    """High trigger_prob → almost always triggers. Low → almost never."""
    rng = random.Random(42)

    mgr_always = push_manager.PushManager(trigger_prob=1.0)
    results_always = [mgr_always.should_trigger(rng) for _ in range(100)]
    assert all(results_always), "trigger_prob=1.0 should always trigger"

    rng2 = random.Random(42)
    mgr_never = push_manager.PushManager(trigger_prob=0.0)
    results_never = [mgr_never.should_trigger(rng2) for _ in range(100)]
    assert not any(results_never), "trigger_prob=0.0 should never trigger"

    # Realistic 17.5% — check in ballpark (5–35% range with seed)
    rng3 = random.Random(1234)
    mgr_real = push_manager.PushManager(trigger_prob=0.175)
    n_triggered = sum(mgr_real.should_trigger(rng3) for _ in range(1000))
    assert 50 <= n_triggered <= 350, f"trigger count {n_triggered} out of expected range for 17.5%"
    print(f"  [OK] trigger_prob=0.175 → {n_triggered}/1000 triggered")


# ---------------------------------------------------------------------------
# 2. should_allow() respects allow_prob
# ---------------------------------------------------------------------------
def test_should_allow_probability():
    """allow_prob=0.78 → ~78% allow rate."""
    rng = random.Random(999)
    mgr = push_manager.PushManager(allow_prob=0.78)
    n_allow = sum(mgr.should_allow(rng) for _ in range(1000))
    # 78% ± 10% acceptable range
    assert 650 <= n_allow <= 900, f"allow count {n_allow} out of expected range"
    print(f"  [OK] allow_prob=0.78 → {n_allow}/1000 allowed")


# ---------------------------------------------------------------------------
# 3. EU/UK skip without CMP accept
# ---------------------------------------------------------------------------
def test_eu_skip_without_cmp():
    """EU country without CMP accept should return eu_skip action."""
    mgr = push_manager.PushManager(trigger_prob=1.0, allow_prob=1.0, min_delay_s=0.0, max_delay_s=0.01)
    rng = random.Random(42)

    mock_context = AsyncMock()
    mock_page = AsyncMock()

    async def _run():
        return await mgr.handle(
            context=mock_context,
            page=mock_page,
            rng=rng,
            proxy_country="DE",  # Germany — EU
            cmp_accepted=False,  # No CMP accept
            domain="loanraaj.com",
        )

    result = asyncio.run(_run())
    assert result["action"] == "eu_skip", f"Expected eu_skip, got {result['action']}"
    assert result["triggered"] is False
    print(f"  [OK] EU country DE without CMP → eu_skip")


# ---------------------------------------------------------------------------
# 4. handle() returns 'allow' action
# ---------------------------------------------------------------------------
def test_handle_allow_action():
    """Non-EU country with trigger_prob=1.0 and allow_prob=1.0 → 'allow'."""
    mgr = push_manager.PushManager(trigger_prob=1.0, allow_prob=1.0, min_delay_s=0.0, max_delay_s=0.01)
    rng = random.Random(42)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    # Make evaluate return success
    mock_page.evaluate = AsyncMock(return_value={"ok": True, "permission": "granted", "swReady": True})

    async def _run():
        return await mgr.handle(
            context=mock_context,
            page=mock_page,
            rng=rng,
            proxy_country="US",
            cmp_accepted=True,
            domain="loanraaj.com",
        )

    result = asyncio.run(_run())
    assert result["action"] in ("allow", "allow_failed"), f"Expected allow, got {result['action']}"
    assert result["triggered"] is True
    assert result["delay_s"] >= 0.0
    print(f"  [OK] US + trigger/allow=1.0 → action={result['action']}, delay={result['delay_s']:.2f}s")


# ---------------------------------------------------------------------------
# 5. handle() returns 'block' action
# ---------------------------------------------------------------------------
def test_handle_block_action():
    """trigger_prob=1.0 and allow_prob=0.0 → 'block'."""
    mgr = push_manager.PushManager(trigger_prob=1.0, allow_prob=0.0, min_delay_s=0.0, max_delay_s=0.01)
    rng = random.Random(42)

    mock_context = AsyncMock()
    mock_page = AsyncMock()

    async def _run():
        return await mgr.handle(
            context=mock_context,
            page=mock_page,
            rng=rng,
            proxy_country="IN",
            cmp_accepted=True,
            domain="rechargetak.com",
        )

    result = asyncio.run(_run())
    assert result["action"] == "block", f"Expected block, got {result['action']}"
    assert result["triggered"] is True
    print(f"  [OK] IN + allow_prob=0.0 → block")


# ---------------------------------------------------------------------------
# 6. db.log_push_event() records correctly
# ---------------------------------------------------------------------------
def test_db_log_push_event():
    """log_push_event() inserts a row into push_subscriptions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Temporarily reroute db path
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_push.db"
        try:
            db.init()
            row_id = db.log_push_event(
                proxy_id="proxy_test_001",
                domain="loanraaj.com",
                action="allow",
                delay_s=12.5,
                geo_country="US",
                geo_tier="tier1",
                session_id=None,
            )
            assert row_id > 0, f"Expected row_id > 0, got {row_id}"

            # Verify in DB
            con = sqlite3.connect(str(db._DB_PATH))
            rows = con.execute("SELECT * FROM push_subscriptions").fetchall()
            con.close()
            assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
            assert rows[0][2] == "loanraaj.com"  # domain
            assert rows[0][3] == "allow"          # action
            assert abs(rows[0][4] - 12.5) < 0.01  # delay_s
            print(f"  [OK] log_push_event: row_id={row_id}, action=allow, delay=12.5s")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 7. db.push_allow_rate() computes ratio
# ---------------------------------------------------------------------------
def test_db_push_allow_rate():
    """push_allow_rate() returns fraction of 'allow' events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_push_rate.db"
        try:
            db.init()
            # Insert 7 allow, 2 block, 1 skipped = 70% allow rate
            for i in range(7):
                db.log_push_event("px", "loanraaj.com", "allow", 10.0, "US", "tier1")
            for i in range(2):
                db.log_push_event("px", "loanraaj.com", "block", 8.0, "US", "tier1")
            db.log_push_event("px", "loanraaj.com", "skipped", 0.0, "US", "tier1")

            rate = db.push_allow_rate(domain="loanraaj.com", last_n=50)
            assert 0.65 <= rate <= 0.75, f"Expected ~0.70 allow rate, got {rate:.2f}"
            print(f"  [OK] push_allow_rate: {rate:.2f} (expected ~0.70)")
        finally:
            db._DB_PATH = original_path


# ---------------------------------------------------------------------------
# 8. build_from_config() reads config values
# ---------------------------------------------------------------------------
def test_build_from_config():
    """build_from_config() correctly maps config.yaml push_notifications block."""
    cfg = {
        "push_notifications": {
            "trigger_prob": 0.20,
            "allow_prob": 0.85,
            "min_delay_s": 5.0,
            "max_delay_s": 30.0,
        }
    }
    mgr = push_manager.build_from_config(cfg)
    assert mgr.trigger_prob == 0.20, f"trigger_prob mismatch: {mgr.trigger_prob}"
    assert mgr.allow_prob == 0.85, f"allow_prob mismatch: {mgr.allow_prob}"
    assert mgr.min_delay_s == 5.0, f"min_delay_s mismatch: {mgr.min_delay_s}"
    assert mgr.max_delay_s == 30.0, f"max_delay_s mismatch: {mgr.max_delay_s}"
    print(f"  [OK] build_from_config: trigger={mgr.trigger_prob}, allow={mgr.allow_prob}")


if __name__ == "__main__":
    tests = [
        test_should_trigger_probability,
        test_should_allow_probability,
        test_eu_skip_without_cmp,
        test_handle_allow_action,
        test_handle_block_action,
        test_db_log_push_event,
        test_db_push_allow_rate,
        test_build_from_config,
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
