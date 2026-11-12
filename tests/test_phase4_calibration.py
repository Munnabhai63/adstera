"""Deterministic unit & integration tests for Phase 4 Calibration & Drift Monitor."""
from __future__ import annotations

import asyncio
import datetime
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

from phase3.calibration import (
    CalibrationConfig,
    CalibrationMonitor,
    CalibrationService,
    load_calibration_config,
)
from phase3.calibration.service import main as service_main
from phase3.db.migrations.runner import Phase3Store


def _make_day(offset: int, base_date: datetime.date = datetime.date(2026, 10, 1)) -> str:
    return (base_date + datetime.timedelta(days=offset)).isoformat()


def _day_ts(offset_days_ago: int) -> float:
    now = time.time()
    return now - offset_days_ago * 86400.0


# ---------------------------------------------------------------------------
# 1. Config & Environment Overrides
# ---------------------------------------------------------------------------


def test_config_loads_defaults_and_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHASE4_CALIBRATION_WINDOW_DAYS", "14")
    monkeypatch.setenv("PHASE4_DB_PATH", "custom/phase3_custom.db")
    monkeypatch.setenv("PHASE4_LEGACY_DB_PATH", "custom/legacy.db")
    monkeypatch.setenv("PHASE4_CHECK_INTERVAL_SECONDS", "900")

    cfg = load_calibration_config()
    assert cfg.rolling_window_days == 14
    assert cfg.db_path == "custom/phase3_custom.db"
    assert cfg.legacy_db_path == "custom/legacy.db"
    assert cfg.check_interval_seconds == 900
    assert cfg.target_coverage == pytest.approx(0.80)
    assert cfg.min_acceptable_coverage == pytest.approx(0.65)
    assert cfg.max_acceptable_coverage == pytest.approx(0.95)
    assert cfg.alerts.telegram_token_env_var == "TELEGRAM_BOT_TOKEN"
    assert cfg.alerts.telegram_chat_id_env_var == "TELEGRAM_CHAT_ID"
    assert cfg.alerts.webhook_url_env_var == "PHASE3_ALERT_WEBHOOK_URL"


# ---------------------------------------------------------------------------
# 2. A3 Calibration: Well-Calibrated vs Miscalibrated / Shifted Forecasts
# ---------------------------------------------------------------------------


def test_a3_well_calibrated_30_day_forecasts_no_drift(tmp_path: Path) -> None:
    db_file = tmp_path / "phase3.db"
    Phase3Store(db_file)

    forecasts: List[Dict[str, Any]] = []
    actuals: List[Dict[str, Any]] = []
    # 30 days: 24 inside [8.0, 12.0] (80% coverage), 6 slightly outside
    for i in range(30):
        day = _make_day(i)
        forecasts.append({"date": day, "p10": 8.0, "p50": 10.0, "p90": 12.0})
        if i % 5 == 0:
            # 6 days outside: 3 below, 3 above -> symmetrical 0 bias
            act_val = 7.0 if (i % 10 == 0) else 13.0
        else:
            act_val = 10.0
        actuals.append({"date": day, "revenue": act_val})

    monitor = CalibrationMonitor(db_path=db_file)
    report = monitor.run_check(forecasts=forecasts, actuals=actuals)

    assert report["status"] == "ok"
    assert report["a3_matched_days"] == 30
    assert report["coverage_pct"] == pytest.approx(0.80, abs=1e-6)
    assert report["p50_mae"] == pytest.approx(0.60, abs=1e-6)
    assert report["p50_bias"] == pytest.approx(0.0, abs=1e-6)
    assert report["a3_drift_detected"] is False
    assert report["a3_retrain_recommended"] is False
    assert report["drift_detected"] is False
    assert report["persisted"] is True


def test_a3_shifted_low_coverage_triggers_drift_and_alerts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "phase3.db"
    Phase3Store(db_file)

    captured_requests: List[Dict[str, Any]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(
            {
                "url": str(request.url),
                "body": json.loads(request.content.decode("utf-8")),
            }
        )
        return httpx.Response(200, json={"ok": True})

    mock_client = httpx.Client(transport=httpx.MockTransport(_handler))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_tg_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("PHASE3_ALERT_WEBHOOK_URL", "https://alerts.example.local/hook")

    forecasts: List[Dict[str, Any]] = []
    actuals: List[Dict[str, Any]] = []
    # Shifted forecasts: only 6/30 (20%) inside [8, 12]; rest at 16.0
    for i in range(30):
        day = _make_day(i)
        forecasts.append({"date": day, "p10": 8.0, "p50": 10.0, "p90": 12.0})
        actuals.append({"date": day, "revenue": 10.0 if i < 6 else 16.0})

    monitor = CalibrationMonitor(db_path=db_file, http_client=mock_client)
    report = monitor.run_check(forecasts=forecasts, actuals=actuals)

    assert report["status"] == "drift_detected"
    assert report["a3_matched_days"] == 30
    assert report["coverage_pct"] == pytest.approx(0.20, abs=1e-6)
    assert report["p50_bias"] < 0.0  # forecast p50=10 < actual avg=14.8
    assert report["a3_drift_detected"] is True
    assert report["a3_retrain_recommended"] is True
    assert report["retrain_recommended"] is True
    assert report["alerts"]["dispatched"] is True
    assert report["alerts"]["telegram"] == "sent"
    assert report["alerts"]["webhook"] == "sent"
    assert len(captured_requests) == 2
    assert any("sendMessage" in r["url"] for r in captured_requests)
    assert any("alerts.example.local" in r["url"] for r in captured_requests)


def test_alerts_fail_safe_on_http_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "phase3.db"
    Phase3Store(db_file)

    def _failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network outage", request=request)

    mock_client = httpx.Client(transport=httpx.MockTransport(_failing_handler))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_tg_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("PHASE3_ALERT_WEBHOOK_URL", "https://alerts.example.local/hook")

    forecasts = [{"date": _make_day(i), "p10": 1.0, "p50": 2.0, "p90": 3.0} for i in range(10)]
    actuals = [{"date": _make_day(i), "revenue": 10.0} for i in range(10)]

    monitor = CalibrationMonitor(db_path=db_file, http_client=mock_client)
    report = monitor.run_check(forecasts=forecasts, actuals=actuals)

    assert report["status"] == "drift_detected"
    assert report["a3_drift_detected"] is True
    assert report["alerts"]["dispatched"] is False
    assert str(report["alerts"]["telegram"]).startswith("error:")
    assert str(report["alerts"]["webhook"]).startswith("error:")
    assert report["persisted"] is True


# ---------------------------------------------------------------------------
# 3. A5 RPM Drift Tests (explicit predicted + GammaPoissonRPMPredictor fallback)
# ---------------------------------------------------------------------------


def test_a5_rpm_calibrated_vs_drift(tmp_path: Path) -> None:
    db_file = tmp_path / "phase3.db"
    Phase3Store(db_file)
    monitor = CalibrationMonitor(db_path=db_file)

    # Calibrated RPM series (~5% error)
    good_rpm = [
        {"predicted_rpm": 2.10, "actual_rpm": 2.00},
        {"predicted_rpm": 1.95, "actual_rpm": 2.05},
        {"predicted_rpm": 2.40, "actual_rpm": 2.30},
        {"predicted_rpm": 1.85, "actual_rpm": 1.90},
        {"predicted_rpm": 2.20, "actual_rpm": 2.15},
        {"predicted_rpm": 2.05, "actual_rpm": 2.00},
    ]
    ok_report = monitor.run_check(rpm_records=good_rpm)
    assert ok_report["status"] == "ok"
    assert ok_report["a5_sample_count"] == 6
    assert ok_report["a5_mape"] < 0.10
    assert abs(ok_report["a5_bias"]) < 0.10
    assert ok_report["a5_drift_detected"] is False
    assert ok_report["a5_retrain_recommended"] is False

    # Drifted RPM series using GammaPoissonRPMPredictor raw features (high historical_ecpm vs low actual_rpm)
    drifted_rpm = [
        {
            "historical_ecpm": 5.00,
            "adsterra_impressions": 5000,
            "adsterra_revenue": 25.0,
            "gsc_impressions": 1000,
            "gsc_ctr": 0.04,
            "gsc_position": 2.0,
            "actual_rpm": 1.20,
        }
        for _ in range(6)
    ]
    drift_report = monitor.run_check(rpm_records=drifted_rpm)
    assert drift_report["status"] == "drift_detected"
    assert drift_report["a5_sample_count"] == 6
    assert drift_report["a5_mape"] > 0.35
    assert drift_report["a5_bias"] > 0.30
    assert drift_report["a5_drift_detected"] is True
    assert drift_report["a5_retrain_recommended"] is True


# ---------------------------------------------------------------------------
# 4. Missing / Locked / Empty DB Fail-Safe Tests
# ---------------------------------------------------------------------------


def test_missing_db_degrades_gracefully(tmp_path: Path) -> None:
    missing_db = tmp_path / "does_not_exist.db"
    monitor = CalibrationMonitor(
        db_path=missing_db,
        legacy_db_path=tmp_path / "missing_legacy.db",
    )
    report = monitor.run_check()

    assert report["status"] == "degraded"
    assert "database_not_found" in report["error"]
    assert report["persisted"] is False
    assert not missing_db.exists()


def test_locked_db_degrades_gracefully(tmp_path: Path) -> None:
    locked_db = tmp_path / "locked.db"
    Phase3Store(locked_db)

    cfg = CalibrationConfig(
        db_path=str(locked_db),
        legacy_db_path=str(tmp_path / "none.db"),
        db_timeout_seconds=0.2,
    )
    monitor = CalibrationMonitor(cfg)

    # Hold an exclusive write lock on locked_db from another connection
    blocker = sqlite3.connect(str(locked_db), isolation_level=None)
    try:
        blocker.execute("BEGIN EXCLUSIVE;")
        report = monitor.run_check()
    finally:
        blocker.execute("ROLLBACK;")
        blocker.close()

    assert report["status"] == "degraded"
    assert "locked" in report["error"].lower() or "sqlite_error" in report["error"]
    assert report["persisted"] is False


def test_empty_history_returns_insufficient_data_and_persists(tmp_path: Path) -> None:
    db_file = tmp_path / "empty_phase3.db"
    Phase3Store(db_file)

    monitor = CalibrationMonitor(db_path=db_file, legacy_db_path=tmp_path / "none.db")
    report = monitor.run_check()

    assert report["status"] == "insufficient_data"
    assert report["a3_matched_days"] == 0
    assert report["a5_sample_count"] == 0
    assert report["a3_drift_detected"] is False
    assert report["a5_drift_detected"] is False
    assert report["persisted"] is True


# ---------------------------------------------------------------------------
# 5. SQLite End-to-End Persistence Test (p3_forecasts + p3_decisions_rewards)
# ---------------------------------------------------------------------------


def test_sqlite_overcoverage_triggers_drift_on_decisions_rewards_only(tmp_path: Path) -> None:
    db_file = tmp_path / "phase3_overcov.db"
    store = Phase3Store(db_file)

    # Seed 10 days of A3 forecasts (horizon=1) and matching realized rewards in p3_decisions_rewards
    for d_ago in range(10, 0, -1):
        ts = _day_ts(d_ago)
        store.log_forecast(
            horizon_days=1,
            sample_count=14,
            method="irls_quantile",
            p10_revenue=2.0,
            p50_revenue=10.0,
            p90_revenue=20.0,
            p10_ecpm=0.5,
            p50_ecpm=2.0,
            p90_ecpm=4.0,
            created_at=ts,
        )
        for j in range(5):
            store.log_decision_reward(
                session_id=f"s_{d_ago}_{j}",
                correlation_id=f"c_{d_ago}_{j}",
                device_id="dev_1",
                domain="example.com",
                slot_type="banner",
                action="paper_click" if j == 0 else "skip",
                executed_touch=False,
                bbox=(10, 20, 300, 50),
                a4_source="dom",
                a4_confidence=0.95,
                a2_severity="OK",
                safe_mode=False,
                rpm=2.0,
                ctr=0.03,
                reward_value=2.0,
                reason="test",
                ts=ts + j * 10.0,
            )

    monitor = CalibrationMonitor(db_path=db_file, legacy_db_path=tmp_path / "none.db")
    report = monitor.run_check()

    # 100% coverage (10/10) exceeds max_acceptable_coverage (0.95) -> over-wide bands flagged
    assert report["a3_matched_days"] == 10
    assert report["coverage_pct"] == pytest.approx(1.0)
    assert report["a3_drift_detected"] is True
    assert report["a3_retrain_recommended"] is True
    assert report["status"] == "drift_detected"
    assert report["persisted"] is True


def test_sqlite_end_to_end_calibrated_persists_row(tmp_path: Path) -> None:
    db_file = tmp_path / "phase3_calibrated.db"
    store = Phase3Store(db_file)

    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS adsterra_api_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                date TEXT NOT NULL,
                api_impressions INTEGER NOT NULL,
                api_clicks INTEGER NOT NULL,
                api_ctr REAL NOT NULL,
                api_cpm REAL NOT NULL,
                api_revenue REAL NOT NULL,
                local_impressions INTEGER NOT NULL,
                discrepancy_pct REAL NOT NULL,
                synced_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

    for idx, d_ago in enumerate(range(10, 0, -1)):
        ts = _day_ts(d_ago)
        day_str = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()
        store.log_forecast(
            horizon_days=1,
            sample_count=14,
            method="irls_quantile",
            p10_revenue=8.0,
            p50_revenue=10.0,
            p90_revenue=12.0,
            p10_ecpm=1.6,
            p50_ecpm=2.0,
            p90_ecpm=2.4,
            created_at=ts,
        )
        store.log_decision_reward(
            session_id=f"s_{d_ago}",
            correlation_id=f"c_{d_ago}",
            device_id="dev_1",
            domain="example.com",
            slot_type="banner",
            action="skip",
            executed_touch=False,
            bbox=None,
            a4_source="dom",
            a4_confidence=0.95,
            a2_severity="OK",
            safe_mode=False,
            rpm=2.0,
            ctr=0.03,
            reward_value=0.0,
            reason="test",
            ts=ts,
        )
        # 8/10 days inside [8, 12], 2/10 outside (7.0 and 13.0) -> 80% coverage!
        rev = 7.0 if idx == 0 else (13.0 if idx == 1 else 10.0)
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO adsterra_api_sync
                (domain, date, api_impressions, api_clicks, api_ctr, api_cpm, api_revenue, local_impressions, discrepancy_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("example.com", day_str, 5000, 150, 3.0, 2.0, rev, 5000, 0.0),
            )

    monitor = CalibrationMonitor(db_path=db_file, legacy_db_path=tmp_path / "none.db")
    report = monitor.run_check()

    assert report["status"] == "ok"
    assert report["a3_matched_days"] == 10
    assert report["coverage_pct"] == pytest.approx(0.80)
    assert report["a5_sample_count"] == 10
    assert report["a5_mape"] == pytest.approx(0.0)
    assert report["persisted"] is True

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM p3_calibration_reports").fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["status"] == "ok"
        assert row["a3_matched_days"] == 10
        assert row["a3_coverage_pct"] == pytest.approx(0.80)
        assert row["a5_sample_count"] == 10
        assert row["a5_mape"] == pytest.approx(0.0)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 6. Service & CLI --once Smoke Test
# ---------------------------------------------------------------------------


def test_cli_once_smoke_in_process_and_subprocess(tmp_path: Path) -> None:
    db_file = tmp_path / "cli_phase3.db"
    Phase3Store(db_file)

    rc = service_main(["--once", "--db-path", str(db_file)])
    assert rc == 0

    proc = subprocess.run(
        [sys.executable, "-m", "phase3.calibration.service", "--once", "--db-path", str(db_file)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "Expected JSON output on stdout from --once"
    parsed = json.loads(lines[-1])
    assert parsed["status"] == "insufficient_data"
    assert parsed["persisted"] is True


def test_service_async_loop_stops_cleanly(tmp_path: Path) -> None:
    db_file = tmp_path / "svc_phase3.db"
    Phase3Store(db_file)

    svc = CalibrationService(db_path=db_file, interval_seconds=60)

    async def _runner() -> List[Dict[str, Any]]:
        task = asyncio.create_task(svc.run_forever())
        await asyncio.sleep(0.05)
        svc.stop()
        return await asyncio.wait_for(task, timeout=2.0)

    reports = asyncio.run(_runner())
    assert len(reports) == 1
    assert reports[0]["status"] == "insufficient_data"


def test_adsterra_dotenv_autoload_respects_pytest_guard_and_explicit_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from phase3.adapters.adsterra_feed import AdsterraFeedAdapter, load_dotenv_into_environ

    env_file = tmp_path / ".env"
    env_file.write_text('ADSTERRA_API_KEY="unit_test_secret_key_999"\n', encoding="utf-8")
    monkeypatch.delenv("ADSTERRA_API_KEY", raising=False)

    # Under PYTEST_CURRENT_TEST, default auto-load stays disabled unless force=True
    loaded_default = load_dotenv_into_environ(env_file)
    assert loaded_default == {}

    # Explicit force=True loads from env_file without overwriting existing env vars
    loaded_forced = load_dotenv_into_environ(env_file, force=True)
    assert loaded_forced["ADSTERRA_API_KEY"] == "unit_test_secret_key_999"

    monkeypatch.setenv("ADSTERRA_API_KEY", "explicit_override_key")
    load_dotenv_into_environ(env_file, force=True)
    feed = AdsterraFeedAdapter(auto_load_env=True, env_path=env_file)
    assert feed.cfg.resolve_env_secret("ADSTERRA_API_KEY") == "explicit_override_key"

