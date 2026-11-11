"""
tests/test_layer5_gsc_oauth.py — Comprehensive Layer 5 GSC OAuth2, Real APIs & Weekly Report Tests.
"""
from __future__ import annotations

import asyncio
import datetime
import functools
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import gsc_auth
import gsc_monitor
import gsc_submitter
from gsc_auth import GSCAuthManager, SCOPE_INDEXING, SCOPE_WEBMASTERS, SCOPE_WEBMASTERS_RO, sign_rs256_jwt
from gsc_monitor import DEFAULT_DOMAINS, GSCMonitor
from gsc_submitter import GoogleIndexingSubmitter


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gsc_auth, "DEFAULT_SA_PATH", tmp_path / "state" / "gsc_service_account.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_OAUTH_TOKEN_PATH", tmp_path / "state" / "gsc_oauth_token.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_OAUTH_CLIENT_PATH", tmp_path / "state" / "gsc_oauth_client.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(gsc_monitor, "GSC_STATE_PATH", tmp_path / "state" / "gsc_metrics.json")
    monkeypatch.setattr(gsc_monitor, "WEEKLY_REPORT_STATE_PATH", tmp_path / "state" / "gsc_weekly_report_state.json")
    monkeypatch.setattr(gsc_monitor, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(gsc_submitter, "STATE_FILE", tmp_path / "state" / "gsc_submissions.json")
    for k in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GSC_SERVICE_ACCOUNT_JSON",
        "GSC_ACCESS_TOKEN",
        "GSC_SERVICE_ACCOUNT_KEY",
        "GSC_CLIENT_ID",
        "GSC_CLIENT_SECRET",
        "GSC_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)


@functools.lru_cache(maxsize=1)
def _generate_ephemeral_pkcs8_pem() -> str:
    """Generate an ephemeral 2048-bit PKCS#8 RSA test key using Windows .NET Cryptography."""
    ps_script = (
        '$p = New-Object System.Security.Cryptography.CngKeyCreationParameters;'
        '$p.ExportPolicy = [System.Security.Cryptography.CngExportPolicies]::AllowPlaintextExport;'
        '$k = [System.Security.Cryptography.CngKey]::Create([System.Security.Cryptography.CngAlgorithm]::Rsa, [NullString]::Value, $p);'
        '$b = $k.Export([System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob);'
        '$k.Dispose();'
        'Write-Output ("-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String($b, "InsertLineBreaks") + "`n-----END PRIVATE KEY-----")'
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        check=True,
    )
    pem = res.stdout.strip()
    assert "BEGIN PRIVATE KEY" in pem
    return pem


def _verify_jwt_with_dotnet(pem: str, jwt_str: str) -> bool:
    parts = jwt_str.split(".")
    assert len(parts) == 3
    signing_input = f"{parts[0]}.{parts[1]}"
    sig_b64url = parts[2]
    b64_key = pem.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "").replace("\r", "").replace("\n", "").strip()
    ps_script = (
        f'$b = [Convert]::FromBase64String("{b64_key}");'
        '$k = [System.Security.Cryptography.CngKey]::Import($b, [System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob);'
        '$r = New-Object System.Security.Cryptography.RSACng($k);'
        f'$s = "{sig_b64url}".Replace("-", "+").Replace("_", "/");'
        'while ($s.Length % 4 -ne 0) { $s += "=" };'
        '$sig = [Convert]::FromBase64String($s);'
        f'$data = [System.Text.Encoding]::ASCII.GetBytes("{signing_input}");'
        '$ok = $r.VerifyData($data, $sig, [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1);'
        '$r.Dispose(); $k.Dispose();'
        'Write-Output $ok'
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip().lower() == "true"


def test_rs256_jwt_cryptographic_verification() -> None:
    pem = _generate_ephemeral_pkcs8_pem()
    claims = {
        "iss": "gsc-bot@example-proj.iam.gserviceaccount.com",
        "scope": SCOPE_WEBMASTERS,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": 1700000000,
        "exp": 1700003600,
    }
    jwt_str = sign_rs256_jwt(claims, pem, key_id="key-test-1")
    assert _verify_jwt_with_dotnet(pem, jwt_str) is True


def test_service_account_oauth2_exchange_and_caching(tmp_path: Path) -> None:
    pem = _generate_ephemeral_pkcs8_pem()
    sa_data = {
        "type": "service_account",
        "project_id": "adstera-seo-test",
        "private_key_id": "kid123",
        "private_key": pem,
        "client_email": "gsc-reader@adstera-seo-test.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    mgr = GSCAuthManager(cfg={"gsc": {}}, env_path=tmp_path / ".env")
    saved = mgr.save_credentials_payload(sa_data, sa_target=gsc_auth.DEFAULT_SA_PATH)
    assert saved["saved"] is True
    assert saved["auth_type"] == "service_account"

    status = mgr.get_status()
    assert status["configured"] is True
    assert status["client_email"] == sa_data["client_email"]
    assert "private_key" not in json.dumps(status)

    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if str(request.url) == "https://oauth2.googleapis.com/token":
            token_calls += 1
            body = request.content.decode("utf-8")
            assert "jwt-bearer" in body
            return httpx.Response(200, json={"access_token": "ya29.mock-sa-token", "expires_in": 3600})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        tok1 = mgr.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)
        tok2 = mgr.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)

    assert tok1 == "ya29.mock-sa-token"
    assert tok2 == "ya29.mock-sa-token"
    assert token_calls == 1


def test_oauth2_pkce_code_exchange_and_refresh_flow(tmp_path: Path) -> None:
    client_secret_bundle = {
        "installed": {
            "client_id": "123456.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        }
    }
    mgr = GSCAuthManager(
        cfg={"gsc": {}},
        oauth_token_path=tmp_path / "state" / "gsc_oauth_token.json",
        oauth_client_path=tmp_path / "state" / "gsc_oauth_client.json",
    )
    saved_client = mgr.save_credentials_payload(client_secret_bundle)
    assert saved_client["auth_type"] == "oauth2_client_secret"

    auth_bundle = mgr.build_oauth_authorize_url()
    assert "accounts.google.com/o/oauth2/v2/auth" in auth_bundle["auth_url"]
    assert "code_challenge_method=S256" in auth_bundle["auth_url"]

    seen_grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8")
        if "grant_type=authorization_code" in body:
            seen_grants.append("authorization_code")
            return httpx.Response(200, json={"access_token": "ya29.init", "refresh_token": "1//mock-refresh", "expires_in": 3600})
        if "grant_type=refresh_token" in body:
            seen_grants.append("refresh_token")
            return httpx.Response(200, json={"access_token": "ya29.refreshed", "expires_in": 3600})
        return httpx.Response(400)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ex = mgr.exchange_oauth_code("4/mock-code", code_verifier=auth_bundle["code_verifier"], client=client)
        assert ex["saved"] is True
        assert ex["has_refresh_token"] is True
        mgr.clear_cache()
        refreshed = mgr.get_access_token(client=client)
        assert refreshed == "ya29.refreshed"

    assert seen_grants == ["authorization_code", "refresh_token"]
    status = mgr.get_status()
    assert status["auth_type"] == "oauth2_refresh_token"
    assert "1//mock-refresh" not in json.dumps(status)
    assert "GOCSPX-test-secret" not in json.dumps(status)


def test_save_credentials_rejects_bad_json(tmp_path: Path) -> None:
    mgr = GSCAuthManager(cfg={"gsc": {}})
    with pytest.raises(ValueError):
        mgr.save_credentials_payload({"type": "service_account", "client_email": "bad"})
    with pytest.raises(ValueError):
        mgr.save_credentials_payload("{not-json")


def test_gsc_monitor_honest_unconfigured_tags(tmp_path: Path) -> None:
    mon = GSCMonitor(cfg={"gsc": {"enabled": True}})
    est = mon.fetch_domain_performance("loanraaj.com", mock_fallback=True)
    assert est["is_mock"] is True
    assert est["data_source"] == "mock_estimate"
    assert est["credentials_configured"] is False

    strict = mon.fetch_domain_performance("loanraaj.com", mock_fallback=False)
    assert strict["data_source"] == "unconfigured"
    assert strict["impressions"] == 0


def test_gsc_monitor_live_search_console_apis(tmp_path: Path) -> None:
    pem = _generate_ephemeral_pkcs8_pem()
    sa_path = gsc_auth.DEFAULT_SA_PATH
    sa_path.parent.mkdir(parents=True, exist_ok=True)
    sa_path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "adstera-seo-live",
                "private_key": pem,
                "client_email": "gsc@adstera-seo-live.iam.gserviceaccount.com",
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://oauth2.googleapis.com/token":
            return httpx.Response(200, json={"access_token": "ya29.live-test", "expires_in": 3600})
        assert request.headers.get("authorization") == "Bearer ya29.live-test"

        if url == "https://www.googleapis.com/webmasters/v3/sites":
            return httpx.Response(
                200,
                json={
                    "siteEntry": [
                        {"siteUrl": "sc-domain:loanraaj.com", "permissionLevel": "siteOwner"},
                    ]
                },
            )
        if "/searchAnalytics/query" in url:
            body = json.loads(request.content.decode("utf-8"))
            if body.get("dimensions"):
                return httpx.Response(
                    200,
                    json={
                        "rows": [
                            {
                                "keys": ["pmegp loan apply online", "https://loanraaj.com/pmegp-loan"],
                                "clicks": 42,
                                "impressions": 620,
                                "ctr": 0.0677,
                                "position": 9.4,
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"rows": [{"clicks": 85, "impressions": 1940, "ctr": 0.0438, "position": 11.2}]},
            )
        if url.endswith("/sitemaps"):
            return httpx.Response(
                200,
                json={
                    "sitemap": [
                        {
                            "path": "https://loanraaj.com/sitemap.xml",
                            "lastSubmitted": "2026-11-10T10:00:00Z",
                            "contents": [{"type": "web", "submitted": "60", "indexed": "48"}],
                            "warnings": 0,
                            "errors": 0,
                        }
                    ]
                },
            )
        if url == "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect":
            return httpx.Response(
                200,
                json={
                    "inspectionResult": {
                        "indexStatusResult": {
                            "verdict": "PASS",
                            "coverageState": "Submitted and indexed",
                            "indexingState": "INDEXING_ALLOWED",
                            "lastCrawlTime": "2026-11-10T08:30:00Z",
                        }
                    }
                },
            )
        return httpx.Response(404)

    mon = GSCMonitor(cfg={"gsc": {"enabled": True, "service_account_json": str(sa_path)}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        perf = mon.fetch_domain_performance("loanraaj.com", days=7, inspect_homepage=True, client=client)

    assert perf["data_source"] == "google_search_console_api"
    assert perf["is_mock"] is False
    assert perf["credentials_configured"] is True
    assert perf["property_url"] == "sc-domain:loanraaj.com"
    assert perf["impressions"] == 1940
    assert perf["clicks"] == 85
    assert perf["avg_position"] == 11.2
    assert perf["indexed_pages"] == 48
    assert perf["is_indexed"] is True
    assert perf["top_queries"][0]["query"] == "pmegp loan apply online"
    assert len(perf["quick_wins"]) == 1
    assert perf["homepage_inspection"]["verdict"] == "PASS"


def test_gsc_monitor_403_unverified_property_does_not_lie(tmp_path: Path) -> None:
    mgr = GSCAuthManager(cfg={"gsc": {}}, direct_token="ya29.fake-bearer")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://www.googleapis.com/webmasters/v3/sites":
            return httpx.Response(200, json={"siteEntry": []})
        return httpx.Response(403, text="User does not have sufficient permission for site")

    mon = GSCMonitor(cfg={"gsc": {}}, auth_manager=mgr)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        strict = mon.fetch_domain_performance("loanraaj.com", mock_fallback=False, client=client)

    assert strict["data_source"] == "api_error"
    assert strict["is_mock"] is False
    assert "403" in str(strict["api_error"])


def test_gsc_submitter_real_indexing_and_sitemap_put(tmp_path: Path) -> None:
    mgr = GSCAuthManager(cfg={"gsc": {}}, direct_token="ya29.submit-token")
    sub = GoogleIndexingSubmitter(auth_manager=mgr, state_file=tmp_path / "subs.json")

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if "urlNotifications:publish" in str(request.url):
            body = json.loads(request.content.decode("utf-8"))
            if "forbidden" in body["url"]:
                return httpx.Response(403, text="Permission denied")
            return httpx.Response(200, json={"urlNotificationMetadata": {"url": body["url"]}})
        if "/sitemaps/" in str(request.url) and request.method == "PUT":
            return httpx.Response(204)
        return httpx.Response(404)

    async def _run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ok = await sub.submit_url("https://loanraaj.com/new-post", client=client)
            assert ok["status"] == "ok"
            assert ok["authenticated"] is True
            assert ok["method"] == "indexing_api"

            dup = await sub.submit_url("https://loanraaj.com/new-post", client=client)
            assert dup["status"] == "skipped"

            err = await sub.submit_url("https://loanraaj.com/forbidden", client=client)
            assert err["status"] == "error"
            assert err["http_code"] == 403

            sm = await sub.submit_sitemap("https://loanraaj.com/sitemap.xml", mock_fallback=False, client=client)
            assert sm is True

    asyncio.run(_run())
    assert any(m == "PUT" and "sitemaps" in u for m, u in calls)


def test_weekly_gsc_report_generation_and_iso_week_dedup(tmp_path: Path) -> None:
    mon = GSCMonitor(
        cfg={
            "gsc": {
                "enabled": True,
                "weekly_report_enabled": True,
                "weekly_report_day": 0,
                "weekly_report_hour": 9,
                "default_days": 7,
            }
        }
    )

    with patch("alert_bot.TelegramAlertBot") as MockBot:
        bot_inst = MagicMock()
        bot_inst.send_message.return_value = {"ok": True}
        MockBot.return_value = bot_inst

        monday_morning = datetime.datetime(2026, 11, 9, 10, 0, 0)
        res1 = mon.maybe_send_scheduled_weekly_report(now=monday_morning)
        assert res1["sent"] is True
        assert res1["week"] == "2026-W46"
        assert Path(res1["report"]["txt_path"]).is_file()
        assert Path(res1["report"]["json_path"]).is_file()
        assert "ESTIMATE MODE" in res1["report"]["message_html"]
        bot_inst.send_message.assert_called_once()

        # Second call within the same ISO week must deduplicate
        res2 = mon.maybe_send_scheduled_weekly_report(now=monday_morning + datetime.timedelta(hours=4))
        assert res2["sent"] is False
        assert res2["reason"] == "already_sent_this_week"

        # Before scheduled hour on Monday should not fire for next week
        early_next = datetime.datetime(2026, 11, 16, 7, 0, 0)
        res3 = mon.maybe_send_scheduled_weekly_report(now=early_next)
        assert res3["sent"] is False
        assert res3["reason"] == "before_schedule"


def test_all_10_sites_have_google_verification_files_and_meta() -> None:
    sites_root = Path(__file__).parent.parent / "sites"
    for dom in DEFAULT_DOMAINS:
        sdir = sites_root / dom
        assert (sdir / "google31976c4df01121b2.html").is_file(), f"Missing verification HTML in {sdir}"
        idx_text = (sdir / "index.html").read_text(encoding="utf-8")
        assert "google31976c4df01121b2" in idx_text, f"Missing google-site-verification meta in {sdir / 'index.html'}"


def test_live_ui_gsc_endpoints() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=8) as resp:
        assert resp.status == 200
        crm_body = resp.read().decode("utf-8", errors="replace")
        for marker in ("u5KpiGscAuth", "u5BtnSyncGsc", "u5BtnWeeklyGsc", "u5GscCredForm"):
            assert marker in crm_body

    with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=8) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8", errors="replace")
        for marker in ("gscAuthBadge", "btnGscSync", "btnGscWeekly", "saveGscCredentials", "fetchGscStatus"):
            assert marker in body

    with urllib.request.urlopen("http://127.0.0.1:5050/api/gsc/status", timeout=8) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert "auth" in data and "summary" in data
        assert len(data["domains"]) == 10

    req = urllib.request.Request(
        "http://127.0.0.1:5050/api/gsc/credentials",
        data=json.dumps({"credentials_json": "{}"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=8)
    assert exc_info.value.code == 400
