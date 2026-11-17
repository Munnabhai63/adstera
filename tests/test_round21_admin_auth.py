"""tests/test_round21_admin_auth.py — Round 21 verification suite for deny-by-default auth guard and branded landing page."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Generator, Tuple

import httpx
import pytest
from bs4 import BeautifulSoup

from admin_ui import auth_guard, profile_auth
try:
    from admin_ui.views.login_branded import render_login_branded
except ImportError:
    render_login_branded = None
import ui

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _start_ui_server(port: int = 0) -> Tuple[str, ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", port), ui.UIRequestHandler)
    bound_host, bound_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://{bound_host}:{bound_port}", server, thread


@pytest.fixture
def auth_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Tuple[httpx.Client, str, Path, str, str], None, None]:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(profile_auth, "DEFAULT_STATE_DIR", state_dir)
    monkeypatch.delenv("PHASE4_FIRST_RUN_SETUP", raising=False)

    pw = "AdminSecret2026!#"
    email = "admin@adsterrafleet.local"
    profile_auth.set_password(pw, confirm_password=pw, require_login=True, state_dir=state_dir)
    profile_auth.save_profile({"email": email}, state_dir=state_dir)

    base_url, server, thread = _start_ui_server(port=0)
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            yield client, base_url, state_dir, email, pw
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)


def test_01_all_api_literals_in_ui_protected() -> None:
    """1. every '/api/...' literal in ui.py is protected (none public except the whitelist)."""
    ui_src = (PROJECT_ROOT / "ui.py").read_text(encoding="utf-8")
    api_literals = set(re.findall(r'["\'](/api/[a-zA-Z0-9_\-\./]+)["\']', ui_src))
    assert len(api_literals) >= 60, f"Expected at least 60 API routes, found {len(api_literals)}"

    public_api_count = 0
    for route in api_literals:
        if auth_guard.is_public_path(route):
            assert route == "/api/auth/login", f"Unexpected public API route: {route}"
            public_api_count += 1

    assert public_api_count == 1, f"Expected exactly 1 public API route, found {public_api_count}"
    assert auth_guard.PUBLIC_API_PATHS == frozenset({"/api/auth/login"})


def test_02_deny_by_default_unlisted_api_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """2. deny-by-default: invented path /api/zzz_unlisted -> 401."""
    client, *_ = auth_server
    r = client.get("/api/zzz_unlisted")
    assert r.status_code == 401
    body = r.json()
    assert body.get("ok") is False
    assert body.get("locked") is True
    assert body.get("error") == "unauthorized"


def test_03_get_autopublish_stats_no_cookie_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """3. GET /api/autopublish/stats, no cookie -> 401, body has 'locked': true."""
    client, *_ = auth_server
    r = client.get("/api/autopublish/stats")
    assert r.status_code == 401
    body = r.json()
    assert body.get("ok") is False
    assert body.get("locked") is True
    assert body.get("error") == "unauthorized"


def test_04_get_adsterra_funnel_no_cookie_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """4. GET /api/adsterra/funnel, no cookie -> 401."""
    client, *_ = auth_server
    r = client.get("/api/adsterra/funnel")
    assert r.status_code == 401
    body = r.json()
    assert body.get("locked") is True


def test_05_get_config_no_cookie_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """5. GET /api/config, no cookie -> 401."""
    client, *_ = auth_server
    r = client.get("/api/config")
    assert r.status_code == 401
    body = r.json()
    assert body.get("locked") is True


def test_06_get_crm_no_cookie_redirects_302(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """6. GET /crm, no cookie -> 302 to /crm/login."""
    client, *_ = auth_server
    r = client.get("/crm", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("Location") == "/crm/login"


def test_07_get_crm_login_no_cookie_returns_200(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """7. GET /crm/login, no cookie -> 200, contains 'Sign in'."""
    client, *_ = auth_server
    r = client.get("/crm/login")
    assert r.status_code == 200
    assert "Sign In" in r.text or "Sign in" in r.text or "sign-in" in r.text.lower()


def test_08_get_crm_assets_no_cookie_returns_200(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """8. GET /crm-assets/<real file>, no cookie -> 200."""
    client, *_ = auth_server
    r = client.get("/crm-assets/js/crm-shell.js")
    assert r.status_code == 200
    assert len(r.text) > 100


def test_09_post_login_correct_credentials_returns_200_and_cookie(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """9. POST /api/auth/login correct creds -> 200 + Set-Cookie."""
    client, _, _, email, pw = auth_server
    r = client.post("/api/auth/login", json={"identifier": email, "password": pw})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    set_cookie = r.headers.get("Set-Cookie", "")
    assert f"{profile_auth.COOKIE_NAME}=" in set_cookie


def test_10_post_login_wrong_identifier_form_post_redirects(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """10. same with wrong identifier -> 302 ?error=invalid."""
    client, _, _, _, pw = auth_server
    r = client.post("/api/auth/login", data={"identifier": "wrong_ident", "password": pw}, follow_redirects=False)
    assert r.status_code == 302
    assert "?error=invalid" in r.headers.get("Location", "")


def test_11_login_then_get_protected_route_with_cookie_returns_200(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """11. login, then GET a protected route WITH cookie -> 200."""
    client, _, _, email, pw = auth_server
    r = client.post("/api/auth/login", json={"identifier": email, "password": pw})
    assert r.status_code == 200
    cookie_val = r.headers.get("Set-Cookie", "").split(";")[0]

    r_prot = client.get("/api/config", headers={"Cookie": cookie_val})
    assert r_prot.status_code == 200
    assert "config" in r_prot.json()


def test_12_rate_limit_six_bad_logins_trips_too_many_attempts(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """12. 6 bad logins -> the 6th is too_many_attempts."""
    client, _, state_dir, email, _ = auth_server
    for idx in range(5):
        res = client.post("/api/auth/login", json={"identifier": email, "password": "WrongPassword1!"})
        assert res.status_code == 401
        assert res.json().get("error") != "too_many_attempts", f"Premature rate limit at attempt {idx+1}"

    # 6th attempt must be blocked by rate limiter
    res6 = client.post("/api/auth/login", json={"identifier": email, "password": "WrongPassword1!"})
    assert res6.status_code == 401
    assert res6.json().get("error") == "too_many_attempts"


def test_13_landing_page_zero_external_requests() -> None:
    """13. landing page has ZERO external requests (regex src=/href=/@import for http)."""
    html = render_login_branded({})
    external_refs = re.findall(r'(?:src|href|url|@import)\s*=\s*["\']?https?://', html, re.IGNORECASE)
    assert len(external_refs) == 0, f"Found external requests: {external_refs}"


def test_14_landing_page_zero_img_and_zero_external_script_src() -> None:
    """14. landing page has ZERO <img> and ZERO external <script src>."""
    html = render_login_branded({})
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.find_all("img")) == 0, "Found <img> tag in branded landing page"
    script_srcs = [s.get("src") for s in soup.find_all("script") if s.get("src")]
    assert len(script_srcs) == 0, f"Found script src: {script_srcs}"


def test_15_landing_page_contains_meta_robots_noindex() -> None:
    """15. landing page contains <meta name="robots" content="noindex."""
    html = render_login_branded({})
    soup = BeautifulSoup(html, "html.parser")
    meta_robots = soup.find("meta", attrs={"name": "robots"})
    assert meta_robots is not None, "Missing <meta name='robots'> tag"
    assert "noindex" in str(meta_robots.get("content", "")).lower()


def test_16_landing_page_renders_under_26_kb() -> None:
    """16. landing page renders in <= 26 KB."""
    html_bytes = render_login_branded({}).encode("utf-8")
    assert len(html_bytes) <= 26 * 1024, f"Landing page is {len(html_bytes)} bytes, exceeds 26 KB"


def test_17_landing_page_works_plain_form_post_no_js() -> None:
    """17. landing page works as a plain form POST with JS disabled."""
    html = render_login_branded({})
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    assert form is not None, "Missing <form> element"
    assert form.get("method", "").upper() == "POST"
    assert "/api/auth/login" in form.get("action", "")
    assert form.find("input", attrs={"name": "email"}) is not None or form.find("input", attrs={"name": "identifier"}) is not None
    assert form.find("input", attrs={"name": "password"}) is not None
    btn = form.find("button", attrs={"type": "submit"}) or form.find("input", attrs={"type": "submit"})
    assert btn is not None, "Missing submit button on form"


def test_18_phase4_first_run_setup_bypasses_lock(auth_server: Tuple[httpx.Client, str, Path, str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """18. PHASE4_FIRST_RUN_SETUP=1 still bypasses the lock."""
    client, *_ = auth_server
    monkeypatch.setenv("PHASE4_FIRST_RUN_SETUP", "1")
    r = client.get("/api/config")
    assert r.status_code == 200
    assert "config" in r.json()


def test_19_design_unchanged_assets_and_shell_empty_diff() -> None:
    """19. design unchanged: admin_ui/assets/** and shell.py have an empty git diff."""
    for path in ("admin_ui/assets", "admin_ui/shell.py"):
        res = subprocess.run(["git", "diff", "origin/arena/7a0464cb-adstera", "--", path], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        assert res.stdout.strip() == "", f"Unexpected git diff in {path}:\n{res.stdout}"


def test_20_render_login_branded_shows_eight_integration_cards() -> None:
    """20. render_login_branded output still shows 8 integration cards and wires."""
    html = render_login_branded({})
    cards = re.findall(r'class="node-card\b', html)
    assert len(cards) == 8, f"Expected 8 cards, found {len(cards)}"
    wires = re.findall(r'class="wire-charge\b', html)
    assert len(wires) == 8, f"Expected 8 wire paths, found {len(wires)}"
