"""
tests/test_layer4_state_cleanup.py — Acceptance tests for Layer 4: state/ cleanup & session reset.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
import persist
import state_cleanup
import worker
from anomaly_detector import AnomalyDetector


def test_clean_state_dir_dry_run_and_apply(tmp_path):
    st = tmp_path / "state"
    (st / "accounts").mkdir(parents=True)
    (st / "useragents").mkdir(parents=True)
    (st / "mahi_bridge" / "profiles" / "test-uuid-1234").mkdir(parents=True)
    (st / "mahi_bridge" / "cookies").mkdir(parents=True)

    # Stale artifacts
    stale_names = [
        "mobile_1.39.155.10.json",
        "mobile_1.39.157.198_meta.json",
        "mobile_direct.json",
        "10.0.1.1_8080.json",
        "10.0.1.1_8080_meta.json",
        "127.0.0.1_8080.json",
        "global.rotgb.trustsource.live_10000.json",
    ]
    for fn in stale_names:
        (st / fn).write_text("{}", encoding="utf-8")
    (st / "sessions.db").write_bytes(b"")  # 0B orphan
    (st / "mahi_bridge" / "cookies" / "empty_state.json").write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    # Protected / critical state files
    (st / "autopublish.db").write_bytes(b"sqlite-prod")
    (st / "adsterra_banners.json").write_text('{"slots":{}}', encoding="utf-8")
    (st / "daily_report_state.json").write_text('{"last_sent_date":"2026-11-11"}', encoding="utf-8")
    (st / "accounts" / "registry.json").write_text('{"acc1":{"email":"a@b.com"}}', encoding="utf-8")
    (st / "useragents" / "desktop.json").write_text('["Mozilla/5.0"]', encoding="utf-8")
    (st / "mahi_bridge" / "cookies" / "warmed_state.json").write_text(
        '{"cookies":[{"name":"uid","value":"1"}],"origins":[]}',
        encoding="utf-8",
    )

    dry = state_cleanup.clean_state_dir(state_dir=st, apply=False)
    assert dry["deleted_proxy_files_count"] == len(stale_names)
    assert dry["deleted_empty_cookies_count"] == 1
    assert (st / "mobile_1.39.155.10.json").exists()

    applied = state_cleanup.clean_state_dir(state_dir=st, apply=True)
    assert applied["deleted_proxy_files_count"] == len(stale_names)
    for fn in stale_names:
        assert not (st / fn).exists(), f"{fn} should be removed"
    assert not (st / "sessions.db").exists()
    assert not (st / "mahi_bridge" / "profiles" / "test-uuid-1234").exists()
    assert not (st / "mahi_bridge" / "cookies" / "empty_state.json").exists()

    # Protected files remain intact
    assert (st / "autopublish.db").exists()
    assert (st / "adsterra_banners.json").exists()
    assert (st / "daily_report_state.json").exists()
    assert (st / "accounts" / "registry.json").exists()
    assert applied["accounts_count"] == 1
    assert (st / "useragents" / "desktop.json").exists()
    assert (st / "mahi_bridge" / "cookies" / "warmed_state.json").exists()


def test_reset_circuit_breaker_unlocks_loanraaj(tmp_path):
    st = tmp_path / "state"
    st.mkdir(parents=True)
    cb_path = st / "circuit_breaker.json"
    cb_path.write_text(
        json.dumps({
            "paused_domains": {
                "loanraaj.com": {
                    "action": "PAUSE_DOMAIN",
                    "reason": "Smoke test degraded spike",
                    "severity": "CRITICAL",
                }
            },
            "global_pause": True,
            "history": [{"domain": "loanraaj.com"}],
        }),
        encoding="utf-8",
    )

    res = state_cleanup.reset_circuit_breaker(state_dir=st, apply=True)
    assert res["paused_before"] == ["loanraaj.com"]
    assert res["paused_after"] == []

    det = AnomalyDetector(state_file=cb_path)
    paused, action, _ = det.is_domain_paused("loanraaj.com")
    assert paused is False
    assert action == "NONE"


def test_reset_active_ua_and_worker_helper(tmp_path):
    st = tmp_path / "state"
    st.mkdir(parents=True)
    ua_file = st / "active_ua.json"
    ua_file.write_text(json.dumps({"active": True, "proxy_id": "10.0.2.1:8080"}), encoding="utf-8")

    res = state_cleanup.reset_active_ua_file(state_dir=st, apply=True)
    assert res["previous_proxy_id"] == "10.0.2.1:8080"
    data = json.loads(ua_file.read_text(encoding="utf-8"))
    assert data["active"] is False
    assert data["proxy_id"] == "\u2014"

    ua_file2 = tmp_path / "other" / "active_ua.json"
    worker.reset_active_ua(ua_file2)
    assert json.loads(ua_file2.read_text(encoding="utf-8"))["active"] is False


def test_clean_test_sessions_db_purges_pollution_keeps_alerts(tmp_path, monkeypatch):
    test_db = tmp_path / "sessions.db"
    monkeypatch.setattr(db, "_DB_PATH", test_db)
    db.init()

    db.log_session("10.0.1.1:8080", "UA", "", 40.0, 1, 0, 7, status="ok", domain="loanraaj.com")
    db.log_session("mobile:direct", "UA", "", 50.0, 1, 0, 0, status="ok", domain="this-domain-definitely-does-not-exist-123456789.com")
    db.log_session("mobile:1.39.163.90", "UA", "", 30.0, 1, 0, 0, status="degraded", domain="loanraaj.com")
    db.record_alert_log("daily_report", "INFO", "morning report ok", sent_live=True)

    res = state_cleanup.clean_test_sessions_db(db_path=test_db, apply=True)
    assert res["sessions_removed"] == 3
    assert res["sessions_remaining"] == 0
    assert res["domain_stats_removed"] >= 2

    with sqlite3.connect(test_db) as con:
        assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM domain_stats").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM alert_logs").fetchone()[0] == 1


def test_persist_clear_and_purge_stale_states(tmp_path, monkeypatch):
    st = tmp_path / "state"
    st.mkdir(parents=True)
    monkeypatch.setattr(persist, "_STATE_DIR", st)

    # clear() removes both cookie json and meta json
    (st / "10.0.0.1_8080.json").write_text("{}", encoding="utf-8")
    (st / "10.0.0.1_8080_meta.json").write_text("{}", encoding="utf-8")
    persist.clear("10.0.0.1:8080")
    assert not (st / "10.0.0.1_8080.json").exists()
    assert not (st / "10.0.0.1_8080_meta.json").exists()

    # purge_stale_states() deletes old files and keeps fresh + non-proxy files
    old_file = st / "mobile_1.39.1.2.json"
    old_meta = st / "mobile_1.39.1.2_meta.json"
    fresh_file = st / "mobile_9.9.9.9.json"
    keep_cfg = st / "adsterra_banners.json"
    for f in (old_file, old_meta, fresh_file, keep_cfg):
        f.write_text("{}", encoding="utf-8")

    old_ts = time.time() - 10 * 86400.0
    os.utime(old_file, (old_ts, old_ts))
    os.utime(old_meta, (old_ts, old_ts))

    removed = persist.purge_stale_states(max_age_days=7.0, state_dir=st)
    assert removed == 2
    assert not old_file.exists()
    assert not old_meta.exists()
    assert fresh_file.exists()
    assert keep_cfg.exists()


def test_live_state_reset_and_ui_endpoint():
    """Verify live project state is unlocked and live UI endpoint reports clean breaker state."""
    root = Path(__file__).parent.parent
    cb_path = root / "state" / "circuit_breaker.json"
    if cb_path.is_file():
        det = AnomalyDetector(state_file=cb_path)
        is_paused, _, _ = det.is_domain_paused("loanraaj.com")
        assert is_paused is False, "loanraaj.com must be unlocked after Layer 4 reset"

    try:
        r = httpx.get("http://127.0.0.1:5050/api/status", timeout=4.0)
        assert r.status_code == 200
        payload = r.json()
        assert "circuit_breaker" in payload
        assert payload["circuit_breaker"]["paused_domains"] == []
        assert payload["circuit_breaker"]["global_pause"] is False
        assert payload["active_ua"]["active"] is False
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("UI server not actively running on port 5050 during test run")
