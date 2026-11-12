"""
alerts.py — Alert dispatcher for A2 anomaly events.

Sends anomaly notifications to one or more configured channels:

* **Telegram** — via the Bot API ``sendMessage`` endpoint (token from env).
* **Webhook**  — HTTP POST with a JSON payload to any URL.
* **Email**    — stub (email_enabled=false by default; extend as needed).

Deduplication: the same ``(metric, severity)`` pair is not re-dispatched
within a 5-minute window.

Design contract:

* :meth:`AlertDispatcher.dispatch` **never raises**.  All exceptions are
  caught and logged so that an alert failure never interrupts the main loop.
* The dispatcher is stateless beyond its in-memory dedup table, so it can be
  recreated at any time without data loss.

Usage::

    from ai_engine.a2_anomaly.alerts import AlertDispatcher
    from ai_engine.config import load_ai_config

    cfg = load_ai_config("ai_engine_config.yaml")
    dispatcher = AlertDispatcher(cfg.a2_anomaly.alert)
    dispatcher.dispatch(anomaly_result)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_engine.config import AlertConfig
    from ai_engine.interfaces import AnomalyResult

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_S: float = 300.0  # 5 minutes


class AlertDispatcher:
    """Dispatches anomaly alerts to Telegram, webhook, and/or email.

    Args:
        config: :class:`~ai_engine.config.AlertConfig` with channel settings, or None.
        dedup_window_s: Window in seconds for suppressing duplicates.
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        dedup_window_s: float = _DEDUP_WINDOW_S,
    ) -> None:
        self._cfg = config
        self._dedup_window_s = float(dedup_window_s)
        # Dedup table: key -> last_dispatch_ts
        self._dedup: Dict[Any, float] = {}
        self._handlers: list = []

    def register_handler(self, handler) -> None:
        """Register a callback for alert dispatching."""
        self._handlers.append(handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dispatch(self, anomaly_result: Any, message: str = "") -> None:
        """Send alerts for *anomaly_result* to all configured channels.

        Can also be called as `dispatch(alert_key, message)`.
        OK-severity results are silently ignored (no alert needed).
        Duplicate alerts within the dedup window are suppressed.

        This method **never raises** — all exceptions are logged internally.
        """
        now = time.time()
        if isinstance(anomaly_result, str):
            key = anomaly_result
            last = self._dedup.get(key, 0.0)
            if now - last < self._dedup_window_s:
                logger.debug("alerts: suppressed duplicate %s alert (%.0fs ago)", key, now - last)
                return
            self._dedup[key] = now
            for h in self._handlers:
                try:
                    h(message or key)
                except Exception as exc:
                    logger.error("alerts: handler error — %s", exc)
            return

        if anomaly_result.ok or anomaly_result.severity == "OK":
            return

        # Build a composite key for dedup: join all triggered reason metrics
        # with the overall severity.
        dedup_key: Tuple[str, str] = (
            ";".join(anomaly_result.reasons[:3]),
            anomaly_result.severity,
        )
        last = self._dedup.get(dedup_key, 0.0)
        if now - last < self._dedup_window_s:
            logger.debug(
                "alerts: suppressed duplicate %s alert (%.0fs ago)",
                anomaly_result.severity,
                now - last,
            )
            return

        self._dedup[dedup_key] = now

        formatted_msg = self._format_message(anomaly_result)

        for h in self._handlers:
            try:
                h(formatted_msg)
            except Exception as exc:
                logger.error("alerts: handler error — %s", exc)

        if self._cfg is not None:
            if getattr(self._cfg, "telegram_enabled", False):
                self._send_telegram(formatted_msg, anomaly_result)

            if getattr(self._cfg, "webhook_url", ""):
                self._send_webhook(anomaly_result)

            if getattr(self._cfg, "email_enabled", False):
                self._send_email(formatted_msg, anomaly_result)

    # ------------------------------------------------------------------
    # Channel implementations
    # ------------------------------------------------------------------

    def _format_message(self, result: "AnomalyResult") -> str:
        """Build a human-readable alert text.

        Args:
            result: The anomaly result to describe.

        Returns:
            Formatted alert string.
        """
        lines = [
            f"🚨 AI Engine Anomaly [{result.severity}]",
            f"Metrics domain: {result.metrics.domain or 'global'}",
        ]
        for reason in result.reasons:
            lines.append(f"  • {reason}")
        scores_txt = ", ".join(
            f"{k}={v:.2f}" for k, v in result.scores.items()
        )
        if scores_txt:
            lines.append(f"Scores: {scores_txt}")
        lines.append(
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(result.metrics.ts))}"
        )
        return "\n".join(lines)

    def _send_telegram(self, message: str, result: "AnomalyResult") -> None:
        """POST the alert text to the Telegram Bot API.

        Reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from the
        environment.  Silently skips if either variable is absent.

        Args:
            message: Pre-formatted text to send.
            result:  Original anomaly result (unused here, available for subclasses).
        """
        try:
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                logger.debug(
                    "alerts: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping"
                )
                return

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps(
                {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.getcode()
                if status != 200:
                    logger.warning("alerts: Telegram returned HTTP %d", status)
                else:
                    logger.info("alerts: Telegram alert sent (%s)", result.severity)
        except Exception as exc:
            logger.error("alerts: Telegram dispatch failed — %s", exc)

    def _send_webhook(self, result: "AnomalyResult") -> None:
        """POST a JSON payload to the configured webhook URL.

        Args:
            result: Anomaly result to serialise and POST.
        """
        try:
            url = self._cfg.webhook_url
            payload = json.dumps(
                {
                    "severity": result.severity,
                    "reasons": result.reasons,
                    "scores": result.scores,
                    "metrics": {
                        "rpm": result.metrics.rpm,
                        "ctr": result.metrics.ctr,
                        "empty_ad_rate": result.metrics.empty_ad_rate,
                        "load_time_ms": result.metrics.load_time_ms,
                        "error_rate": result.metrics.error_rate,
                        "repeated_creative_rate": result.metrics.repeated_creative_rate,
                        "domain": result.metrics.domain,
                        "device_id": result.metrics.device_id,
                        "ts": result.metrics.ts,
                    },
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.getcode()
                if status not in (200, 201, 202, 204):
                    logger.warning("alerts: webhook returned HTTP %d", status)
                else:
                    logger.info("alerts: webhook alert dispatched (%s)", result.severity)
        except Exception as exc:
            logger.error("alerts: webhook dispatch failed — %s", exc)

    def _send_email(self, message: str, result: "AnomalyResult") -> None:
        """Email alert stub — extend to wire up smtplib when needed.

        Args:
            message: Pre-formatted text to email.
            result:  Original anomaly result.
        """
        logger.info(
            "alerts: email_enabled=true but no SMTP config present — skipping email for %s",
            result.severity,
        )
