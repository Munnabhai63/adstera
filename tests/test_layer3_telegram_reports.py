"""Layer 3 acceptance tests: publishing + IndexNow daily report, morning scheduler, and instant Telegram alerts."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import re
import sqlite3
import sys
import urllib.request
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import alert_bot
import autopublish_daemon
import daily_report
import db
import instant_indexer


def _create_test_autopublish_db(db_path: Path, today_str: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE published_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT,
                slug TEXT UNIQUE,
                title TEXT,
                category TEXT,
                words INTEGER,
                published_at TIMESTAMP,
                cf_deployed INTEGER DEFAULT 0,
                google_pinged INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 100.0
            )
            """
        )
        con.execute(
            """
            CREATE TABLE topic_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT,
                category TEXT,
                topic TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP
            )
            """
        )
        con.execute(
            "INSERT INTO published_posts (domain, slug, title, category, words, published_at, cf_deployed, google_pinged) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("loankiseva", "mudra-post-1", "Mudra 1", "Mudra", 1600, f"{today_str}T06:00:00", 1, 1),
        )
        con.execute(
            "INSERT INTO published_posts (domain, slug, title, category, words, published_at, cf_deployed, google_pinged) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("loankiseva", "mudra-post-2", "Mudra 2", "Mudra", 1550, f"{today_str}T07:10:00", 1, 0),
        )
        con.execute(
            "INSERT INTO published_posts (domain, slug, title, category, words, published_at, cf_deployed, google_pinged) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("tazaloan", "old-post", "Old", "Loans", 1500, "2026-10-01T10:00:00", 1, 1),
        )
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("loanraaj", "Business", "Pending Topic 1", "pending", f"{today_str}T01:00:00"),
        )
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("karzseva", "Credit", "Pending Topic 2", "pending", f"{today_str}T01:05:00"),
        )
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("loankiseva", "Mudra", "Done Topic", "published", f"{today_str}T06:00:00"),
        )
        con.commit()


def test_daily_fleet_stats_includes_publishing_and_indexnow(tmp_path: Path, monkeypatch) -> None:
    sess_db = tmp_path / "sessions.db"
    ap_db = tmp_path / "autopublish.db"
    today_str = "2026-11-11"
    _create_test_autopublish_db(ap_db, today_str)

    monkeypatch.setattr(db, "_DB_PATH", sess_db)
    db.init()
    db.record_alert_log("error_cloudflare_deploy", "WARNING", "Wrangler err", domain="loankiseva", sent_live=True)

    stats = daily_report.get_daily_fleet_stats(target_date=today_str, autopublish_db_path=ap_db)
    assert stats["published_today"] == 2
    assert stats["published_total"] == 3
    assert stats["pending_topics"] == 2
    assert stats["cf_deployed_today"] == 2
    assert stats["indexnow_pinged_today"] == 1
    assert stats["indexnow_pinged_total"] == 2
    assert stats["top_publishing_domain"] == "loankiseva"
    assert stats["top_publishing_count"] == 2
    assert stats["daemon_errors_today"] >= 0


def test_format_telegram_report_includes_publishing_section_and_escapes_html() -> None:
    stats = {
        "date": "2026-11-11",
        "published_today": 5,
        "published_total": 180,
        "pending_topics": 42,
        "cf_deployed_today": 5,
        "indexnow_pinged_today": 4,
        "indexnow_pinged_total": 175,
        "top_publishing_domain": "loankiseva<script>",
        "top_publishing_count": 3,
        "daemon_errors_today": 1,
        "total_sessions": 0,
        "ok_sessions": 0,
        "degraded_sessions": 0,
        "degraded_pct": 0.0,
        "avg_dwell": 0.0,
        "total_impressions": 0,
        "total_clicks": 0,
        "fleet_ctr": 0.0,
        "cpa_conversions": 0,
        "cpa_revenue_usd": 0.0,
        "ad_revenue_usd": 0.0,
        "total_revenue_usd": 0.0,
        "top_domain": "—",
        "worst_domain": "—",
    }
    html_msg = daily_report.format_telegram_report(stats)
    assert "Articles Published Today" in html_msg
    assert "Pending Topics Queue" in html_msg
    assert "IndexNow Status" in html_msg
    assert "Top Publishing Domain" in html_msg
    assert "<script>" not in html_msg
    assert "&lt;script&gt;" in html_msg


def test_morning_report_scheduler_gates_and_deduplicates(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "daily_report_state.json"
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr(daily_report, "send_daily_report_telegram", mock_send)

    early = daily_report.maybe_send_scheduled_morning_report(
        morning_hour=8,
        now=datetime.datetime(2026, 11, 11, 6, 30),
        state_path=state_file,
    )
    assert early["sent"] is False and early["reason"] == "before_schedule"
    assert mock_send.call_count == 0

    morning = daily_report.maybe_send_scheduled_morning_report(
        morning_hour=8,
        now=datetime.datetime(2026, 11, 11, 8, 15),
        state_path=state_file,
    )
    assert morning["sent"] is True and morning["reason"] == "dispatched"
    assert mock_send.call_count == 1

    repeat = daily_report.maybe_send_scheduled_morning_report(
        morning_hour=8,
        now=datetime.datetime(2026, 11, 11, 11, 0),
        state_path=state_file,
    )
    assert repeat["sent"] is False and repeat["reason"] == "already_sent"
    assert mock_send.call_count == 1

    next_day = daily_report.maybe_send_scheduled_morning_report(
        morning_hour=8,
        now=datetime.datetime(2026, 11, 12, 8, 1),
        state_path=state_file,
    )
    assert next_day["sent"] is True and next_day["date"] == "2026-11-12"
    assert mock_send.call_count == 2


def test_pipeline_error_alert_cooldown_and_logging(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "sessions.db")
    bot = alert_bot.TelegramAlertBot(token="", chat_id="")
    first = bot.send_pipeline_error_alert(
        stage="cloudflare_deploy",
        detail="Wrangler exit=1 <err>",
        domain="loanraaj",
        level="WARNING",
        cooldown_sec=900,
    )
    assert first["success"] is True and "log_id" in first

    suppressed = bot.send_pipeline_error_alert(
        stage="cloudflare_deploy",
        detail="Repeated failure",
        domain="loanraaj",
        level="WARNING",
        cooldown_sec=900,
    )
    assert suppressed.get("suppressed") is True

    other_stage = bot.send_pipeline_error_alert(
        stage="indexnow_ping",
        detail="IndexNow HTTP 500",
        domain="loanraaj",
    )
    assert "log_id" in other_stage


def test_autopublish_daemon_error_hooks_on_failure(tmp_path: Path, monkeypatch) -> None:
    ap_db = tmp_path / "autopublish.db"
    monkeypatch.setattr(autopublish_daemon, "DB_PATH", str(ap_db))
    autopublish_daemon.init_db()
    with sqlite3.connect(ap_db) as con:
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            ("loanraaj", "Business", "Test Failure Topic", "2026-11-11T00:00:00"),
        )
        con.commit()

    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "generate_seo_brief",
        lambda site, topic: {"seo_title": "T", "meta_description": "D", "primary_keyword": "kw"},
    )
    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "get_dynamic_seo_image",
        lambda kw, site: {"url": "https://example.com/a.jpg", "alt": "alt"},
    )
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: ("", []))

    captured: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        autopublish_daemon,
        "_notify_pipeline_error",
        lambda stage, detail, domain="", level="WARNING": captured.append((stage, domain, detail)),
    )

    ok = autopublish_daemon.publish_next_post(specific_site="loanraaj")
    assert ok is False
    assert captured and captured[0][0] == "article_generation" and captured[0][1] == "loanraaj"


def test_instant_indexer_records_honest_ping_status(tmp_path: Path, monkeypatch) -> None:
    import gsc_auth

    ap_db = tmp_path / "autopublish.db"
    _create_test_autopublish_db(ap_db, "2026-11-11")
    monkeypatch.setattr(instant_indexer, "DB_PATH", str(ap_db))
    monkeypatch.setattr(instant_indexer, "provision_verification_keys", lambda: None)
    monkeypatch.setattr(instant_indexer, "update_sitemap_xml", lambda site_id, url: None)
    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", lambda dom, urls: False)
    monkeypatch.setattr(instant_indexer, "ping_google_sitemap", lambda dom: False)
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: False)

    ok = instant_indexer.broadcast_new_post("loankiseva", "https://loankiseva.com/mudra-post-1")
    assert ok is False
    with sqlite3.connect(ap_db) as con:
        pinged = con.execute("SELECT google_pinged FROM published_posts WHERE slug='mudra-post-1'").fetchone()[0]
        assert pinged == 0


def test_no_hardcoded_telegram_tokens_in_layer3_modules() -> None:
    bot_token_pat = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{25,}\b")
    checked = []
    for name in ("telegram_link.py", "alert_bot.py", "daily_report.py", "autopublish_daemon.py"):
        target = ROOT_DIR / name
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        assert not bot_token_pat.search(text), f"Hardcoded Telegram token found in {name}"
        checked.append(name)
    assert "alert_bot.py" in checked
    assert "daily_report.py" in checked
    assert "autopublish_daemon.py" in checked


def test_live_ui_telegram_status_and_daily_report_button() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/api/telegram/status", timeout=8) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read().decode("utf-8"))
        assert payload.get("success") is True
        assert payload.get("configured") is True

    with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=8) as resp:
        assert resp.status == 200
        crm_body = resp.read().decode("utf-8", errors="replace")
        assert "u5BtnTgDailyReport" in crm_body

    with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=8) as resp:
        assert resp.status == 200
        html_body = resp.read().decode("utf-8", errors="replace")
        assert "btnTgDailyReport" in html_body
        assert "sendTelegramDailyReport" in html_body


def test_live_ui_telegram_status_against_fresh_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEFECT P-1: Telegram status route must return well-formed JSON even against an uninitialized empty DB."""
    fresh_db = tmp_path / "fresh_empty_sessions.db"
    monkeypatch.setattr(db, "_DB_PATH", fresh_db)

    with urllib.request.urlopen("http://127.0.0.1:5050/api/telegram/status", timeout=8) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read().decode("utf-8"))
        assert "success" in payload
        assert "summary" in payload
        assert "recent_alerts" in payload
        assert isinstance(payload["recent_alerts"], list)
