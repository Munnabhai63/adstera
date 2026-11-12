"""Regression tests for the 5 Claude architectural audit fixes."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

import db
from admin_ui.phase4_data import Phase4DashboardConfig, Phase4DashboardReader, load_phase4_config
from admin_ui.phase4_server import create_phase4_server
from ai_engine.config import load_ai_config
from ai_engine.safe_mode import SafeModeStateMachine
from common.paths import DEFAULT_SAFE_MODE_PATH, atomic_write_json, get_safe_mode_path, read_safe_mode_state
from phase3.a6_scheduler.cgnat_tracker import CGNATTracker
from phase3.adapters import DeviceDisconnectedError, DeviceTouchCaptureBridge, Phase1DeviceAdapter
from phase3.config_loader import load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.wiring.live_orchestrator import Phase3LiveOrchestrator


def test_sqlite_wal_busy_timeout_and_concurrent_cgnat(tmp_path: Path) -> None:
    db_file = tmp_path / "wal_test.db"
    store = Phase3Store(db_file)
    with store.connect() as conn:
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert str(jm).lower() == "wal"
    assert int(bt) == 10000

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(db_file)
    tracker = CGNATTracker(cfg, store)

    # Multiple concurrent threads racing on the same /24 subnet must serialize via BEGIN IMMEDIATE
    results: list[bool] = []
    lock = threading.Lock()

    def _worker(dev_idx: int) -> None:
        ok = tracker.acquire_slot(f"dev-{dev_idx}", f"100.64.16.{10 + dev_idx}", now_ts=2000.0)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(results) == 6
    assert sum(1 for r in results if r) == 1


def test_safe_mode_single_source_of_truth_and_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHASE4_SAFE_MODE_PATH", raising=False)
    assert str(get_safe_mode_path()).replace("\\", "/") == DEFAULT_SAFE_MODE_PATH
    assert load_phase4_config().safe_mode_path == DEFAULT_SAFE_MODE_PATH

    missing_sm = tmp_path / "missing" / "safe_mode.json"
    # Direct path helper fails closed
    state = read_safe_mode_state(missing_sm, fail_closed=True)
    assert state["active"] is True
    assert "missing" in state["reason"].lower()

    # SafeModeStateMachine fails closed when file is missing
    ai_cfg = load_ai_config(None)
    sm_missing = SafeModeStateMachine(ai_cfg.a2_anomaly.safe_mode, state_file=missing_sm)
    assert sm_missing.is_active() is True

    # Dashboard reader fails closed when file is corrupt JSON
    corrupt_sm = tmp_path / "corrupt_safe_mode.json"
    corrupt_sm.write_text("{not-valid-json", encoding="utf-8")
    sm_corrupt = SafeModeStateMachine(ai_cfg.a2_anomaly.safe_mode, state_file=corrupt_sm)
    assert sm_corrupt.is_active() is True

    dash_cfg = Phase4DashboardConfig(
        phase3_db_path=str(tmp_path / "nope.db"),
        safe_mode_path=str(corrupt_sm),
        legacy_db_path=str(tmp_path / "nope_legacy.db"),
    )
    dash_sm = Phase4DashboardReader(dash_cfg).read_safe_mode()
    assert dash_sm["active"] is True

    # Atomic write leaves no temp files and synchronizes SafeModeStateMachine + Dashboard
    clean_sm = tmp_path / "shared" / "safe_mode.json"
    atomic_write_json(
        clean_sm,
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    leftover_tmps = list(clean_sm.parent.glob("*.tmp"))
    assert leftover_tmps == []
    sm_shared = SafeModeStateMachine(ai_cfg.a2_anomaly.safe_mode, state_file=clean_sm)
    assert sm_shared.is_active() is False
    sm_shared.enter("audit_test_trigger")
    assert Phase4DashboardReader(
        Phase4DashboardConfig(safe_mode_path=str(clean_sm))
    ).read_safe_mode()["active"] is True


def test_screenshot_raises_device_disconnected_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import phase3.adapters.phase1_device as p1_mod

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "disc_p3.db")
    cfg.phase3.state_dir = str(tmp_path / "disc_state")
    cfg.phase3.default_mode = "paper"
    atomic_write_json(
        Path(cfg.phase3.state_dir) / "ai_engine" / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )

    adapter = Phase1DeviceAdapter(cfg)

    # Empty serial raises DeviceDisconnectedError instead of 1x1 dummy PNG
    with pytest.raises(DeviceDisconnectedError):
        adapter.screenshot("")

    # Non-zero ADB returncode raises DeviceDisconnectedError
    monkeypatch.setattr(p1_mod.mobile_adb, "get_adb_path", lambda custom="": "adb")
    monkeypatch.setattr(
        p1_mod.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout=b"", stderr=b"error: device offline"),
    )
    with pytest.raises(DeviceDisconnectedError):
        adapter.screenshot("RZCX21WTS9E")

    # Corrupted/non-PNG stdout raises DeviceDisconnectedError
    monkeypatch.setattr(
        p1_mod.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"NOT_A_PNG", stderr=b""),
    )
    with pytest.raises(DeviceDisconnectedError):
        adapter.screenshot("RZCX21WTS9E")

    # Orchestrator catches DeviceDisconnectedError in failsafe without calling A4 on 1x1 garbage
    bridge = DeviceTouchCaptureBridge(adapter, "RZCX21WTS9E", paper=True)
    orch = Phase3LiveOrchestrator(cfg, seed=42)
    res = asyncio.run(
        orch.run_step(touch=bridge, capture=bridge, device_id="RZCX21WTS9E", domain="loanraaj.com")
    )
    assert res["action"] == "skip"
    assert res["executed_touch"] is False
    assert res["safe_mode"] is True
    assert "disconnected" in res["error"].lower()


def test_db_utc_timestamp_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_db = tmp_path / "sessions_utc.db"
    monkeypatch.setattr(db, "_DB_PATH", test_db)
    db.init()

    with db._conn() as con:
        jm = con.execute("PRAGMA journal_mode;").fetchone()[0]
        bt = con.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert str(jm).lower() == "wal"
    assert int(bt) == 10000

    db.log_session(
        proxy_id="1.2.3.4:8080",
        ua="Mozilla/5.0",
        referrer="",
        dwell=30.0,
        impressions=2,
        ad_clicks=0,
        domain="loanraaj.com",
    )

    with db._conn() as con:
        row = con.execute("SELECT ts, datetime('now') AS utc_now FROM sessions LIMIT 1").fetchone()
    logged_ts = datetime.strptime(row["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    utc_now = datetime.strptime(row["utc_now"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    assert abs((utc_now - logged_ts).total_seconds()) < 15.0
    assert db.per_ip_today("1.2.3.4:8080") == 1
    assert db.today() == 1


def test_ui_py_phase4_dashboard_returns_503_when_db_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ui

    locked_db = tmp_path / "locked_ui.db"
    Phase3Store(locked_db)
    safe_path = tmp_path / "safe_mode.json"
    atomic_write_json(
        safe_path,
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )

    monkeypatch.setenv("PHASE4_DB_PATH", str(locked_db))
    monkeypatch.setenv("PHASE4_SAFE_MODE_PATH", str(safe_path))

    # Write short-timeout yaml config override or lower config timeout? Wait: ui.py uses load_phase4_config()
    orig_load = load_phase4_config
    import admin_ui.phase4_data as p4_data

    def _fast_cfg():
        c = orig_load()
        c.sqlite_timeout_seconds = 0.1
        return c

    monkeypatch.setattr(p4_data, "load_phase4_config", _fast_cfg)

    server = HTTPServer(("127.0.0.1", 0), ui.UIRequestHandler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    locker = sqlite3.connect(str(locked_db), isolation_level=None, timeout=1.0)
    try:
        locker.execute("PRAGMA journal_mode=DELETE;")
        locker.execute("BEGIN EXCLUSIVE;")
        port = server.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/phase4/dashboard", method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5.0)
        assert exc_info.value.code == 503
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert body["ok"] is False
        assert body["db_status"] == "locked"
    finally:
        try:
            locker.execute("ROLLBACK;")
        except Exception:
            pass
        locker.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
