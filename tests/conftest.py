"""
tests/conftest.py — Global test fixtures, environment isolation, and live UI server lifecycle.
Ensures zero environment leaks, cached config pollution, or order-dependence across tests.
Provides live UI server on 127.0.0.1:5050 for dashboard endpoint tests.
"""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Generator
import urllib.request
import pytest


@pytest.fixture(autouse=True)
def isolate_test_environment() -> Generator[None, None, None]:
    """Snapshot and restore os.environ for every test to guarantee order independence."""
    saved_env = os.environ.copy()
    os.environ.setdefault("PHASE4_ALLOW_DEV_UNLOCK", "1")
    yield
    os.environ.clear()
    os.environ.update(saved_env)


@pytest.fixture(scope="session", autouse=True)
def live_ui_server() -> Generator[str, None, None]:
    """Start ui.start_server(port=5050) for dashboard tests and tear down at session end."""
    import ui
    from admin_ui import profile_auth

    os.environ["PHASE4_ALLOW_DEV_UNLOCK"] = "1"
    try:
        profile_auth.unlock_without_password()
    except Exception:
        pass

    port = 5050
    already_running = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=1) as resp:
            if resp.status in (200, 302, 401, 403):
                already_running = True
    except Exception:
        already_running = False

    if not already_running:
        try:
            ui.start_server(port=port, host="127.0.0.1")
        except Exception:
            pass

    # Poll until reachable (up to 5 seconds)
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=1) as resp:
                if resp.status in (200, 302, 401, 403):
                    break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:5050"

    if not already_running:
        try:
            ui.stop_server()
        except Exception:
            pass
