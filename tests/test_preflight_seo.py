"""
tests/test_preflight_seo.py — DEFECT S1-B verification:
Tests for scripts/preflight_seo.py:
1. Clean-clone missing inputs exit non-zero (exit code 1) with clear remedies.
2. Stubbed valid inputs return exit code 0 and all checks OK.
3. Grep proof that output leaks zero secrets, tokens, or private keys.
4. docs/STEP1_OWNER_ACTIONS.md exists and covers all three setup areas.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

import scripts.preflight_seo as preflight_seo


def test_preflight_clean_clone_missing_transport_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When transport or tokens are missing, run_preflight must return exit code 1."""
    empty_proxy_file = tmp_path / "proxies.txt"
    empty_proxy_file.write_text("", encoding="utf-8")

    dummy_cfg = tmp_path / "config.yaml"
    dummy_cfg.write_text("proxy:\n  file: proxies.txt\n", encoding="utf-8")

    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")

    # Clear environment tokens and mock ADB
    monkeypatch.delenv("FREELLMAPI_TOKEN", raising=False)
    monkeypatch.delenv("FREELLMAPI_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_TUNNEL_TOKEN", raising=False)
    monkeypatch.delenv("TUNNEL_TOKEN", raising=False)
    monkeypatch.setattr(preflight_seo, "PROJECT_ROOT", tmp_path)

    import mobile_adb
    monkeypatch.setattr(mobile_adb, "list_devices", lambda: [])

    exit_code, checks, snapshot = preflight_seo.run_preflight(dummy_cfg, empty_env)

    assert exit_code == 1
    statuses = {c["category"]: c["status"] for c in checks}
    assert "MISSING" in statuses.values()
    # At least Transport or tokens must be MISSING
    assert statuses.get("Transport") == "MISSING" or statuses.get("FreeLLMAPI Token") == "MISSING"


def test_preflight_stubbed_valid_inputs_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When all required inputs are present, run_preflight must return exit code 0."""
    valid_proxy_file = tmp_path / "proxies.txt"
    valid_proxy_file.write_text("user:pass@198.51.100.10:8000\n", encoding="utf-8")

    dummy_cfg = tmp_path / "config.yaml"
    dummy_cfg.write_text(f"proxy:\n  file: {valid_proxy_file.name}\n", encoding="utf-8")

    dummy_env = tmp_path / ".env"
    dummy_env.write_text("FREELLMAPI_TOKEN=fake-token\nCLOUDFLARE_TUNNEL_TOKEN=fake-tunnel\n", encoding="utf-8")

    monkeypatch.setattr(preflight_seo, "PROJECT_ROOT", tmp_path)

    # Mock GSC as configured
    import gsc_auth
    monkeypatch.setattr(
        gsc_auth.GSCAuthManager,
        "get_status",
        lambda self: {"configured": True, "auth_type": "service_account", "client_email": "bot@domain.iam.gserviceaccount.com"},
    )

    # Mock IndexNow keys
    monkeypatch.setattr(
        preflight_seo,
        "check_indexnow_keys",
        lambda: {"category": "IndexNow Verification", "status": "OK", "details": "10/10 verified", "remedy": ""},
    )

    exit_code, checks, snapshot = preflight_seo.run_preflight(dummy_cfg, dummy_env)

    assert exit_code == 0
    for c in checks:
        assert c["status"] == "OK", f"Expected OK for {c['category']}, got {c['status']}"


def test_preflight_output_leaks_no_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Preflight execution and JSON output must never expose secret values or private keys."""
    SECRET_TOKEN_A = "SUPER_SECRET_FREELLMAPI_KEY_999888777"
    SECRET_TUNNEL_B = "SUPER_SECRET_TUNNEL_TOKEN_AAA_BBB_CCC"
    SECRET_PROXY_PASS = "ULTRA_CONFIDENTIAL_PROXY_PASSWORD"

    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text(f"admin:{SECRET_PROXY_PASS}@198.51.100.10:8000\n", encoding="utf-8")

    dummy_cfg = tmp_path / "config.yaml"
    dummy_cfg.write_text(f"proxy:\n  file: {proxy_file.name}\n", encoding="utf-8")

    dummy_env = tmp_path / ".env"
    dummy_env.write_text(f"FREELLMAPI_TOKEN={SECRET_TOKEN_A}\nCLOUDFLARE_TUNNEL_TOKEN={SECRET_TUNNEL_B}\n", encoding="utf-8")

    monkeypatch.setattr(preflight_seo, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("FREELLMAPI_TOKEN", SECRET_TOKEN_A)
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", SECRET_TUNNEL_B)

    # Mock GSC as configured
    import gsc_auth
    monkeypatch.setattr(
        gsc_auth.GSCAuthManager,
        "get_status",
        lambda self: {
            "configured": True,
            "auth_type": "service_account",
            "client_email": "safe-bot@serviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASC...\n-----END PRIVATE KEY-----",
        },
    )
    monkeypatch.setattr(
        preflight_seo,
        "check_indexnow_keys",
        lambda: {"category": "IndexNow Verification", "status": "OK", "details": "10/10 verified", "remedy": ""},
    )

    test_args = ["preflight_seo.py", "--config", str(dummy_cfg), "--env", str(dummy_env)]
    monkeypatch.setattr(sys, "argv", test_args)

    # Run main() in standard text mode
    exit_code = preflight_seo.main()
    captured = capsys.readouterr()
    all_output = captured.out + captured.err

    # Grep proofs: Secret tokens, passwords, and private key blocks must NOT appear in output
    assert SECRET_TOKEN_A not in all_output, "Leaked FREELLMAPI_TOKEN in output!"
    assert SECRET_TUNNEL_B not in all_output, "Leaked CLOUDFLARE_TUNNEL_TOKEN in output!"
    assert SECRET_PROXY_PASS not in all_output, "Leaked proxy password in output!"
    assert "BEGIN PRIVATE KEY" not in all_output, "Leaked private key block in output!"

    # Run main() in JSON mode and verify
    test_args_json = ["preflight_seo.py", "--config", str(dummy_cfg), "--env", str(dummy_env), "--json"]
    monkeypatch.setattr(sys, "argv", test_args_json)
    preflight_seo.main()
    captured_json = capsys.readouterr()
    json_output = captured_json.out + captured_json.err

    assert SECRET_TOKEN_A not in json_output, "Leaked FREELLMAPI_TOKEN in JSON output!"
    assert SECRET_TUNNEL_B not in json_output, "Leaked CLOUDFLARE_TUNNEL_TOKEN in JSON output!"
    assert SECRET_PROXY_PASS not in json_output, "Leaked proxy password in JSON output!"
    assert "BEGIN PRIVATE KEY" not in json_output, "Leaked private key in JSON output!"


def test_docs_step1_owner_actions_exists_and_complete() -> None:
    doc_path = Path(__file__).parent.parent / "docs" / "STEP1_OWNER_ACTIONS.md"
    assert doc_path.is_file(), "docs/STEP1_OWNER_ACTIONS.md must exist"

    text = doc_path.read_text(encoding="utf-8")
    assert "Cloudflare Zero Trust" in text
    assert "FreeLLMAPI" in text
    assert "Google Search Console" in text or "GSC" in text
    assert "Service Account" in text
    assert "CLOUDFLARE_TUNNEL_TOKEN" in text
    assert "FREELLMAPI_TOKEN" in text
    assert "state/gsc_service_account.json" in text
