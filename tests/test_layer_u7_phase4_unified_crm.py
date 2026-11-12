"""Verification tests for Layer U7: Unified Phase 4 Farm & AI Ops inside Vuexy CRM (ui.py + admin_ui)."""
from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Tuple

import httpx
import pytest

import ui
from admin_ui import profile_auth
from admin_ui.shell import render_crm_shell
from phase3.db.migrations.runner import apply_migrations


def _seed_unified_phase3_db(db_path: Path) -> dict:
    """Seed canonical Phase 3 SQLite tables for unified CRM HTTP verification."""
    apply_migrations(db_path)
    now = time.time()
    base_day_ts = now - 6 * 86400.0

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO p3_farm_devices (
                device_id, usb_port, cdp_port, b1_port, status,
                consecutive_failures, quarantined_until, total_sessions,
                total_clicks, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("u7-pixel-01", "1-1.1", 9222, 8765, "healthy", 0, 0.0, 5, 1, now - 15),
        )
        conn.execute(
            """
            INSERT INTO p3_cgnat_slots (
                device_id, ip_address, subnet_24, subnet_20, active, acquired_at, released_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("u7-pixel-01", "100.64.55.10", "100.64.55.0/24", "100.64.48.0/20", 1, now - 60, None),
        )
        conn.execute(
            """
            INSERT INTO p3_sessions (
                session_id, correlation_id, device_id, mode, domain, ip_address,
                subnet_24, subnet_20, status, started_at, ended_at, dwell_seconds, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "u7-sess-001",
                "u7-corr-001",
                "u7-pixel-01",
                "paper",
                "loanraaj.com",
                "100.64.55.10",
                "100.64.55.0/24",
                "100.64.48.0/20",
                "completed",
                now - 120,
                now - 60,
                60.0,
                "",
            ),
        )
        daily_actuals = [10.0, 9.5, 11.0, 8.5, 10.5, 13.0]
        for idx, rev in enumerate(daily_actuals):
            ts = base_day_ts + idx * 86400.0
            conn.execute(
                """
                INSERT INTO p3_forecasts (
                    horizon_days, sample_count, method,
                    p10_revenue, p50_revenue, p90_revenue,
                    p10_ecpm, p50_ecpm, p90_ecpm, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 30, "irls_quantile", 8.0, 10.0, 12.0, 4.0, 5.0, 6.0, ts),
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
                    f"u7-sess-d-{idx}",
                    f"u7-corr-d-{idx}",
                    "u7-pixel-01",
                    "loanraaj.com",
                    "banner",
                    "paper_click",
                    0,
                    "null",
                    "yolo",
                    0.95,
                    "OK",
                    0,
                    rev * 1000.0,
                    0.05,
                    rev,
                    "normal_policy",
                    ts + 30.0,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "total_sessions": 1,
        "active_devices": 1,
        "actual_revenue": sum(daily_actuals),
    }


def _start_ui_server(port: int = 0) -> Tuple[str, ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", port), ui.UIRequestHandler)
    bound_host, bound_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://{bound_host}:{bound_port}", server, thread


def _port_is_free(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        return sock.connect_ex((host, port)) != 0
    finally:
        sock.close()


def test_u7_shell_completeness_and_u1_u6_preservation() -> None:
    """render_crm_shell() preserves U1-U6 views/links and embeds Phase 4 Farm & AI Ops cleanly."""
    html = render_crm_shell()

    # Existing U1-U6 views and markers
    for marker in (
        'id="view-overview"',
        'id="view-autopublish"',
        'id="view-monetization"',
        'id="view-network"',
        'id="view-growth"',
        'id="view-profile"',
        'id="view-settings"',
        "Step 6 / 6 Live",
        'href="/classic"',
        'href="/autopublish"',
        "Component U1&ndash;U6 Live",
    ):
        assert marker in html, f"Missing preserved U1-U6 marker: {marker}"

    # Phase 4 embedded section MUST NOT have active class initially
    m = re.search(r'<section[^>]*id="view-phase4-farm"[^>]*>', html)
    assert m is not None, "Missing embedded #view-phase4-farm section"
    section_tag = m.group(0)
    assert 'class="crm-view"' in section_tag
    assert "active" not in section_tag.split('class="')[1].split('"')[0].split()

    # Sidebar nav link, badge, Quick Switch shortcut, calibration controls, and JS script
    assert 'href="#phase4-farm"' in html
    assert 'data-crm-view="phase4-farm"' in html
    assert 'id="sidebarPhase4Badge"' in html
    assert 'id="p4BtnRunCalibration"' in html
    assert 'id="p4CalibrationSection"' in html
    assert '<script src="/crm-assets/js/crm-phase4.js"></script>' in html

    # Quick Switch shortcut check (appears at least twice: sidebar + navbar quick switch)
    assert html.count('data-crm-view="phase4-farm"') >= 2


def test_u7_js_safety_syntax_and_search_json() -> None:
    """Validate JS syntax, zero XSS sinks, and search-vertical.json navigation entries."""
    repo_root = Path(__file__).resolve().parent.parent
    crm_phase4_js = repo_root / "admin_ui" / "assets" / "js" / "crm-phase4.js"
    crm_shell_js = repo_root / "admin_ui" / "assets" / "js" / "crm-shell.js"
    search_json = repo_root / "admin_ui" / "assets" / "json" / "search-vertical.json"

    phase4_src = crm_phase4_js.read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert forbidden not in phase4_src, f"Forbidden DOM sink {forbidden!r} found in crm-phase4.js"

    node_bin = shutil.which("node")
    assert node_bin, "node executable required to syntax-check CRM JS files"
    for js_file in (crm_shell_js, crm_phase4_js):
        res = subprocess.run([node_bin, "--check", str(js_file)], capture_output=True, text=True)
        assert res.returncode == 0, f"node --check failed for {js_file}: {res.stderr}"

    nav = json.loads(search_json.read_text(encoding="utf-8"))
    classic_urls = [item["url"] for item in nav["navigation"]["classic"]]
    assert "/classic" in classic_urls
    assert "/autopublish" in classic_urls
    assert "/" not in classic_urls

    workspace_urls = [item["url"] for item in nav["navigation"]["workspaces"]]
    assert "#phase4-farm" in workspace_urls
    assert "#overview" in workspace_urls

    suggestion_ws = nav["suggestions"].get("Workspaces", [])
    assert any(item.get("url") == "#phase4-farm" for item in suggestion_ws)


def test_u7_ui_server_unified_routes_vhost_auth_and_phase4_apis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify ui.py live HTTP routes, VHost isolation, auth 401 gate, and Phase 4 APIs."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(profile_auth, "DEFAULT_STATE_DIR", state_dir)

    db_path = tmp_path / "phase3.db"
    missing_legacy_db = tmp_path / "missing_sessions.db"
    safe_mode_path = tmp_path / "safe_mode.json"
    safe_mode_path.write_text(
        json.dumps({"active": False, "entry_reason": "", "clean_window_count": 3}),
        encoding="utf-8",
    )
    expected = _seed_unified_phase3_db(db_path)

    for env_key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "PHASE3_ALERT_WEBHOOK_URL"):
        monkeypatch.delenv(env_key, raising=False)
    monkeypatch.setenv("PHASE4_DB_PATH", str(db_path))
    monkeypatch.setenv("PHASE4_LEGACY_DB_PATH", str(missing_legacy_db))
    monkeypatch.setenv("PHASE4_SAFE_MODE_PATH", str(safe_mode_path))
    monkeypatch.setenv("PHASE4_CALIBRATION_WINDOW_DAYS", "30")

    ports_to_test = [0]
    if _port_is_free("127.0.0.1", 5050):
        ports_to_test.append(5050)

    for target_port in ports_to_test:
        base_url, server, thread = _start_ui_server(port=target_port)
        try:
            with httpx.Client(base_url=base_url, timeout=5.0) as client:
                # 1. Unified CRM on / and /crm
                for route in ("/", "/crm"):
                    resp = client.get(route)
                    assert resp.status_code == 200
                    assert "no-store" in resp.headers.get("cache-control", "")
                    assert "AdsterraFleet CRM |" in resp.text
                    assert 'id="view-phase4-farm"' in resp.text
                    assert 'src="/crm-assets/js/crm-phase4.js"' in resp.text

                # 2. Legacy /classic & /autopublish preserved
                cls_resp = client.get("/classic")
                assert cls_resp.status_code == 200
                assert 'id="bannerVaultCard"' in cls_resp.text
                assert 'href="/"' in cls_resp.text

                ap_resp = client.get("/autopublish")
                assert ap_resp.status_code == 200
                assert len(ap_resp.text) > 500

                # 3. Domain VHost preservation for loanraaj.com
                vh_resp = client.get("/", headers={"Host": "loanraaj.com"})
                assert vh_resp.status_code == 200
                assert "AdsterraFleet CRM |" not in vh_resp.text
                assert "loanraaj" in vh_resp.text.lower()

                # 4. Unlocked Phase 4 APIs
                health_resp = client.get("/api/phase4/health")
                assert health_resp.status_code == 200
                health = health_resp.json()
                assert health["ok"] is True
                assert health["db_ok"] is True

                dash_resp = client.get("/api/phase4/dashboard")
                assert dash_resp.status_code == 200
                dash = dash_resp.json()
                assert dash["ok"] is True
                assert dash["kpis"]["total_sessions"] == expected["total_sessions"]
                assert dash["kpis"]["active_devices"] == expected["active_devices"]
                assert dash["kpis"]["p50_forecast_vs_actual"]["actual_revenue"] == pytest.approx(
                    expected["actual_revenue"]
                )

                cal_post = client.post("/api/phase4/calibration/run", json={})
                assert cal_post.status_code == 200
                cal_body = cal_post.json()
                assert cal_body["ok"] is True
                assert cal_body["report"]["status"] == "ok"
                assert cal_body["report"]["persisted"] is True

                dash_after = client.get("/api/phase4/dashboard").json()
                assert len(dash_after["calibration_reports"]) >= 1
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3.0)

    # 5. Auth lock check (require_login=True blocks /api/phase4/* with 401 when unauthenticated)
    ok_pw, _, _ = profile_auth.set_password("StrongPass9!", "StrongPass9!", require_login=True, state_dir=state_dir)
    assert ok_pw is True

    base_url, server, thread = _start_ui_server(port=0)
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            for method, endpoint in (
                ("GET", "/api/phase4/health"),
                ("GET", "/api/phase4/dashboard"),
                ("POST", "/api/phase4/calibration/run"),
            ):
                unauth = client.request(method, endpoint)
                assert unauth.status_code == 401, f"Expected 401 for locked {method} {endpoint}"
                assert unauth.json().get("locked") is True

            # Authenticated request with valid session cookie succeeds
            tok = profile_auth.create_session_token("PytestU7/1.0", state_dir=state_dir)
            auth_headers = {"Cookie": f"{profile_auth.COOKIE_NAME}={tok}"}
            auth_health = client.get("/api/phase4/health", headers=auth_headers)
            assert auth_health.status_code == 200
            assert auth_health.json()["ok"] is True

            auth_dash = client.get("/api/phase4/dashboard", headers=auth_headers)
            assert auth_dash.status_code == 200
            assert auth_dash.json()["ok"] is True

            auth_cal = client.post("/api/phase4/calibration/run", json={}, headers=auth_headers)
            assert auth_cal.status_code == 200
            assert auth_cal.json()["ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)
