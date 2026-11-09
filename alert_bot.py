"""
alert_bot.py — Layer 4: 24/7 Telegram Live Revenue & Circuit Breaker Bot.

Delivers real-time fleet heartbeats, instant CTR circuit breaker warnings/emergencies,
CPL lead bounties, and daily revenue milestones to the operator via Telegram.
Supports dual-mode execution: Live Telegram Bot API and Mock/Interactive Standby.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

import db

# Ensure clean UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("alert_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _load_env_file() -> None:
    """Load key-value pairs from .env into os.environ if not already set."""
    env_path = Path(".env")
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception as exc:
        logger.debug("Failed reading .env: %s", exc)


_load_env_file()


class TelegramAlertBot:
    """
    Asynchronous and synchronous Telegram alert dispatcher.
    Monitors CTR across 10 publisher domains and pushes instant alerts.
    """

    TELEGRAM_API_BASE = "https://api.telegram.org"

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        bot_username: str | None = None,
    ) -> None:
        _load_env_file()
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.bot_username = (
            bot_username
            if bot_username is not None
            else os.environ.get("TELEGRAM_BOT_USERNAME", "adsterra_domain_alerts_bot").strip()
        )
        self._last_alert_ts: dict[str, float] = {}

    def is_live_configured(self) -> bool:
        """Returns True if bot token and chat_id are present and non-empty."""
        return bool(self.token and self.chat_id)

    def get_me(self) -> dict[str, Any]:
        """Test bot token validity via Telegram getMe API."""
        if not self.token:
            return {"ok": False, "description": "No bot token configured"}
        url = f"{self.TELEGRAM_API_BASE}/bot{self.token}/getMe"
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url)
                return res.json()
        except Exception as exc:
            return {"ok": False, "description": str(exc)}

    def poll_for_chat_id(self) -> dict[str, Any]:
        """
        Polls getUpdates to detect user's chat_id when they send /start to the bot.
        Returns the discovered chat_id and sender information.
        """
        if not self.token:
            return {"ok": False, "description": "No bot token configured"}
        url = f"{self.TELEGRAM_API_BASE}/bot{self.token}/getUpdates"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                data = res.json()
                if not data.get("ok"):
                    return {"ok": False, "description": data.get("description", "Failed to fetch updates")}
                updates = data.get("result", [])
                if not updates:
                    return {
                        "ok": False,
                        "description": "No messages received yet. Please open Telegram, search @"
                        + self.bot_username
                        + " and press /start",
                    }
                # Grab the latest update with a message
                for update in reversed(updates):
                    msg = update.get("message") or update.get("channel_post")
                    if msg and "chat" in msg:
                        chat = msg["chat"]
                        sender = msg.get("from", {})
                        return {
                            "ok": True,
                            "chat_id": str(chat["id"]),
                            "username": sender.get("username", chat.get("username", "Unknown")),
                            "first_name": sender.get("first_name", chat.get("title", "")),
                            "text": msg.get("text", ""),
                        }
                return {"ok": False, "description": "No chat messages found in updates"}
        except Exception as exc:
            return {"ok": False, "description": str(exc)}

    def send_message(
        self,
        text: str,
        alert_type: str = "INFO",
        level: str = "INFO",
        domain: str = "",
    ) -> dict[str, Any]:
        """
        Synchronously dispatch an alert message.
        If live Telegram credentials exist, sends via Telegram API.
        Always logs event to SQLite alert_logs for auditing.
        """
        sent_live = False
        api_error = ""

        if self.is_live_configured():
            url = f"{self.TELEGRAM_API_BASE}/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, json=payload)
                    data = resp.json()
                    if resp.status_code == 200 and data.get("ok"):
                        sent_live = True
                    else:
                        api_error = data.get("description", f"HTTP {resp.status_code}")
                        logger.warning("Telegram API rejected message: %s", api_error)
            except Exception as exc:
                api_error = str(exc)
                logger.warning("Failed to contact Telegram API: %s", exc)
        else:
            # Standby mode / simulated dispatch
            logger.info("[TELEGRAM STANDBY %s] [%s] %s", level, domain or "FLEET", text.replace("\n", " "))

        # Record to database
        db.init()
        log_id = db.record_alert_log(
            alert_type=alert_type,
            level=level,
            message=text,
            domain=domain,
            sent_live=sent_live,
        )

        return {
            "success": True if (sent_live or not self.is_live_configured()) else False,
            "sent_live": sent_live,
            "log_id": log_id,
            "level": level,
            "alert_type": alert_type,
            "error": api_error,
        }

    # ==========================================
    # High-Level Alert Templates
    # ==========================================

    def send_heartbeat(self, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Send periodic fleet heartbeat every 2 hours:
        Shows total sessions, impressions, clicks, CTR, Adsterra revenue, and CPL lead bounties.
        """
        if metrics is None:
            # Pull live metrics from database
            metrics_data = db.get_metrics(cpm_rate=5.50)
            lead_summary = db.today_leads_summary()
            fleet = db.all_domains_summary()

            impressions = metrics_data.get("impressions", 0)
            clicks = metrics_data.get("clicks", 0)
            ctr = metrics_data.get("ctr", 0.0)
            leads = lead_summary.get("today_leads", 0)
            bounty = lead_summary.get("estimated_bounty", 0.0)
            active_domains = len(fleet) if fleet else 10
            est_revenue = metrics_data.get("revenue", 0.0)
        else:
            impressions = metrics.get("impressions", 0)
            clicks = metrics.get("clicks", 0)
            ctr = metrics.get("ctr", 0.0)
            leads = metrics.get("leads", 0)
            bounty = metrics.get("bounty", 0.0)
            active_domains = metrics.get("active_domains", 10)
            est_revenue = metrics.get("revenue", 0.0)

        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        msg = (
            "📊 <b>MAHI Multi-Domain Fleet 2-Hour Heartbeat</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Active Domains:</b> {active_domains}/10\n"
            f"👁️ <b>Impressions:</b> {impressions:,}\n"
            f"🖱️ <b>Ad Clicks:</b> {clicks:,} (CTR: <b>{ctr:.2f}%</b>)\n"
            f"💰 <b>Est. Adsterra Yield:</b> ${est_revenue:.4f}\n"
            f"🎯 <b>CPL Leads Captured:</b> {leads} (~${bounty:.2f} bounty)\n"
            "🛡️ <b>Circuit Breaker:</b> 🟢 NORMAL (Safety ceiling &lt; 4.4%)\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{utc_now}</i>"
        )
        return self.send_message(msg, alert_type="heartbeat", level="INFO")

    def send_circuit_breaker_warning(self, domain: str, ctr: float) -> dict[str, Any]:
        """
        Triggered when a domain's CTR reaches or exceeds 4.40%.
        Throttles click probability by 80% to keep the account completely safe.
        """
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        msg = (
            "⚠️ <b>CIRCUIT BREAKER WARNING: CTR SPIKE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Domain:</b> <code>{domain}</code>\n"
            f"📈 <b>Current CTR:</b> <b>{ctr:.2f}%</b> (Ceiling: 4.40%)\n"
            "🛡️ <b>Defensive Action:</b> Dynamic click probability throttled by 80%.\n"
            "🔄 <b>Mode:</b> Dilution traffic accelerated to protect domain.\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{now}</i>"
        )
        return self.send_message(msg, alert_type="warning", level="WARNING", domain=domain)

    def send_circuit_breaker_emergency(self, domain: str, ctr: float) -> dict[str, Any]:
        """
        Triggered when a domain's CTR reaches or exceeds 5.00%.
        Immediately halts 100% of clicks for that domain.
        """
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        msg = (
            "🚨 <b>CRITICAL EMERGENCY: CIRCUIT BREAKER TRIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Domain:</b> <code>{domain}</code>\n"
            f"🔥 <b>Current CTR:</b> <b>{ctr:.2f}%</b> (EXCEEDED 5.00% MAXIMUM!)\n"
            "🛑 <b>Defensive Action:</b> 100% Ad Clicks PAUSED immediately.\n"
            "🛡️ Pure dwell and impression dilution active until CTR drops &lt; 3.5%.\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{now}</i>"
        )
        return self.send_message(msg, alert_type="emergency", level="CRITICAL", domain=domain)

    def send_milestone_alert(self, milestone_name: str, value: float) -> dict[str, Any]:
        """Triggered when a daily revenue or lead bounty milestone is reached."""
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        msg = (
            "🎯 <b>DAILY MILESTONE ACHIEVED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>Milestone:</b> {milestone_name}\n"
            f"💵 <b>Current Value:</b> <b>${value:.2f}</b>\n"
            "🚀 Multi-domain cluster running at peak organic yield!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{now}</i>"
        )
        return self.send_message(msg, alert_type="milestone", level="SUCCESS")

    def send_pool_warning(self, healthy_ips: int, minimum_required: int = 10) -> dict[str, Any]:
        """Triggered when proxy pool dips below safe threshold."""
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        msg = (
            "⚠️ <b>PROXY POOL HEALTH WARNING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔌 <b>Healthy IPs Available:</b> <b>{healthy_ips}</b> (Target: ≥{minimum_required})\n"
            "🔄 Failover cooldown recycling active. Pool replenishment recommended.\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{now}</i>"
        )
        return self.send_message(msg, alert_type="pool_low", level="WARNING")

    def send_test_alert(self) -> dict[str, Any]:
        """Send a test ping to verify end-to-end bot connectivity."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        status_mode = "LIVE (Push Notifications Enabled)" if self.is_live_configured() else "STANDBY (Mock / UI Log Mode)"
        msg = (
            "🚀 <b>MAHI Antigravity Telegram Alert System Live!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot:</b> <code>@{self.bot_username}</code>\n"
            f"📡 <b>Status:</b> {status_mode}\n"
            "🛡️ <b>Monitored:</b> 10 High-Yield Financial & Utility Domains\n"
            "⚡ <b>Circuit Breakers:</b> Active (4.4% Warning, 5.0% Emergency)\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{now}</i>"
        )
        return self.send_message(msg, alert_type="test_ping", level="INFO")


def check_and_trigger_circuit_breaker(domain: str, bot: TelegramAlertBot | None = None) -> dict[str, Any]:
    """
    Check current CTR for a domain and dispatch alerts if thresholds are breached.
    Includes 15-minute rate-limiting per domain to prevent spam.
    """
    if bot is None:
        bot = TelegramAlertBot()

    safety = db.check_domain_safety(domain)
    ctr = safety.get("current_ctr", 0.0)
    status = safety.get("status", "OPTIMAL")

    now_ts = datetime.now(timezone.utc).timestamp()
    last_ts = bot._last_alert_ts.get(domain, 0.0)

    # 15-minute cooldown between repeated warnings for the same domain
    if now_ts - last_ts < 900:
        return {"status": "cooldown", "ctr": ctr, "domain": domain}

    if status == "PAUSED" or ctr >= 5.00:
        bot._last_alert_ts[domain] = now_ts
        res = bot.send_circuit_breaker_emergency(domain, ctr)
        return {"status": "emergency_sent", "ctr": ctr, "res": res}
    elif status == "GUARD_ACTIVE" or ctr >= 4.40:
        bot._last_alert_ts[domain] = now_ts
        res = bot.send_circuit_breaker_warning(domain, ctr)
        return {"status": "warning_sent", "ctr": ctr, "res": res}

    return {"status": "normal", "ctr": ctr, "domain": domain}


def main() -> None:
    parser = argparse.ArgumentParser(description="MAHI Layer 4: Telegram Live Alert Bot")
    parser.add_argument("--test-alert", action="store_true", help="Send a test ping alert")
    parser.add_argument("--heartbeat", action="store_true", help="Send a 2-hour fleet heartbeat summary")
    parser.add_argument("--check-config", action="store_true", help="Verify Telegram bot token via getMe")
    parser.add_argument("--get-chat-id", action="store_true", help="Poll for chat_id after sending /start to bot")

    args = parser.parse_args()
    bot = TelegramAlertBot()

    print("==================================================================")
    print("  MAHI LAYER 4: 24/7 TELEGRAM REVENUE & CIRCUIT BREAKER BOT")
    print(f"  Bot Username: @{bot.bot_username}")
    print(f"  Live Configured: {'YES (Push Active)' if bot.is_live_configured() else 'NO (Standby Mock Mode)'}")
    print("==================================================================")

    if args.check_config:
        info = bot.get_me()
        print(f"[*] Telegram getMe response: {info}")
        return

    if args.get_chat_id:
        print("[*] Polling Telegram getUpdates for chat_id...")
        res = bot.poll_for_chat_id()
        if res.get("ok"):
            print(f"[+] Found User Chat ID: {res.get('chat_id')}")
            print(f"[+] Username: @{res.get('username')}, Name: {res.get('first_name')}")
            print(f"[+] Add this to your .env file: TELEGRAM_CHAT_ID={res.get('chat_id')}")
        else:
            print(f"[-] {res.get('description')}")
        return

    if args.heartbeat:
        print("[*] Dispatching fleet heartbeat...")
        res = bot.send_heartbeat()
        print(f"[+] Heartbeat dispatched: {res}")
        return

    # Default action or --test-alert
    print("[*] Dispatching test alert...")
    res = bot.send_test_alert()
    print(f"[+] Alert Result: {res}")
    print("[+] Check sessions.db table 'alert_logs' or your Telegram app.")


if __name__ == "__main__":
    main()
