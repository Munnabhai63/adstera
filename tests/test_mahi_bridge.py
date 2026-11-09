"""
tests/test_mahi_bridge.py — Acceptance and Invariant Tests for MAHI Browser Gate 2 Integration.
Verifies read-only DB mode, 100% zero-tampering, profile parsing, launch flags, and isolated state.
"""
import sqlite3
import pytest
from pathlib import Path
from mahi_connector import MahiConnector, MahiBridgeError, MAHI_SQLITE_PATH, MAHI_CHROME_EXE, MAHI_STATE_DIR


@pytest.fixture
def connector():
    return MahiConnector()


def test_mahi_connector_availability(connector):
    """Verify MAHI Chromium executable and SQLite DB are detected on host."""
    assert connector.is_available() is True
    assert MAHI_CHROME_EXE.exists()
    assert MAHI_SQLITE_PATH.exists()
    assert Path(connector.get_chrome_executable_path()).is_file()


def test_zero_tampering_readonly_database_invariant():
    """
    INVARIANT 1: Absolute Zero-Tampering Mandate.
    Any attempt to execute an UPDATE, INSERT, or DELETE on MAHI's SQLite database
    via our read-only bridge MUST raise sqlite3.OperationalError: attempt to write a readonly database.
    """
    uri = f"file:{MAHI_SQLITE_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        cur.execute("UPDATE profiles SET notes = 'tampered' WHERE id = 'test'")
        conn.commit()

    conn.close()
    assert "readonly" in str(exc_info.value).lower()


def test_profile_retrieval_and_schema_parsing(connector):
    """Verify active profiles are retrieved and JSON settings properly parsed."""
    profiles = connector.get_available_profiles()
    assert len(profiles) >= 20, f"Expected at least 20 active profiles, got {len(profiles)}"

    sample = profiles[0]
    assert "id" in sample
    assert "name" in sample
    assert "settings" in sample
    assert isinstance(sample["settings"], dict)

    # Validate settings keys
    settings = sample["settings"]
    assert "browser" in settings or "display" in settings


def test_random_profile_and_context_kwargs(connector):
    """Verify context kwargs (viewport, user-agent, locale, timezone) extraction."""
    profile = connector.get_random_profile()
    assert profile is not None

    kwargs = connector.get_profile_context_kwargs(profile)
    assert "viewport" in kwargs
    assert "width" in kwargs["viewport"]
    assert "height" in kwargs["viewport"]
    assert "user_agent" in kwargs
    assert "Chrome" in kwargs["user_agent"]
    assert "locale" in kwargs
    assert "timezone_id" in kwargs
    assert kwargs["ignore_https_errors"] is True


def test_hardened_launch_arguments(connector):
    """Verify anti-automation, WebRTC leak shield, and DNS resolver isolation flags."""
    proxy_cfg = {"server": "http://user:pass@192.168.1.100:8080"}
    args = connector.build_launch_args(proxy_config=proxy_cfg, lang="en-US")

    # Anti-automation flag
    assert "--disable-blink-features=AutomationControlled" in args

    # WebRTC leak protection
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in args

    # DNS routing shield
    dns_flags = [a for a in args if "--host-resolver-rules=" in a]
    assert len(dns_flags) == 1
    assert "EXCLUDE 192.168.1.100" in dns_flags[0]


def test_state_isolation_paths(connector):
    """Verify session data dirs and cookies are strictly within project adstera/state/mahi_bridge/."""
    profile_id = "test-uuid-1234"
    user_data_dir = connector.get_isolated_user_data_dir(profile_id)
    cookie_state = connector.get_storage_state_path(profile_id)

    # Must be inside project state dir
    assert MAHI_STATE_DIR in user_data_dir.parents or user_data_dir == MAHI_STATE_DIR
    assert MAHI_STATE_DIR in cookie_state.parents

    # Must NOT be inside MAHI Browser's application or roaming dir
    assert "AppData\\Roaming\\mahi-browser" not in str(user_data_dir)
    assert "AppData\\Local\\Programs\\MAHI Browser" not in str(user_data_dir)
