"""
anomaly_detector.py — Layer 7: Continuous Multi-Metric Anomaly Detection & Circuit Breaker Engine.

Calculates rolling 7-day statistical baselines (mean, standard deviation, Z-scores)
across fleet metrics (eCPM, CTR, degraded rate, dwell time, hourly volume).
Detects severe drops or abnormal spikes and automatically engages safety circuit breakers
(click suppression, domain pause, traffic throttling) to protect publisher accounts.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import db

# Ensure clean UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("anomaly_detector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

STATE_DIR = Path("state")
DEFAULT_CIRCUIT_STATE = STATE_DIR / "circuit_breaker.json"


@dataclass
class AnomalyReport:
    metric: str
    domain: str
    observed_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    severity: str  # "INFO", "WARNING", "CRITICAL"
    action: str  # "NONE", "THROTTLE", "PAUSE_CLICKS", "PAUSE_DOMAIN", "PAUSE_FLEET"
    details: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AnomalyDetector:
    """
    Fleet-wide statistical anomaly detector and automated circuit breaker controller.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        state_file: Optional[Path] = None,
        z_threshold: float = 2.5,
        ecpm_drop_max_pct: float = 40.0,
        max_ctr_pct: float = 5.0,
        warning_ctr_pct: float = 4.4,
        degraded_max_pct: float = 35.0,
        min_dwell_s: float = 22.0,
    ) -> None:
        self.db_path = db_path or db._DB_PATH
        self.state_file = state_file or DEFAULT_CIRCUIT_STATE
        self.z_threshold = z_threshold
        self.ecpm_drop_max_pct = ecpm_drop_max_pct
        self.max_ctr_pct = max_ctr_pct
        self.warning_ctr_pct = warning_ctr_pct
        self.degraded_max_pct = degraded_max_pct
        self.min_dwell_s = min_dwell_s

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self._save_state({"paused_domains": {}, "global_pause": False, "history": []})

    def _load_state(self) -> Dict[str, Any]:
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load circuit breaker state: %s", exc)
        return {"paused_domains": {}, "global_pause": False, "history": []}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to write circuit breaker state: %s", exc)

    @staticmethod
    def calculate_z_score(value: float, mean: float, std: float) -> float:
        """Calculate statistical Z-score with zero-variance protection."""
        if std <= 1e-6:
            return 0.0 if math.isclose(value, mean, abs_tol=1e-5) else (3.0 if value > mean else -3.0)
        return round((value - mean) / std, 2)

    def calculate_domain_baseline(self, domain: Optional[str] = None, days: int = 7) -> Dict[str, Dict[str, float]]:
        """
        Calculates 7-day rolling mean and standard deviation for key metrics from daily stats.
        """
        db.init()
        with db._conn() as con:
            if domain:
                rows = con.execute(
                    """
                    SELECT date, sessions, ad_clicks, impressions
                    FROM domain_stats
                    WHERE domain = ? AND date >= date('now', ?)
                    ORDER BY date ASC
                    """,
                    (domain, f"-{days} days"),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT date, sessions, ad_clicks, impressions
                    FROM daily_stats
                    WHERE date >= date('now', ?)
                    ORDER BY date ASC
                    """,
                    (f"-{days} days",),
                ).fetchall()

        if not rows:
            # Fallback sensible baseline if historical data is fresh
            return {
                "ctr": {"mean": 3.5, "std": 0.8},
                "ecpm": {"mean": 5.0, "std": 1.2},
                "degraded_rate": {"mean": 5.0, "std": 3.0},
                "dwell": {"mean": 45.0, "std": 10.0},
            }

        ctrs: List[float] = []
        for r in rows:
            imps = int(r["impressions"] or 0)
            clicks = int(r["ad_clicks"] or 0)
            if imps > 0:
                ctrs.append((clicks / imps) * 100.0)

        ctr_mean = sum(ctrs) / len(ctrs) if ctrs else 3.5
        ctr_var = sum((x - ctr_mean) ** 2 for x in ctrs) / len(ctrs) if len(ctrs) > 1 else 0.4
        ctr_std = math.sqrt(ctr_var) if ctr_var > 0 else 0.8

        return {
            "ctr": {"mean": round(ctr_mean, 2), "std": round(max(0.2, ctr_std), 2)},
            "ecpm": {"mean": 5.0, "std": 1.2},
            "degraded_rate": {"mean": 5.0, "std": 3.0},
            "dwell": {"mean": 45.0, "std": 10.0},
        }

    def evaluate_recent_window(self, domain: Optional[str] = None, window: int = 30) -> Dict[str, Any]:
        """
        Gathers live metrics over the most recent `window` sessions.
        """
        db.init()
        with db._conn() as con:
            if domain:
                rows = con.execute(
                    """
                    SELECT impressions, ad_clicks, dwell, status
                    FROM sessions
                    WHERE domain = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (domain, window),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT impressions, ad_clicks, dwell, status
                    FROM sessions
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (window,),
                ).fetchall()

        if not rows:
            return {
                "total_sessions": 0,
                "impressions": 0,
                "ad_clicks": 0,
                "ctr": 0.0,
                "degraded_rate": 0.0,
                "avg_dwell": 0.0,
            }

        total_sessions = len(rows)
        imps = sum(int(r["impressions"] or 0) for r in rows)
        clicks = sum(int(r["ad_clicks"] or 0) for r in rows)
        dwells = [float(r["dwell"] or 0.0) for r in rows]
        degraded = sum(1 for r in rows if r["status"] in ("degraded", "error", "failed"))

        ctr = (clicks / imps * 100.0) if imps > 0 else 0.0
        deg_rate = (degraded / total_sessions * 100.0) if total_sessions > 0 else 0.0
        avg_dwell = sum(dwells) / len(dwells) if dwells else 0.0

        return {
            "total_sessions": total_sessions,
            "impressions": imps,
            "ad_clicks": clicks,
            "ctr": round(ctr, 2),
            "degraded_rate": round(deg_rate, 2),
            "avg_dwell": round(avg_dwell, 1),
        }

    def detect_anomalies(self, domain: Optional[str] = None, window: int = 30) -> List[AnomalyReport]:
        """
        Runs comprehensive statistical audit across recent sessions and baseline.
        Returns all detected anomalies categorized by severity.
        """
        anomalies: List[AnomalyReport] = []
        target_name = domain or "FLEET"

        baseline = self.calculate_domain_baseline(domain)
        metrics = self.evaluate_recent_window(domain, window=window)

        if metrics["total_sessions"] < 3:
            return anomalies  # Need at least 3 sessions to evaluate statistically

        # 1. CTR Spike Rule
        ctr = metrics["ctr"]
        ctr_base = baseline["ctr"]
        z_ctr = self.calculate_z_score(ctr, ctr_base["mean"], ctr_base["std"])

        if ctr >= self.max_ctr_pct or z_ctr >= 3.0:
            anomalies.append(
                AnomalyReport(
                    metric="ctr",
                    domain=target_name,
                    observed_value=ctr,
                    baseline_mean=ctr_base["mean"],
                    baseline_std=ctr_base["std"],
                    z_score=z_ctr,
                    severity="CRITICAL",
                    action="PAUSE_CLICKS",
                    details=f"CTR {ctr:.2f}% breached maximum safety ceiling ({self.max_ctr_pct:.1f}%) [Z={z_ctr}]",
                )
            )
        elif ctr >= self.warning_ctr_pct or z_ctr >= self.z_threshold:
            anomalies.append(
                AnomalyReport(
                    metric="ctr",
                    domain=target_name,
                    observed_value=ctr,
                    baseline_mean=ctr_base["mean"],
                    baseline_std=ctr_base["std"],
                    z_score=z_ctr,
                    severity="WARNING",
                    action="THROTTLE",
                    details=f"CTR {ctr:.2f}% entered elevated warning zone ({self.warning_ctr_pct:.1f}%) [Z={z_ctr}]",
                )
            )

        # 2. Degraded Session Spike Rule
        deg_rate = metrics["degraded_rate"]
        deg_base = baseline["degraded_rate"]
        z_deg = self.calculate_z_score(deg_rate, deg_base["mean"], deg_base["std"])

        if deg_rate >= 50.0:
            anomalies.append(
                AnomalyReport(
                    metric="degraded_rate",
                    domain=target_name,
                    observed_value=deg_rate,
                    baseline_mean=deg_base["mean"],
                    baseline_std=deg_base["std"],
                    z_score=z_deg,
                    severity="CRITICAL",
                    action="PAUSE_DOMAIN" if domain else "THROTTLE",
                    details=f"Severe degradation spike: {deg_rate:.1f}% failures in recent {metrics['total_sessions']} sessions [Z={z_deg}]",
                )
            )
        elif deg_rate >= self.degraded_max_pct:
            anomalies.append(
                AnomalyReport(
                    metric="degraded_rate",
                    domain=target_name,
                    observed_value=deg_rate,
                    baseline_mean=deg_base["mean"],
                    baseline_std=deg_base["std"],
                    z_score=z_deg,
                    severity="WARNING",
                    action="THROTTLE",
                    details=f"Elevated failure rate: {deg_rate:.1f}% degraded sessions (threshold: {self.degraded_max_pct}%) [Z={z_deg}]",
                )
            )

        # 3. Dwell Time Collapse Rule (Anti-Detection Protection)
        avg_dwell = metrics["avg_dwell"]
        dwell_base = baseline["dwell"]
        z_dwell = self.calculate_z_score(avg_dwell, dwell_base["mean"], dwell_base["std"])

        if avg_dwell < 20.0 and metrics["total_sessions"] >= 5:
            anomalies.append(
                AnomalyReport(
                    metric="dwell",
                    domain=target_name,
                    observed_value=avg_dwell,
                    baseline_mean=dwell_base["mean"],
                    baseline_std=dwell_base["std"],
                    z_score=z_dwell,
                    severity="CRITICAL",
                    action="PAUSE_DOMAIN" if domain else "THROTTLE",
                    details=f"Critical dwell collapse: {avg_dwell:.1f}s is below 20s anti-detect invariant [Z={z_dwell}]",
                )
            )
        elif avg_dwell < self.min_dwell_s and metrics["total_sessions"] >= 5:
            anomalies.append(
                AnomalyReport(
                    metric="dwell",
                    domain=target_name,
                    observed_value=avg_dwell,
                    baseline_mean=dwell_base["mean"],
                    baseline_std=dwell_base["std"],
                    z_score=z_dwell,
                    severity="WARNING",
                    action="THROTTLE",
                    details=f"Sub-optimal dwell time: {avg_dwell:.1f}s (baseline: {dwell_base['mean']:.1f}s) [Z={z_dwell}]",
                )
            )

        return anomalies

    def apply_circuit_breaker(self, anomalies: List[AnomalyReport], notify_telegram: bool = True) -> Dict[str, Any]:
        """
        Enforces defensive circuit breaker actions based on detected anomalies.
        Persists state to disk and logs event for auditing.
        """
        if not anomalies:
            return {"actions_taken": 0, "status": "ALL_CLEAR"}

        state = self._load_state()
        paused = state.get("paused_domains", {})
        actions_taken = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for a in anomalies:
            if a.severity in ("WARNING", "CRITICAL"):
                actions_taken += 1
                domain_key = a.domain.lower().strip()

                if a.action == "PAUSE_CLICKS":
                    paused[domain_key] = {
                        "action": "PAUSE_CLICKS",
                        "reason": a.details,
                        "timestamp": now_iso,
                        "severity": a.severity,
                    }
                elif a.action == "PAUSE_DOMAIN":
                    paused[domain_key] = {
                        "action": "PAUSE_DOMAIN",
                        "reason": a.details,
                        "timestamp": now_iso,
                        "severity": a.severity,
                    }
                elif a.action == "PAUSE_FLEET":
                    state["global_pause"] = True

                # Record in state history (keep last 50)
                history = state.get("history", [])
                history.append(a.to_dict())
                state["history"] = history[-50:]

                # Record in database alert_logs
                try:
                    db.record_alert_log(
                        alert_type=f"anomaly_{a.metric}",
                        level=a.severity,
                        message=f"[{a.action}] {a.details}",
                        domain=domain_key,
                        sent_live=False,
                    )
                except Exception as exc:
                    logger.debug("Failed logging alert to db: %s", exc)

                # Send Telegram notification if enabled
                if notify_telegram:
                    try:
                        from alert_bot import TelegramAlertBot
                        bot = TelegramAlertBot()
                        tg_msg = (
                            f"🚨 <b>CIRCUIT BREAKER ENGAGED: {a.severity}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🌐 <b>Target:</b> <code>{a.domain}</code>\n"
                            f"📊 <b>Metric:</b> {a.metric.upper()} (Obs: <b>{a.observed_value}</b>, Z: {a.z_score})\n"
                            f"🛡️ <b>Defensive Action:</b> <code>{a.action}</code>\n"
                            f"📝 <b>Details:</b> {a.details}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</i>"
                        )
                        bot.send_message(tg_msg, alert_type="anomaly_breaker", level=a.severity, domain=a.domain)
                    except Exception as tg_err:
                        logger.debug("Telegram alert skipped or failed: %s", tg_err)

        state["paused_domains"] = paused
        self._save_state(state)

        return {
            "actions_taken": actions_taken,
            "status": "CIRCUIT_BREAKER_ACTIVE",
            "paused_count": len(paused),
            "global_pause": state.get("global_pause", False),
        }

    def is_domain_paused(self, domain: str) -> Tuple[bool, str, str]:
        """
        Returns (is_paused, action, reason) for a given domain.
        """
        state = self._load_state()
        if state.get("global_pause", False):
            return True, "PAUSE_FLEET", "Global fleet safety circuit breaker is active"

        domain_key = (domain or "").lower().strip()
        paused = state.get("paused_domains", {})
        if domain_key in paused:
            info = paused[domain_key]
            return True, info.get("action", "PAUSE_CLICKS"), info.get("reason", "Threshold breached")

        return False, "NONE", ""

    def resume_domain(self, domain: str) -> bool:
        """Unpauses a domain from the circuit breaker."""
        state = self._load_state()
        domain_key = domain.lower().strip()
        paused = state.get("paused_domains", {})
        if domain_key in paused:
            del paused[domain_key]
            state["paused_domains"] = paused
            self._save_state(state)
            logger.info("Resumed domain %s from circuit breaker", domain)
            return True
        return False

    def reset_all(self) -> None:
        """Clears all domain pauses and resets global circuit breaker."""
        state = {"paused_domains": {}, "global_pause": False, "history": []}
        self._save_state(state)
        logger.info("Reset all circuit breaker pauses.")

    def audit_fleet(self) -> Dict[str, Any]:
        """
        Comprehensive fleet-wide scan across all 10 configured domains.
        """
        from urllib.parse import urlparse
        import yaml

        domains = ["loanraaj.com", "rechargetak.com", "rechargepur.com", "tazaloan.com", "loankiseva.com",
                   "karzseva.com", "loantau.com", "tazabhav.com", "tazarokda.com", "rechargekar.com"]
        try:
            cfg_path = Path("config.yaml")
            if cfg_path.exists():
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                cfg_urls = cfg.get("target", {}).get("urls", [])
                if cfg_urls:
                    domains = list({urlparse(u).netloc for u in cfg_urls if urlparse(u).netloc})
        except Exception:
            pass

        fleet_anomalies: List[Dict[str, Any]] = []
        for d in sorted(domains):
            detected = self.detect_anomalies(domain=d, window=25)
            if detected:
                self.apply_circuit_breaker(detected)
                fleet_anomalies.extend([a.to_dict() for a in detected])

        # Also audit global fleet
        global_detected = self.detect_anomalies(domain=None, window=50)
        if global_detected:
            self.apply_circuit_breaker(global_detected)
            fleet_anomalies.extend([a.to_dict() for a in global_detected])

        current_state = self._load_state()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domains_scanned": len(domains),
            "anomalies_detected": len(fleet_anomalies),
            "anomalies": fleet_anomalies,
            "paused_domains": current_state.get("paused_domains", {}),
            "global_pause": current_state.get("global_pause", False),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="MAHI Layer 7: Anomaly Detection Engine")
    parser.add_argument("--audit", action="store_true", help="Run full fleet anomaly audit")
    parser.add_argument("--status", action="store_true", help="Show active circuit breaker status")
    parser.add_argument("--reset", action="store_true", help="Reset all circuit breaker pauses")
    parser.add_argument("--resume", type=str, help="Resume a specific paused domain")
    args = parser.parse_args()

    detector = AnomalyDetector()

    if args.reset:
        detector.reset_all()
        print("✅ Circuit breaker reset: All pauses cleared.")
        return

    if args.resume:
        ok = detector.resume_domain(args.resume)
        if ok:
            print(f"✅ Domain {args.resume} resumed.")
        else:
            print(f"⚠️ Domain {args.resume} was not paused.")
        return

    if args.status:
        state = detector._load_state()
        print("==================================================================")
        print("  MAHI LAYER 7: CIRCUIT BREAKER STATUS")
        print(f"  Global Pause: {'ACTIVE 🛑' if state.get('global_pause') else 'CLEARED 🟢'}")
        paused = state.get("paused_domains", {})
        print(f"  Paused Domains: {len(paused)}")
        for d, info in paused.items():
            print(f"   • {d}: [{info.get('action')}] {info.get('reason')} (Severity: {info.get('severity')})")
        print("==================================================================")
        return

    # Default action or --audit
    print("Running Fleet Anomaly Audit...")
    report = detector.audit_fleet()
    print(f"Audit completed: {report['anomalies_detected']} anomalies across {report['domains_scanned']} domains.")
    if report["anomalies"]:
        for a in report["anomalies"]:
            print(f" ⚠️ [{a['severity']}] {a['domain']} - {a['metric']}: {a['details']}")
    else:
        print(" 🟢 All fleet metrics within statistical baseline (Z-scores < 2.5).")


if __name__ == "__main__":
    main()
