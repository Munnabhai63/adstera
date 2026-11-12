"""End-to-end integration tests for Phase 4 (SQLite -> CalibrationMonitor -> Phase 4 Dashboard HTTP)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterator, Tuple

import httpx
import pytest

from admin_ui.phase4_data import Phase4DashboardConfig, load_phase4_config
from admin_ui.phase4_server import create_phase4_server
from phase3.calibration.monitor import CalibrationMonitor, load_calibration_config
from phase3.db.migrations.runner import apply_migrations


def _seed_phase3_db(db_path: Path) -> dict:
    """Apply canonical Phase 3 migrations and seed deterministic multi-table rows."""
    apply_migrations(db_path)

    now = time.time()
    base_day_ts = now - 7 * 86400.0

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. p3_farm_devices (2 healthy, 1 quarantined)
        devices = [
            ("dev-pixel-01", "1-1.1", 9222, 8765, "healthy", 0, 0.0, 12, 2, now - 30),
            ("dev-pixel-02", "1-1.2", 9223, 8766, "healthy", 0, 0.0, 8, 1, now - 45),
            ("dev-pixel-03", "1-1.3", 9224, 8767, "quarantined", 3, now + 1800, 4, 0, now - 300),
        ]
        conn.executemany(
            """
            INSERT INTO p3_farm_devices (
                device_id, usb_port, cdp_port, b1_port, status,
                consecutive_failures, quarantined_until, total_sessions,
                total_clicks, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            devices,
        )

        # 2. p3_cgnat_slots (1 active slot on dev-pixel-01, 2 released slots sharing a /24 subnet)
        slots = [
            ("dev-pixel-01", "100.64.10.21", "100.64.10.0/24", "100.64.0.0/20", 1, now - 120, None),
            ("dev-pixel-02", "100.64.20.11", "100.64.20.0/24", "100.64.16.0/20", 0, now - 3600, now - 3000),
            ("dev-pixel-03", "100.64.20.44", "100.64.20.0/24", "100.64.16.0/20", 0, now - 1800, now - 1200),
        ]
        conn.executemany(
            """
            INSERT INTO p3_cgnat_slots (
                device_id, ip_address, subnet_24, subnet_20, active, acquired_at, released_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            slots,
        )

        # 3. p3_sessions (2 completed, 1 failed, 1 collision-blocked)
        sessions = [
            ("sess-001", "corr-1", "dev-pixel-01", "paper", "example.com", "100.64.10.21", "100.64.10.0/24", "100.64.0.0/20", "completed", now - 600, now - 540, 60.0, ""),
            ("sess-002", "corr-2", "dev-pixel-02", "paper", "example.com", "100.64.20.11", "100.64.20.0/24", "100.64.16.0/20", "completed", now - 500, now - 455, 45.0, ""),
            ("sess-003", "corr-3", "dev-pixel-03", "paper", "example.com", "100.64.20.44", "100.64.20.0/24", "100.64.16.0/20", "failed", now - 400, now - 390, 10.0, "timeout"),
            ("sess-004", "corr-4", "dev-pixel-02", "paper", "example.com", "100.64.20.44", "100.64.20.0/24", "100.64.16.0/20", "blocked", now - 300, now - 299, 0.0, "cgnat collision prevented"),
        ]
        conn.executemany(
            """
            INSERT INTO p3_sessions (
                session_id, correlation_id, device_id, mode, domain, ip_address,
                subnet_24, subnet_20, status, started_at, ended_at, dwell_seconds, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sessions,
        )

        # 4. p3_forecasts & p3_decisions_rewards across 6 distinct days in rolling window
        # 5 days inside [8.0, 12.0] and 1 day at 13.0 -> 5/6 = 83.33% coverage (calibrated)
        daily_actuals = [10.0, 9.5, 11.0, 8.5, 10.5, 13.0]
        for idx, actual_rev in enumerate(daily_actuals):
            day_ts = base_day_ts + idx * 86400.0
            conn.execute(
                """
                INSERT INTO p3_forecasts (
                    horizon_days, sample_count, method,
                    p10_revenue, p50_revenue, p90_revenue,
                    p10_ecpm, p50_ecpm, p90_ecpm, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 30, "irls_quantile", 8.0, 10.0, 12.0, 4.0, 5.0, 6.0, day_ts),
            )
            conn.execute(
                """
                INSERT INTO p3_decisions_rewards (
                    session_id, correlation_id, device_id, domain, slot_type,
                    action, executed_touch, bbox_json, a4_source, a4_confidence,
                    a2_severity, safe_mode, rpm, ctr, reward_value, reason, ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"sess-day-{idx}",
                    f"corr-day-{idx}",
                    "dev-pixel-01",
                    "example.com",
                    "banner",
                    "paper_click" if idx % 2 == 0 else "skip",
                    0,
                    "null",
                    "yolo",
                    0.92,
                    "OK",
                    0,
                    actual_rev * 1000.0,
                    0.04,
                    actual_rev,
                    "cgnat_verified" if idx == 0 else "normal_policy",
                    day_ts + 60.0,
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "total_sessions": 4,
        "completed_sessions": 2,
        "failed_sessions": 1,
        "active_devices": 2,
        "healthy_farm_devices": 2,
        "quarantined_devices": 1,
        "total_farm_devices": 3,
        "active_cgnat_slots": 1,
        "total_clicks": 3,
        "expected_actual_revenue": sum(daily_actuals),
        # 1 session collision block + 1 decision reason mentioning cgnat + 1 repeated /24 subnet hit (3 slots - 2 distinct)
        "ip_collisions_prevented": 3,
    }


def _start_ephemeral_server(
    cfg: Phase4DashboardConfig,
) -> Tuple[str, object, threading.Thread]:
    server = create_phase4_server(config=cfg, host="127.0.0.1", port=0)
    bound_host, bound_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://{bound_host}:{bound_port}", server, thread


def test_phase4_end_to_end_live_db_calibration_and_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed SQLite, run CalibrationMonitor, boot Phase 4 HTTP server, and verify live HTML + JSON."""
    db_path = tmp_path / "phase3.db"
    missing_legacy_db = tmp_path / "missing_sessions.db"
    safe_mode_path = tmp_path / "safe_mode.json"
    safe_mode_path.write_text(
        json.dumps(
            {
                "active": True,
                "entry_reason": "e2e_anomaly_check",
                "clean_window_count": 2,
                "entry_ts": 1700000100.0,
            }
        ),
        encoding="utf-8",
    )

    expected = _seed_phase3_db(db_path)

    # Clear alert env vars so no external network call occurs
    for env_key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "PHASE3_ALERT_WEBHOOK_URL"):
        monkeypatch.delenv(env_key, raising=False)

    # Verify env-driven configuration overrides
    monkeypatch.setenv("PHASE4_CALIBRATION_WINDOW_DAYS", "30")
    monkeypatch.setenv("PHASE4_DB_PATH", str(db_path))
    monkeypatch.setenv("PHASE4_LEGACY_DB_PATH", str(missing_legacy_db))
    monkeypatch.setenv("PHASE4_SAFE_MODE_PATH", str(safe_mode_path))
    monkeypatch.setenv("PHASE4_DASHBOARD_PORT", "0")

    cal_cfg = load_calibration_config()
    assert cal_cfg.rolling_window_days == 30
    assert cal_cfg.db_path == str(db_path)

    monitor = CalibrationMonitor(cal_cfg)
    cal_report = monitor.run_check()
    assert cal_report["status"] == "ok"
    assert cal_report["persisted"] is True
    assert cal_report["a3_matched_days"] == 6
    assert cal_report["coverage_pct"] == pytest.approx(5.0 / 6.0, rel=1e-4)
    assert cal_report["a3_drift_detected"] is False

    dash_cfg = load_phase4_config()
    assert dash_cfg.port == 0
    assert dash_cfg.phase3_db_path == str(db_path)

    base_url, server, thread = _start_ephemeral_server(dash_cfg)
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            # 1. Fetch HTML page
            page_resp = client.get("/")
            assert page_resp.status_code == 200
            assert "text/html" in page_resp.headers["content-type"]
            html = page_resp.text
            assert "AdsterraFleet" in html
            assert "/crm-assets/js/crm-phase4.js" in html
            assert "p4KpiSessions" in html
            assert "p4TableCalibration" in html

            # 2. Fetch static JS asset and verify no innerHTML XSS sink
            js_resp = client.get("/crm-assets/js/crm-phase4.js")
            assert js_resp.status_code == 200
            assert "innerHTML" not in js_resp.text

            # 3. Fetch live dashboard JSON API
            api_resp = client.get("/api/phase4/dashboard")
            assert api_resp.status_code == 200
            payload = api_resp.json()

            assert payload["ok"] is True
            assert payload["db_status"] == "ok"
            assert payload["error"] == ""

            kpis = payload["kpis"]
            assert kpis["total_sessions"] == expected["total_sessions"]
            assert kpis["completed_sessions"] == expected["completed_sessions"]
            assert kpis["failed_sessions"] == expected["failed_sessions"]
            assert kpis["active_devices"] == expected["active_devices"]
            assert kpis["healthy_farm_devices"] == expected["healthy_farm_devices"]
            assert kpis["quarantined_devices"] == expected["quarantined_devices"]
            assert kpis["total_farm_devices"] == expected["total_farm_devices"]
            assert kpis["active_cgnat_slots"] == expected["active_cgnat_slots"]
            assert kpis["total_clicks"] == expected["total_clicks"]
            assert kpis["ip_collisions_prevented"] == expected["ip_collisions_prevented"]

            fva = kpis["p50_forecast_vs_actual"]
            assert fva["p10_revenue"] == pytest.approx(8.0)
            assert fva["p50_revenue"] == pytest.approx(10.0)
            assert fva["p90_revenue"] == pytest.approx(12.0)
            assert fva["actual_revenue"] == pytest.approx(expected["expected_actual_revenue"])

            assert kpis["safe_mode"]["active"] is True
            assert kpis["safe_mode"]["reason"] == "e2e_anomaly_check"
            assert kpis["safe_mode"]["clean_windows"] == 2

            # Verify live table rows match seeded SQLite records
            assert len(payload["sessions"]) == 4
            assert {r["session_id"] for r in payload["sessions"]} == {
                "sess-001",
                "sess-002",
                "sess-003",
                "sess-004",
            }
            assert len(payload["cgnat_slots"]) == 3
            assert len(payload["forecasts"]) == 6
            assert len(payload["farm_devices"]) == 3
            assert {r["device_id"] for r in payload["farm_devices"]} == {
                "dev-pixel-01",
                "dev-pixel-02",
                "dev-pixel-03",
            }

            # Verify calibration report generated by CalibrationMonitor appears in API payload
            assert len(payload["calibration_reports"]) == 1
            cal_row = payload["calibration_reports"][0]
            assert cal_row["status"] == "ok"
            assert cal_row["a3_matched_days"] == 6
            assert cal_row["a3_coverage_pct"] == pytest.approx(5.0 / 6.0, rel=1e-4)

            # 4. Health endpoint
            health_resp = client.get("/api/phase4/health")
            assert health_resp.status_code == 200
            health = health_resp.json()
            assert health["ok"] is True
            assert health["db_ok"] is True
            assert health["safe_mode_active"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)


def test_phase4_e2e_missing_db_graceful_degradation(tmp_path: Path) -> None:
    """Dashboard HTTP server must degrade gracefully when phase3.db does not exist."""
    missing_db = tmp_path / "does_not_exist.db"
    cfg = Phase4DashboardConfig(
        host="127.0.0.1",
        port=0,
        phase3_db_path=str(missing_db),
        safe_mode_path=str(tmp_path / "missing_safe_mode.json"),
        legacy_db_path=str(tmp_path / "missing_legacy.db"),
    )

    base_url, server, thread = _start_ephemeral_server(cfg)
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            page_resp = client.get("/")
            assert page_resp.status_code == 200
            assert "p4DbErrorBanner" in page_resp.text

            api_resp = client.get("/api/phase4/dashboard")
            assert api_resp.status_code == 503
            payload = api_resp.json()
            assert payload["ok"] is False
            assert payload["db_status"] == "missing"
            assert "not found" in payload["error"].lower()
            assert payload["kpis"]["total_sessions"] == 0
            assert payload["sessions"] == []
            assert payload["farm_devices"] == []
            assert payload["calibration_reports"] == []

            health_resp = client.get("/api/phase4/health")
            assert health_resp.status_code == 503
            health = health_resp.json()
            assert health["ok"] is False
            assert health["db_ok"] is False
            assert health["db_status"] == "missing"

            # Path traversal on /crm-assets/ must be rejected cleanly
            trav_resp = client.get("/crm-assets/../../phase4_config.yaml")
            assert trav_resp.status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)
