"""
tests/test_anomaly_detector.py — Acceptance & Invariant Tests for Step 7.3:
Multi-Metric Statistical Anomaly Detection & Circuit Breaker Engine.
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path
from anomaly_detector import AnomalyDetector, AnomalyReport
import db

TEST_DB = Path("test_anomaly.db")


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    if TEST_DB.exists():
        TEST_DB.unlink()
    monkeypatch.setattr(db, "_DB_PATH", TEST_DB)
    db.init()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_z_score_calculation():
    """Verify statistical Z-score calculations with standard and edge conditions."""
    # Normal case: value=5.5, mean=3.5, std=1.0 -> z = 2.0
    z = AnomalyDetector.calculate_z_score(value=5.5, mean=3.5, std=1.0)
    assert z == 2.0

    # Negative deviation: value=1.5, mean=3.5, std=1.0 -> z = -2.0
    z_neg = AnomalyDetector.calculate_z_score(value=1.5, mean=3.5, std=1.0)
    assert z_neg == -2.0

    # Zero variance edge-case: value == mean -> z = 0.0
    z_zero = AnomalyDetector.calculate_z_score(value=3.5, mean=3.5, std=0.0)
    assert z_zero == 0.0

    # Zero variance with disparity
    z_high = AnomalyDetector.calculate_z_score(value=6.0, mean=3.5, std=0.0)
    assert z_high == 3.0


def test_baseline_and_window_evaluation():
    """Verify baseline calculation and recent window metrics aggregation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "circuit_breaker.json"
        detector = AnomalyDetector(state_file=state_file)

        # Seed database sessions
        with db._conn() as con:
            for _ in range(10):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'loanraaj.com', 'Mozilla/5.0 Chrome/120', 45.0, 2, 0, 'ok', datetime('now'))
                    """
                )
            # Add 2 sessions with clicks
            for _ in range(2):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'loanraaj.com', 'Mozilla/5.0 Chrome/120', 50.0, 2, 1, 'ok', datetime('now'))
                    """
                )

        metrics = detector.evaluate_recent_window(domain="loanraaj.com", window=20)
        assert metrics["total_sessions"] == 12
        assert metrics["impressions"] == 24
        assert metrics["ad_clicks"] == 2
        # CTR = 2 / 24 * 100 = 8.33%
        assert 8.0 <= metrics["ctr"] <= 8.5
        assert metrics["degraded_rate"] == 0.0
        assert metrics["avg_dwell"] > 40.0


def test_ctr_spike_anomaly_triggers_pause_clicks():
    """Verify elevated CTR triggers CRITICAL anomaly and PAUSE_CLICKS action."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "circuit_breaker.json"
        detector = AnomalyDetector(state_file=state_file, max_ctr_pct=5.0)

        # Seed 10 sessions with 5 ad clicks -> 50% CTR (huge breach!)
        with db._conn() as con:
            for _ in range(10):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'tazaloan.com', 'Mozilla/5.0 Chrome/120', 40.0, 1, 1, 'ok', datetime('now'))
                    """
                )

        anomalies = detector.detect_anomalies(domain="tazaloan.com", window=10)
        assert len(anomalies) >= 1

        ctr_anom = next((a for a in anomalies if a.metric == "ctr"), None)
        assert ctr_anom is not None
        assert ctr_anom.severity == "CRITICAL"
        assert ctr_anom.action == "PAUSE_CLICKS"

        # Apply circuit breaker
        result = detector.apply_circuit_breaker(anomalies, notify_telegram=False)
        assert result["actions_taken"] >= 1

        # Verify domain is paused
        is_paused, action, reason = detector.is_domain_paused("tazaloan.com")
        assert is_paused is True
        assert action == "PAUSE_CLICKS"
        assert "breached maximum safety ceiling" in reason


def test_degraded_session_spike_detection():
    """Verify spike in failed/degraded sessions triggers anomaly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "circuit_breaker.json"
        detector = AnomalyDetector(state_file=state_file, degraded_max_pct=30.0)

        # Seed 10 sessions with 6 degraded
        with db._conn() as con:
            for _ in range(4):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'karzseva.com', 'Mozilla/5.0 Chrome/120', 35.0, 2, 0, 'ok', datetime('now'))
                    """
                )
            for _ in range(6):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'karzseva.com', 'Mozilla/5.0 Chrome/120', 25.0, 0, 0, 'degraded', datetime('now'))
                    """
                )

        anomalies = detector.detect_anomalies(domain="karzseva.com", window=10)
        deg_anom = next((a for a in anomalies if a.metric == "degraded_rate"), None)
        assert deg_anom is not None
        assert deg_anom.observed_value == 60.0  # 6/10 = 60%
        assert deg_anom.severity == "CRITICAL"


def test_dwell_collapse_anti_detect_breach():
    """Verify dwell time collapse below 20s invariant triggers critical anomaly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "circuit_breaker.json"
        detector = AnomalyDetector(state_file=state_file)

        # Seed sessions with average dwell 12.0s
        with db._conn() as con:
            for _ in range(8):
                con.execute(
                    """
                    INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
                    VALUES ('1.2.3.4:8080', 'rechargetak.com', 'Mozilla/5.0 Chrome/120', 12.0, 1, 0, 'ok', datetime('now'))
                    """
                )

        anomalies = detector.detect_anomalies(domain="rechargetak.com", window=8)
        dwell_anom = next((a for a in anomalies if a.metric == "dwell"), None)
        assert dwell_anom is not None
        assert dwell_anom.severity == "CRITICAL"
        assert dwell_anom.observed_value == 12.0
        assert "below 20s anti-detect invariant" in dwell_anom.details


def test_circuit_breaker_resume_and_reset():
    """Verify manual resume of a specific domain and global reset_all."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "circuit_breaker.json"
        detector = AnomalyDetector(state_file=state_file)

        # Manually create anomalies and apply
        report = [
            AnomalyReport(
                metric="ctr",
                domain="loantau.com",
                observed_value=7.5,
                baseline_mean=3.5,
                baseline_std=0.8,
                z_score=5.0,
                severity="CRITICAL",
                action="PAUSE_CLICKS",
                details="Test CTR Spike",
            ),
            AnomalyReport(
                metric="degraded_rate",
                domain="tazarokda.com",
                observed_value=55.0,
                baseline_mean=5.0,
                baseline_std=2.0,
                z_score=25.0,
                severity="CRITICAL",
                action="PAUSE_DOMAIN",
                details="Test Failure Burst",
            ),
        ]
        detector.apply_circuit_breaker(report, notify_telegram=False)

        # Both domains should be paused
        assert detector.is_domain_paused("loantau.com")[0] is True
        assert detector.is_domain_paused("tazarokda.com")[0] is True
        assert detector.is_domain_paused("loanraaj.com")[0] is False

        # Resume loantau.com
        resumed = detector.resume_domain("loantau.com")
        assert resumed is True
        assert detector.is_domain_paused("loantau.com")[0] is False
        assert detector.is_domain_paused("tazarokda.com")[0] is True

        # Reset all
        detector.reset_all()
        assert detector.is_domain_paused("tazarokda.com")[0] is False
