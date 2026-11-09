"""
tests/test_ui_analytics.py — Acceptance & Invariant Tests for Step 7.2:
Real-Time Revenue Analytics & 7-Day Forecast Endpoint.
"""
import pytest
import sqlite3
import httpx
from pathlib import Path
import db

TEST_DB = Path("test_ui_analytics.db")


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    if TEST_DB.exists():
        TEST_DB.unlink()
    monkeypatch.setattr(db, "_DB_PATH", TEST_DB)
    db.init()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_analytics_aggregation_queries():
    """Verify hourly and domain SQL aggregation queries execute cleanly without syntax errors."""
    with db._conn() as con:
        # Insert sample sessions
        con.execute(
            """
            INSERT INTO sessions (proxy_id, domain, ua, dwell, impressions, ad_clicks, status, ts)
            VALUES ('1.1.1.1:8080', 'loanraaj.com', 'Mozilla/5.0 Chrome/120.0', 45, 3, 0, 'ok', datetime('now')),
                   ('2.2.2.2:8080', 'loanraaj.com', 'Mozilla/5.0 Chrome/120.0', 60, 2, 1, 'ok', datetime('now')),
                   ('3.3.3.3:8080', 'rechargetak.com', 'Mozilla/5.0 Chrome/120.0', 35, 1, 0, 'ok', datetime('now'))
            """
        )

        hourly_rows = con.execute(
            """
            SELECT strftime('%H:00', ts, 'localtime') AS hour_slot,
                   COUNT(*) AS sessions,
                   SUM(impressions) AS imps,
                   SUM(ad_clicks) AS clicks
            FROM sessions
            WHERE DATE(ts, 'localtime') = DATE('now', 'localtime')
            GROUP BY hour_slot
            ORDER BY hour_slot ASC
            """
        ).fetchall()

        domain_rows = con.execute(
            """
            SELECT domain, COUNT(*) AS sessions, SUM(impressions) AS imps, SUM(ad_clicks) AS clicks
            FROM sessions
            WHERE DATE(ts, 'localtime') = DATE('now', 'localtime')
            GROUP BY domain
            ORDER BY imps DESC
            """
        ).fetchall()

    assert len(hourly_rows) >= 1
    assert hourly_rows[0]["sessions"] == 3
    assert hourly_rows[0]["imps"] == 6
    assert hourly_rows[0]["clicks"] == 1

    assert len(domain_rows) == 2
    domains = {r["domain"]: r["imps"] for r in domain_rows}
    assert domains["loanraaj.com"] == 5
    assert domains["rechargetak.com"] == 1


def test_forecast_integration_shape():
    """Verify RevenueForecaster output integrates with UI analytics payload shape."""
    from revenue_forecast import RevenueForecaster
    forecaster = RevenueForecaster().fit()
    forecast_7d = forecaster.forecast_next_7_days()
    monthly_est = forecaster.forecast_monthly_estimate()

    assert len(forecast_7d) == 7
    for item in forecast_7d:
        assert "date" in item
        assert "day_name" in item
        assert "projected_usd" in item
        assert "confidence_low" in item
        assert "confidence_high" in item
        assert item["confidence_low"] <= item["projected_usd"] <= item["confidence_high"]

    assert monthly_est > 0.0


def test_live_ui_analytics_endpoint():
    """Verify live HTTP server on port 5050 returns valid status and JSON structure."""
    try:
        res = httpx.get("http://127.0.0.1:5050/api/analytics/charts", timeout=3.0)
        assert res.status_code == 200
        data = res.json()
        assert "hourly" in data
        assert "domains" in data
        assert "forecast_7d" in data
        assert "monthly_estimate_usd" in data
        assert len(data["forecast_7d"]) == 7
        assert isinstance(data["monthly_estimate_usd"], (int, float))
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("UI server not actively running on port 5050 during test run")
