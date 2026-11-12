"""Phase 4 Calibration & Drift Monitor for A3 Quantile Forecaster and A5 RPM Predictor.

Evaluates rolling-window calibration without modifying Phase 1-3 core schemas or models:
- A3: P10/P50/P90 forecast coverage, P50 MAE, P50 bias, and quantile drift/retrain flags.
- A5: Gamma-Poisson predicted RPM vs realized Adsterra RPM (MAPE, signed bias, drift/retrain flags).
- Persistence: stores reports in ``p3_calibration_reports`` (created via ``CREATE TABLE IF NOT EXISTS``).
- Alerts: dispatches Telegram / Webhook alerts strictly via environment variables (fail-safe).
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
import yaml

from phase3.a5_seo_gate.rpm_predictor import GammaPoissonRPMPredictor
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import get_correlation_id, log_event, new_correlation_id

logger = logging.getLogger("phase3.calibration.monitor")

DEFAULT_CALIBRATION_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

CALIBRATION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS p3_calibration_reports (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id          TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL,
    window_days             INTEGER NOT NULL,
    a3_matched_days         INTEGER NOT NULL DEFAULT 0,
    a3_coverage_pct         REAL DEFAULT NULL,
    a3_p50_mae              REAL DEFAULT NULL,
    a3_p50_bias             REAL DEFAULT NULL,
    a3_drift_detected       INTEGER NOT NULL DEFAULT 0,
    a3_retrain_recommended  INTEGER NOT NULL DEFAULT 0,
    a5_sample_count         INTEGER NOT NULL DEFAULT 0,
    a5_mape                 REAL DEFAULT NULL,
    a5_bias                 REAL DEFAULT NULL,
    a5_drift_detected       INTEGER NOT NULL DEFAULT 0,
    a5_retrain_recommended  INTEGER NOT NULL DEFAULT 0,
    alert_dispatched        INTEGER NOT NULL DEFAULT 0,
    details_json            TEXT NOT NULL DEFAULT '{}',
    created_at              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p3_calibration_created
    ON p3_calibration_reports(created_at);
"""


@dataclass
class AlertEnvConfig:
    """Environment variable names for alert channels (zero hardcoded secrets)."""

    telegram_token_env_var: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env_var: str = "TELEGRAM_CHAT_ID"
    webhook_url_env_var: str = "PHASE3_ALERT_WEBHOOK_URL"
    timeout_seconds: float = 10.0


@dataclass
class CalibrationConfig:
    """Configuration for rolling-window A3/A5 calibration monitoring."""

    rolling_window_days: int = 30
    target_coverage: float = 0.80
    min_acceptable_coverage: float = 0.65
    max_acceptable_coverage: float = 0.95
    rpm_mape_drift_threshold: float = 0.35
    rpm_bias_threshold: float = 0.30
    min_samples_for_drift_check: int = 5
    db_path: str = "state/phase3/phase3.db"
    legacy_db_path: str = "sessions.db"
    check_interval_seconds: int = 3600
    db_timeout_seconds: float = 2.0
    log_level: str = "INFO"
    alerts: AlertEnvConfig = field(default_factory=AlertEnvConfig)

    def resolve_env(self, env_var_name: str) -> str:
        """Read an env variable strictly from process environment."""
        if not env_var_name:
            return ""
        return os.environ.get(env_var_name, "").strip()


def _apply_calibration_dict(target: Any, data: Dict[str, Any]) -> Any:
    if not isinstance(data, dict):
        return target
    for key, val in data.items():
        if not hasattr(target, key) or val is None:
            continue
        cur = getattr(target, key)
        if hasattr(cur, "__dataclass_fields__") and isinstance(val, dict):
            _apply_calibration_dict(cur, val)
        else:
            setattr(target, key, val)
    return target


def load_calibration_config(path: Optional[str | Path] = None) -> CalibrationConfig:
    """Load CalibrationConfig from YAML and apply environment variable overrides."""
    cfg = CalibrationConfig()
    cfg_path = Path(path) if path is not None else DEFAULT_CALIBRATION_CONFIG_PATH
    if cfg_path.is_file():
        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                section = raw.get("calibration") if isinstance(raw.get("calibration"), dict) else raw
                _apply_calibration_dict(cfg, section)
                if isinstance(raw.get("alerts"), dict):
                    _apply_calibration_dict(cfg.alerts, raw["alerts"])
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "calibration_config_load_failed",
                path=str(cfg_path),
                error=str(exc),
            )

    # Apply explicit environment variable overrides
    env_window = os.environ.get("PHASE4_CALIBRATION_WINDOW_DAYS", "").strip()
    if env_window:
        try:
            cfg.rolling_window_days = max(1, int(env_window))
        except ValueError:
            log_event(
                logger,
                logging.WARNING,
                "calibration_invalid_env_override",
                env_var="PHASE4_CALIBRATION_WINDOW_DAYS",
                value=env_window,
            )

    env_db = os.environ.get("PHASE4_DB_PATH", "").strip()
    if env_db:
        cfg.db_path = env_db

    env_legacy_db = os.environ.get("PHASE4_LEGACY_DB_PATH", "").strip()
    if env_legacy_db:
        cfg.legacy_db_path = env_legacy_db

    env_interval = (
        os.environ.get("PHASE4_CHECK_INTERVAL_SECONDS", "").strip()
        or os.environ.get("PHASE4_CALIBRATION_INTERVAL", "").strip()
    )
    if env_interval:
        try:
            cfg.check_interval_seconds = max(1, int(env_interval))
        except ValueError:
            log_event(
                logger,
                logging.WARNING,
                "calibration_invalid_env_override",
                env_var="PHASE4_CHECK_INTERVAL_SECONDS",
                value=env_interval,
            )

    cfg.rolling_window_days = max(1, int(cfg.rolling_window_days))
    cfg.min_samples_for_drift_check = max(1, int(cfg.min_samples_for_drift_check))
    cfg.check_interval_seconds = max(1, int(cfg.check_interval_seconds))
    cfg.db_timeout_seconds = max(0.1, float(cfg.db_timeout_seconds))
    return cfg


def ensure_calibration_table(conn: sqlite3.Connection) -> None:
    """Safely create ``p3_calibration_reports`` if missing without modifying core schema.sql."""
    conn.executescript(CALIBRATION_TABLE_DDL)


def _safe_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        parsed = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _utc_date_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()


def _extract_date_key(item: Dict[str, Any]) -> Optional[str]:
    for key in ("date", "day", "target_date"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:10]
    for ts_key in ("ts", "created_at", "timestamp"):
        ts_val = _safe_float(item.get(ts_key))
        if ts_val is not None:
            return _utc_date_from_ts(ts_val)
    return None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


class CalibrationMonitor:
    """Rolling-window calibration & drift monitor for A3 and A5 models."""

    def __init__(
        self,
        cfg: Optional[CalibrationConfig | Dict[str, Any] | str | Path] = None,
        *,
        db_path: Optional[str | Path] = None,
        legacy_db_path: Optional[str | Path] = None,
        phase3_cfg: Optional[Phase3Config] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        if isinstance(cfg, CalibrationConfig):
            self.cfg = cfg
        elif isinstance(cfg, dict):
            base = CalibrationConfig()
            _apply_calibration_dict(base, cfg)
            if isinstance(cfg.get("alerts"), dict):
                _apply_calibration_dict(base.alerts, cfg["alerts"])
            self.cfg = base
        elif isinstance(cfg, (str, Path)):
            self.cfg = load_calibration_config(cfg)
        else:
            self.cfg = load_calibration_config()

        if db_path is not None:
            self.cfg.db_path = str(db_path)
            if legacy_db_path is None and not os.environ.get("PHASE4_LEGACY_DB_PATH", "").strip():
                default_db = CalibrationConfig().db_path
                if str(db_path) != default_db:
                    self.cfg.legacy_db_path = str(Path(db_path).parent / "sessions.db")
        if legacy_db_path is not None:
            self.cfg.legacy_db_path = str(legacy_db_path)

        self.phase3_cfg = phase3_cfg if phase3_cfg is not None else load_phase3_config()
        self._rpm_predictor = GammaPoissonRPMPredictor(self.phase3_cfg)
        self._http_client = http_client

    def _open_conn(
        self,
        path: Path,
        *,
        read_only: bool = False,
        immediate: bool = False,
    ) -> sqlite3.Connection:
        timeout = float(self.cfg.db_timeout_seconds)
        if read_only:
            uri = f"{path.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=timeout, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout = {max(50, int(timeout * 1000))};")
            return conn
        busy_ms = max(10000, int(timeout * 1000)) if timeout >= 1.0 else max(50, int(timeout * 1000))
        conn = sqlite3.connect(
            str(path),
            timeout=timeout,
            isolation_level=None if immediate else "",
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(f"PRAGMA busy_timeout = {busy_ms};")
        if immediate:
            conn.execute("BEGIN IMMEDIATE;")
        return conn

    # ------------------------------------------------------------------
    # Evaluation math (A3 & A5)
    # ------------------------------------------------------------------

    def evaluate_a3(
        self,
        forecasts: Sequence[Dict[str, Any]],
        actuals: Sequence[Dict[str, Any] | float | int],
    ) -> Dict[str, Any]:
        """Evaluate A3 P10/P50/P90 forecasts against realized daily actuals."""
        paired: List[Tuple[str, float, float, float, float]] = []

        # Normalize forecasts
        fc_rows: List[Tuple[Optional[str], float, float, float]] = []
        for idx, fc in enumerate(forecasts or ()):
            if not isinstance(fc, dict):
                continue
            horizon = max(1, int(_safe_float(fc.get("horizon_days")) or 1))
            if "p10_daily" in fc or "p10" in fc:
                p10 = _safe_float(fc.get("p10_daily", fc.get("p10")))
                p50 = _safe_float(fc.get("p50_daily", fc.get("p50")))
                p90 = _safe_float(fc.get("p90_daily", fc.get("p90")))
            else:
                p10_raw = _safe_float(fc.get("p10_revenue"))
                p50_raw = _safe_float(fc.get("p50_revenue"))
                p90_raw = _safe_float(fc.get("p90_revenue"))
                p10 = (p10_raw / horizon) if p10_raw is not None else None
                p50 = (p50_raw / horizon) if p50_raw is not None else None
                p90 = (p90_raw / horizon) if p90_raw is not None else None

            if p10 is None or p50 is None or p90 is None:
                continue
            lo, mid, hi = sorted((p10, p50, p90))
            fc_rows.append((_extract_date_key(fc), lo, mid, hi))

        # Normalize actuals
        act_rows: List[Tuple[Optional[str], float]] = []
        for act in actuals or ():
            if isinstance(act, (int, float)) and not isinstance(act, bool):
                val = _safe_float(act)
                if val is not None:
                    act_rows.append((None, val))
                continue
            if not isinstance(act, dict):
                continue
            val = None
            for key in ("actual", "actual_revenue", "revenue", "total_revenue", "api_revenue", "reward_value"):
                val = _safe_float(act.get(key))
                if val is not None:
                    break
            if val is not None:
                act_rows.append((_extract_date_key(act), val))

        # Match by date if dates exist in both, otherwise align sequentially
        fc_by_date = {d: (lo, mid, hi) for d, lo, mid, hi in fc_rows if d is not None}
        act_by_date = {d: val for d, val in act_rows if d is not None}

        if fc_by_date and act_by_date:
            for d in sorted(set(fc_by_date.keys()) & set(act_by_date.keys())):
                lo, mid, hi = fc_by_date[d]
                paired.append((d, lo, mid, hi, act_by_date[d]))
        elif fc_rows and act_rows and len(fc_rows) == len(act_rows):
            for idx, ((_, lo, mid, hi), (_, val)) in enumerate(zip(fc_rows, act_rows)):
                paired.append((f"day_{idx}", lo, mid, hi, val))

        n = len(paired)
        if n == 0:
            return {
                "a3_matched_days": 0,
                "coverage_pct": None,
                "p50_mae": None,
                "p50_bias": None,
                "a3_drift_detected": False,
                "a3_retrain_recommended": False,
                "reason": "no_matched_days",
            }

        covered = sum(1 for _, lo, _, hi, actual in paired if lo <= actual <= hi)
        coverage_pct = round(covered / n, 6)
        p50_mae = round(sum(abs(actual - mid) for _, _, mid, _, actual in paired) / n, 6)
        p50_bias = round(sum(mid - actual for _, _, mid, _, actual in paired) / n, 6)

        min_samples = int(self.cfg.min_samples_for_drift_check)
        min_cov = float(self.cfg.min_acceptable_coverage)
        max_cov = float(self.cfg.max_acceptable_coverage)

        if n < min_samples:
            drift = False
            reason = f"insufficient_samples:{n}<{min_samples}"
        elif coverage_pct < min_cov:
            drift = True
            reason = f"coverage_below_min:{coverage_pct:.4f}<{min_cov:.4f}"
        elif coverage_pct > max_cov:
            drift = True
            reason = f"coverage_above_max:{coverage_pct:.4f}>{max_cov:.4f}"
        else:
            drift = False
            reason = "calibrated"

        return {
            "a3_matched_days": n,
            "coverage_pct": coverage_pct,
            "p50_mae": p50_mae,
            "p50_bias": p50_bias,
            "a3_drift_detected": drift,
            "a3_retrain_recommended": drift,
            "reason": reason,
        }

    def evaluate_a5(self, rpm_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate A5 Gamma-Poisson predicted RPM against realized actual RPM."""
        ape_list: List[float] = []
        signed_err_list: List[float] = []

        for rec in rpm_records or ():
            if not isinstance(rec, dict):
                continue

            pred_rpm = None
            for key in ("predicted_rpm", "expected_rpm", "pred_rpm", "rpm"):
                pred_rpm = _safe_float(rec.get(key))
                if pred_rpm is not None and pred_rpm > 0.0:
                    break
            if pred_rpm is None or pred_rpm <= 0.0:
                try:
                    predicted = self._rpm_predictor.predict_one(rec)
                    pred_rpm = _safe_float(predicted.get("expected_rpm"))
                except Exception:
                    pred_rpm = None

            actual_rpm = None
            for key in ("actual_rpm", "realized_rpm", "api_cpm", "actual_ecpm"):
                actual_rpm = _safe_float(rec.get(key))
                if actual_rpm is not None:
                    break
            if actual_rpm is None:
                rev = _safe_float(rec.get("actual_revenue", rec.get("api_revenue", rec.get("revenue"))))
                impr = _safe_float(rec.get("impressions", rec.get("api_impressions")))
                if rev is not None and impr is not None and impr > 0.0:
                    actual_rpm = (rev / impr) * 1000.0

            if pred_rpm is None or actual_rpm is None or actual_rpm <= 0.0:
                continue

            rel_err = (pred_rpm - actual_rpm) / actual_rpm
            ape_list.append(abs(rel_err))
            signed_err_list.append(rel_err)

        m = len(ape_list)
        if m == 0:
            return {
                "a5_sample_count": 0,
                "a5_mape": None,
                "a5_bias": None,
                "a5_drift_detected": False,
                "a5_retrain_recommended": False,
                "reason": "no_rpm_samples",
            }

        mape = round(sum(ape_list) / m, 6)
        bias = round(sum(signed_err_list) / m, 6)

        min_samples = int(self.cfg.min_samples_for_drift_check)
        mape_thresh = float(self.cfg.rpm_mape_drift_threshold)
        bias_thresh = float(self.cfg.rpm_bias_threshold)

        if m < min_samples:
            drift = False
            reason = f"insufficient_samples:{m}<{min_samples}"
        elif mape > mape_thresh or abs(bias) > bias_thresh:
            drift = True
            reason = f"rpm_drift:mape={mape:.4f},bias={bias:.4f}"
        else:
            drift = False
            reason = "calibrated"

        return {
            "a5_sample_count": m,
            "a5_mape": mape,
            "a5_bias": bias,
            "a5_drift_detected": drift,
            "a5_retrain_recommended": drift,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # SQLite History Extraction
    # ------------------------------------------------------------------

    def _load_history_from_db(
        self,
        now_ts: float,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
        """Load rolling-window A3 forecasts, daily actuals, and A5 RPM pairs from SQLite.

        Returns ``(forecasts, actuals, rpm_records, error_msg)``.
        """
        db_file = Path(self.cfg.db_path)
        if not db_file.is_file():
            return [], [], [], f"database_not_found:{db_file}"

        window_days = int(self.cfg.rolling_window_days)
        cutoff_ts = now_ts - window_days * 86400.0
        cutoff_date = (
            datetime.fromtimestamp(now_ts, tz=timezone.utc).date() - timedelta(days=window_days)
        ).isoformat()

        forecasts_by_day: Dict[str, Dict[str, Any]] = {}
        actuals_by_day: Dict[str, float] = {}
        pred_rpm_by_dom_day: Dict[Tuple[str, str], float] = {}
        pred_rpm_by_day: Dict[str, float] = {}
        rewards_realized_by_day: Dict[str, Tuple[float, int]] = {}
        adsterra_rows: List[Dict[str, Any]] = []

        try:
            conn = self._open_conn(db_file, read_only=False)
            try:
                # 1. A3 forecasts from p3_forecasts
                if _table_exists(conn, "p3_forecasts"):
                    rows = conn.execute(
                        """
                        SELECT horizon_days, p10_revenue, p50_revenue, p90_revenue,
                               p10_ecpm, p50_ecpm, p90_ecpm, created_at
                        FROM p3_forecasts
                        WHERE created_at >= ?
                        ORDER BY created_at ASC, id ASC
                        """,
                        (cutoff_ts,),
                    ).fetchall()
                    for r in rows:
                        day = _utc_date_from_ts(float(r["created_at"]))
                        forecasts_by_day[day] = {
                            "date": day,
                            "horizon_days": int(r["horizon_days"]),
                            "p10_revenue": float(r["p10_revenue"]),
                            "p50_revenue": float(r["p50_revenue"]),
                            "p90_revenue": float(r["p90_revenue"]),
                            "p50_ecpm": float(r["p50_ecpm"]),
                        }

                # 2. Realized revenue & predicted RPM from p3_decisions_rewards
                if _table_exists(conn, "p3_decisions_rewards"):
                    rows = conn.execute(
                        """
                        SELECT domain, rpm, reward_value, ts
                        FROM p3_decisions_rewards
                        WHERE ts >= ?
                        ORDER BY ts ASC, id ASC
                        """,
                        (cutoff_ts,),
                    ).fetchall()
                    dom_day_rpms: Dict[Tuple[str, str], List[float]] = {}
                    day_rpms: Dict[str, List[float]] = {}
                    for r in rows:
                        day = _utc_date_from_ts(float(r["ts"]))
                        domain = str(r["domain"] or "default").strip().lower()
                        rpm_val = float(r["rpm"] or 0.0)
                        rev_val = float(r["reward_value"] or 0.0)
                        prev_rev, prev_cnt = rewards_realized_by_day.get(day, (0.0, 0))
                        rewards_realized_by_day[day] = (prev_rev + rev_val, prev_cnt + 1)
                        if rpm_val > 0.0:
                            dom_day_rpms.setdefault((domain, day), []).append(rpm_val)
                            day_rpms.setdefault(day, []).append(rpm_val)
                    for key, vals in dom_day_rpms.items():
                        pred_rpm_by_dom_day[key] = sum(vals) / len(vals)
                    for day, vals in day_rpms.items():
                        pred_rpm_by_day[day] = sum(vals) / len(vals)

                # 3. Authoritative Adsterra API sync in phase3.db (if present)
                if _table_exists(conn, "adsterra_api_sync"):
                    adsterra_rows = self._query_adsterra_sync(conn, cutoff_date)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log_event(
                logger,
                logging.WARNING,
                "calibration_db_read_failed",
                db_path=str(db_file),
                error=str(exc),
            )
            return [], [], [], f"sqlite_error:{exc}"

        # Optional fallback to legacy_db_path (sessions.db) ONLY if phase3.db had no adsterra_api_sync
        # and no positive realized rewards in p3_decisions_rewards.
        has_positive_rewards = any(rev > 0.0 for rev, _ in rewards_realized_by_day.values())
        if not adsterra_rows and not has_positive_rewards and self.cfg.legacy_db_path:
            legacy_file = Path(self.cfg.legacy_db_path)
            if legacy_file.is_file():
                try:
                    lconn = self._open_conn(legacy_file, read_only=True)
                    try:
                        if _table_exists(lconn, "adsterra_api_sync"):
                            adsterra_rows = self._query_adsterra_sync(lconn, cutoff_date)
                    finally:
                        lconn.close()
                except sqlite3.Error as exc:
                    log_event(
                        logger,
                        logging.WARNING,
                        "calibration_legacy_db_read_failed",
                        legacy_db_path=str(legacy_file),
                        error=str(exc),
                    )

        # Build daily actuals series
        if adsterra_rows:
            for row in adsterra_rows:
                d = row["date"]
                actuals_by_day[d] = actuals_by_day.get(d, 0.0) + float(row["api_revenue"])
        elif rewards_realized_by_day:
            for d, (rev_sum, _) in rewards_realized_by_day.items():
                actuals_by_day[d] = rev_sum

        actuals = [{"date": d, "revenue": rev} for d, rev in sorted(actuals_by_day.items())]
        forecasts = [forecasts_by_day[d] for d in sorted(forecasts_by_day.keys())]

        # Build A5 RPM evaluation pairs
        rpm_records: List[Dict[str, Any]] = []
        if adsterra_rows:
            for row in adsterra_rows:
                dom = str(row["domain"] or "default").strip().lower()
                d = row["date"]
                impr = int(row["api_impressions"] or 0)
                rev = float(row["api_revenue"] or 0.0)
                api_cpm = float(row["api_cpm"] or 0.0)
                realized_rpm = api_cpm if api_cpm > 0.0 else ((rev / impr) * 1000.0 if impr > 0 else 0.0)
                if realized_rpm <= 0.0:
                    continue

                pred_rpm = pred_rpm_by_dom_day.get((dom, d)) or pred_rpm_by_day.get(d)
                if pred_rpm is None and d in forecasts_by_day:
                    pred_rpm = _safe_float(forecasts_by_day[d].get("p50_ecpm"))
                rec: Dict[str, Any] = {
                    "domain": dom,
                    "date": d,
                    "actual_rpm": realized_rpm,
                    "adsterra_impressions": impr,
                    "adsterra_revenue": rev,
                    "historical_ecpm": api_cpm,
                }
                if pred_rpm is not None and pred_rpm > 0.0:
                    rec["predicted_rpm"] = pred_rpm
                rpm_records.append(rec)
        elif has_positive_rewards:
            for d, (rev_sum, cnt) in sorted(rewards_realized_by_day.items()):
                if cnt <= 0 or rev_sum <= 0.0:
                    continue
                realized_rpm = (rev_sum / cnt) * 1000.0
                pred_rpm = pred_rpm_by_day.get(d)
                if pred_rpm is None and d in forecasts_by_day:
                    pred_rpm = _safe_float(forecasts_by_day[d].get("p50_ecpm"))
                rec = {
                    "date": d,
                    "actual_rpm": realized_rpm,
                }
                if pred_rpm is not None and pred_rpm > 0.0:
                    rec["predicted_rpm"] = pred_rpm
                rpm_records.append(rec)

        return forecasts, actuals, rpm_records, None

    @staticmethod
    def _query_adsterra_sync(conn: sqlite3.Connection, cutoff_date: str) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT domain, date, api_impressions, api_clicks, api_ctr, api_cpm, api_revenue
            FROM adsterra_api_sync
            WHERE date >= ?
              AND id IN (
                  SELECT MAX(id) FROM adsterra_api_sync GROUP BY domain, date
              )
            ORDER BY date ASC
            """,
            (cutoff_date,),
        ).fetchall()
        return [
            {
                "domain": str(r["domain"]),
                "date": str(r["date"])[:10],
                "api_impressions": int(r["api_impressions"] or 0),
                "api_clicks": int(r["api_clicks"] or 0),
                "api_ctr": float(r["api_ctr"] or 0.0),
                "api_cpm": float(r["api_cpm"] or 0.0),
                "api_revenue": float(r["api_revenue"] or 0.0),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Persistence & Alerts
    # ------------------------------------------------------------------

    def _persist_report(self, report: Dict[str, Any], *, create_db: bool = False) -> Tuple[bool, Optional[str]]:
        db_file = Path(self.cfg.db_path)
        if not db_file.is_file() and not create_db:
            return False, f"database_not_found:{db_file}"
        try:
            db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = self._open_conn(db_file, read_only=False, immediate=False)
            try:
                ensure_calibration_table(conn)
                conn.isolation_level = None
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    INSERT INTO p3_calibration_reports (
                        correlation_id, status, window_days,
                        a3_matched_days, a3_coverage_pct, a3_p50_mae, a3_p50_bias,
                        a3_drift_detected, a3_retrain_recommended,
                        a5_sample_count, a5_mape, a5_bias,
                        a5_drift_detected, a5_retrain_recommended,
                        alert_dispatched, details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(report.get("correlation_id", "")),
                        str(report.get("status", "unknown")),
                        int(report.get("window_days", self.cfg.rolling_window_days)),
                        int(report.get("a3_matched_days", 0)),
                        report.get("coverage_pct"),
                        report.get("p50_mae"),
                        report.get("p50_bias"),
                        1 if report.get("a3_drift_detected") else 0,
                        1 if report.get("a3_retrain_recommended") else 0,
                        int(report.get("a5_sample_count", 0)),
                        report.get("a5_mape"),
                        report.get("a5_bias"),
                        1 if report.get("a5_drift_detected") else 0,
                        1 if report.get("a5_retrain_recommended") else 0,
                        1 if report.get("alerts", {}).get("dispatched") else 0,
                        json.dumps(report.get("details", {}), ensure_ascii=False, default=str),
                        float(report.get("created_at", time.time())),
                    ),
                )
                conn.execute("COMMIT;")
                return True, None
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
                raise
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log_event(
                logger,
                logging.WARNING,
                "calibration_report_persist_failed",
                db_path=str(db_file),
                error=str(exc),
            )
            return False, f"sqlite_error:{exc}"

    def dispatch_alerts(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch drift/retrain alerts via Telegram or Webhook from env vars (fail-safe)."""
        telegram_token = self.cfg.resolve_env(self.cfg.alerts.telegram_token_env_var)
        telegram_chat_id = self.cfg.resolve_env(self.cfg.alerts.telegram_chat_id_env_var)
        webhook_url = self.cfg.resolve_env(self.cfg.alerts.webhook_url_env_var)
        timeout = max(0.5, float(self.cfg.alerts.timeout_seconds))

        result: Dict[str, Any] = {
            "dispatched": False,
            "telegram": "skipped_missing_env",
            "webhook": "skipped_missing_env",
        }

        summary_text = (
            f"[Phase 4 Calibration Drift] status={report.get('status')} | "
            f"A3 cov={report.get('coverage_pct')} drift={report.get('a3_drift_detected')} | "
            f"A5 mape={report.get('a5_mape')} bias={report.get('a5_bias')} "
            f"drift={report.get('a5_drift_detected')}"
        )

        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.Client(timeout=timeout)

        try:
            if telegram_token and telegram_chat_id:
                try:
                    resp = client.post(
                        f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                        json={
                            "chat_id": telegram_chat_id,
                            "text": summary_text,
                            "disable_web_page_preview": True,
                        },
                    )
                    if 200 <= resp.status_code < 300:
                        result["telegram"] = "sent"
                        result["dispatched"] = True
                    else:
                        result["telegram"] = f"http_{resp.status_code}"
                        log_event(
                            logger,
                            logging.WARNING,
                            "calibration_telegram_alert_http_error",
                            status_code=resp.status_code,
                        )
                except Exception as exc:
                    result["telegram"] = f"error:{exc}"
                    log_event(
                        logger,
                        logging.WARNING,
                        "calibration_telegram_alert_failed",
                        error=str(exc),
                    )

            if webhook_url:
                try:
                    resp = client.post(
                        webhook_url,
                        json={
                            "event": "phase4_calibration_drift",
                            "summary": summary_text,
                            "report": {
                                k: v
                                for k, v in report.items()
                                if k != "alerts"
                            },
                        },
                    )
                    if 200 <= resp.status_code < 300:
                        result["webhook"] = "sent"
                        result["dispatched"] = True
                    else:
                        result["webhook"] = f"http_{resp.status_code}"
                        log_event(
                            logger,
                            logging.WARNING,
                            "calibration_webhook_alert_http_error",
                            status_code=resp.status_code,
                        )
                except Exception as exc:
                    result["webhook"] = f"error:{exc}"
                    log_event(
                        logger,
                        logging.WARNING,
                        "calibration_webhook_alert_failed",
                        error=str(exc),
                    )
        finally:
            if owns_client and client is not None:
                client.close()

        return result

    # ------------------------------------------------------------------
    # Public Run Entrypoint
    # ------------------------------------------------------------------

    def run_check(
        self,
        *,
        forecasts: Optional[Sequence[Dict[str, Any]]] = None,
        actuals: Optional[Sequence[Dict[str, Any] | float | int]] = None,
        rpm_records: Optional[Sequence[Dict[str, Any]]] = None,
        persist: bool = True,
        create_db: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute one full A3 + A5 calibration check, persist report, and dispatch alerts."""
        cid = correlation_id or get_correlation_id() or new_correlation_id("p4cal")
        now_ts = time.time()
        supplied_any = forecasts is not None or actuals is not None or rpm_records is not None

        db_error: Optional[str] = None
        if not supplied_any:
            db_forecasts, db_actuals, db_rpm, db_error = self._load_history_from_db(now_ts)
            fc_data: Sequence[Dict[str, Any]] = db_forecasts
            act_data: Sequence[Dict[str, Any] | float | int] = db_actuals
            rpm_data: Sequence[Dict[str, Any]] = db_rpm
        else:
            fc_data = forecasts or []
            act_data = actuals or []
            rpm_data = rpm_records or []

        a3_res = self.evaluate_a3(fc_data, act_data)
        a5_res = self.evaluate_a5(rpm_data)

        a3_drift = bool(a3_res["a3_drift_detected"])
        a5_drift = bool(a5_res["a5_drift_detected"])
        drift_detected = a3_drift or a5_drift
        retrain_recommended = bool(a3_res["a3_retrain_recommended"] or a5_res["a5_retrain_recommended"])

        min_samples = int(self.cfg.min_samples_for_drift_check)
        has_enough_data = (
            int(a3_res["a3_matched_days"]) >= min_samples
            or int(a5_res["a5_sample_count"]) >= min_samples
        )

        if db_error is not None:
            status = "degraded"
        elif drift_detected:
            status = "drift_detected"
        elif not has_enough_data:
            status = "insufficient_data"
        else:
            status = "ok"

        report: Dict[str, Any] = {
            "status": status,
            "correlation_id": cid,
            "created_at": round(now_ts, 6),
            "window_days": int(self.cfg.rolling_window_days),
            "a3_matched_days": int(a3_res["a3_matched_days"]),
            "coverage_pct": a3_res["coverage_pct"],
            "p50_mae": a3_res["p50_mae"],
            "p50_bias": a3_res["p50_bias"],
            "a3_drift_detected": a3_drift,
            "a3_retrain_recommended": bool(a3_res["a3_retrain_recommended"]),
            "a5_sample_count": int(a5_res["a5_sample_count"]),
            "a5_mape": a5_res["a5_mape"],
            "a5_bias": a5_res["a5_bias"],
            "a5_drift_detected": a5_drift,
            "a5_retrain_recommended": bool(a5_res["a5_retrain_recommended"]),
            "drift_detected": drift_detected,
            "retrain_recommended": retrain_recommended,
            "alerts": {"dispatched": False, "telegram": "not_triggered", "webhook": "not_triggered"},
            "persisted": False,
            "error": db_error or "",
            "details": {
                "a3_reason": a3_res.get("reason", ""),
                "a5_reason": a5_res.get("reason", ""),
                "thresholds": {
                    "target_coverage": float(self.cfg.target_coverage),
                    "min_acceptable_coverage": float(self.cfg.min_acceptable_coverage),
                    "max_acceptable_coverage": float(self.cfg.max_acceptable_coverage),
                    "rpm_mape_drift_threshold": float(self.cfg.rpm_mape_drift_threshold),
                    "rpm_bias_threshold": float(self.cfg.rpm_bias_threshold),
                    "min_samples_for_drift_check": min_samples,
                },
            },
        }

        if drift_detected:
            report["alerts"] = self.dispatch_alerts(report)

        if persist and db_error is None:
            persisted, persist_err = self._persist_report(report, create_db=create_db)
            report["persisted"] = persisted
            if persist_err and not create_db and not Path(self.cfg.db_path).is_file():
                # Supplied data run with no DB file on disk yet: stay non-degraded unless DB failed
                pass
            elif persist_err:
                report["status"] = "degraded"
                report["error"] = persist_err

        log_event(
            logger,
            logging.WARNING if drift_detected or report["status"] == "degraded" else logging.INFO,
            "phase4_calibration_check_completed",
            correlation_id=cid,
            status=report["status"],
            a3_matched_days=report["a3_matched_days"],
            coverage_pct=report["coverage_pct"],
            a3_drift_detected=a3_drift,
            a5_sample_count=report["a5_sample_count"],
            a5_mape=report["a5_mape"],
            a5_bias=report["a5_bias"],
            a5_drift_detected=a5_drift,
            persisted=report["persisted"],
            alert_dispatched=report["alerts"]["dispatched"],
        )

        return report
