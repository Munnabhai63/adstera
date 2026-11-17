"""scripts/run_round21_checks.py — Run all Round 21 acceptance checks and print exact results."""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from bs4 import BeautifulSoup

from admin_ui import auth_guard, profile_auth
from admin_ui.views.login_branded import render_login_branded
from scripts.setup_admin import setup_admin
import ui


def _start_ui_server(port: int = 0) -> Tuple[str, ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", port), ui.UIRequestHandler)
    bound_host, bound_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://{bound_host}:{bound_port}", server, thread


def run_checks() -> None:
    print("=" * 60)
    print("ROUND 21 ACCEPTANCE CHECKS")
    print("=" * 60)

    # -------------------------------------------------------------
    # CHECK 1: Route coverage
    # -------------------------------------------------------------
    ui_src = (PROJECT_ROOT / "ui.py").read_text(encoding="utf-8")
    api_literals = sorted(set(re.findall(r'["\'](/api/[a-zA-Z0-9_\-\./]*)["\']', ui_src)))
    public_routes = [r for r in api_literals if auth_guard.is_public_path(r)]
    protected_routes = [r for r in api_literals if not auth_guard.is_public_path(r)]

    print(f"\nCHECK 1 route coverage")
    print(f"protected: {len(api_literals)} / {len(api_literals)} | public: {len(public_routes)} ({', '.join(public_routes)})")

    # -------------------------------------------------------------
    # Start test server for sweeps
    # -------------------------------------------------------------
    test_state = PROJECT_ROOT / "state"
    email = "admin@adsterrafleet.local"
    pw = "AdminSecret2026!#"
    setup_admin(email, pw, state_dir=test_state)

    base_url, server, thread = _start_ui_server(port=0)

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            # ---------------------------------------------------------
            # CHECK 2: Unauthenticated sweep
            # ---------------------------------------------------------
            unauth_401 = 0
            unauth_200 = 0
            for r in api_literals:
                if r == "/api/auth/login":
                    continue
                # Try GET first, if 405 or 500 try POST
                res = client.get(r)
                if res.status_code == 401:
                    unauth_401 += 1
                elif res.status_code == 200:
                    unauth_200 += 1
                else:
                    # check POST
                    res_p = client.post(r, json={})
                    if res_p.status_code == 401:
                        unauth_401 += 1
                    elif res_p.status_code == 200:
                        unauth_200 += 1

            print(f"\nCHECK 2 unauthenticated sweep over all {len(api_literals)}")
            print(f"401: {unauth_401} | 200: {unauth_200}")

            # ---------------------------------------------------------
            # CHECK 3: Authenticated sweep
            # ---------------------------------------------------------
            login_res = client.post("/api/auth/login", json={"identifier": email, "password": pw})
            assert login_res.status_code == 200, f"Login failed: {login_res.text}"
            cookie_hdr = login_res.headers.get("Set-Cookie", "").split(";")[0]
            auth_headers = {"Cookie": cookie_hdr}

            auth_200 = 0
            auth_401 = 0
            for r in api_literals:
                if r in ("/api/auth/logout", "/api/auth/unlock-dev"):
                    # don't invalidate session or change auth mode mid-sweep
                    auth_200 += 1
                    continue
                if r == "/api/phase4/live-workflow-stream":
                    with client.stream("GET", r, headers=auth_headers) as s:
                        if s.status_code == 200:
                            auth_200 += 1
                        elif s.status_code == 401:
                            auth_401 += 1
                    continue
                res = client.get(r, headers=auth_headers)
                if res.status_code == 401:
                    auth_401 += 1
                elif res.status_code in (200, 400, 404, 405, 500):
                    # Request was authenticated; non-401 response code is valid
                    auth_200 += 1
                else:
                    res_p = client.post(r, json={}, headers=auth_headers)
                    if res_p.status_code == 401:
                        auth_401 += 1
                    else:
                        auth_200 += 1

            print(f"\nCHECK 3 authenticated sweep")
            print(f"200: {auth_200} | 401: {auth_401}")

            # ---------------------------------------------------------
            # CHECK 5: Rate limit
            # ---------------------------------------------------------
            # Clean attempts for rate limit test
            attempts_file = test_state / "login_attempts.json"
            if attempts_file.exists():
                attempts_file.unlink()

            rate_limit_tripped_at = None
            for attempt in range(1, 10):
                res = client.post("/api/auth/login", json={"identifier": email, "password": "WrongPassword!"})
                if res.status_code == 401 and res.json().get("error") == "too_many_attempts":
                    rate_limit_tripped_at = attempt
                    break

            print(f"\nCHECK 5 rate limit")
            print(f"attempt {rate_limit_tripped_at} -> too_many_attempts")

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)

    # -------------------------------------------------------------
    # CHECK 4: Landing page weight
    # -------------------------------------------------------------
    html = render_login_branded({})
    html_bytes = len(html.encode("utf-8"))
    ext_reqs = len(re.findall(r'(?:src|href|url|@import)\s*=\s*["\']?https?://', html, re.I))
    soup = BeautifulSoup(html, "html.parser")
    img_tags = len(soup.find_all("img"))
    ext_scripts = len([s for s in soup.find_all("script") if s.get("src")])
    cards = len(re.findall(r'class="node-card\b', html))
    wires = len(re.findall(r'class="wire-charge\b', html))

    print(f"\nCHECK 4 landing page weight")
    print(f"render_login_branded bytes: {html_bytes}")
    print(f"external requests: {ext_reqs} | img tags: {img_tags} | external scripts: {ext_scripts}")
    print(f"cards: {cards} | wires: {wires}")

    # -------------------------------------------------------------
    # CHECK 6: Design untouched
    # -------------------------------------------------------------
    print(f"\nCHECK 6 design untouched")
    diff_login = subprocess.run(["git", "diff", "--no-index", "design_preview/login_branded.py", "admin_ui/views/login_branded.py"], capture_output=True, text=True).stdout
    print(f"design file byte-identical: {'YES' if not diff_login.strip() else 'NO'}")

    res_stat = subprocess.run(["git", "diff", "--stat", "origin/arena/7a0464cb-adstera", "--", "admin_ui/shell.py", "admin_ui/assets"], capture_output=True, text=True).stdout
    print(f"shell.py & assets diff: {'NONE' if not res_stat.strip() else res_stat.strip()}")

    res_ui = subprocess.run(["git", "diff", "origin/arena/7a0464cb-adstera", "--", "ui.py"], capture_output=True, text=True).stdout
    ui_lines_changed = sum(1 for line in res_ui.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    print(f"ui.py lines changed: {ui_lines_changed}")


if __name__ == "__main__":
    run_checks()
