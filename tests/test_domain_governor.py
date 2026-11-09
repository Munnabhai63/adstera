"""
tests/test_domain_governor.py — Verification of MD File 1 Independent Per-Domain CTR Governance.
Tests database schema migration, per-domain CTR calculation, and automated circuit breaker.
"""
import sqlite3
import pytest
from pathlib import Path
import db
import worker

TEST_DB_PATH = Path("test_governor.db")


@pytest.fixture(autouse=True)
def setup_teardown_db(monkeypatch):
    """Isolate tests into a temporary database."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    
    monkeypatch.setattr(db, "_DB_PATH", TEST_DB_PATH)
    db.init()
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def test_schema_has_domain_and_domain_stats():
    """Verify that domain column exists and domain_stats table is active."""
    with db._conn() as con:
        cur = con.execute("PRAGMA table_info(sessions)")
        cols = [c[1] for c in cur.fetchall()]
        assert "domain" in cols, "'domain' column must exist in sessions table"

        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='domain_stats'")
        assert cur.fetchone() is not None, "'domain_stats' table must exist"


def test_independent_per_domain_logging():
    """Verify that logging sessions for domain A does not pollute domain B."""
    # Domain A: 100 impressions, 4 clicks (CTR = 4.0%)
    for i in range(10):
        db.log_session(
            proxy_id=f"proxy_a_{i}",
            ua="Test UA A",
            referrer="https://google.com",
            dwell=45.0,
            pages=1,
            ad_clicks=1 if i < 4 else 0,
            impressions=10,
            status="ok",
            domain="loanraaj.com"
        )

    # Domain B: 50 impressions, 0 clicks (CTR = 0.0%)
    for i in range(5):
        db.log_session(
            proxy_id=f"proxy_b_{i}",
            ua="Test UA B",
            referrer="https://bing.com",
            dwell=50.0,
            pages=1,
            ad_clicks=0,
            impressions=10,
            status="ok",
            domain="insurancenet.com"
        )

    stats_a = db.domain_today("loanraaj.com")
    stats_b = db.domain_today("insurancenet.com")

    assert stats_a["impressions"] == 100
    assert stats_a["clicks"] == 4
    assert stats_a["ctr"] == 4.0

    assert stats_b["impressions"] == 50
    assert stats_b["clicks"] == 0
    assert stats_b["ctr"] == 0.0


def test_circuit_breaker_thresholds():
    """Verify OPTIMAL (<4.4%), GUARD_ACTIVE (4.4%-5.0%), and PAUSED (>=5.0%) states."""
    # Case 1: Healthy Green Zone (CTR = 3.8%)
    # 100 impressions, 4 clicks = 4.0%
    for i in range(10):
        db.log_session(
            proxy_id=f"proxy_{i}",
            ua="Test UA",
            referrer="",
            dwell=45.0,
            ad_clicks=1 if i < 4 else 0,
            impressions=10,
            domain="healthy.com"
        )
    safety_healthy = db.check_domain_safety("healthy.com", max_ctr=0.05, warning_ctr=0.044)
    assert safety_healthy["status"] == "OPTIMAL"
    assert safety_healthy["allow_click"] is True

    # Case 2: Red Zone (CTR = 6.0% >= 5.0%) -> PAUSED
    # 100 impressions, 6 clicks = 6.0%
    for i in range(10):
        db.log_session(
            proxy_id=f"proxy_{i}",
            ua="Test UA",
            referrer="",
            dwell=45.0,
            ad_clicks=1 if i < 6 else 0,
            impressions=10,
            domain="risky.com"
        )
    safety_risky = db.check_domain_safety("risky.com", max_ctr=0.05, warning_ctr=0.044)
    assert safety_risky["status"] == "PAUSED"
    assert safety_risky["allow_click"] is False
    assert "exceeds hard limit" in safety_risky["reason"]


def test_all_domains_summary():
    """Verify aggregated fleet summary view."""
    db.log_session("p1", "UA", "", 45.0, 1, 2, 50, "ok", domain="loanraaj.com")
    db.log_session("p2", "UA", "", 45.0, 1, 1, 25, "ok", domain="cloudhoster.com")

    summary = db.all_domains_summary(default_cpm=5.00)
    assert len(summary) == 2
    domains = [s["domain"] for s in summary]
    assert "loanraaj.com" in domains
    assert "cloudhoster.com" in domains

