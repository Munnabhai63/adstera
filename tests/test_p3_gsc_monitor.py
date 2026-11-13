from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from gsc_monitor import GSCMonitor
from daily_report import _get_gsc_indexing_stats, format_telegram_report


def test_gsc_monitor_records_to_autopublish_db():
    mon = GSCMonitor()
    # Limit to 1 domain for instant test execution
    mon.domains = ["loanraaj.com"]
    report = mon.audit_all_domains(days=7, mock_fallback=True)
    assert "domains" in report
    assert len(report["domains"]) > 0

    # Verify state/autopublish.db has gsc_domain_metrics populated
    db_path = Path("state") / "autopublish.db"
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM gsc_domain_metrics").fetchall()
        assert len(rows) > 0
        r = rows[0]
        assert "domain" in r.keys()
        assert "published_pages" in r.keys()
        assert "indexed_pages" in r.keys()
        assert "indexing_ratio" in r.keys()
        assert "impressions" in r.keys()
        assert "clicks" in r.keys()
    finally:
        conn.close()


def test_daily_report_surfaces_low_indexing_alerts():
    # Create a temporary DB with a domain having < 0.3 indexing ratio
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db_path = Path(tf.name)

    conn = sqlite3.connect(temp_db_path)
    try:
        conn.execute(
            """
            CREATE TABLE gsc_domain_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                published_pages INTEGER DEFAULT 0,
                indexed_pages INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                ctr REAL DEFAULT 0.0,
                indexing_ratio REAL DEFAULT 0.0,
                is_mock INTEGER DEFAULT 1,
                data_source TEXT,
                recorded_at TEXT NOT NULL
            )
            """
        )
        # Normal domain: 10/10 indexed (100%)
        conn.execute(
            """
            INSERT INTO gsc_domain_metrics
            (domain, published_pages, indexed_pages, impressions, clicks, ctr, indexing_ratio, is_mock, data_source, recorded_at)
            VALUES ('healthy.com', 10, 10, 100, 5, 0.05, 1.0, 1, 'mock', '2026-11-13T10:00:00')
            """
        )
        # Deindexed domain: 1/10 indexed (10% < 30%)
        conn.execute(
            """
            INSERT INTO gsc_domain_metrics
            (domain, published_pages, indexed_pages, impressions, clicks, ctr, indexing_ratio, is_mock, data_source, recorded_at)
            VALUES ('deindexed.com', 10, 1, 10, 0, 0.0, 0.1, 1, 'mock', '2026-11-13T10:00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    try:
        stats = _get_gsc_indexing_stats(autopublish_db_path=temp_db_path)
        assert stats["domains_monitored"] == 2
        assert len(stats["low_indexing_alerts"]) == 1
        assert stats["low_indexing_alerts"][0]["domain"] == "deindexed.com"
        assert stats["low_indexing_alerts"][0]["ratio"] == 0.1

        # Check format_telegram_report outputs the alert
        mock_stats = {
            "date": "2026-11-13",
            "fleet_ctr": 3.5,
            "degraded_pct": 5.0,
            "published_today": 2,
            "published_total": 50,
            "pending_topics": 10,
            "cf_deployed_today": 2,
            "indexnow_pinged_today": 2,
            "indexnow_pinged_total": 50,
            "top_publishing_domain": "healthy.com",
            "top_publishing_count": 2,
            "daemon_errors_today": 0,
            "total_sessions": 100,
            "ok_sessions": 95,
            "degraded_sessions": 5,
            "avg_dwell": 65.0,
            "total_impressions": 200,
            "total_clicks": 7,
            "cpa_conversions": 1,
            "cpa_revenue_usd": 2.50,
            "ad_revenue_usd": 0.50,
            "total_revenue_usd": 3.00,
            "top_domain": "healthy.com",
            "worst_domain": "healthy.com",
            "gsc_stats": stats,
        }
        msg = format_telegram_report(mock_stats)
        assert "Low Indexing Ratio" in msg
        assert "deindexed.com" in msg
    finally:
        try:
            if temp_db_path.exists():
                temp_db_path.unlink()
        except Exception:
            pass
