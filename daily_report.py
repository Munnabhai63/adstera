"""
daily_report.py — Step 7.1: Automated Daily Fleet Performance Report Generator

Aggregates daily fleet traffic, engagement, ad monetization, and CPA conversion metrics:
- Total sessions, OK vs degraded count, degradation rate
- Total impressions, ad clicks, and fleet CTR (with IVT safe guard indicator)
- CPA lead conversions count & bounty earnings
- Combined estimated revenue breakdown (CPM ads + CPA leads)
- Top-performing and lowest-performing domains by eCPM
- Formats structured Telegram HTML alert and archives to reports/daily_report_YYYY-MM-DD.txt
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any, Optional

import db

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def get_daily_fleet_stats(target_date: Optional[str] = None, cpm_rate: float = 2.50) -> dict[str, Any]:
    """Queries sessions.db and aggregates complete fleet performance for a specific date (YYYY-MM-DD)."""
    with db._conn() as con:
        if target_date:
            date_str = target_date
            sess_cond = "DATE(ts) = ? OR DATE(ts, 'localtime') = ?"
            cpa_cond = "DATE(ts) = ? OR DATE(ts, 'localtime') = ?"
            api_cond = "date = ?"
            sess_params = (date_str, date_str)
            cpa_params = (date_str, date_str)
            api_params = (date_str,)
        else:
            db_date_row = con.execute("SELECT DATE('now')").fetchone()
            date_str = str(db_date_row[0]) if db_date_row else datetime.date.today().isoformat()
            sess_cond = (
                "DATE(ts) = DATE('now') "
                "OR DATE(ts) = DATE('now', '+5 hours', '30 minutes') "
                "OR DATE(ts, 'localtime') = DATE('now', 'localtime') "
                "OR DATE(ts, '-5 hours', '-30 minutes') = DATE('now')"
            )
            cpa_cond = (
                "DATE(ts) = DATE('now') "
                "OR DATE(ts) = DATE('now', '+5 hours', '30 minutes') "
                "OR DATE(ts, 'localtime') = DATE('now', 'localtime') "
                "OR DATE(ts, '-5 hours', '-30 minutes') = DATE('now')"
            )
            api_cond = (
                "date = DATE('now') "
                "OR date = DATE('now', '+5 hours', '30 minutes') "
                "OR date = DATE('now', 'localtime')"
            )
            sess_params = ()
            cpa_params = ()
            api_params = ()

        # 1. Session aggregates from sessions table
        sess_row = con.execute(
            f"""
            SELECT COUNT(*) AS total_sessions,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS ok_sessions,
                   SUM(CASE WHEN status='degraded' THEN 1 ELSE 0 END) AS degraded_sessions,
                   SUM(impressions) AS total_impressions,
                   SUM(ad_clicks) AS total_clicks,
                   AVG(dwell) AS avg_dwell
            FROM sessions
            WHERE {sess_cond}
            """,
            sess_params,
        ).fetchone()

        # 2. Per-domain aggregates
        domain_rows = con.execute(
            f"""
            SELECT domain,
                   COUNT(*) AS sessions,
                   SUM(impressions) AS imps,
                   SUM(ad_clicks) AS clicks,
                   AVG(dwell) AS avg_dwell
            FROM sessions
            WHERE {sess_cond}
            GROUP BY domain
            ORDER BY imps DESC
            """,
            sess_params,
        ).fetchall()

        # 3. CPA / Lead conversions
        cpa_row = con.execute(
            f"""
            SELECT COUNT(*) AS total_conversions,
                   COALESCE(SUM(payout_usd), 0.0) AS cpa_bounty_usd
            FROM cpa_conversions
            WHERE ({cpa_cond}) AND status != 'rejected'
            """,
            cpa_params,
        ).fetchone()

        # 4. Adsterra API verified sync (if available)
        api_row = con.execute(
            f"""
            SELECT COALESCE(SUM(api_revenue), 0.0) AS api_rev,
                   COALESCE(SUM(api_impressions), 0) AS api_imps,
                   COALESCE(SUM(api_clicks), 0) AS api_clicks
            FROM adsterra_api_sync
            WHERE {api_cond}
            """,
            api_params,
        ).fetchone()

    total_sess = int(sess_row["total_sessions"] or 0)
    ok_sess = int(sess_row["ok_sessions"] or 0)
    deg_sess = int(sess_row["degraded_sessions"] or 0)
    total_imps = int(sess_row["total_impressions"] or 0)
    total_clicks = int(sess_row["total_clicks"] or 0)
    avg_dwell = float(sess_row["avg_dwell"] or 0.0)

    fleet_ctr = round(total_clicks / total_imps * 100.0, 2) if total_imps > 0 else 0.0
    degraded_pct = round(deg_sess / total_sess * 100.0, 1) if total_sess > 0 else 0.0

    cpa_count = int(cpa_row["total_conversions"] or 0)
    cpa_bounty = float(cpa_row["cpa_bounty_usd"] or 0.0)

    # Use Adsterra verified API revenue if synced, otherwise CPM estimation
    api_rev = float(api_row["api_rev"] or 0.0)
    ad_revenue = api_rev if api_rev > 0.0 else round((total_imps / 1000.0) * cpm_rate, 2)
    total_revenue = round(ad_revenue + cpa_bounty, 2)

    # Calculate top and worst domains
    domains_data = []
    for r in domain_rows:
        dom_name = str(r["domain"])
        d_imps = int(r["imps"] or 0)
        d_clicks = int(r["clicks"] or 0)
        d_ctr = round(d_clicks / d_imps * 100.0, 2) if d_imps > 0 else 0.0
        d_ecpm = round((d_clicks * 0.05 + d_imps * (cpm_rate / 1000.0)) / max(d_imps, 1) * 1000, 2)
        domains_data.append({
            "domain": dom_name,
            "sessions": int(r["sessions"] or 0),
            "impressions": d_imps,
            "clicks": d_clicks,
            "ctr": d_ctr,
            "ecpm": d_ecpm,
        })

    top_domain = domains_data[0]["domain"] if domains_data else "—"
    worst_domain = domains_data[-1]["domain"] if len(domains_data) > 1 else top_domain

    return {
        "date": date_str,
        "total_sessions": total_sess,
        "ok_sessions": ok_sess,
        "degraded_sessions": deg_sess,
        "degraded_pct": degraded_pct,
        "total_impressions": total_imps,
        "total_clicks": total_clicks,
        "fleet_ctr": fleet_ctr,
        "avg_dwell": round(avg_dwell, 1),
        "cpa_conversions": cpa_count,
        "cpa_revenue_usd": round(cpa_bounty, 2),
        "ad_revenue_usd": round(ad_revenue, 2),
        "total_revenue_usd": total_revenue,
        "top_domain": top_domain,
        "worst_domain": worst_domain,
        "domains": domains_data,
    }


def format_telegram_report(stats: dict[str, Any]) -> str:
    """Formats stats dictionary into a clean Telegram HTML message."""
    ctr_badge = "✅ Safe" if stats["fleet_ctr"] <= 5.0 else "⚠️ High"
    deg_badge = "✅ Healthy" if stats["degraded_pct"] <= 15.0 else "⚠️ Elevated"

    return (
        f"📊 <b>DAILY FLEET PERFORMANCE REPORT</b>\n"
        f"📅 <b>Date:</b> {stats['date']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 <b>Total Sessions:</b> {stats['total_sessions']:,}\n"
        f"   • OK: {stats['ok_sessions']:,} (100% - {stats['degraded_pct']}%) [{deg_badge}]\n"
        f"   • Degraded: {stats['degraded_sessions']:,} ({stats['degraded_pct']}%)\n"
        f"⏱️ <b>Avg Dwell:</b> {stats['avg_dwell']}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👁️ <b>Total Impressions:</b> {stats['total_impressions']:,}\n"
        f"🖱️ <b>Total Clicks:</b> {stats['total_clicks']:,}\n"
        f"🎯 <b>Fleet CTR:</b> {stats['fleet_ctr']}% [{ctr_badge}]\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>CPA Conversions:</b> {stats['cpa_conversions']} (${stats['cpa_revenue_usd']:.2f})\n"
        f"💰 <b>Estimated Ad Rev:</b> ${stats['ad_revenue_usd']:.2f}\n"
        f"💵 <b>TOTAL REVENUE:</b> <b>${stats['total_revenue_usd']:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Top Domain:</b> {stats['top_domain']}\n"
        f"📉 <b>Lowest Domain:</b> {stats['worst_domain']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Autonomous Enterprise Fleet Autopilot</i>"
    )


def generate_and_save_report(target_date: Optional[str] = None, cpm_rate: float = 2.50) -> dict[str, Any]:
    """Generates daily report, writes txt and json files to reports/ folder, returns report data."""
    stats = get_daily_fleet_stats(target_date=target_date, cpm_rate=cpm_rate)
    date_str = stats["date"]

    txt_content = format_telegram_report(stats)
    txt_path = REPORTS_DIR / f"daily_report_{date_str}.txt"
    json_path = REPORTS_DIR / f"daily_report_{date_str}.json"

    txt_path.write_text(txt_content, encoding="utf-8")
    json_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    logger.info("Daily report saved for %s: %s", date_str, txt_path)
    return {
        "stats": stats,
        "txt_path": str(txt_path),
        "json_path": str(json_path),
        "telegram_message": txt_content,
    }


def send_daily_report_telegram(target_date: Optional[str] = None) -> bool:
    """Generates and dispatches the daily report to Telegram."""
    report = generate_and_save_report(target_date=target_date)
    msg = report["telegram_message"]

    try:
        from alert_bot import TelegramAlertBot
        bot = TelegramAlertBot()
        res = bot.send_message(msg, alert_type="daily_report", level="INFO")
        logger.info("Telegram daily report sent: %s", res)
        return True
    except Exception as exc:
        logger.warning("Failed to dispatch daily report via Telegram: %s", exc)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate daily fleet performance report")
    parser.add_argument("--date", help="Date to report on (YYYY-MM-DD)", default=None)
    parser.add_argument("--telegram", help="Send report to Telegram", action="store_true")
    args = parser.parse_args()

    rep = generate_and_save_report(target_date=args.date)
    print("\n" + rep["telegram_message"] + "\n")
    print(f"Report saved to: {rep['txt_path']}")

    if args.telegram:
        send_daily_report_telegram(target_date=args.date)
