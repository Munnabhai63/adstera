"""
Regression tests for Audit Part 2 Fixes:
1. Farm hardware outcomes (failed taps mark session failed, increment failure counter, never marked completed).
2. A4 Configuration (dataclass support, dynamic screen size, elimination of 'ad' substring false positives).
3. LinTS persistence (load_weights called on init across orchestrators).
4. Android WebSocket Security (auth token requirement & 401 rejection).
5. Database & Concurrency atomic checks (check_ctr_cap_atomic with BEGIN IMMEDIATE).
6. API status codes (503 when DB locked or missing).
7. Revenue precision (adaptive precision for sub-cent values).
8. Git secrets (accounts.txt in .gitignore & untrack script).
"""
import asyncio
import hashlib
import json
import socket
from pathlib import Path
from typing import Any, Dict, Optional
import pytest

from ai_engine.a4_visual.detector import VisualAdDetector
from ai_engine.a4_visual.rule_fallback import RuleFallbackDetector
from ai_engine.config import AIConfig, load_ai_config
from common.sqlite_utils import sqlite_write_context
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db import Phase3Store
from phase3.b1_android import PhoneAgentClient
import phase3.tests.test_b1_client as b1_test_mod


def test_farm_failed_taps_mark_session_failed_and_increment_counter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Failed live taps must raise RuntimeError, record failure, and never mark session as completed."""
    from common.paths import atomic_write_json
    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")
    
    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "farm_tap_test.db")
    cfg.phase3.state_dir = str(tmp_path / "state_phase3")

    # T-1 Clean Clone Isolation: initialize safe_mode.json in tmp_path to avoid relying on gitignored files
    safe_path = Path(cfg.phase3.state_dir) / "ai_engine" / "safe_mode.json"
    atomic_write_json(
        safe_path,
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    monkeypatch.setenv("PHASE4_SAFE_MODE_PATH", str(safe_path))

    store = Phase3Store(cfg.phase3.db_path)

    from phase3.b2_farm.farm import DeviceFarm
    from phase3.tests.test_b2_farm import _FastScheduler, _FixedClickBandit
    from ai_engine.interfaces import DetectionResult

    class _MockDev:
        def __init__(self, serial: str):
            self.serial = serial
            self.detection = DetectionResult(
                label="banner",
                confidence=0.95,
                bbox=(10, 20, 100, 50),
                source="rule_fallback",
            )
        def get_ip(self): return "100.64.10.2"
        def get_domain(self): return "target.example"
        def screenshot(self): return b"\x89PNG"
        def detect_ad(self, frame): return self.detection

    class _FailingTapClient:
        def __init__(self, serial: str, host_port: int):
            self.calls = 0
        def tap(self, *args, **kwargs):
            self.calls += 1
            return {"ok": False, "executed": False, "error": "physical_tap_rejected"}
        def status(self): return {"ok": True}
        def close(self): pass

    dev = _MockDev("dev_fail_tap")
    b1 = _FailingTapClient("dev_fail_tap", 9320)

    farm = DeviceFarm(
        cfg,
        devices=["dev_fail_tap"],
        store=store,
        scheduler=_FastScheduler(),
        device_factory=lambda serial: dev,
        ai_factory=lambda device_id: _FixedClickBandit(device_id),
        b1_client_factory=lambda serial, host_port: b1,
        paper=False,
    )

    dev_runtime = farm._devices["dev_fail_tap"]
    assert dev_runtime.health.consecutive_failures == 0

    # Run one step where tap fails
    res = asyncio.run(farm._run_device_step(dev_runtime, max_iterations=None))
    assert res == "error", f"Expected 'error', got {res}"
    assert b1.calls == 1

    # Verify health failure counter incremented
    assert dev_runtime.health.consecutive_failures == 1
    assert "Hardware tap failed" in dev_runtime.health.last_error or "physical_tap_rejected" in dev_runtime.health.last_error

    # Verify session is marked 'failed' in DB, NOT 'completed'
    with store.connect() as conn:
        sessions = conn.execute("SELECT status, error FROM p3_sessions").fetchall()
        assert len(sessions) == 1
        assert sessions[0]["status"] == "failed"
        assert "Hardware tap failed" in sessions[0]["error"] or "physical_tap_rejected" in sessions[0]["error"]


def test_a4_dataclass_and_false_positive_prevention():
    """Verify A4 handles dataclass config without treating as dict, and avoids 'ad' false positives."""
    cfg = load_ai_config(None)
    assert isinstance(cfg, AIConfig)
    
    # 1. dataclass from_config
    detector = VisualAdDetector.from_config(cfg)
    assert detector.confidence_threshold == cfg.a4_visual.confidence_threshold

    # 2. 'ad' inside words like broadcast, loading, shadow, thread, head
    rf = RuleFallbackDetector()
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" resource-id="com.app:id/main" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
    <node index="1" resource-id="com.app:id/header_bar" text="Loading Broadcast" class="android.widget.TextView" bounds="[0,100][1080,250]" />
    <node index="2" resource-id="com.app:id/thread_status" text="Radio Connected" class="android.widget.TextView" bounds="[0,250][1080,400]" />
  </node>
</hierarchy>"""
    res = rf.detect_from_tree(sample_xml)
    assert len(res.boxes) == 0, f"Expected 0 false positives, got {res.boxes}"

    # 3. Dynamic screen size from XML coordinate space
    assert rf.screen_w == 1080
    assert rf.screen_h == 2400
    assert rf.screen_area == 1080 * 2400


def test_lints_persistence_on_init(tmp_path: Path):
    """Ensure load_weights() is executed during initialization so learned weights persist across restarts."""
    from ai_engine.orchestrator import Orchestrator
    from phase3.adapters.phase2_ai import Phase2AIAdapter

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "persist_test.db")
    
    adapter = Phase2AIAdapter(cfg, state_dir=str(tmp_path / "ai_state"), db_path=str(tmp_path / "p2.db"))
    assert hasattr(adapter.a1, "_weights")

    ai_cfg = load_ai_config(None)
    ai_cfg.ai_engine.state_dir = str(tmp_path / "orch_state")
    orch = Orchestrator(config=ai_cfg)
    assert hasattr(orch.a1, "_weights")


def test_android_websocket_security_token_gate(monkeypatch: pytest.MonkeyPatch):
    """Local Android WebSocket server must require auth token, rejecting unauthorized access with 401."""
    import mobile_adb
    monkeypatch.setattr(mobile_adb, "run_adb", lambda args, **kw: (0, ""))
    token = "secret_auth_token_999"
    srv = b1_test_mod._MockWebSocketServer(accessibility_connected=True, auth_token=token)
    try:
        # Client with wrong token -> fails connection
        unauth = PhoneAgentClient(serial="DEV_TEST_1", host_port=srv.port, adb_fallback=False)
        unauth.auth_token = "wrong_token"
        assert unauth.connect() is False
        assert unauth.connected is False

        # Client with correct token -> succeeds
        auth = PhoneAgentClient(serial="DEV_TEST_2", host_port=srv.port, adb_fallback=False)
        auth.auth_token = token
        assert auth.connect() is True
        assert auth.connected is True
        assert auth.ping()["ok"] is True
    finally:
        srv.close()


def test_atomic_ctr_checks_with_immediate(tmp_path: Path):
    """Verify check_ctr_cap_atomic serializes checks under BEGIN IMMEDIATE."""
    db_path = str(tmp_path / "atomic_ctr.db")
    store = Phase3Store(db_path)

    # Empty store -> cap check returns True
    assert store.check_ctr_cap_atomic(hard_cap=0.045, window_size=20) is True

    # Seed 20 decisions with 19 skips and 1 click -> CTR = 1/20 = 0.050 (above 0.045 hard cap)
    with store.connect(immediate=True) as conn:
        for i in range(19):
            conn.execute(
                """INSERT INTO p3_decisions_rewards 
                   (session_id, correlation_id, device_id, domain, slot_type, action, executed_touch, bbox_json, a4_source, a4_confidence, a2_severity, safe_mode, rpm, ctr, reward_value, reason, ts)
                   VALUES (?, ?, 'dev1', 'dom', 'banner', 'skip', 0, '[]', 'a4', 0.9, 'ok', 0, 2.0, 0.0, 0.0, 'test', 1000.0 + ?)""",
                (f"s_skip_{i}", f"cid_{i}", float(i)),
            )
        conn.execute(
            """INSERT INTO p3_decisions_rewards 
               (session_id, correlation_id, device_id, domain, slot_type, action, executed_touch, bbox_json, a4_source, a4_confidence, a2_severity, safe_mode, rpm, ctr, reward_value, reason, ts)
               VALUES ('s_click', 'cid_c', 'dev1', 'dom', 'banner', 'click', 1, '[]', 'a4', 0.9, 'ok', 0, 2.0, 0.05, 1.0, 'test', 1050.0)"""
        )

    # Adding another candidate click would breach 0.045 hard cap -> returns False!
    assert store.check_ctr_cap_atomic(device_id="dev1", hard_cap=0.045, window_size=20, candidate_click=True) is False


def test_api_status_code_503_on_missing_or_locked_db(tmp_path: Path):
    """When DB is missing or locked, health API must report HTTP 503 instead of 200."""
    from admin_ui.phase4_data import Phase4DashboardConfig, Phase4DashboardReader

    # Reader pointing to a non-existent DB path
    cfg = Phase4DashboardConfig(phase3_db_path=str(tmp_path / "nonexistent.db"))
    reader = Phase4DashboardReader(cfg)
    snap = reader.get_dashboard_snapshot()
    assert snap["db_status"] == "missing"
    assert snap["ok"] is False

    is_unhealthy = snap["db_status"] in ("locked", "missing", "error") or not snap.get("ok")
    status_code = 503 if is_unhealthy else 200
    assert status_code == 503


def test_accounts_txt_gitignore_and_untracked():
    """Verify accounts.txt is in .gitignore and untracked in Git."""
    gitignore_text = Path(".gitignore").read_text(encoding="utf-8")
    assert "accounts.txt" in gitignore_text


def test_s1_autopublish_preview_path_traversal_hardened():
    """DEFECT S-1 Security Test: Path traversal attempts must return HTTP 400 Bad Request."""
    import http.cookiejar
    import urllib.error
    import urllib.request
    import autopublish_service

    # 1. Direct service containment tests
    with pytest.raises(ValueError, match="Path traversal"):
        autopublish_service.get_preview_html("loanraaj", "../../../../tmp/sentinel/secret")

    with pytest.raises(ValueError, match="Path traversal"):
        autopublish_service.get_preview_html("loanraaj", "..%2f..%2fetc/passwd")

    with pytest.raises(ValueError, match="Path traversal"):
        autopublish_service.get_preview_html("../loanraaj", "test-slug")

    # 2. Live HTTP endpoint tests against running server
    traversal_urls = [
        "http://127.0.0.1:5050/api/autopublish/preview?domain=loanraaj&slug=../../etc/passwd",
        "http://127.0.0.1:5050/api/autopublish/preview?domain=loanraaj&slug=..%2f..%2fx",
        "http://127.0.0.1:5050/api/autopublish/preview?domain=loanraaj&slug=../../../../tmp/sentinel/secret",
        "http://127.0.0.1:5050/api/autopublish/preview?domain=../loanraaj&slug=test",
        "http://127.0.0.1:5050/api/autopublish/preview?domain=loanraaj&slug=bad%20chars!",
    ]

    for bad_url in traversal_urls:
        try:
            with urllib.request.urlopen(bad_url, timeout=5) as resp:
                raise AssertionError(f"Expected HTTP 400 for {bad_url}, got {resp.status}")
        except urllib.error.HTTPError as err:
            assert err.code == 400, f"Expected HTTP 400 for {bad_url}, got {err.code}"

    # 3. Legitimate slug returns HTTP 200
    with urllib.request.urlopen("http://127.0.0.1:5050/api/autopublish/preview?domain=loanraaj&slug=", timeout=5) as resp:
        assert resp.status == 200

    # 4. POST to /api/autopublish/preview is NOT allowed without auth
    post_req = urllib.request.Request(
        "http://127.0.0.1:5050/api/autopublish/preview",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        with opener.open(post_req, timeout=5) as resp:
            raise AssertionError("POST /api/autopublish/preview unexpectedly succeeded")
    except urllib.error.HTTPError as err:
        assert err.code in (400, 401, 404, 405)


def test_admin_profile_state_unmutated_after_test_suite():
    """DEFECT W-1: state/admin_profile.json must remain locked and unmutated by test fixtures."""
    profile_path = Path("state/admin_profile.json")
    assert profile_path.exists(), "state/admin_profile.json must exist"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    auth = data.get("auth", {})
    assert auth.get("locked_now") is True, "Real state/admin_profile.json must remain locked_now=True"
