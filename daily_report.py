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
import html
import json
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any, Optional

import yaml

import db

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
AUTOPUBLISH_DB_PATH = Path(__file__).parent / "state" / "autopublish.db"
DAILY_REPORT_STATE_PATH = Path(__file__).parent / "state" / "daily_report_state.json"
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_morning_report_hour(default: int = 8) -> int:
    try:
        if CONFIG_PATH.is_file():
            cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            hour = int((cfg.get("telegram") or {}).get("daily_report_hour", default))
            if 0 <= hour <= 23:
                return hour
    except Exception:
        pass
    return default


def _get_publishing_stats(
    date_str: str,
    target_date: Optional[str],
    autopublish_db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Aggregate daily publishing, pending topic queue, and IndexNow stats from autopublish.db."""
    ap_path = Path(autopublish_db_path) if autopublish_db_path is not None else AUTOPUBLISH_DB_PATH
    stats: dict[str, Any] = {
        "published_today": 0,
        "published_total": 0,
        "pending_topics": 0,
        "cf_deployed_today": 0,
        "indexnow_pinged_today": 0,
        "indexnow_pinged_total": 0,
        "top_publishing_domain": "—",
        "top_publishing_count": 0,
        "publishing_domains": [],
        "last_published_at": "",
    }
    if not ap_path.is_file():
        return stats

    with sqlite3.connect(ap_path) as con:
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "published_posts" in tables:
            local_today = datetime.date.today().isoformat()
            if target_date:
                pub_cond = "DATE(published_at) = ? OR SUBSTR(published_at, 1, 10) = ?"
                pub_params: tuple[Any, ...] = (date_str, date_str)
            else:
                pub_cond = (
                    "DATE(published_at) IN (?, ?) "
                    "OR SUBSTR(published_at, 1, 10) IN (?, ?)"
                )
                pub_params = (date_str, local_today, date_str, local_today)

            tot_row = con.execute(
                """
                SELECT COUNT(*) AS published_total,
                       SUM(CASE WHEN COALESCE(google_pinged, 0) = 1 THEN 1 ELSE 0 END) AS pinged_total,
                       MAX(published_at) AS last_published_at
                FROM published_posts
                """
            ).fetchone()
            stats["published_total"] = int(tot_row["published_total"] or 0)
            stats["indexnow_pinged_total"] = int(tot_row["pinged_total"] or 0)
            stats["last_published_at"] = str(tot_row["last_published_at"] or "")

            day_row = con.execute(
                f"""
                SELECT COUNT(*) AS published_today,
                       SUM(CASE WHEN COALESCE(cf_deployed, 0) = 1 THEN 1 ELSE 0 END) AS cf_today,
                       SUM(CASE WHEN COALESCE(google_pinged, 0) = 1 THEN 1 ELSE 0 END) AS pinged_today
                FROM published_posts
                WHERE {pub_cond}
                """,
                pub_params,
            ).fetchone()
            stats["published_today"] = int(day_row["published_today"] or 0)
            stats["cf_deployed_today"] = int(day_row["cf_today"] or 0)
            stats["indexnow_pinged_today"] = int(day_row["pinged_today"] or 0)

            dom_rows = con.execute(
                f"""
                SELECT domain,
                       COUNT(*) AS total_posts,
                       SUM(CASE WHEN {pub_cond} THEN 1 ELSE 0 END) AS posts_today,
                       SUM(CASE WHEN COALESCE(google_pinged, 0) = 1 THEN 1 ELSE 0 END) AS pinged_posts
                FROM published_posts
                GROUP BY domain
                ORDER BY posts_today DESC, total_posts DESC, domain ASC
                """,
                pub_params,
            ).fetchall()
            pub_domains = [
                {
                    "domain": str(r["domain"]),
                    "posts_today": int(r["posts_today"] or 0),
                    "total_posts": int(r["total_posts"] or 0),
                    "pinged_posts": int(r["pinged_posts"] or 0),
                }
                for r in dom_rows
            ]
            stats["publishing_domains"] = pub_domains
            if pub_domains:
                top_row = pub_domains[0]
                stats["top_publishing_domain"] = top_row["domain"]
                stats["top_publishing_count"] = (
                    top_row["posts_today"] if top_row["posts_today"] > 0 else top_row["total_posts"]
                )

        if "topic_queue" in tables:
            pending_row = con.execute(
                "SELECT COUNT(*) AS pending_cnt FROM topic_queue WHERE status = 'pending'"
            ).fetchone()
            stats["pending_topics"] = int(pending_row["pending_cnt"] or 0)

    return stats


def _get_gsc_indexing_stats(autopublish_db_path: Optional[Path] = None) -> dict[str, Any]:
    """Fetch per-domain Search Console indexing health, impressions, clicks from autopublish.db (P3-7)."""
    ap_path = Path(autopublish_db_path) if autopublish_db_path is not None else AUTOPUBLISH_DB_PATH
    res: dict[str, Any] = {
        "total_organic_clicks": 0,
        "total_organic_impressions": 0,
        "domains_monitored": 0,
        "low_indexing_alerts": [],
        "domain_breakdown": [],
    }
    if not ap_path.is_file():
        return res

    con = None
    try:
        con = sqlite3.connect(ap_path)
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "gsc_domain_metrics" in tables:
            rows = con.execute(
                """
                SELECT m.*
                FROM gsc_domain_metrics m
                INNER JOIN (
                    SELECT domain, MAX(recorded_at) as max_rec
                    FROM gsc_domain_metrics
                    GROUP BY domain
                ) r ON m.domain = r.domain AND m.recorded_at = r.max_rec
                """
            ).fetchall()
            for r in rows:
                dom = r["domain"]
                pub = int(r["published_pages"] or 0)
                idx = int(r["indexed_pages"] or 0)
                imps = int(r["impressions"] or 0)
                clks = int(r["clicks"] or 0)
                ratio = float(r["indexing_ratio"] or (idx / pub if pub > 0 else 1.0))

                res["total_organic_clicks"] += clks
                res["total_organic_impressions"] += imps
                res["domains_monitored"] += 1
                res["domain_breakdown"].append({
                    "domain": dom,
                    "published": pub,
                    "indexed": idx,
                    "ratio": ratio,
                    "impressions": imps,
                    "clicks": clks,
                })
                if pub > 0 and ratio < 0.3:
                    res["low_indexing_alerts"].append({
                        "domain": dom,
                        "published": pub,
                        "indexed": idx,
                        "ratio": ratio,
                    })
    except Exception as exc:
        logger.debug("Failed to read GSC stats from autopublish.db: %s", exc)
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass

    return res


def get_daily_fleet_stats(
    target_date: Optional[str] = None,
    cpm_rate: float = 2.50,
    autopublish_db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Queries sessions.db and autopublish.db for daily fleet performance + publishing stats."""
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

        # 5. Pipeline & circuit breaker error count today from alert_logs
        err_row = con.execute(
            f"""
            SELECT COUNT(*) AS error_alerts
            FROM alert_logs
            WHERE ({sess_cond})
              AND level IN ('WARNING', 'CRITICAL', 'ERROR')
            """,
            sess_params,
        ).fetchone()
        daemon_errors_today = int(err_row["error_alerts"] or 0) if err_row else 0

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

    pub_stats = _get_publishing_stats(date_str, target_date, autopublish_db_path=autopublish_db_path)
    gsc_stats = _get_gsc_indexing_stats(autopublish_db_path=autopublish_db_path)

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
        "daemon_errors_today": daemon_errors_today,
        "gsc_stats": gsc_stats,
        **pub_stats,
    }


def format_telegram_report(stats: dict[str, Any]) -> str:
    """Formats stats dictionary into a clean Telegram HTML message."""
    ctr_badge = "✅ Safe" if stats["fleet_ctr"] <= 5.0 else "⚠️ High"
    deg_badge = "✅ Healthy" if stats["degraded_pct"] <= 15.0 else "⚠️ Elevated"

    pub_today = int(stats.get("published_today", 0))
    pub_total = int(stats.get("published_total", 0))
    pending_topics = int(stats.get("pending_topics", 0))
    cf_today = int(stats.get("cf_deployed_today", 0))
    idx_today = int(stats.get("indexnow_pinged_today", 0))
    idx_total = int(stats.get("indexnow_pinged_total", 0))
    top_pub = html.escape(str(stats.get("top_publishing_domain", "—")))
    top_pub_cnt = int(stats.get("top_publishing_count", 0))
    err_cnt = int(stats.get("daemon_errors_today", 0))
    idx_status = (
        f"✅ {idx_today}/{pub_today} today ({idx_total} total)"
        if pub_today > 0
        else f"📡 {idx_total} indexed overall"
    )
    err_badge = "🟢 0" if err_cnt == 0 else f"🚨 {err_cnt}"

    gsc = stats.get("gsc_stats", {})
    gsc_section = ""
    if gsc and gsc.get("domains_monitored", 0) > 0:
        gsc_lines = [
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"🔍 <b>GSC Indexing & Organic Search:</b>",
            f"   • Organic Clicks (7d): <b>{gsc.get('total_organic_clicks', 0):,}</b>",
            f"   • Organic Impressions (7d): <b>{gsc.get('total_organic_impressions', 0):,}</b>",
            f"   • Domains Monitored: <b>{gsc.get('domains_monitored', 0)}</b>",
        ]
        low_alerts = gsc.get("low_indexing_alerts", [])
        if low_alerts:
            gsc_lines.append("   ⚠️ <b>Low Indexing Ratio (&lt;30%):</b>")
            for a in low_alerts:
                gsc_lines.append(f"     - {a['domain']}: {a['indexed']}/{a['published']} indexed ({a['ratio']:.1%})")
        gsc_section = "\n".join(gsc_lines) + "\n"

    return (
        f"📊 <b>DAILY FLEET PERFORMANCE REPORT</b>\n"
        f"📅 <b>Date:</b> {html.escape(str(stats['date']))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 <b>Articles Published Today:</b> {pub_today:,} (Total Live: {pub_total:,})\n"
        f"🗂️ <b>Pending Topics Queue:</b> {pending_topics:,}\n"
        f"☁️ <b>CF Pages Deploys Today:</b> {cf_today:,}/{pub_today:,}\n"
        f"⚡ <b>IndexNow Status:</b> {idx_status}\n"
        f"🏅 <b>Top Publishing Domain:</b> {top_pub} ({top_pub_cnt} posts)\n"
        f"🛡️ <b>Pipeline Alerts Today:</b> {err_badge}\n"
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
        f"🏆 <b>Top Domain:</b> {html.escape(str(stats['top_domain']))}\n"
        f"📉 <b>Lowest Domain:</b> {html.escape(str(stats['worst_domain']))}\n"
        f"{gsc_section}"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Autonomous Enterprise Fleet Autopilot</i>"
    )


def generate_and_save_report(
    target_date: Optional[str] = None,
    cpm_rate: float = 2.50,
    autopublish_db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Generates daily report, writes txt and json files to reports/ folder, returns report data."""
    stats = get_daily_fleet_stats(
        target_date=target_date,
        cpm_rate=cpm_rate,
        autopublish_db_path=autopublish_db_path,
    )
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


def send_daily_report_telegram(
    target_date: Optional[str] = None,
    autopublish_db_path: Optional[Path] = None,
) -> bool:
    """Generates and dispatches the daily report to Telegram."""
    report = generate_and_save_report(
        target_date=target_date,
        autopublish_db_path=autopublish_db_path,
    )
    msg = report["telegram_message"]

    try:
        from alert_bot import TelegramAlertBot
        bot = TelegramAlertBot()
        res = bot.send_message(msg, alert_type="daily_report", level="INFO")
        logger.info("Telegram daily report sent: %s", res)
        if isinstance(res, dict):
            return bool(res.get("success", res.get("ok", True)))
        return bool(res)
    except Exception as exc:
        logger.warning("Failed to dispatch daily report via Telegram: %s", exc)
        return False


def maybe_send_scheduled_morning_report(
    morning_hour: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
    state_path: Optional[Path] = None,
    autopublish_db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Send today's morning Telegram report at most once per calendar day once hour >= morning_hour."""
    current = now or datetime.datetime.now()
    target_hour = _load_morning_report_hour() if morning_hour is None else int(morning_hour)
    today_str = current.date().isoformat()
    state_file = Path(state_path) if state_path is not None else DAILY_REPORT_STATE_PATH

    if current.hour < target_hour:
        return {"sent": False, "reason": "before_schedule", "date": today_str, "hour": current.hour}

    try:
        if state_file.is_file():
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            if saved.get("last_sent_date") == today_str:
                return {"sent": False, "reason": "already_sent", "date": today_str}
    except Exception:
        pass

    sent_ok = send_daily_report_telegram(
        target_date=today_str,
        autopublish_db_path=autopublish_db_path,
    )
    if sent_ok:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {"last_sent_date": today_str, "sent_at": current.isoformat(), "morning_hour": target_hour},
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"sent": True, "reason": "dispatched", "date": today_str}

    return {"sent": False, "reason": "dispatch_failed", "date": today_str}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Generate daily fleet performance report")
    parser.add_argument("--date", help="Date to report on (YYYY-MM-DD)", default=None)
    parser.add_argument("--telegram", help="Send report to Telegram", action="store_true")
    parser.add_argument(
        "--schedule-tick",
        help="Send morning Telegram report once per day if local hour >= configured daily_report_hour",
        action="store_true",
    )
    args = parser.parse_args()

    if args.schedule_tick:
        res = maybe_send_scheduled_morning_report()
        print("Schedule tick result:", json.dumps(res))
    else:
        rep = generate_and_save_report(target_date=args.date)
        print("\n" + rep["telegram_message"] + "\n")
        print(f"Report saved to: {rep['txt_path']}")
        if args.telegram:
            send_daily_report_telegram(target_date=args.date)
