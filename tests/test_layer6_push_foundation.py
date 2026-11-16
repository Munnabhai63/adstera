"""
tests/test_layer6_push_foundation.py — Layer 6 End-to-End Verification Suite

Verifies:
1. Pure-Python NIST P-256 VAPID keypair + PKCS#8 PEM + ES256 JWT verified by Windows CNG ECDsa
2. Persistent VAPID state storage & zero private-key leakage in public status APIs
3. OneSignal REST client credential validation, secret redaction, and App stats fetch
4. Strict testing-phase delivery lock (`collect_only=True`, `delivery_enabled=False`)
5. SQLite `push_subscribers` idempotent upsert & masked stats queries
6. Idempotent HTML/SW injection across fixture sites + all 10 live canonical domains
7. `site_templates.render_master_page()` balanced `<div>` & embedded public push collector
8. Real Chromium Service Worker + `PushManager.handle()` collection flow against localhost site
9. Live QA Control Dashboard `/api/push/status` & `/api/push/deliver-test` endpoints
"""
from __future__ import annotations

import asyncio
import base64
import functools
import http.server
import json
import random
import socketserver
import subprocess
import sys
import pytest
import threading
from pathlib import Path

import httpx
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import db
import network_registry
import push_foundation
import push_manager
import site_templates
import vapid_keys


def test_vapid_p256_keygen_pkcs8_and_dotnet_verification() -> None:
    kp = vapid_keys.generate_vapid_keypair("mailto:admin@loanraaj.com")
    pub_raw = vapid_keys.b64url_decode(kp["public_key"])
    assert len(pub_raw) == 65
    assert pub_raw[0] == 0x04
    assert vapid_keys.validate_vapid_pair(kp["public_key"], kp["private_key"])

    hdr = vapid_keys.build_vapid_auth_header(
        "https://fcm.googleapis.com/fcm/send/sample-token",
        kp["public_key"],
        kp["private_key"],
        subject="mailto:admin@loanraaj.com",
    )
    assert hdr["Authorization"].startswith("vapid t=")
    decoded = vapid_keys.verify_vapid_jwt(hdr["jwt"], kp["public_key"])
    assert decoded["header"]["alg"] == "ES256"
    assert decoded["claims"]["aud"] == "https://fcm.googleapis.com"

    # Cross-verify PKCS#8 PEM + ES256 signature
    parts = hdr["jwt"].split(".")
    signing_input = f"{parts[0]}.{parts[1]}"
    raw_sig = vapid_keys.b64url_decode(parts[2])
    assert len(raw_sig) == 64

    # Native zero-dependency ES256 cryptographic verification (RFC 8292)
    assert vapid_keys.verify_vapid_jwt(hdr["jwt"], kp["public_key"]) is not None

    # If running on Windows with PowerShell available, also cross-verify with Windows CNG ECDsaCng
    import shutil
    if sys.platform == "win32" and shutil.which("powershell"):
        sig_b64 = base64.b64encode(raw_sig).decode("ascii")
        b64_pem = (
            kp["private_key_pem"]
            .replace("-----BEGIN PRIVATE KEY-----", "")
            .replace("-----END PRIVATE KEY-----", "")
            .replace("\r", "")
            .replace("\n", "")
            .strip()
        )
        ps_script = (
            f'$b=[Convert]::FromBase64String("{b64_pem}");'
            '$k=[System.Security.Cryptography.CngKey]::Import($b,[System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob);'
            '$ec=New-Object System.Security.Cryptography.ECDsaCng($k);'
            f'$data=[System.Text.Encoding]::ASCII.GetBytes("{signing_input}");'
            f'$sig=[Convert]::FromBase64String("{sig_b64}");'
            '$ec.HashAlgorithm=[System.Security.Cryptography.CngAlgorithm]::Sha256;'
            '$ok=$ec.VerifyData($data,$sig);'
            '$ec.Dispose();$k.Dispose();Write-Output $ok'
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "-"],
            input=ps_script,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        out = res.stdout.strip()
        assert out == "True", f"Windows ECDsaCng rejected signature: {out!r}"


def test_vapid_state_persistence_and_public_status_redacts_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    state_file = tmp_path / "vapid_keys.json"

    k1 = vapid_keys.load_or_create_vapid_keys(state_path=state_file, subject="mailto:test@karzseva.com")
    k2 = vapid_keys.load_or_create_vapid_keys(state_path=state_file, subject="mailto:test@karzseva.com")
    assert k1["public_key"] == k2["public_key"]
    assert k1["private_key"] == k2["private_key"]

    pub_status = vapid_keys.get_public_vapid_status(state_path=state_file)
    assert pub_status["configured"] is True
    assert pub_status["public_key"] == k1["public_key"]
    assert "private_key" not in pub_status
    assert "private_key_pem" not in pub_status

    k3 = vapid_keys.load_or_create_vapid_keys(state_path=state_file, force_rotate=True)
    assert k3["public_key"] != k1["public_key"]


def test_onesignal_credentials_validation_and_secret_redaction(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ONESIGNAL_APP_ID", raising=False)
    monkeypatch.delenv("ONESIGNAL_REST_API_KEY", raising=False)
    net_file = tmp_path / "push_network.json"
    client = push_manager.OneSignalPushClient(cfg={"push_notifications": {}}, state_path=net_file)

    try:
        client.save_credentials(app_id="00000000-0000-0000-0000-000000000000")
        assert False, "Expected ValueError for dummy UUID"
    except ValueError:
        pass

    valid_uuid = "a1b2c3d4-e5f6-4a7b-8c9d-0123456789ab"
    secret_rest = "os_v2_rest_secret_test_key_never_leak_999"
    saved = client.save_credentials(app_id=valid_uuid, rest_api_key=secret_rest)
    assert saved["configured"] is True
    assert saved["app_id"] == valid_uuid
    assert saved["rest_api_key_configured"] is True
    assert secret_rest not in json.dumps(saved)

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/apps/{valid_uuid}"
        assert request.headers["Authorization"] == f"Key {secret_rest}"
        return httpx.Response(200, json={"id": valid_uuid, "name": "LoanRaaj Push", "players": 42, "messageable_players": 39})

    with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
        stats = client.fetch_app_stats(client=http)
    assert stats["data_source"] == "onesignal_api"
    assert stats["players"] == 42
    assert stats["messageable_players"] == 39


def test_testing_phase_delivery_hard_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ONESIGNAL_APP_ID", raising=False)
    monkeypatch.delenv("ONESIGNAL_REST_API_KEY", raising=False)

    cfg = yaml.safe_load((ROOT_DIR / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["push_notifications"]["collect_only"] is True
    assert cfg["push_notifications"]["delivery_enabled"] is False

    mgr = push_manager.build_from_config(cfg)
    assert mgr.collect_only is True
    assert mgr.delivery_enabled is False

    calls = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"id": "msg-123", "recipients": 10})

    valid_uuid = "a1b2c3d4-e5f6-4a7b-8c9d-0123456789ab"
    client = push_manager.OneSignalPushClient(
        cfg=cfg,
        state_path=tmp_path / "push_network.json",
        app_id=valid_uuid,
        rest_api_key="os_v2_rest_secret_test_key_never_leak_999",
    )
    with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
        blocked = client.send_campaign("Test", "Msg", "https://loanraaj.com/", client=http)
        assert blocked["delivered"] is False
        assert blocked["status"] == "blocked_testing_phase"
        assert calls == 0

        sent = client.send_campaign(
            "Live Headline",
            "Live Push Body",
            "https://loanraaj.com/guide",
            collect_only=False,
            delivery_enabled=True,
            client=http,
        )
        assert sent["ok"] is True
        assert sent["delivered"] is True
        assert sent["recipients"] == 10
        assert calls == 1


def test_db_push_subscribers_upsert_and_stats(tmp_path: Path) -> None:
    orig_db = db._DB_PATH
    db._DB_PATH = tmp_path / "push_subs_test.db"
    try:
        db.init()
        ep = "https://fcm.googleapis.com/fcm/send/unique-sub-1"
        row1 = db.upsert_push_subscriber(
            domain="https://loanraaj.com/",
            endpoint=ep,
            provider="vapid_local",
            p256dh="PUBLIC_P256DH_TOKEN",
            auth_secret="AUTH_SECRET_VALUE_MUST_NOT_LEAK",
            proxy_id="px_us_1",
            geo_country="us",
            collect_only=True,
        )
        row2 = db.upsert_push_subscriber(
            domain="loanraaj.com",
            endpoint=ep,
            provider="onesignal",
            subscription_id="sub-uuid-1",
            proxy_id="px_us_2",
            geo_country="US",
            collect_only=True,
        )
        assert row1 == row2 > 0
        db.log_push_event("px_us_1", "loanraaj.com", "allow", 8.5, "US", "tier1")

        stats = db.get_push_subscriber_stats()
        assert stats["total_subscribers"] == 1
        assert stats["by_domain"]["loanraaj.com"] == 1
        assert stats["by_provider"]["onesignal"] == 1
        assert stats["allow_rate"] == 1.0
        assert "AUTH_SECRET_VALUE_MUST_NOT_LEAK" not in json.dumps(stats)
    finally:
        db._DB_PATH = orig_db


def test_push_foundation_injection_idempotency_div_balance_and_live_sites(tmp_path: Path) -> None:
    fixture_sites = tmp_path / "sites"
    monetag_sw = 'self.options = {"domain": "5gvci.com", "zoneId": 12227843}\n'
    for dom in ["loanraaj.com", "karzseva.com"]:
        d = fixture_sites / dom
        d.mkdir(parents=True, exist_ok=True)
        (d / "sw.js").write_text(monetag_sw, encoding="utf-8")
        (d / "index.html").write_text(
            f"<!DOCTYPE html><html><head><title>{dom}</title></head><body><div class='wrap'><p>Hi</p></div></body></html>",
            encoding="utf-8",
        )
        (d / "google31976c4df01121b2.html").write_text("google-site-verification: google31976c4df01121b2.html", encoding="utf-8")

    vapid_file = tmp_path / "vapid.json"
    cfg = {
        "push_notifications": {
            "enabled": True,
            "collect_only": True,
            "vapid_keys_path": str(vapid_file),
            "network_state_path": str(tmp_path / "push_net.json"),
        }
    }
    res1 = push_foundation.inject_push_all_sites(sites_dir=fixture_sites, dry_run=False, cfg=cfg)
    assert res1["errors"] == []
    assert res1["files_inserted"] == 2
    assert (fixture_sites / "loanraaj.com" / "sw.js").read_text(encoding="utf-8") == monetag_sw
    assert (fixture_sites / "loanraaj.com" / "push-sw.js").is_file()
    assert (fixture_sites / "loanraaj.com" / "OneSignalSDKWorker.js").is_file()

    # Re-run must be 100% idempotent
    res2 = push_foundation.inject_push_all_sites(sites_dir=fixture_sites, dry_run=False, cfg=cfg)
    assert res2["files_inserted"] == 0
    assert res2["files_updated"] == 0
    assert res2["files_unchanged"] == 2

    # Audit real live sites/ directory for all 10 domains
    live_cov = push_foundation.audit_sites_push_coverage(sites_dir=ROOT_DIR / "sites")
    assert live_cov["total_domains"] == 10
    assert live_cov["ready_domains"] == 10
    assert live_cov["all_ready"] is True
    assert live_cov["secret_leak_detected"] is False


def test_site_templates_emits_push_foundation_with_balanced_divs() -> None:
    cfg = network_registry.NETWORK_REGISTRY["karzseva"]
    html_out = site_templates.render_master_page(
        site_config=cfg,
        title="Layer 6 Template Check",
        desc="Checking push foundation script injection",
        canonical="https://karzseva.com/layer6-check",
        main_body="<main><div><p>Content</p></div></main>",
    )
    assert push_foundation.PUSH_MARKER_START in html_out
    assert "window.__ADSTERRA_PUSH__" in html_out
    assert "BEGIN PRIVATE KEY" not in html_out
    assert html_out.lower().count("<div") == html_out.lower().count("</div>")


@pytest.mark.browser
def test_playwright_real_chromium_push_collector_and_sw_registration(tmp_path: Path) -> None:
    from playwright.async_api import async_playwright

    site_dir = tmp_path / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    push_foundation.write_site_service_workers(site_dir)
    raw_html = (
        "<!DOCTYPE html><html><head><title>LoanRaaj Local</title></head>"
        "<body><h1>LoanRaaj Test</h1></body></html>"
    )
    kp = vapid_keys.generate_vapid_keypair("mailto:admin@loanraaj.com")
    injected_html, _ = push_foundation.inject_push_html_content(
        raw_html,
        "loanraaj.com",
        vapid_public_key=kp["public_key"],
        onesignal_app_id="",
    )
    (site_dir / "index.html").write_text(injected_html, encoding="utf-8")

    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    handler = functools.partial(_QuietHandler, directory=str(site_dir))

    async def _run() -> None:
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=False,
                        args=["--window-position=-2400,-2400", "--window-size=800,600"],
                    )
                    try:
                        context = await browser.new_context()
                        page = await context.new_page()
                        page_errors: list[str] = []
                        page.on("pageerror", lambda err: page_errors.append(str(err)))
                        await page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                        await page.wait_for_timeout(400)

                        push_cfg = await page.evaluate("() => window.__ADSTERRA_PUSH__")
                        assert push_cfg["domain"] == "loanraaj.com"
                        assert push_cfg["collectOnly"] is True
                        assert push_cfg["vapidPublicKey"] == kp["public_key"]

                        sw_info = await page.evaluate(
                            """async () => {
                                const reg = await navigator.serviceWorker.getRegistration('/');
                                return reg ? { scope: reg.scope, active: !!(reg.active || reg.installing || reg.waiting) } : null;
                            }"""
                        )
                        assert sw_info is not None, "Expected /push-sw.js registration"
                        assert "127.0.0.1" in sw_info["scope"]

                        mgr = push_manager.PushManager(
                            trigger_prob=1.0,
                            allow_prob=1.0,
                            min_delay_s=0.0,
                            max_delay_s=0.01,
                            collect_only=True,
                            delivery_enabled=False,
                            vapid_public_key=kp["public_key"],
                        )
                        res = await mgr.handle(
                            context=context,
                            page=page,
                            rng=random.Random(42),
                            proxy_country="US",
                            cmp_accepted=True,
                            domain="loanraaj.com",
                        )
                        assert res["triggered"] is True
                        assert res["action"] == "allow"
                        assert res["collect_only"] is True
                        assert page_errors == []
                    finally:
                        await browser.close()
            finally:
                httpd.shutdown()

    asyncio.run(_run())


def test_live_ui_push_endpoints() -> None:
    with httpx.Client(base_url="http://127.0.0.1:5050", timeout=15.0) as client:
        r_status = client.get("/api/push/status")
        assert r_status.status_code == 200
        d = r_status.json()
        assert d["success"] is True
        assert d["vapid"]["configured"] is True
        assert "private_key" not in d["vapid"]
        assert "private_key_pem" not in d["vapid"]
        assert d["onesignal"]["delivery_locked"] is True
        assert d["sites_coverage"]["total_domains"] == 10
        assert d["sites_coverage"]["ready_domains"] == 10

        r_lock = client.post("/api/push/deliver-test", json={"domain": "loanraaj.com"})
        assert r_lock.status_code == 200
        dl = r_lock.json()
        assert dl["success"] is True
        assert dl["result"]["delivered"] is False
        assert dl["result"]["status"] == "blocked_testing_phase"
