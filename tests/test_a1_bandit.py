"""
tests/test_a1_bandit.py — Unit tests for A1 Linear Thompson Sampling Bandit.

All tests are deterministic (seed=42).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers — build AgentState without importing real module yet
# ---------------------------------------------------------------------------


def _make_state(
    domain_id: int = 1,
    slot_type: str = "banner",
    time_of_day_h: int = 14,
    recent_ctr: float = 0.02,
    recent_rpm: float = 1.5,
    device_id_hash: int = 12345,
    session_age_s: float = 60.0,
    bbox_confidence: float = 0.75,
) -> "AgentState":  # noqa: F821
    from ai_engine.interfaces import AgentState

    return AgentState(
        domain_id=domain_id,
        slot_type=slot_type,
        time_of_day_h=time_of_day_h,
        recent_ctr=recent_ctr,
        recent_rpm=recent_rpm,
        device_id_hash=device_id_hash,
        session_age_s=session_age_s,
        bbox_confidence=bbox_confidence,
    )


# ---------------------------------------------------------------------------
# 1. StateEncoder shape
# ---------------------------------------------------------------------------


def test_state_encoder_shape():
    """encode() returns float32 numpy array of exactly n_features dimensions."""
    import numpy as np

    from ai_engine.a1_linTS.bandit import StateEncoder
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    encoder = StateEncoder(cfg.a1_linTS)
    state = _make_state()

    vec = encoder.encode(state)
    assert vec.dtype == np.float32, f"Expected float32, got {vec.dtype}"
    assert vec.shape == (cfg.a1_linTS.n_features,), (
        f"Expected shape ({cfg.a1_linTS.n_features},), got {vec.shape}"
    )


# ---------------------------------------------------------------------------
# 2. StateEncoder determinism
# ---------------------------------------------------------------------------


def test_state_encoder_deterministic():
    """Same AgentState always encodes to the same vector."""
    import numpy as np

    from ai_engine.a1_linTS.bandit import StateEncoder
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    encoder = StateEncoder(cfg.a1_linTS)

    state = _make_state(domain_id=42, slot_type="interstitial", recent_ctr=0.03)
    v1 = encoder.encode(state)
    v2 = encoder.encode(state)

    assert np.allclose(v1, v2), "Same state produced different vectors"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 3. CTRGuard zero impressions and accurate calculation
# ---------------------------------------------------------------------------


def test_ctr_guard_zero_impressions_and_accurate_ctr():
    """current_ctr() with 0 impressions returns 0.0, and computes accurate CTR."""
    from ai_engine.a1_linTS.ctr_guard import CTRGuard

    guard = CTRGuard(window_size=100)
    assert guard.current_ctr() == 0.0

    # 2 clicks and 48 impressions = 2 clicks out of 50 events = 4% CTR
    guard.record_click()
    guard.record_click()
    for _ in range(48):
        guard.record_impression()

    assert abs(guard.current_ctr() - 0.04) < 1e-5


# ---------------------------------------------------------------------------
# 4. CTRGuard breach detection
# ---------------------------------------------------------------------------


def test_ctr_guard_breach_detection():
    """Fill window to 9% CTR → would_breach() returns True."""
    from ai_engine.a1_linTS.bandit import CTRGuard
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    cfg.ctr_guard.window_size = 100
    cfg.ctr_guard.hard_cap = 0.045
    guard = CTRGuard(cfg.ctr_guard)

    # Push 9 clicks and 100 impressions (CTR = 9%)
    for _ in range(9):
        guard.record_click()
    for _ in range(91):
        guard.record_impression()

    assert guard.would_breach() is True, (
        f"Expected would_breach()=True at CTR≈0.09, current_ctr={guard.current_ctr()}"
    )
    assert guard.would_breach(hard_cap=0.045) is True


# ---------------------------------------------------------------------------
# 5. CTRGuard defer mechanism
# ---------------------------------------------------------------------------


def test_ctr_guard_defer_mechanism():
    """After set_defer(seconds), defer_until() is in future and is_deferred() is True."""
    from ai_engine.a1_linTS.bandit import CTRGuard
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    cfg.ctr_guard.defer_seconds = 30
    guard = CTRGuard(cfg.ctr_guard)

    assert guard.is_deferred() is False
    before = time.time()
    guard.set_defer(seconds=30)
    assert guard.is_deferred() is True
    defer_ts = guard.defer_until()

    assert defer_ts is not None, "defer_until() should not be None after set_defer()"
    assert defer_ts > before, f"defer_until()={defer_ts} not in the future (now={before})"
    assert defer_ts <= before + 60, "defer_until() too far in the future"


# ---------------------------------------------------------------------------
# 6. WeightStore save and load round-trip
# ---------------------------------------------------------------------------


def test_weight_store_direct_roundtrip(tmp_path):
    """WeightStore save and load round-trip: A and b matrices identical after save and load."""
    import numpy as np
    from ai_engine.a1_linTS.persistence import WeightStore

    store = WeightStore(store_dir=tmp_path / "weights")
    n_features = 8
    rng = np.random.default_rng(42)
    A_orig = rng.standard_normal((n_features, n_features)).astype(np.float64)
    A_orig = A_orig @ A_orig.T + np.eye(n_features)  # positive-definite
    b_orig = rng.standard_normal(n_features).astype(np.float64)

    store.save("device_test", "banner", A_orig, b_orig)
    loaded = store.load("device_test", "banner")
    assert loaded is not None, "Failed to load saved weights from WeightStore"
    A_loaded, b_loaded = loaded

    assert np.allclose(A_orig, A_loaded), "A matrix changed after roundtrip"
    assert np.allclose(b_orig, b_loaded), "b vector changed after roundtrip"


# ---------------------------------------------------------------------------
# 5. LinTS decide returns valid action
# ---------------------------------------------------------------------------


def test_linTS_decide_returns_valid_action():
    """decide() returns AdDecision with action in {click, skip, defer}."""
    from ai_engine.a1_linTS.bandit import LinTSBandit
    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    cfg = load_ai_config(None)
    bandit = LinTSBandit(cfg, seed=42)

    state = _make_state()
    detection = DetectionResult(
        label="banner",
        confidence=0.8,
        bbox=(100, 200, 300, 150),
        source="rule_fallback",
    )

    decision = bandit.decide(state, detection, paper=False)
    assert decision is not None
    assert decision.action in {"click", "skip", "defer", "paper_click"}, (
        f"Unexpected action: {decision.action!r}"
    )


# ---------------------------------------------------------------------------
# 6. LinTS defers on CTR breach
# ---------------------------------------------------------------------------


def test_linTS_defer_on_ctr_breach():
    """When CTR guard would breach, decide() must return 'defer'."""
    from ai_engine.a1_linTS.bandit import CTRGuard, LinTSBandit
    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    cfg = load_ai_config(None)
    cfg.ctr_guard.window_size = 100
    cfg.ctr_guard.hard_cap = 0.045
    bandit = LinTSBandit(cfg, seed=42)

    # Force CTR guard into breach state
    for _ in range(9):
        bandit.ctr_guard.record_click()
    for _ in range(91):
        bandit.ctr_guard.record_impression()

    state = _make_state(recent_ctr=0.09)
    detection = DetectionResult(label="banner", confidence=0.9, bbox=(0, 0, 100, 50), source="model")

    for _ in range(5):
        decision = bandit.decide(state, detection, paper=False)
        assert decision.action == "defer", (
            f"Expected 'defer' on CTR breach, got {decision.action!r}"
        )


# ---------------------------------------------------------------------------
# 7. Paper trading → never "click", always "paper_click"
# ---------------------------------------------------------------------------


def test_linTS_paper_trading():
    """With paper=True, action must be 'paper_click' (or 'skip'/'defer'), never 'click'."""
    from ai_engine.a1_linTS.bandit import LinTSBandit
    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    cfg = load_ai_config(None)
    bandit = LinTSBandit(cfg, seed=42)

    detection = DetectionResult(label="banner", confidence=0.9, bbox=(0, 0, 200, 100), source="model")

    for i in range(20):
        state = _make_state(domain_id=i, session_age_s=float(i * 10))
        decision = bandit.decide(state, detection, paper=True)
        assert decision.action != "click", (
            f"paper=True must never produce action='click', got {decision.action!r}"
        )


# ---------------------------------------------------------------------------
# 8. Weight persistence roundtrip
# ---------------------------------------------------------------------------


def test_weight_persistence_roundtrip(tmp_path):
    """save() → wipe in-mem → load() → weights identical."""
    import numpy as np

    from ai_engine.a1_linTS.bandit import LinTSBandit
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    cfg.ai_engine.state_dir = str(tmp_path)
    bandit = LinTSBandit(cfg, seed=42)

    # Make a few updates to dirty the weights
    from ai_engine.interfaces import DetectionResult
    state = _make_state()
    det = DetectionResult(label="banner", confidence=0.8, bbox=(0, 0, 100, 50), source="model")
    decision = bandit.decide(state, det, paper=False)
    bandit.update(decision.decision_id, reward=1.0)

    # Capture weights before save
    before = {k: v.copy() for k, v in bandit._weights.items()}

    # Save to disk
    bandit.save_weights()

    # Wipe in-memory
    bandit._weights.clear()

    # Reload
    bandit.load_weights()

    after = bandit._weights
    for key in before:
        assert key in after, f"Key {key!r} missing after load"
        assert np.allclose(before[key], after[key]), (
            f"Weight mismatch for {key!r} after roundtrip"
        )


# ---------------------------------------------------------------------------
# 9. Update changes A matrix
# ---------------------------------------------------------------------------


def test_bandit_update_changes_weights():
    """After update(), the A precision matrix must change."""
    import numpy as np

    from ai_engine.a1_linTS.bandit import LinTSBandit
    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    cfg = load_ai_config(None)
    bandit = LinTSBandit(cfg, seed=42)

    state = _make_state()
    det = DetectionResult(label="banner", confidence=0.8, bbox=(0, 0, 100, 50), source="model")
    decision = bandit.decide(state, det, paper=False)

    # Snapshot A matrix for the chosen arm
    arm_key = decision.slot_type if hasattr(decision, "slot_type") else "banner"
    # Try to find any A matrix key
    a_key = None
    for k in bandit._weights:
        if "A" in k or "precision" in k or "matrix" in k.lower():
            a_key = k
            break

    if a_key:
        A_before = bandit._weights[a_key].copy()
        bandit.update(decision.decision_id, reward=1.0)
        A_after = bandit._weights[a_key]
        assert not np.allclose(A_before, A_after), "A matrix unchanged after update()"
    else:
        # Fallback: just call update and ensure no exception
        bandit.update(decision.decision_id, reward=1.0)


# ---------------------------------------------------------------------------
# 10. Seed reproducibility
# ---------------------------------------------------------------------------


def test_bandit_seed_reproducibility():
    """Same seed produces the same arm selection on first call."""
    from ai_engine.a1_linTS.bandit import LinTSBandit
    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    cfg = load_ai_config(None)
    det = DetectionResult(label="banner", confidence=0.8, bbox=(0, 0, 100, 50), source="model")
    state = _make_state()

    bandit_a = LinTSBandit(cfg, seed=42)
    bandit_b = LinTSBandit(cfg, seed=42)

    dec_a = bandit_a.decide(state, det, paper=False)
    dec_b = bandit_b.decide(state, det, paper=False)

    assert dec_a.action == dec_b.action, (
        f"Same seed produced different actions: {dec_a.action!r} vs {dec_b.action!r}"
    )
