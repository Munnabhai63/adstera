"""
tests/test_alert_bot.py — Unit test suite for Layer 4: Telegram Alert Bot.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import db
from alert_bot import TelegramAlertBot, check_and_trigger_circuit_breaker


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_sessions.db"
    monkeypatch.setattr(db, "_DB_PATH", test_db)
    db.init()
    yield


def test_alert_bot_init_defaults():
    bot = TelegramAlertBot(token="", chat_id="", bot_username="adsterra_domain_alerts_bot")
    assert bot.token == ""
    assert bot.chat_id == ""
    assert bot.bot_username == "adsterra_domain_alerts_bot"
    assert bot.is_live_configured() is False


def test_alert_bot_is_live_configured():
    live_bot = TelegramAlertBot(token="123456:ABC-DEF", chat_id="987654321")
    assert live_bot.is_live_configured() is True

    missing_chat = TelegramAlertBot(token="123456:ABC-DEF", chat_id="")
    assert missing_chat.is_live_configured() is False


def test_alert_bot_send_heartbeat_standby():
    bot = TelegramAlertBot(token="", chat_id="")
    metrics = {
        "impressions": 1500,
        "clicks": 30,
        "ctr": 2.0,
        "revenue": 8.25,
        "leads": 5,
        "bounty": 15.00,
        "active_domains": 10,
    }
    res = bot.send_heartbeat(metrics=metrics)
    assert res["success"] is True
    assert res["sent_live"] is False
    assert res["level"] == "INFO"
    assert res["alert_type"] == "heartbeat"

    # Verify stored in SQLite alert_logs
    alerts = db.get_recent_alerts(limit=5)
    assert len(alerts) >= 1
    latest = alerts[0]
    assert latest["alert_type"] == "heartbeat"
    assert "1,500" in latest["message"]
    assert "$8.25" in latest["message"]
    assert "CTR: <b>2.00%</b>" in latest["message"]


def test_alert_bot_circuit_breaker_warning_and_emergency():
    bot = TelegramAlertBot(token="", chat_id="")

    # Warning alert
    res_warn = bot.send_circuit_breaker_warning("tazaloan.com", ctr=4.52)
    assert res_warn["level"] == "WARNING"
    assert res_warn["alert_type"] == "warning"

    # Emergency alert
    res_emerg = bot.send_circuit_breaker_emergency("loanraaj.com", ctr=5.35)
    assert res_emerg["level"] == "CRITICAL"
    assert res_emerg["alert_type"] == "emergency"

    alerts = db.get_recent_alerts(limit=5)
    types = [a["alert_type"] for a in alerts]
    assert "warning" in types
    assert "emergency" in types


def test_alert_bot_milestone_and_pool_warning():
    bot = TelegramAlertBot(token="", chat_id="")

    m_res = bot.send_milestone_alert("First $50 Day", 52.40)
    assert m_res["level"] == "SUCCESS"
    assert m_res["alert_type"] == "milestone"

    p_res = bot.send_pool_warning(healthy_ips=6, minimum_required=10)
    assert p_res["level"] == "WARNING"
    assert p_res["alert_type"] == "pool_low"


def test_alert_bot_live_dispatch_mock():
    bot = TelegramAlertBot(token="123456:FAKE_TOKEN", chat_id="999888777")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = bot.send_test_alert()
        assert res["success"] is True
        assert res["sent_live"] is True
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "bot123456:FAKE_TOKEN/sendMessage" in call_url


def test_check_and_trigger_circuit_breaker_logic():
    bot = TelegramAlertBot(token="", chat_id="")
    domain = "karzseva.com"

    # Simulate 20 impressions, 2 clicks -> CTR 10% (exceeds 5.0%)
    for _ in range(20):
        db.log_session("p1", "ua", "ref", 30.0, pages=1, ad_clicks=0, impressions=1, domain=domain)
    db.log_session("p1", "ua", "ref", 30.0, pages=1, ad_clicks=2, impressions=1, domain=domain)

    res = check_and_trigger_circuit_breaker(domain, bot=bot)
    assert res["status"] in ("emergency_sent", "warning_sent")
    assert res["ctr"] >= 4.40

    # Second call should trigger 15-minute cooldown
    res_cooldown = check_and_trigger_circuit_breaker(domain, bot=bot)
    assert res_cooldown["status"] == "cooldown"
