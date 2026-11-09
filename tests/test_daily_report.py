"""
tests/test_daily_report.py — Step 7.1: Automated Daily Fleet Performance Report Tests

Covers:
1. get_daily_fleet_stats aggregates sessions, impressions, clicks, CTR, and CPA conversions
2. format_telegram_report produces structured HTML with key metrics and status badges
3. generate_and_save_report writes report txt and json files to disk
4. send_daily_report_telegram dispatches through TelegramAlertBot
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import daily_report
import db


def test_daily_fleet_stats_aggregation():
    """get_daily_fleet_stats aggregates sessions, clicks, dwell, and revenue accurately."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_db = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_report.db"
        try:
            db.init()
            # Insert 5 OK sessions on loanraaj.com
            for _ in range(5):
                db.log_session("p1", "UA", "", 35.0, 1, ad_clicks=1, impressions=20, status="ok", domain="loanraaj.com")
            # Insert 1 degraded session on tazaloan.com
            db.log_session("p2", "UA", "", 10.0, 1, ad_clicks=0, impressions=0, status="degraded", domain="tazaloan.com")
            # Insert 1 CPA conversion
            db.log_cpa_conversion("mb_1", "maxbounty", "loan", "p1", "loanraaj.com", payout_usd=15.0)

            stats = daily_report.get_daily_fleet_stats()
            assert stats["total_sessions"] == 6
            assert stats["ok_sessions"] == 5
            assert stats["degraded_sessions"] == 1
            assert stats["total_impressions"] == 100
            assert stats["total_clicks"] == 5
            assert stats["fleet_ctr"] == 5.0  # 5 / 100 * 100 = 5%
            assert stats["cpa_conversions"] == 1
            assert stats["cpa_revenue_usd"] == 15.0
            assert stats["total_revenue_usd"] > 15.0
            print(f"  [OK] Daily fleet stats verified: 6 sessions, {stats['total_impressions']} imps, ${stats['total_revenue_usd']:.2f}")
        finally:
            db._DB_PATH = orig_db


def test_format_telegram_report_content():
    """format_telegram_report builds HTML message with indicators."""
    dummy_stats = {
        "date": "2026-11-10",
        "total_sessions": 2000,
        "ok_sessions": 1820,
        "degraded_sessions": 180,
        "degraded_pct": 9.0,
        "avg_dwell": 42.5,
        "total_impressions": 14200,
        "total_clicks": 590,
        "fleet_ctr": 4.15,
        "cpa_conversions": 4,
        "cpa_revenue_usd": 64.0,
        "ad_revenue_usd": 35.50,
        "total_revenue_usd": 99.50,
        "top_domain": "loanraaj.com",
        "worst_domain": "rechargekar.com",
    }
    msg = daily_report.format_telegram_report(dummy_stats)
    assert "DAILY FLEET PERFORMANCE REPORT" in msg
    assert "2,000" in msg
    assert "Safe" in msg  # CTR 4.15% is safe
    assert "Healthy" in msg  # Degraded 9% is healthy
    assert "$99.50" in msg
    print("  [OK] Telegram HTML report formatted with correct badges")


def test_generate_and_save_report_files():
    """generate_and_save_report outputs both text and json files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_reports = daily_report.REPORTS_DIR
        daily_report.REPORTS_DIR = Path(tmpdir)
        try:
            res = daily_report.generate_and_save_report(target_date="2026-11-10")
            assert Path(res["txt_path"]).exists()
            assert Path(res["json_path"]).exists()

            saved_data = json.loads(Path(res["json_path"]).read_text(encoding="utf-8"))
            assert saved_data["date"] == "2026-11-10"
            print("  [OK] Report txt and json files saved successfully")
        finally:
            daily_report.REPORTS_DIR = orig_reports


def test_send_daily_report_telegram_dispatch():
    """send_daily_report_telegram invokes TelegramAlertBot."""
    with patch("alert_bot.TelegramAlertBot") as MockBot:
        mock_instance = MagicMock()
        mock_instance.send_message.return_value = {"ok": True}
        MockBot.return_value = mock_instance

        success = daily_report.send_daily_report_telegram()
        assert success
        mock_instance.send_message.assert_called_once()
        print("  [OK] Telegram dispatch verified")


if __name__ == "__main__":
    test_daily_fleet_stats_aggregation()
    test_format_telegram_report_content()
    test_generate_and_save_report_files()
    test_send_daily_report_telegram_dispatch()
    print("\nAll daily report tests PASSED!")
