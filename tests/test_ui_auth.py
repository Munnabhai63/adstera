"""
tests/test_ui_auth.py — Verification of dashboard security:
1. P2-3: is_crm_locked() returns True when no password hash is set (secure by default).
2. P2-2: Unauthenticated state-changing POST endpoints (/api/start, /api/config, /api/proxies/fetch)
   return 401 without cookie, and 200/accepted with a valid session token.
3. P2-2: SSRF protection on /api/proxies/fetch (rejects non-https, private/loopback IPs).
4. P2-2: /api/auth/unlock-dev is forbidden unless PHASE4_ALLOW_DEV_UNLOCK=1.
"""
import http.server
import json
import os
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
import pytest

from admin_ui import profile_auth
import ui


@pytest.fixture(autouse=True)
def _isolate_env_and_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(profile_auth, "DEFAULT_STATE_DIR", state_dir)
    monkeypatch.setattr(ui, "BASE_DIR", tmp_path)
    # Ensure fresh setup
    if "PHASE4_FIRST_RUN_SETUP" in os.environ:
        monkeypatch.delenv("PHASE4_FIRST_RUN_SETUP", raising=False)
    if "PHASE4_ALLOW_DEV_UNLOCK" in os.environ:
        monkeypatch.delenv("PHASE4_ALLOW_DEV_UNLOCK", raising=False)
    yield state_dir


def test_p2_3_open_by_default_crm_lock_inverted(tmp_path):
    sdir = tmp_path / "custom_state"
    sdir.mkdir(parents=True, exist_ok=True)

    # With no profile.json or admin_profile.json, is_crm_locked must be True
    assert profile_auth.is_crm_locked("", sdir) is True

    # When PHASE4_FIRST_RUN_SETUP=1 escape hatch is active, returns False
    os.environ["PHASE4_FIRST_RUN_SETUP"] = "1"
    try:
        assert profile_auth.is_crm_locked("", sdir) is False
    finally:
        del os.environ["PHASE4_FIRST_RUN_SETUP"]

    # Still True after removing escape hatch
    assert profile_auth.is_crm_locked("", sdir) is True


def test_p2_2_ui_endpoints_require_auth(tmp_path):
    sdir = tmp_path / "state"

    # Start ui server on free port
    server = http.server.HTTPServer(("127.0.0.1", 0), ui.UIRequestHandler)
    port = server.server_port
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    base_url = f"http://127.0.0.1:{port}"

    def make_post(path, data, cookie=None):
        req = urllib.request.Request(
            f"{base_url}{path}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
        )
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    try:
        # 1. Without cookie, endpoints must return 401
        for ep, body in [
            ("/api/start", {}),
            ("/api/config", {"scheduler": {"daily_cap": 500}}),
            ("/api/proxies/fetch", {"api_url": "https://example.com/proxies"}),
        ]:
            code, res = make_post(ep, body)
            assert code == 401, f"Expected 401 for unauthenticated {ep}, got {code}"
            assert res.get("ok") is False

        # 2. Configure password and create valid session token
        ok, msg, _ = profile_auth.set_password("AdminPass123!", "AdminPass123!", state_dir=sdir)
        assert ok is True
        token = profile_auth.create_session_token("TestRunner/1.0", state_dir=sdir)
        valid_cookie = f"{profile_auth.COOKIE_NAME}={token}"

        # 3. Unlock-dev must return 403 without env var
        code, res = make_post("/api/auth/unlock-dev", {}, cookie=None)
        assert code == 403

        # 4. With valid session cookie, endpoints are authorized
        code, res = make_post("/api/start", {}, cookie=valid_cookie)
        assert code == 200, f"Expected 200 for authenticated /api/start, got {code}"
        assert res.get("ok") is True

        # 5. SSRF protection on /api/proxies/fetch
        # Non-https rejected
        code, res = make_post("/api/proxies/fetch", {"api_url": "http://example.com/proxies"}, cookie=valid_cookie)
        assert code == 400
        assert "Only https://" in res.get("error", "")

        # Loopback / private IP rejected
        code, res = make_post("/api/proxies/fetch", {"api_url": "https://127.0.0.1:8000/proxies"}, cookie=valid_cookie)
        assert code == 400
        assert "forbidden" in res.get("error", "").lower()

    finally:
        server.shutdown()
        server.server_close()
