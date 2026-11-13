"""Verification tests for Vuexy CRM Component U2.5: Profile, Auth Lock, Connections & Notifications."""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request
from pathlib import Path

from admin_ui import profile_auth
from admin_ui.shell import render_crm_shell
from admin_ui.views import render_login_view


def test_profile_and_auth_lifecycle_isolated(tmp_path: Path) -> None:
    sdir = tmp_path / "state"
    # 1. Default profile is locked until password is set (P2-3 secure by default)
    prof = profile_auth.load_profile(sdir)
    assert prof["require_login"] is False
    assert prof["has_password"] is False
    assert profile_auth.is_crm_locked("", sdir) is True

    # Escape hatch for initial setup
    import os
    os.environ["PHASE4_FIRST_RUN_SETUP"] = "1"
    assert profile_auth.is_crm_locked("", sdir) is False
    del os.environ["PHASE4_FIRST_RUN_SETUP"]

    # 2. Cannot enable Sign-In gate without a password first
    ok, _, _ = profile_auth.set_require_login(True, sdir)
    assert ok is False

    # 3. Profile validation rejects invalid email and accepts valid save
    ok, _, _ = profile_auth.save_profile({"display_name": "Ops", "email": "bad-email"}, sdir)
    assert ok is False
    ok, _, updated = profile_auth.save_profile(
        {
            "display_name": "Munaf Admin",
            "email": "munaf@publisherhub.in",
            "role": "Founder & Operator",
            "avatar": "/crm-assets/img/avatars/3.png",
        },
        sdir,
    )
    assert ok is True
    assert updated["display_name"] == "Munaf Admin"
    assert updated["avatar"] == "/crm-assets/img/avatars/3.png"

    # 4. PBKDF2 password set, timing-safe check, salted storage (never plaintext)
    ok, _, _ = profile_auth.set_password("weak", "weak", state_dir=sdir)
    assert ok is False
    ok, _, prof_pw = profile_auth.set_password("StrongPass9!", "StrongPass9!", state_dir=sdir)
    assert ok is True
    assert prof_pw["has_password"] is True
    raw_disk = (sdir / "admin_profile.json").read_text(encoding="utf-8")
    assert "StrongPass9!" not in raw_disk
    assert profile_auth.verify_credentials("munaf@publisherhub.in", "WrongPass9!", sdir) is False
    assert profile_auth.verify_credentials("munaf@publisherhub.in", "StrongPass9!", sdir) is True

    # 5. Session cookie stored as SHA-256 digest only, lock/unlock cycle
    ok, _, _ = profile_auth.set_require_login(True, sdir)
    assert ok is True
    assert profile_auth.is_crm_locked("", sdir) is True
    tok = profile_auth.create_session_token("PytestUA/1.0", state_dir=sdir)
    sess_disk = (sdir / "admin_sessions.json").read_text(encoding="utf-8")
    assert tok not in sess_disk
    cookie_hdr = f"{profile_auth.COOKIE_NAME}={tok}"
    assert profile_auth.is_crm_locked(cookie_hdr, sdir) is False

    # 6. Dev unlock must be blocked once a password exists
    ok_dev, _ = profile_auth.unlock_without_password(sdir)
    assert ok_dev is False

    # 7. Sign out revokes token & locks CRM immediately
    profile_auth.revoke_session_and_lock(cookie_hdr, sdir)
    assert profile_auth.is_crm_locked(cookie_hdr, sdir) is True

    # 8. Clear password requires current password
    ok, _, _ = profile_auth.clear_password("wrong", sdir)
    assert ok is False
    ok, _, prof_cleared = profile_auth.clear_password("StrongPass9!", sdir)
    assert ok is True
    assert prof_cleared["has_password"] is False
    assert profile_auth.is_crm_locked("", sdir) is True


def test_connections_never_leak_secrets(tmp_path: Path) -> None:
    fake_env = tmp_path / ".env"
    secret_val = "SUPER_SECRET_TOKEN_XYZ_987654"
    fake_env.write_text(f"ADSTERRA_API_KEY={secret_val}\n", encoding="utf-8")
    conns = profile_auth.get_connections_summary(base_dir=tmp_path, cfg={})
    serialized = json.dumps(conns)
    assert secret_val not in serialized
    adsterra = next(c for c in conns if c["id"] == "adsterra")
    assert adsterra["configured"] is True


def test_notifications_mark_read_isolated(tmp_path: Path) -> None:
    sdir = tmp_path / "state"
    cleaned = profile_auth._clean_alert_text("⚠️ <b>PROXY POOL</b>\n─────\n🔑 <i>0 left</i> &amp; ok")
    assert "<b>" not in cleaned
    assert "<i>" not in cleaned
    assert "&amp;" not in cleaned
    assert "───" not in cleaned
    assert "& ok" in cleaned

    initial = profile_auth.get_notifications(state_dir=sdir, limit=10)
    assert "items" in initial
    assert "unread_count" in initial
    after = profile_auth.mark_notifications_read(mark_all=True, state_dir=sdir, limit=10)
    assert after["unread_count"] == 0


def test_crm_shell_and_login_markup() -> None:
    shell = render_crm_shell()
    for needle in (
        'id="view-profile"',
        'id="shellNotifBellBtn"',
        'id="shellLogoutBtn"',
        'id="u25ProfileForm"',
        'id="u25PasswordForm"',
        'src="/crm-assets/js/crm-profile.js"',
    ):
        assert needle in shell

    login_setup = render_login_view({"has_password": False, "email": "op@local", "display_name": "Op"})
    assert 'name="mode" value="setup"' in login_setup
    assert 'id="u25DevUnlockBtn"' in login_setup

    login_pw = render_login_view({"has_password": True, "email": "op@local", "display_name": "Op"})
    assert 'name="mode" value="login"' in login_pw
    assert 'id="u25DevUnlockBtn"' not in login_pw


def test_live_u25_http_routes_and_lock_roundtrip() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/api/profile", timeout=5) as resp:
        assert resp.status == 200
        pdata = json.loads(resp.read().decode("utf-8"))
        assert pdata["ok"] is True
        assert "profile" in pdata and "connections" in pdata

    with urllib.request.urlopen("http://127.0.0.1:5050/api/notifications", timeout=5) as resp:
        assert resp.status == 200
        ndata = json.loads(resp.read().decode("utf-8"))
        assert ndata["ok"] is True
        assert isinstance(ndata["items"], list)

    with urllib.request.urlopen("http://127.0.0.1:5050/crm/login", timeout=5) as resp:
        assert resp.status == 200
        lhtml = resp.read().decode("utf-8")
        assert "AdsterraFleet CRM" in lhtml

    # Test lock -> /crm redirects -> unlock-dev restores open mode (only if no password set)
    if not pdata["profile"]["has_password"]:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        logout_req = urllib.request.Request(
            "http://127.0.0.1:5050/api/auth/logout",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(logout_req, timeout=5) as r_out:
            assert json.loads(r_out.read().decode("utf-8"))["redirect"] == "/crm/login"

        # Visiting /, /crm, /classic, or /autopublish while locked redirects to /crm/login
        for protected_html in ("/", "/crm", "/classic", "/autopublish"):
            with opener.open(f"http://127.0.0.1:5050{protected_html}", timeout=5) as r_html:
                assert r_html.geturl().endswith("/crm/login"), f"{protected_html} did not redirect to /crm/login"

        # Sensitive GET & POST /api/* endpoints return 401 while locked
        for locked_get in ("/api/profile", "/api/config", "/api/status", "/api/autopublish/stats", "/api/gsc/status"):
            try:
                opener.open(f"http://127.0.0.1:5050{locked_get}", timeout=5)
                raise AssertionError(f"{locked_get} unexpectedly accessible while locked")
            except urllib.error.HTTPError as err:
                assert err.code == 401

        try:
            post_cfg = urllib.request.Request(
                "http://127.0.0.1:5050/api/config",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener.open(post_cfg, timeout=5)
            raise AssertionError("POST /api/config unexpectedly accessible while locked")
        except urllib.error.HTTPError as err:
            assert err.code == 401

        # Public /api/autopublish/preview stays open for preview widgets
        with opener.open("http://127.0.0.1:5050/api/autopublish/preview", timeout=5) as r_prev:
            assert r_prev.status == 200

        # Restore open state via unlock-dev cleanly
        unlock_req = urllib.request.Request(
            "http://127.0.0.1:5050/api/auth/unlock-dev",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(unlock_req, timeout=5) as r_un:
            assert json.loads(r_un.read().decode("utf-8"))["ok"] is True
