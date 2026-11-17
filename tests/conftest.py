"""
tests/conftest.py — Global test fixtures, environment isolation, and live UI server lifecycle.
Ensures zero environment leaks, cached config pollution, or order-dependence across tests.
Provides live UI server on 127.0.0.1:5050 for dashboard endpoint tests.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
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


def pytest_collection_modifyitems(items):
    for item in items:
        if "live" in item.name.lower():
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session", autouse=True)
def live_ui_server() -> Generator[str, None, None]:
    """Start UI server on 127.0.0.1:5050 for dashboard tests and tear down at session end.
    Isolates CRM state to a temporary directory so real state/admin_profile.json is NEVER mutated.
    """
    import shutil
    import tempfile
    import ui
    from admin_ui import profile_auth

    real_profile_path = Path("state/admin_profile.json")
    temp_state = Path(tempfile.mkdtemp(prefix="test_crm_state_"))
    if real_profile_path.exists():
        shutil.copy2(real_profile_path, temp_state / "admin_profile.json")
    os.environ["ADMIN_PROFILE_STATE_DIR"] = str(temp_state)
    os.environ["PHASE4_ALLOW_DEV_UNLOCK"] = "1"
    profile_auth.DEFAULT_STATE_DIR = temp_state

    try:
        profile_auth.unlock_without_password(state_dir=temp_state)
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

    server = None
    if not already_running:
        try:
            server = ui.ThreadingHTTPServer(("127.0.0.1", port), ui.UIRequestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
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

    if server is not None:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
    try:
        shutil.rmtree(temp_state, ignore_errors=True)
    except Exception:
        pass
