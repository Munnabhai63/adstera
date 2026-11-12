"""Tests for Phase 4 Vuexy Dashboard (config, reader, server, DOM XSS safety)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from admin_ui.phase4_data import (
    Phase4DashboardConfig,
    Phase4DashboardReader,
    load_phase4_config,
)
from admin_ui.phase4_server import create_phase4_server
from phase3.db.migrations.runner import Phase3Store


def _http_get(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Content-Type", ""), err.read()


def _seed_phase3_db(tmp_path: Path) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "phase3.db"
    safe_path = tmp_path / "safe_mode.json"
    legacy_path = tmp_path / "missing_legacy.db"

    store = Phase3Store(db_path)
    now = time.time()

    store.upsert_farm_device(
        device_id="dev-pixel-1",
        usb_port="port_1",
        cdp_port=9222,
        b1_port=9320,
        status="healthy",
        total_sessions=12,
        total_clicks=2,
        last_seen_at=now,
    )
    store.upsert_farm_device(
        device_id="dev-pixel-2",
        usb_port="port_2",
        cdp_port=9223,
        b1_port=9321,
        status="healthy",
        total_sessions=8,
        total_clicks=1,
        last_seen_at=now - 10,
    )
    store.upsert_farm_device(
        device_id="dev-pixel-3",
        usb_port="port_3",
        cdp_port=9224,
        b1_port=9322,
        status="quarantined",
        consecutive_failures=3,
        quarantined_until=now + 300,
        total_sessions=4,
        total_clicks=0,
        last_seen_at=now - 60,
    )

    store.start_session(
        session_id="sess-001",
        correlation_id="p3_001",
        device_id="dev-pixel-1",
        mode="paper",
        domain="loanraaj.com",
        ip_address="100.64.10.22",
        subnet_24="100.64.10.0/24",
        subnet_20="100.64.0.0/20",
        started_at=now - 120,
    )
    store.finish_session("sess-001", status="completed", dwell_seconds=45.0, ended_at=now - 75)

    store.start_session(
        session_id="sess-002",
        correlation_id="p3_002",
        device_id="dev-pixel-2",
        mode="paper",
        domain="tazaloan.com",
        ip_address="100.64.20.15",
        subnet_24="100.64.20.0/24",
        subnet_20="100.64.16.0/20",
        started_at=now - 60,
    )
    store.finish_session("sess-002", status="completed", dwell_seconds=38.5, ended_at=now - 20)

    store.start_session(
        session_id="sess-003",
        correlation_id="p3_003",
        device_id="dev-pixel-3",
        mode="paper",
        domain="loanraaj.com",
        ip_address="100.64.10.29",
        subnet_24="100.64.10.0/24",
        subnet_20="100.64.0.0/20",
        started_at=now - 15,
    )
    store.finish_session(
        "sess-003",
        status="blocked_cgnat",
        dwell_seconds=0.0,
        error="cgnat subnet collision prevented",
        ended_at=now - 14,
    )

    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO p3_cgnat_slots (device_id, ip_address, subnet_24, subnet_20, active, acquired_at, released_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("dev-pixel-1", "100.64.10.22", "100.64.10.0/24", "100.64.0.0/20", 1, now - 10, None),
        )
        conn.execute(
            """
            INSERT INTO p3_cgnat_slots (device_id, ip_address, subnet_24, subnet_20, active, acquired_at, released_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("dev-pixel-2", "100.64.10.18", "100.64.10.0/24", "100.64.0.0/20", 0, now - 500, now - 400),
        )
        conn.execute(
            """
            INSERT INTO p3_cgnat_slots (device_id, ip_address, subnet_24, subnet_20, active, acquired_at, released_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("dev-pixel-2", "100.64.20.15", "100.64.20.0/24", "100.64.16.0/20", 0, now - 300, now - 200),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS p3_calibration_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                window_days INTEGER NOT NULL DEFAULT 30,
                a3_coverage_pct REAL DEFAULT NULL,
                a3_p50_mae REAL DEFAULT NULL,
                a5_mape REAL DEFAULT NULL,
                a3_drift_detected INTEGER NOT NULL DEFAULT 0,
                a5_drift_detected INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO p3_calibration_reports
            (status, window_days, a3_coverage_pct, a3_p50_mae, a5_mape, a3_drift_detected, a5_drift_detected, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ok", 30, 0.82, 0.41, 0.12, 0, 0, now),
        )

    store.log_decision_reward(
        session_id="sess-001",
        correlation_id="p3_001",
        device_id="dev-pixel-1",
        domain="loanraaj.com",
        slot_type="banner_300x250",
        action="paper_click",
        executed_touch=False,
        bbox=(10, 20, 310, 270),
        a4_source="dom",
        a4_confidence=0.95,
        a2_severity="OK",
        safe_mode=False,
        rpm=1.25,
        ctr=0.025,
        reward_value=7.50,
        reason="paper click",
        ts=now - 80,
    )
    store.log_decision_reward(
        session_id="sess-002",
        correlation_id="p3_002",
        device_id="dev-pixel-2",
        domain="tazaloan.com",
        slot_type="native",
        action="skip",
        executed_touch=False,
        bbox=None,
        a4_source="none",
        a4_confidence=0.0,
        a2_severity="OK",
        safe_mode=False,
        rpm=1.10,
        ctr=0.020,
        reward_value=5.00,
        reason="skip dwell",
        ts=now - 25,
    )

    store.log_forecast(
        horizon_days=7,
        sample_count=14,
        method="irls_quantile",
        p10_revenue=8.0,
        p50_revenue=15.0,
        p90_revenue=24.0,
        p10_ecpm=0.40,
        p50_ecpm=0.75,
        p90_ecpm=1.20,
        created_at=now,
    )

    safe_path.write_text(
        json.dumps(
            {
                "active": True,
                "entry_reason": "A2 CRITICAL: CTR spike",
                "entry_ts": now - 30,
                "clean_window_count": 2,
            }
        ),
        encoding="utf-8",
    )

    return db_path, safe_path, legacy_path


def test_config_loads_yaml_and_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    base_cfg = load_phase4_config()
    assert base_cfg.port == 5054
    assert base_cfg.phase3_db_path == "state/phase3/phase3.db"
    assert base_cfg.safe_mode_path == "state/phase3/ai_engine/safe_mode.json"

    monkeypatch.setenv("PHASE4_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("PHASE4_DASHBOARD_PORT", "5599")
    monkeypatch.setenv("PHASE4_DB_PATH", "/tmp/custom_p3.db")
    monkeypatch.setenv("PHASE4_SAFE_MODE_PATH", "/tmp/custom_safe.json")
    monkeypatch.setenv("PHASE4_LEGACY_DB_PATH", "/tmp/custom_legacy.db")

    override_cfg = load_phase4_config()
    assert override_cfg.host == "0.0.0.0"
    assert override_cfg.port == 5599
    assert override_cfg.phase3_db_path == "/tmp/custom_p3.db"
    assert override_cfg.safe_mode_path == "/tmp/custom_safe.json"
    assert override_cfg.legacy_db_path == "/tmp/custom_legacy.db"


def test_seeded_db_kpis_and_tables(tmp_path: Path) -> None:
    db_path, safe_path, legacy_path = _seed_phase3_db(tmp_path)
    cfg = Phase4DashboardConfig(
        phase3_db_path=str(db_path),
        safe_mode_path=str(safe_path),
        legacy_db_path=str(legacy_path),
    )
    snap = Phase4DashboardReader(cfg).get_dashboard_snapshot()

    assert snap["ok"] is True
    assert snap["db_status"] == "ok"
    assert snap["error"] == ""

    kpis = snap["kpis"]
    assert kpis["total_sessions"] == 3
    assert kpis["completed_sessions"] == 2
    assert kpis["active_devices"] == 2
    assert kpis["healthy_farm_devices"] == 2
    assert kpis["quarantined_devices"] == 1
    assert kpis["active_cgnat_slots"] == 1
    # 1 session collision block + 1 repeated /24 subnet slot hit = 2
    assert kpis["ip_collisions_prevented"] == 2

    fva = kpis["p50_forecast_vs_actual"]
    assert fva["p10_revenue"] == 8.0
    assert fva["p50_revenue"] == 15.0
    assert fva["p90_revenue"] == 24.0
    assert fva["actual_revenue"] == 12.5

    sm = kpis["safe_mode"]
    assert sm["active"] is True
    assert sm["reason"] == "A2 CRITICAL: CTR spike"
    assert sm["clean_windows"] == 2

    assert len(snap["farm_devices"]) == 3
    assert len(snap["sessions"]) == 3
    assert len(snap["cgnat_slots"]) == 3
    assert len(snap["forecasts"]) == 1
    assert len(snap["calibration_reports"]) == 1
    assert len(snap["charts"]["forecast_series"]) == 1
    assert len(snap["charts"]["device_activity"]) == 3


def test_missing_db_returns_graceful_state(tmp_path: Path) -> None:
    cfg = Phase4DashboardConfig(
        phase3_db_path=str(tmp_path / "does_not_exist.db"),
        safe_mode_path=str(tmp_path / "missing_safe.json"),
        legacy_db_path=str(tmp_path / "missing_legacy.db"),
    )
    snap = Phase4DashboardReader(cfg).get_dashboard_snapshot()

    assert snap["ok"] is False
    assert snap["db_status"] == "missing"
    assert "not found" in snap["error"].lower()
    assert snap["sessions"] == []
    assert snap["cgnat_slots"] == []
    assert snap["forecasts"] == []
    assert snap["farm_devices"] == []
    assert snap["kpis"]["total_sessions"] == 0
    assert snap["kpis"]["safe_mode"]["active"] is True
    assert "missing" in snap["kpis"]["safe_mode"]["reason"].lower()


def test_locked_db_returns_graceful_state(tmp_path: Path) -> None:
    db_path = tmp_path / "locked_p3.db"
    Phase3Store(db_path)

    # Switch to DELETE journal mode so BEGIN EXCLUSIVE acquires an immediate file lock
    locker = sqlite3.connect(str(db_path), isolation_level=None, timeout=1.0)
    try:
        locker.execute("PRAGMA journal_mode=DELETE;")
        locker.execute("BEGIN EXCLUSIVE;")

        cfg = Phase4DashboardConfig(
            phase3_db_path=str(db_path),
            safe_mode_path=str(tmp_path / "missing_safe.json"),
            legacy_db_path=str(tmp_path / "missing_legacy.db"),
            sqlite_timeout_seconds=0.1,
        )
        snap = Phase4DashboardReader(cfg).get_dashboard_snapshot()
        assert snap["ok"] is False
        assert snap["db_status"] == "locked"
        assert "locked" in snap["error"].lower()
        assert snap["sessions"] == []
        assert snap["farm_devices"] == []
    finally:
        try:
            locker.execute("ROLLBACK;")
        except Exception:
            pass
        locker.close()


def test_http_server_endpoints_and_path_traversal(tmp_path: Path) -> None:
    db_path, safe_path, legacy_path = _seed_phase3_db(tmp_path)
    cfg = Phase4DashboardConfig(
        host="127.0.0.1",
        port=0,
        phase3_db_path=str(db_path),
        safe_mode_path=str(safe_path),
        legacy_db_path=str(legacy_path),
    )
    server = create_phase4_server(config=cfg, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        status, ctype, body = _http_get(f"{base}/")
        html = body.decode("utf-8")
        assert status == 200
        assert "text/html" in ctype
        assert "/crm-assets/vendor/css/core.css" in html
        assert "/crm-assets/js/crm-phase4.js" in html
        assert "p4DbErrorBanner" in html
        assert "p4TableDevices" in html
        assert "p4TableSessions" in html
        assert "p4TableCgnat" in html
        assert "p4TableForecasts" in html

        status_api, ctype_api, body_api = _http_get(f"{base}/api/phase4/dashboard")
        assert status_api == 200
        assert "application/json" in ctype_api
        payload = json.loads(body_api.decode("utf-8"))
        assert payload["ok"] is True
        assert payload["kpis"]["total_sessions"] == 3
        assert payload["kpis"]["p50_forecast_vs_actual"]["p50_revenue"] == 15.0

        status_h, _, body_h = _http_get(f"{base}/api/phase4/health")
        assert status_h == 200
        health = json.loads(body_h.decode("utf-8"))
        assert health["ok"] is True
        assert health["db_ok"] is True
        assert health["safe_mode_active"] is True

        status_css, ctype_css, body_css = _http_get(f"{base}/crm-assets/vendor/css/core.css")
        assert status_css == 200
        assert "text/css" in ctype_css
        assert len(body_css) > 100

        # Path traversal attempts must return 404
        for bad_path in (
            "/crm-assets/../phase4_config.yaml",
            "/crm-assets/%2e%2e/phase4_config.yaml",
            "/crm-assets/..%5cphase4_config.yaml",
            "/crm-assets/nonexistent_file_xyz.js",
        ):
            bad_status, _, _ = _http_get(f"{base}{bad_path}")
            assert bad_status == 404, f"Expected 404 for {bad_path}, got {bad_status}"

        # Locked DB over HTTP returns HTTP 503 with structured ok:false payload
        locker = sqlite3.connect(str(db_path), isolation_level=None, timeout=1.0)
        try:
            locker.execute("PRAGMA journal_mode=DELETE;")
            locker.execute("BEGIN EXCLUSIVE;")
            status_locked, _, body_locked = _http_get(f"{base}/api/phase4/dashboard")
            assert status_locked == 503
            locked_payload = json.loads(body_locked.decode("utf-8"))
            assert locked_payload["ok"] is False
            assert locked_payload["db_status"] == "locked"
        finally:
            try:
                locker.execute("ROLLBACK;")
            except Exception:
                pass
            locker.close()

        # Missing DB over HTTP returns HTTP 503 with structured ok:false payload
        db_path.unlink()
        status_missing, _, body_missing = _http_get(f"{base}/api/phase4/dashboard")
        assert status_missing == 503
        missing_payload = json.loads(body_missing.decode("utf-8"))
        assert missing_payload["ok"] is False
        assert missing_payload["db_status"] == "missing"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_crm_phase4_js_has_zero_innerhtml() -> None:
    js_path = Path(__file__).resolve().parent.parent / "admin_ui" / "assets" / "js" / "crm-phase4.js"
    js_text = js_path.read_text(encoding="utf-8")
    assert "innerHTML" not in js_text
    assert "outerHTML" not in js_text
    assert "insertAdjacentHTML" not in js_text
    assert "document.write" not in js_text
    assert "createElement" in js_text
    assert "textContent" in js_text
