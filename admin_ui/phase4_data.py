"""Phase 4 Live SQLite Dashboard Data Reader (read-only, fail-safe)."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from common.paths import DEFAULT_SAFE_MODE_PATH, read_safe_mode_state

DEFAULT_PHASE4_CONFIG_PATH = Path(__file__).resolve().parent / "phase4_config.yaml"


@dataclass
class Phase4DashboardConfig:
    """Typed configuration for the Phase 4 Admin Dashboard."""

    host: str = "127.0.0.1"
    port: int = 5054
    phase3_db_path: str = "state/phase3/phase3.db"
    safe_mode_path: str = DEFAULT_SAFE_MODE_PATH
    legacy_db_path: str = "sessions.db"
    refresh_interval_ms: int = 5000
    max_rows: int = 200
    sqlite_timeout_seconds: float = 0.5


def load_phase4_config(
    config_path: Optional[str | Path] = None,
) -> Phase4DashboardConfig:
    """Load ``admin_ui/phase4_config.yaml`` and apply environment variable overrides."""
    path = Path(config_path) if config_path else DEFAULT_PHASE4_CONFIG_PATH
    raw: Dict[str, Any] = {}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                sub = loaded.get("dashboard")
                raw = sub if isinstance(sub, dict) else loaded
        except Exception:
            raw = {}

    cfg = Phase4DashboardConfig(
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 5054)),
        phase3_db_path=str(raw.get("phase3_db_path", "state/phase3/phase3.db")),
        safe_mode_path=str(raw.get("safe_mode_path", DEFAULT_SAFE_MODE_PATH)),
        legacy_db_path=str(raw.get("legacy_db_path", "sessions.db")),
        refresh_interval_ms=max(1000, int(raw.get("refresh_interval_ms", 5000))),
        max_rows=max(1, int(raw.get("max_rows", 200))),
        sqlite_timeout_seconds=max(0.1, float(raw.get("sqlite_timeout_seconds", 0.5))),
    )

    if os.environ.get("PHASE4_DASHBOARD_HOST"):
        cfg.host = os.environ["PHASE4_DASHBOARD_HOST"].strip()
    if os.environ.get("PHASE4_DASHBOARD_PORT"):
        try:
            cfg.port = int(os.environ["PHASE4_DASHBOARD_PORT"].strip())
        except ValueError:
            pass
    if os.environ.get("PHASE4_DB_PATH"):
        cfg.phase3_db_path = os.environ["PHASE4_DB_PATH"].strip()
    if os.environ.get("PHASE4_SAFE_MODE_PATH"):
        cfg.safe_mode_path = os.environ["PHASE4_SAFE_MODE_PATH"].strip()
    if os.environ.get("PHASE4_LEGACY_DB_PATH"):
        cfg.legacy_db_path = os.environ["PHASE4_LEGACY_DB_PATH"].strip()

    return cfg


def _classify_sqlite_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "locked" in msg or "busy" in msg:
        return "locked"
    return "error"


def _open_readonly_sqlite(db_path: Path, timeout_s: float) -> sqlite3.Connection:
    """Open an existing SQLite database in strict read-only mode with short timeout."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_s, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON;")
    conn.execute(f"PRAGMA busy_timeout = {max(50, int(round(float(timeout_s) * 1000)))};")
    return conn


def _empty_kpis(safe_mode: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "total_sessions": 0,
        "completed_sessions": 0,
        "failed_sessions": 0,
        "active_devices": 0,
        "healthy_farm_devices": 0,
        "quarantined_devices": 0,
        "total_farm_devices": 0,
        "active_cgnat_slots": 0,
        "ip_collisions_prevented": 0,
        "session_collision_blocks": 0,
        "decision_collision_blocks": 0,
        "subnet_cooldown_hits": 0,
        "total_clicks": 0,
        "executed_touches": 0,
        "p50_forecast_vs_actual": {
            "p10_revenue": 0.0,
            "p50_revenue": 0.0,
            "p90_revenue": 0.0,
            "p10_ecpm": 0.0,
            "p50_ecpm": 0.0,
            "p90_ecpm": 0.0,
            "actual_revenue": 0.0,
            "rewards_revenue": 0.0,
            "adsterra_api_revenue": 0.0,
            "delta_vs_p50": 0.0,
            "pct_of_p50": 0.0,
            "horizon_days": 0,
            "method": "",
        },
        "safe_mode": safe_mode,
    }


class Phase4DashboardReader:
    """Read-only, fail-safe dashboard telemetry reader for Phase 3 & Phase 4 state."""

    def __init__(self, config: Optional[Phase4DashboardConfig] = None) -> None:
        self.config = config or load_phase4_config()

    def read_safe_mode(self) -> Dict[str, Any]:
        """Read ``safe_mode.json`` from the canonical path, failing closed if missing/invalid."""
        state = read_safe_mode_state(self.config.safe_mode_path, fail_closed=True)
        return {
            "active": bool(state["active"]),
            "reason": str(state["reason"]),
            "clean_windows": int(state["clean_windows"]),
            "entry_ts": float(state["entry_ts"]),
        }

    def _read_legacy_adsterra_revenue(self) -> Tuple[float, List[Dict[str, Any]]]:
        """Optionally read realized Adsterra revenue from legacy ``sessions.db``."""
        legacy_path = Path(self.config.legacy_db_path)
        if not legacy_path.is_file():
            return 0.0, []
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _open_readonly_sqlite(legacy_path, self.config.sqlite_timeout_seconds)
            tbl = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='adsterra_api_sync'"
            ).fetchone()
            if tbl is None:
                return 0.0, []
            row = conn.execute(
                "SELECT COALESCE(SUM(api_revenue), 0.0) AS rev FROM adsterra_api_sync"
            ).fetchone()
            daily_rows = conn.execute(
                """
                SELECT date, COALESCE(SUM(api_revenue), 0.0) AS actual_revenue,
                       COALESCE(SUM(api_impressions), 0) AS impressions,
                       COALESCE(SUM(api_clicks), 0) AS clicks
                FROM adsterra_api_sync
                GROUP BY date
                ORDER BY date DESC
                LIMIT 30
                """
            ).fetchall()
            rev = float(row["rev"]) if row else 0.0
            return rev, [dict(r) for r in reversed(daily_rows)]
        except Exception:
            return 0.0, []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """Query Phase 3 SQLite tables and build the full Phase 4 dashboard payload.

        Never raises on missing, unreadable, or locked SQLite databases.
        """
        safe_mode = self.read_safe_mode()
        db_path = Path(self.config.phase3_db_path)
        generated_at = datetime.now(timezone.utc).isoformat()

        if not db_path.is_file():
            return {
                "ok": False,
                "db_status": "missing",
                "error": f"Phase 3 SQLite database not found at '{db_path}'.",
                "generated_at": generated_at,
                "config": {
                    "refresh_interval_ms": self.config.refresh_interval_ms,
                    "max_rows": self.config.max_rows,
                    "phase3_db_path": str(db_path),
                },
                "kpis": _empty_kpis(safe_mode),
                "charts": {
                    "forecast_series": [],
                    "device_activity": [],
                    "session_timeline": [],
                },
                "sessions": [],
                "cgnat_slots": [],
                "forecasts": [],
                "farm_devices": [],
                "calibration_reports": [],
            }

        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _open_readonly_sqlite(db_path, self.config.sqlite_timeout_seconds)
            existing_tables = {
                str(r["name"])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            required_tables = {
                "p3_sessions",
                "p3_cgnat_slots",
                "p3_forecasts",
                "p3_farm_devices",
                "p3_decisions_rewards",
            }
            missing_tables = sorted(required_tables - existing_tables)
            if missing_tables:
                return {
                    "ok": False,
                    "db_status": "error",
                    "error": f"Missing Phase 3 schema tables: {', '.join(missing_tables)}",
                    "generated_at": generated_at,
                    "config": {
                        "refresh_interval_ms": self.config.refresh_interval_ms,
                        "max_rows": self.config.max_rows,
                        "phase3_db_path": str(db_path),
                    },
                    "kpis": _empty_kpis(safe_mode),
                    "charts": {
                        "forecast_series": [],
                        "device_activity": [],
                        "session_timeline": [],
                    },
                    "sessions": [],
                    "cgnat_slots": [],
                    "forecasts": [],
                    "farm_devices": [],
                    "calibration_reports": [],
                }

            limit = self.config.max_rows

            sessions_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM p3_sessions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
            cgnat_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM p3_cgnat_slots ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
            forecast_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM p3_forecasts ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
            device_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM p3_farm_devices ORDER BY last_seen_at DESC, device_id ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]

            calibration_rows: List[Dict[str, Any]] = []
            if "p3_calibration_reports" in existing_tables:
                calibration_rows = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM p3_calibration_reports ORDER BY id DESC LIMIT ?",
                        (min(limit, 50),),
                    ).fetchall()
                ]

            # --- KPI aggregates ---
            sess_agg = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_sessions,
                    SUM(CASE WHEN LOWER(status) IN ('completed', 'ok') THEN 1 ELSE 0 END) AS completed_sessions,
                    SUM(CASE WHEN LOWER(status) IN ('failed', 'error', 'degraded') THEN 1 ELSE 0 END) AS failed_sessions,
                    SUM(
                        CASE WHEN (
                            LOWER(status) LIKE '%collision%'
                            OR LOWER(status) LIKE '%blocked%'
                            OR LOWER(status) LIKE '%cooldown%'
                            OR LOWER(error) LIKE '%cgnat%'
                            OR LOWER(error) LIKE '%collision%'
                            OR LOWER(error) LIKE '%subnet%'
                        ) THEN 1 ELSE 0 END
                    ) AS session_collision_blocks
                FROM p3_sessions
                """
            ).fetchone()

            total_sessions = int(sess_agg["total_sessions"] or 0) if sess_agg else 0
            completed_sessions = int(sess_agg["completed_sessions"] or 0) if sess_agg else 0
            failed_sessions = int(sess_agg["failed_sessions"] or 0) if sess_agg else 0
            session_collision_blocks = (
                int(sess_agg["session_collision_blocks"] or 0) if sess_agg else 0
            )

            # ASSUMPTION: `active_devices` counts distinct device_ids that are either
            # healthy/active in `p3_farm_devices` OR currently hold an active row (`active = 1`)
            # in `p3_cgnat_slots`, avoiding double-counting when one device appears in both.
            healthy_device_ids = {
                str(r["device_id"])
                for r in conn.execute(
                    "SELECT device_id FROM p3_farm_devices WHERE LOWER(status) IN ('healthy', 'active')"
                ).fetchall()
            }
            active_slot_device_ids = {
                str(r["device_id"])
                for r in conn.execute(
                    "SELECT DISTINCT device_id FROM p3_cgnat_slots WHERE active = 1"
                ).fetchall()
            }
            active_cgnat_slots = int(
                conn.execute(
                    "SELECT COUNT(*) AS cnt FROM p3_cgnat_slots WHERE active = 1"
                ).fetchone()["cnt"]
                or 0
            )
            quarantined_devices = int(
                conn.execute(
                    "SELECT COUNT(*) AS cnt FROM p3_farm_devices WHERE LOWER(status) = 'quarantined'"
                ).fetchone()["cnt"]
                or 0
            )
            total_farm_devices = int(
                conn.execute("SELECT COUNT(*) AS cnt FROM p3_farm_devices").fetchone()["cnt"]
                or 0
            )
            active_devices = len(healthy_device_ids | active_slot_device_ids)

            # ASSUMPTION: Phase 3 `schema.sql` has no dedicated `collisions_prevented`
            # counter column. We compute `ip_collisions_prevented` from:
            #   (1) `p3_sessions` rows flagged with collision/blocked/cooldown/cgnat errors,
            #   (2) `p3_decisions_rewards` rows whose `reason` mentions collision/cgnat, and
            #   (3) distinct `/24` subnet cooldown hits (released slots on repeated `/24` subnets).
            reward_agg = conn.execute(
                """
                SELECT
                    COALESCE(SUM(reward_value), 0.0) AS rewards_revenue,
                    SUM(CASE WHEN LOWER(action) IN ('click', 'paper_click') THEN 1 ELSE 0 END) AS total_clicks,
                    SUM(CASE WHEN executed_touch = 1 THEN 1 ELSE 0 END) AS executed_touches,
                    SUM(
                        CASE WHEN (
                            LOWER(reason) LIKE '%collision%'
                            OR LOWER(reason) LIKE '%cgnat%'
                        ) THEN 1 ELSE 0 END
                    ) AS decision_collision_blocks
                FROM p3_decisions_rewards
                """
            ).fetchone()

            rewards_revenue = float(reward_agg["rewards_revenue"] or 0.0) if reward_agg else 0.0
            total_clicks = int(reward_agg["total_clicks"] or 0) if reward_agg else 0
            executed_touches = int(reward_agg["executed_touches"] or 0) if reward_agg else 0
            decision_collision_blocks = (
                int(reward_agg["decision_collision_blocks"] or 0) if reward_agg else 0
            )

            subnet_agg = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_slots,
                    COUNT(DISTINCT CASE WHEN subnet_24 != '' THEN subnet_24 END) AS distinct_subnets
                FROM p3_cgnat_slots
                WHERE subnet_24 != ''
                """
            ).fetchone()
            total_subnet_slots = int(subnet_agg["total_slots"] or 0) if subnet_agg else 0
            distinct_subnets = int(subnet_agg["distinct_subnets"] or 0) if subnet_agg else 0
            subnet_cooldown_hits = max(0, total_subnet_slots - distinct_subnets)

            ip_collisions_prevented = (
                session_collision_blocks + decision_collision_blocks + subnet_cooldown_hits
            )

            latest_forecast = forecast_rows[0] if forecast_rows else {}
            p10_rev = float(latest_forecast.get("p10_revenue", 0.0) or 0.0)
            p50_rev = float(latest_forecast.get("p50_revenue", 0.0) or 0.0)
            p90_rev = float(latest_forecast.get("p90_revenue", 0.0) or 0.0)
            p10_ecpm = float(latest_forecast.get("p10_ecpm", 0.0) or 0.0)
            p50_ecpm = float(latest_forecast.get("p50_ecpm", 0.0) or 0.0)
            p90_ecpm = float(latest_forecast.get("p90_ecpm", 0.0) or 0.0)

            adsterra_api_rev, adsterra_daily = self._read_legacy_adsterra_revenue()
            # ASSUMPTION: Use realized `p3_decisions_rewards.reward_value` sum as primary
            # actual revenue when > 0, falling back to `adsterra_api_sync` in legacy DB.
            actual_revenue = rewards_revenue if rewards_revenue > 0.0 else adsterra_api_rev

            # Build chart series in chronological order
            daily_rewards_rows = conn.execute(
                """
                SELECT
                    DATE(ts, 'unixepoch') AS day,
                    COALESCE(SUM(reward_value), 0.0) AS reward_sum
                FROM p3_decisions_rewards
                GROUP BY day
                ORDER BY day ASC
                """
            ).fetchall()
            rewards_by_day = {
                str(r["day"]): float(r["reward_sum"] or 0.0)
                for r in daily_rewards_rows
                if r["day"]
            }
            adsterra_by_day = {
                str(r["date"]): float(r["actual_revenue"] or 0.0)
                for r in adsterra_daily
                if r.get("date")
            }

            forecast_series: List[Dict[str, Any]] = []
            for f_row in reversed(forecast_rows[:30]):
                created_ts = float(f_row.get("created_at") or 0.0)
                day_label = (
                    datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    if created_ts > 0
                    else f"F#{f_row.get('id', '')}"
                )
                matched_actual = rewards_by_day.get(
                    day_label, adsterra_by_day.get(day_label, actual_revenue)
                )
                forecast_series.append(
                    {
                        "id": f_row.get("id"),
                        "label": day_label,
                        "p10_revenue": round(float(f_row.get("p10_revenue", 0.0) or 0.0), 4),
                        "p50_revenue": round(float(f_row.get("p50_revenue", 0.0) or 0.0), 4),
                        "p90_revenue": round(float(f_row.get("p90_revenue", 0.0) or 0.0), 4),
                        "actual_revenue": round(float(matched_actual), 4),
                    }
                )

            device_activity = [
                {
                    "device_id": str(d.get("device_id", "")),
                    "total_sessions": int(d.get("total_sessions", 0) or 0),
                    "total_clicks": int(d.get("total_clicks", 0) or 0),
                    "status": str(d.get("status", "unknown")),
                }
                for d in device_rows[:20]
            ]

            session_timeline_rows = conn.execute(
                """
                SELECT
                    DATE(started_at, 'unixepoch') AS day,
                    COUNT(*) AS sessions,
                    SUM(CASE WHEN LOWER(status) IN ('completed', 'ok') THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN LOWER(status) NOT IN ('completed', 'ok', 'started') THEN 1 ELSE 0 END) AS issues
                FROM p3_sessions
                GROUP BY day
                ORDER BY day DESC
                LIMIT 14
                """
            ).fetchall()
            session_timeline = [
                {
                    "day": str(r["day"] or "unknown"),
                    "sessions": int(r["sessions"] or 0),
                    "completed": int(r["completed"] or 0),
                    "issues": int(r["issues"] or 0),
                }
                for r in reversed(session_timeline_rows)
            ]

            return {
                "ok": True,
                "db_status": "ok",
                "error": "",
                "generated_at": generated_at,
                "config": {
                    "refresh_interval_ms": self.config.refresh_interval_ms,
                    "max_rows": self.config.max_rows,
                    "phase3_db_path": str(db_path),
                },
                "kpis": {
                    "total_sessions": total_sessions,
                    "completed_sessions": completed_sessions,
                    "failed_sessions": failed_sessions,
                    "active_devices": active_devices,
                    "healthy_farm_devices": len(healthy_device_ids),
                    "quarantined_devices": quarantined_devices,
                    "total_farm_devices": total_farm_devices,
                    "active_cgnat_slots": active_cgnat_slots,
                    "ip_collisions_prevented": ip_collisions_prevented,
                    "session_collision_blocks": session_collision_blocks,
                    "decision_collision_blocks": decision_collision_blocks,
                    "subnet_cooldown_hits": subnet_cooldown_hits,
                    "total_clicks": total_clicks,
                    "executed_touches": executed_touches,
                    "p50_forecast_vs_actual": {
                        "p10_revenue": round(p10_rev, 4),
                        "p50_revenue": round(p50_rev, 4),
                        "p90_revenue": round(p90_rev, 4),
                        "p10_ecpm": round(p10_ecpm, 4),
                        "p50_ecpm": round(p50_ecpm, 4),
                        "p90_ecpm": round(p90_ecpm, 4),
                        "actual_revenue": round(actual_revenue, 4),
                        "rewards_revenue": round(rewards_revenue, 4),
                        "adsterra_api_revenue": round(adsterra_api_rev, 4),
                        "delta_vs_p50": round(actual_revenue - p50_rev, 4),
                        "pct_of_p50": round((actual_revenue / p50_rev) * 100.0, 2)
                        if p50_rev > 0
                        else 0.0,
                        "horizon_days": int(latest_forecast.get("horizon_days", 0) or 0),
                        "method": str(latest_forecast.get("method", "")),
                    },
                    "safe_mode": safe_mode,
                },
                "charts": {
                    "forecast_series": forecast_series,
                    "device_activity": device_activity,
                    "session_timeline": session_timeline,
                },
                "sessions": sessions_rows,
                "cgnat_slots": cgnat_rows,
                "forecasts": forecast_rows,
                "farm_devices": device_rows,
                "calibration_reports": calibration_rows,
            }
        except sqlite3.OperationalError as exc:
            status = _classify_sqlite_error(exc)
            return {
                "ok": False,
                "db_status": status,
                "error": f"SQLite operational error ({status}): {exc}",
                "generated_at": generated_at,
                "config": {
                    "refresh_interval_ms": self.config.refresh_interval_ms,
                    "max_rows": self.config.max_rows,
                    "phase3_db_path": str(db_path),
                },
                "kpis": _empty_kpis(safe_mode),
                "charts": {
                    "forecast_series": [],
                    "device_activity": [],
                    "session_timeline": [],
                },
                "sessions": [],
                "cgnat_slots": [],
                "forecasts": [],
                "farm_devices": [],
                "calibration_reports": [],
            }
        except Exception as exc:
            return {
                "ok": False,
                "db_status": "error",
                "error": f"Unexpected dashboard reader error: {exc}",
                "generated_at": generated_at,
                "config": {
                    "refresh_interval_ms": self.config.refresh_interval_ms,
                    "max_rows": self.config.max_rows,
                    "phase3_db_path": str(db_path),
                },
                "kpis": _empty_kpis(safe_mode),
                "charts": {
                    "forecast_series": [],
                    "device_activity": [],
                    "session_timeline": [],
                },
                "sessions": [],
                "cgnat_slots": [],
                "forecasts": [],
                "farm_devices": [],
                "calibration_reports": [],
            }
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
