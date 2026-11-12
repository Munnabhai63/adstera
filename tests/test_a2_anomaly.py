"""
tests/test_a2_anomaly.py — Unit tests for A2 Anomaly Detector.

All tests are deterministic (seed=42) and use synthetic data.
No real DB is needed: tmp_path fixture provides SQLite paths.
"""
from __future__ import annotations

import importlib
import math
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a MetricsSnapshot without importing the real module
# (the real module may not exist yet; tests import it lazily)
# ---------------------------------------------------------------------------


def _make_snapshot(
    rpm: float = 1.0,
    ctr: float = 0.02,
    empty_ad_rate: float = 0.0,
    load_time_ms: float = 500.0,
    error_rate: float = 0.0,
    repeated_creative_rate: float = 0.0,
    domain: str = "example.com",
    device_id: str = "emulator-5554",
) -> "MetricsSnapshot":  # noqa: F821
    from ai_engine.interfaces import MetricsSnapshot

    return MetricsSnapshot(
        rpm=rpm,
        ctr=ctr,
        empty_ad_rate=empty_ad_rate,
        load_time_ms=load_time_ms,
        error_rate=error_rate,
        repeated_creative_rate=repeated_creative_rate,
        domain=domain,
        device_id=device_id,
    )


# ---------------------------------------------------------------------------
# 1. MetricsBuffer / EWMA convergence
# ---------------------------------------------------------------------------


def test_metrics_buffer_ewma():
    """Buffer fills and EWMA converges monotonically toward target value."""
    from ai_engine.a2_anomaly.detector import MetricsBuffer

    alpha = 0.2
    buf = MetricsBuffer(alpha=alpha, maxlen=50)

    # Feed 40 identical snapshots with rpm=2.0
    for _ in range(40):
        buf.update(_make_snapshot(rpm=2.0))

    ewma_rpm = buf.ewma.get("rpm", 0.0)
    # After many updates EWMA should be close to 2.0
    assert abs(ewma_rpm - 2.0) < 0.3, f"EWMA rpm={ewma_rpm} did not converge to 2.0"
    assert len(buf) == 40

    stats = buf.stats()
    assert "rpm" in stats
    assert abs(stats["rpm"]["mean"] - 2.0) < 1e-4
    assert stats["rpm"]["count"] == 40


# ---------------------------------------------------------------------------
# 2. Z-score within threshold → ok=True
# ---------------------------------------------------------------------------


def test_z_score_normal():
    """Normal metric values produce ok=True result."""
    from ai_engine.a2_anomaly.detector import AnomalyDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    detector = AnomalyDetector(cfg.a2_anomaly, db_path=":memory:")

    # Warm up with normal data
    for _ in range(30):
        detector.ingest(_make_snapshot(rpm=1.5, ctr=0.02))

    result = detector.check(_make_snapshot(rpm=1.5, ctr=0.02))
    assert result.ok is True, f"Expected ok=True, got severity={result.severity}"
    assert result.severity == "OK"


# ---------------------------------------------------------------------------
# 3. CTR spike → CRITICAL
# ---------------------------------------------------------------------------


def test_ctr_spike_triggers_critical():
    """CTR=0.09 (> hard_cap 0.045) must trigger severity=CRITICAL."""
    from ai_engine.a2_anomaly.detector import AnomalyDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    # hard_cap check is absolute — no warm-up needed for hard rule
    detector = AnomalyDetector(cfg.a2_anomaly, db_path=":memory:")

    result = detector.check(_make_snapshot(ctr=0.09))
    assert result.severity == "CRITICAL", (
        f"Expected CRITICAL for CTR=0.09, got {result.severity}"
    )
    assert result.ok is False


# ---------------------------------------------------------------------------
# 4. RPM drop → severity≥WARNING
# ---------------------------------------------------------------------------


def test_rpm_drop_triggers_warning():
    """RPM=0.1 (< rpm_floor=0.5) must trigger at least WARNING."""
    from ai_engine.a2_anomaly.detector import AnomalyDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    detector = AnomalyDetector(cfg.a2_anomaly, db_path=":memory:")

    result = detector.check(_make_snapshot(rpm=0.1))
    assert result.severity in ("WARNING", "CRITICAL"), (
        f"Expected WARNING or CRITICAL for rpm=0.1, got {result.severity}"
    )
    assert result.ok is False


# ---------------------------------------------------------------------------
# 5. CRITICAL → safe_mode.is_active()=True
# ---------------------------------------------------------------------------


def test_safe_mode_entry_on_critical(tmp_path):
    """CRITICAL anomaly result causes safe_mode to become active."""
    from ai_engine.a2_anomaly.detector import AnomalyDetector
    from ai_engine.config import load_ai_config
    from ai_engine.safe_mode import SafeMode
    from common.paths import atomic_write_json

    atomic_write_json(
        tmp_path / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    cfg = load_ai_config(None)
    safe = SafeMode(cfg.a2_anomaly.safe_mode, state_dir=str(tmp_path))
    assert safe.is_active() is False
    detector = AnomalyDetector(cfg.a2_anomaly, db_path=":memory:", safe_mode=safe)

    result = detector.check(_make_snapshot(ctr=0.09))
    assert result.severity == "CRITICAL"
    assert safe.is_active() is True


# ---------------------------------------------------------------------------
# 6. M=5 clean ticks → safe_mode exits
# ---------------------------------------------------------------------------


def test_safe_mode_exit_after_m_clean_windows(tmp_path):
    """After M consecutive clean ticks, safe_mode.is_active() returns False."""
    from ai_engine.config import load_ai_config
    from ai_engine.safe_mode import SafeMode
    from common.paths import atomic_write_json

    atomic_write_json(
        tmp_path / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    cfg = load_ai_config(None)
    cfg.a2_anomaly.safe_mode.exit_clean_windows = 5
    safe = SafeMode(cfg.a2_anomaly.safe_mode, state_dir=str(tmp_path))
    safe.enter("test trigger")

    assert safe.is_active() is True

    for _ in range(5):
        safe.tick(is_clean=True)

    assert safe.is_active() is False, "SafeMode should have exited after 5 clean ticks"


# ---------------------------------------------------------------------------
# 7. sklearn missing → no crash
# ---------------------------------------------------------------------------


def test_isolation_forest_fallback():
    """When sklearn is absent, AnomalyDetector returns a valid (non-crashing) result."""
    # Temporarily hide sklearn from imports
    real_sklearn = sys.modules.get("sklearn")
    real_sklearn_ensemble = sys.modules.get("sklearn.ensemble")

    # Insert a None sentinel so "import sklearn" fails gracefully
    sys.modules["sklearn"] = None  # type: ignore[assignment]
    sys.modules["sklearn.ensemble"] = None  # type: ignore[assignment]

    try:
        # Reload detector so it re-evaluates the import
        if "ai_engine.a2_anomaly.detector" in sys.modules:
            del sys.modules["ai_engine.a2_anomaly.detector"]

        from ai_engine.a2_anomaly.detector import AnomalyDetector
        from ai_engine.config import load_ai_config

        cfg = load_ai_config(None)
        cfg.a2_anomaly.isolation_forest.enabled = True
        detector = AnomalyDetector(cfg.a2_anomaly, db_path=":memory:")

        result = detector.check(_make_snapshot())
        # Must not crash; must return an AnomalyResult
        assert hasattr(result, "ok")
        assert hasattr(result, "severity")
    finally:
        # Restore sklearn
        if real_sklearn is not None:
            sys.modules["sklearn"] = real_sklearn
        else:
            sys.modules.pop("sklearn", None)
        if real_sklearn_ensemble is not None:
            sys.modules["sklearn.ensemble"] = real_sklearn_ensemble
        else:
            sys.modules.pop("sklearn.ensemble", None)
        # Force re-import with real sklearn
        sys.modules.pop("ai_engine.a2_anomaly.detector", None)


# ---------------------------------------------------------------------------
# 8. Alert deduplication
# ---------------------------------------------------------------------------


def test_alert_dispatcher_dedup():
    """Same alert key dispatched twice within 5 min fires only once."""
    from ai_engine.a2_anomaly.alerts import AlertDispatcher

    dispatcher = AlertDispatcher(dedup_window_s=300)  # 5-minute dedup window
    fired: list[str] = []

    def _fake_send(msg: str) -> None:
        fired.append(msg)

    dispatcher.register_handler(_fake_send)

    dispatcher.dispatch("CTR_SPIKE", "CTR exceeded threshold: 0.09")
    dispatcher.dispatch("CTR_SPIKE", "CTR exceeded threshold: 0.09")  # duplicate

    assert len(fired) == 1, (
        f"Expected 1 alert fired (dedup), got {len(fired)}"
    )
