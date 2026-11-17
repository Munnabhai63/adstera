"""
tests/test_round22_content_deploy.py — Round 22 verification suite:
Corpus merge invariants, 301 host-level redirects, deploy control,
content workspace API, state initialization, and panel integrity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from typing import Generator, Tuple

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from admin_ui import auth_guard, profile_auth
import admin_ui.deploy_content_service as deploy_service
from admin_ui.deploy_content_service import KNOWN_DOMAINS
import content_quality_gate
from scripts.seo_onpage_audit import get_all_article_paths, audit_article
import ui


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
        with httpx.Client(base_url=base_url, timeout=15.0) as client:
            yield client, base_url, state_dir, email, pw
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)


def test_01_after_merge_invariants() -> None:
    """1. after merge: 404 index.html, 221 stubs in map, 57 articles >= 3000."""
    sites_dir = PROJECT_ROOT / "sites"
    all_html = list(sites_dir.glob("**/index.html"))
    assert len(all_html) == 404, f"Expected 404 index.html, got {len(all_html)}"

    r20_path = PROJECT_ROOT / "data" / "redirects_round20.json"
    assert r20_path.exists(), "redirects_round20.json must exist"
    with open(r20_path, "r", encoding="utf-8") as f:
        r20_entries = json.load(f)
    assert len(r20_entries) == 221, f"Expected 221 redirect map entries, got {len(r20_entries)}"

    article_paths = get_all_article_paths(sites_dir)
    assert len(article_paths) == 57, f"Expected 57 published articles >= 3000, got {len(article_paths)}"

    stubs_count = sum(
        1 for p in all_html
        if content_quality_gate.is_redirect_stub(p.read_text(encoding="utf-8", errors="ignore"))
    )
    assert stubs_count in (221, 222), f"Expected 221 (or 222 with legacy) stubs, got {stubs_count}"


def test_02_every_redirect_has_matching_line_in_redirects() -> None:
    """2. every redirect in data/redirects_round20.json has a matching line in host _redirects."""
    r20_path = PROJECT_ROOT / "data" / "redirects_round20.json"
    with open(r20_path, "r", encoding="utf-8") as f:
        r20_entries = json.load(f)

    for entry in r20_entries:
        dom = entry["domain"]
        from_slug = entry["from_slug"]
        to_slug = entry["to_slug"]
        dest = f"/category/{to_slug.split('/', 1)[1]}" if to_slug.startswith("category/") else (to_slug if to_slug.startswith("/") else f"/{to_slug}")

        red_file = PROJECT_ROOT / "sites" / dom / "_redirects"
        assert red_file.exists(), f"_redirects missing for {dom}"
        content = red_file.read_text(encoding="utf-8")
        assert f"/{from_slug} " in content and " 301" in content, (
            f"Missing redirect entry in {dom}/_redirects for {from_slug} -> {dest}"
        )


def test_03_no_duplicate_lines_in_any_redirects_file() -> None:
    """3. no duplicate lines in any _redirects file."""
    for dom in KNOWN_DOMAINS:
        red_file = PROJECT_ROOT / "sites" / dom / "_redirects"
        assert red_file.exists(), f"_redirects missing for {dom}"
        lines = [l.strip() for l in red_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        unique_lines = set(lines)
        assert len(lines) == len(unique_lines), f"Duplicate lines detected in {dom}/_redirects"


def test_04_every_redirects_destination_resolves_to_existing_directory() -> None:
    """4. every _redirects destination resolves to an existing directory."""
    r20_path = PROJECT_ROOT / "data" / "redirects_round20.json"
    with open(r20_path, "r", encoding="utf-8") as f:
        r20_entries = json.load(f)

    for entry in r20_entries:
        dom = entry["domain"]
        to_slug = entry["to_slug"].strip("/")
        dest_dir = PROJECT_ROOT / "sites" / dom / to_slug
        assert dest_dir.is_dir(), f"Destination directory does not exist: {dom}/{to_slug}"


def test_05_get_content_articles_unauth_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """5. GET /api/content/articles without a cookie -> 401."""
    client, *_ = auth_server
    r = client.get("/api/content/articles")
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


def test_06_get_deploy_status_unauth_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """6. GET /api/deploy/status without a cookie -> 401."""
    client, *_ = auth_server
    r = client.get("/api/deploy/status")
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


def test_07_post_deploy_sites_unauth_returns_401(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """7. POST /api/deploy/sites without a cookie -> 401."""
    client, *_ = auth_server
    r = client.post("/api/deploy/sites", json={"domains": "all"})
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


def test_08_get_content_articles_with_cookie_returns_200_and_ten_domains(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """8. GET /api/content/articles with a cookie -> 200, JSON, contains the ten domains."""
    client, _, _, email, pw = auth_server
    login_resp = client.post("/api/auth/login", json={"identifier": email, "password": pw})
    assert login_resp.status_code == 200

    r = client.get("/api/content/articles")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "articles" in data
    assert "domains" in data
    for d in KNOWN_DOMAINS:
        assert d in data["domains"]


def test_09_content_list_excludes_redirect_stubs_from_article_count(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """9. the content list excludes redirect stubs from the article count."""
    client, _, _, email, pw = auth_server
    client.post("/api/auth/login", json={"identifier": email, "password": pw})

    r = client.get("/api/content/articles")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 57, f"Expected count == 57, got {data['count']}"
    assert data["stubs_count"] == 221, f"Expected stubs_count == 221, got {data['stubs_count']}"
    for art in data["articles"]:
        assert art["is_stub"] is False
        assert art["prose_words"] >= 3000


def test_10_article_detail_rejects_path_traversal(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """10. article detail rejects path traversal (?slug=../../etc/passwd) -> 400."""
    client, _, _, email, pw = auth_server
    client.post("/api/auth/login", json={"identifier": email, "password": pw})

    r1 = client.get("/api/content/article?slug=../../etc/passwd")
    assert r1.status_code == 400

    r2 = client.get("/api/content/article?domain=loanraaj.com&slug=../../etc/passwd")
    assert r2.status_code == 400


def test_11_article_detail_rejects_domain_not_in_known_ten(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """11. article detail rejects a domain not in the known ten -> 400."""
    client, _, _, email, pw = auth_server
    client.post("/api/auth/login", json={"identifier": email, "password": pw})

    r = client.get("/api/content/article?domain=evil.com&slug=test-article")
    assert r.status_code == 400
    assert "Invalid domain" in r.text or "error" in r.json()


def test_12_concurrent_post_deploy_sites_returns_409(auth_server: Tuple[httpx.Client, str, Path, str, str]) -> None:
    """12. concurrent POST /api/deploy/sites -> second returns 409."""
    client, _, _, email, pw = auth_server
    client.post("/api/auth/login", json={"identifier": email, "password": pw})

    # Simulate an active deployment holding the lock
    acquired = deploy_service._DEPLOY_LOCK.acquire(blocking=False)
    assert acquired is True, "Expected to acquire lock"
    try:
        r = client.post("/api/deploy/sites", json={"domains": "all"})
        assert r.status_code == 409
        body = r.json()
        assert body.get("ok") is False
        assert "409" in body.get("error", "") or "already running" in body.get("error", "")
    finally:
        deploy_service._DEPLOY_LOCK.release()


def test_13_article_list_is_cached_for_60s() -> None:
    """13. article list is cached: two calls within 60 s do not re-walk."""
    # Reset cache
    deploy_service._CONTENT_CACHE["timestamp"] = 0.0
    deploy_service._CONTENT_CACHE["payload"] = None
    deploy_service._CONTENT_CACHE["walk_count"] = 0

    first = deploy_service.get_articles_list()
    assert deploy_service._CONTENT_CACHE["walk_count"] == 1
    assert first["count"] == 57

    second = deploy_service.get_articles_list()
    assert deploy_service._CONTENT_CACHE["walk_count"] == 1, "Expected cached payload, but walk_count increased"
    assert second == first


def test_14_scripts_init_state_is_idempotent() -> None:
    """14. scripts/init_state.py is idempotent (run twice, no error)."""
    cmd = [sys.executable, "scripts/init_state.py"]
    r1 = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert r1.returncode == 0, f"First run failed: {r1.stderr}"

    r2 = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert r2.returncode == 0, f"Second run failed: {r2.stderr}"


def test_15_start_all_services_contains_autopublish() -> None:
    """15. start_all_services.bat contains autopublish_daemon and corrected rechargekar.com/admin URL."""
    bat_content = (PROJECT_ROOT / "start_all_services.bat").read_text(encoding="utf-8")
    assert "autopublish_daemon.py" in bat_content, "autopublish_daemon missing from start_all_services.bat"
    assert "https://rechargekar.com/admin" in bat_content, "rechargekar.com/admin missing from start_all_services.bat"


def test_16_shell_py_diff_limited_to_one_menu_li() -> None:
    """16. shell.py diff is limited to one menu <li> (assert the diff shape <= 20 lines)."""
    proc = subprocess.run(
        ["git", "diff", "round21-admin-auth", "admin_ui/shell.py"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    diff_text = proc.stdout
    changed_lines = [l for l in diff_text.splitlines() if (l.startswith("+") or l.startswith("-")) and not l.startswith("+++") and not l.startswith("---")]
    assert len(changed_lines) <= 20, f"Expected <= 20 changed lines in shell.py, found {len(changed_lines)}"
    assert 'data-crm-view="content"' in diff_text, "Missing data-crm-view='content' in shell.py diff"


def test_17_existing_round21_auth_tests_pass() -> None:
    """17. existing Round 21 auth tests still all pass."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_round21_admin_auth.py", "-q"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Round 21 tests failed:\n{proc.stdout}\n{proc.stderr}"


def test_18_render_login_branded_md5_unchanged() -> None:
    """18. render_login_branded unchanged (md5 still 3e7e79f197bc93b2b3f4bddf5b8e0de1)."""
    login_path = PROJECT_ROOT / "admin_ui" / "views" / "login_branded.py"
    assert login_path.exists(), "login_branded.py must exist"
    md5 = hashlib.md5(login_path.read_bytes()).hexdigest()
    assert md5 == "3e7e79f197bc93b2b3f4bddf5b8e0de1", f"Expected md5 3e7e79f197bc93b2b3f4bddf5b8e0de1, got {md5}"
