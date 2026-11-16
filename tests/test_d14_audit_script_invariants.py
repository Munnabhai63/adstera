"""
tests/test_d14_audit_script_invariants.py — Acceptance verification for D12/D13/D14.

1. test_audit_help_and_exit_codes:
   - --help and -h exit 0 with usage documentation.
   - Missing transport outside CI without --allow-no-transport exits 1.
2. test_audit_skips_transport_in_ci_without_proxies:
   - In CI mode without proxies.txt, transport checks report SKIP and audit exits 0.
   - When browser launcher raises (e.g. missing binary), prints single fatal line and exits 1.
3. test_audit_reports_minimum_executed_checks:
   - Enforces narrow skip policy: at least 7 checks executed, non-transport checks ran.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_audit_help_and_exit_codes(tmp_path):
    # 1. Test --help
    res_help = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tests" / "audit.py"), "--help"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert res_help.returncode == 0
    assert "Usage: python tests/audit.py" in res_help.stdout
    assert "--allow-no-transport" in res_help.stdout

    # 2. Test -h
    res_h = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tests" / "audit.py"), "-h"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert res_h.returncode == 0
    assert "Usage: python tests/audit.py" in res_h.stdout

    # 3. Test exit code 1 when proxies.txt missing outside CI without flag
    dummy_cfg = {
        "proxy": {"file": "nonexistent_proxies_file_987654.txt"},
        "browser": {"headless": True, "slow_mo_ms": 0},
        "target": {"fixture": "tests/fixtures/page.html"},
        "cmp": {"enabled": False, "accept_prob": 0.0},
    }
    cfg_file = tmp_path / "test_cfg.yaml"
    cfg_file.write_text(yaml.dump(dummy_cfg), encoding="utf-8")

    from tests import audit
    clean_env = dict(os.environ)
    clean_env.pop("CI", None)
    clean_env.pop("GITHUB_ACTIONS", None)

    res_fail = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import yaml, sys; sys.path.insert(0, r'{PROJECT_ROOT}'); from tests import audit; "
            f"cfg = yaml.safe_load(open(r'{cfg_file}')); audit.run_all(cfg)",
        ],
        cwd=str(PROJECT_ROOT),
        env=clean_env,
        capture_output=True,
        text=True,
    )
    assert res_fail.returncode == 1, f"Expected exit code 1 outside CI without proxies, got {res_fail.returncode}"
    assert "FAIL" in res_fail.stdout or "Audit FAILED" in res_fail.stdout


def test_audit_skips_transport_in_ci_without_proxies(tmp_path):
    # Part A: Exit 0 on skip in CI mode without proxies.txt
    dummy_cfg = {
        "proxy": {"file": "nonexistent_ci_proxies_12345.txt"},
        "browser": {"headless": True, "slow_mo_ms": 0},
        "target": {"fixture": "tests/fixtures/page.html"},
        "cmp": {"enabled": False, "accept_prob": 0.0},
    }
    cfg_file = tmp_path / "ci_cfg.yaml"
    cfg_file.write_text(yaml.dump(dummy_cfg), encoding="utf-8")

    ci_env = dict(os.environ)
    ci_env["CI"] = "true"

    res_skip = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import yaml, sys; sys.path.insert(0, r'{PROJECT_ROOT}'); from tests import audit; "
            f"cfg = yaml.safe_load(open(r'{cfg_file}')); audit.run_all(cfg)",
        ],
        cwd=str(PROJECT_ROOT),
        env=ci_env,
        capture_output=True,
        text=True,
    )
    assert res_skip.returncode == 0, f"Expected exit code 0 on skip in CI mode, got {res_skip.returncode}\n{res_skip.stdout}\n{res_skip.stderr}"
    assert "SKIP — no transport configured (CI)" in res_skip.stdout
    assert "Audit PASSED" in res_skip.stdout

    # Part B: Exit 1 when browser launcher raises (e.g. executable missing)
    res_fatal = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import sys, yaml
sys.path.insert(0, r'{PROJECT_ROOT}')
from unittest.mock import AsyncMock, patch
from tests import audit

async def mock_launch(*args, **kwargs):
    raise Exception("Executable doesn't exist at path /mock/chromium-1148/headless_shell")

with patch('playwright.async_api._context_manager.PlaywrightContextManager') as mock_pcm:
    cfg = yaml.safe_load(open(r'{cfg_file}'))
    # Monkeypatch pw.chromium.launch in audit module
    from playwright.async_api import async_playwright
    import asyncio

    async def _fail_test():
        with patch('playwright.async_api.BrowserType.launch', side_effect=Exception("Executable doesn't exist at path /mock/chromium/headless_shell")):
            await audit.run_all_async(cfg)

    asyncio.run(_fail_test())
""",
        ],
        cwd=str(PROJECT_ROOT),
        env=ci_env,
        capture_output=True,
        text=True,
    )
    assert res_fatal.returncode == 1, f"Expected exit 1 on launcher failure, got {res_fatal.returncode}"
    assert "[browser] FATAL — chromium binary missing" in res_fatal.stdout
    assert "Traceback" not in res_fatal.stdout, "Stack trace should not be printed on missing binary"


def test_audit_reports_minimum_executed_checks(tmp_path):
    # Verify narrow skip: only transport checks skip, minimum 7 checks executed
    dummy_cfg = {
        "proxy": {"file": "nonexistent_min_checks_proxy.txt"},
        "browser": {"headless": True, "slow_mo_ms": 0},
        "target": {"fixture": "tests/fixtures/page.html"},
        "cmp": {"enabled": False, "accept_prob": 0.0},
    }
    cfg_file = tmp_path / "min_checks_cfg.yaml"
    cfg_file.write_text(yaml.dump(dummy_cfg), encoding="utf-8")

    ci_env = dict(os.environ)
    ci_env["CI"] = "true"

    res = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import yaml, sys; sys.path.insert(0, r'{PROJECT_ROOT}'); from tests import audit; "
            f"cfg = yaml.safe_load(open(r'{cfg_file}')); audit.run_all(cfg)",
        ],
        cwd=str(PROJECT_ROOT),
        env=ci_env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    summary_file = PROJECT_ROOT / "state" / "audit_summary.json"
    assert summary_file.exists(), "audit_summary.json must be written"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))

    # Assert executed checks >= 7 and narrow skip (only transport skipped, <= 3)
    assert summary["passed"] >= 7, f"Expected >= 7 passed checks, got {summary['passed']}"
    assert summary["skipped"] <= 3, f"Expected <= 3 skipped checks, got {summary['skipped']}"
    assert summary["failed"] == 0, f"Expected 0 failed checks, got {summary['failed']}"

    # Verify that core browser checks actually executed
    assert "[1] PASS — UA clean" in res.stdout
    assert "[2] PASS — navigator.webdriver" in res.stdout
    assert "[3] PASS — WebGL renderer" in res.stdout
