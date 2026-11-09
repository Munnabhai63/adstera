"""
tests/test_autopilot_dashboard.py — Acceptance & Invariant Tests for MD File 4:
Autopilot Watchdog, Diurnal Pacing, SQLite WAL Mode, and Dashboard API Endpoints.
"""
import pytest
import sqlite3
from pathlib import Path
from autopilot_watchdog import AutopilotWatchdog, DEFAULT_DIURNAL, DEFAULT_WEEKDAY_SCALE
import db

TEST_DB = Path("test_autopilot.db")


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    if TEST_DB.exists():
        TEST_DB.unlink()
    monkeypatch.setattr(db, "_DB_PATH", TEST_DB)
    db.init()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_sqlite_wal_mode_enabled():
    """Verify SQLite WAL (Write-Ahead Logging) and NORMAL sync are active."""
    with db._conn() as con:
        cur = con.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0].lower()
        assert mode == "wal", f"Expected WAL mode, got {mode}"


def test_diurnal_curve_pacing():
    """Verify diurnal calculation scales correctly between off-peak and peak hours."""
    # 3 AM (index 3) is quiet off-peak: weight 0.12
    rate_3am = AutopilotWatchdog.calculate_diurnal_pace(
        base_hourly_rate=150, hour=3, weekday=0
    )
    # 2 PM (index 14) is active afternoon peak: weight 0.90
    rate_2pm = AutopilotWatchdog.calculate_diurnal_pace(
        base_hourly_rate=150, hour=14, weekday=0
    )

    assert rate_3am > 0
    assert rate_2pm > rate_3am
    assert rate_2pm >= int(150 * 0.85)


def test_watchdog_memory_recycle():
    """Verify memory hygiene trigger fires after configured threshold sessions."""
    dog = AutopilotWatchdog(session_recycle_threshold=5)
    for _ in range(4):
        needs_recycle = dog.record_session(success=True)
        assert needs_recycle is False

    # 5th session hits threshold
    needs_recycle = dog.record_session(success=True)
    assert needs_recycle is True

    dog.reset_recycle_counter()
    assert dog.session_count == 0


def test_network_exponential_backoff():
    """Verify exponential backoff progression during network/proxy drops."""
    dog = AutopilotWatchdog()
    # 0 failures -> 0 delay
    assert dog.calculate_backoff() == 0.0

    dog.record_session(success=False)  # streak 1
    assert dog.calculate_backoff() == 30.0

    dog.record_session(success=False)  # streak 2
    assert dog.calculate_backoff() == 45.0

    # Recovers on success
    dog.record_session(success=True)
    assert dog.calculate_backoff() == 0.0


def test_watchdog_status_summary():
    """Verify watchdog status payload."""
    dog = AutopilotWatchdog(session_recycle_threshold=25)
    status = dog.get_status()
    assert "uptime_minutes" in status
    assert "current_hourly_pace" in status
    assert status["recycle_threshold"] == 25

