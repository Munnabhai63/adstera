"""Step 1 database cleanup, real Adsterra history sync, A3 forecast & calibration baseline.

Usage:
    python -m phase3.scripts.step1_baseline
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase3.a3_forecaster.irls_quantile import IRLSQuantileForecaster
from phase3.adapters.adsterra_feed import AdsterraFeedAdapter, load_dotenv_into_environ
from phase3.calibration.monitor import CalibrationMonitor
from phase3.config_loader import load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import configure_json_logging, log_event

logger = logging.getLogger("phase3.scripts.step1_baseline")


def cleanup_dummy_phase3_rows(db_path: str | Path) -> Dict[str, int]:
    """Remove synthetic/launcher dummy rows from ``state/phase3/phase3.db`` idempotently."""
    db_file = Path(db_path)
    if not db_file.is_file():
        return {"deleted_sessions": 0, "deleted_rewards": 0, "deleted_calibration_reports": 0}

    conn = sqlite3.connect(str(db_file), timeout=15.0)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        deleted_rewards = 0
        deleted_sessions = 0
        deleted_cal = 0

        if "p3_decisions_rewards" in tables and "p3_sessions" in tables:
            cur = conn.execute(
                """
                DELETE FROM p3_decisions_rewards
                WHERE session_id IN (
                    SELECT session_id FROM p3_sessions
                    WHERE mode = 'paper' AND dwell_seconds < 5.0
                )
                OR ABS(rpm - 9.0219) < 1e-6
                """
            )
            deleted_rewards = int(cur.rowcount or 0)

        if "p3_sessions" in tables:
            cur = conn.execute(
                """
                DELETE FROM p3_sessions
                WHERE mode = 'paper' AND dwell_seconds < 5.0
                """
            )
            deleted_sessions = int(cur.rowcount or 0)

        if "p3_calibration_reports" in tables:
            cur = conn.execute(
                """
                DELETE FROM p3_calibration_reports
                WHERE a3_matched_days = 0
                """
            )
            deleted_cal = int(cur.rowcount or 0)

        conn.commit()
        return {
            "deleted_sessions": deleted_sessions,
            "deleted_rewards": deleted_rewards,
            "deleted_calibration_reports": deleted_cal,
        }
    finally:
        conn.close()


def load_real_adsterra_sync_history(legacy_db_path: str | Path) -> List[Dict[str, Any]]:
    """Load real daily aggregated revenue & impressions from ``sessions.db -> adsterra_api_sync``."""
    legacy_file = Path(legacy_db_path)
    if not legacy_file.is_file():
        return []

    conn = sqlite3.connect(str(legacy_file), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        has_tbl = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='adsterra_api_sync' LIMIT 1"
        ).fetchone()
        if not has_tbl:
            return []

        rows = conn.execute(
            """
            SELECT
                date,
                GROUP_CONCAT(DISTINCT domain) AS domains,
                SUM(api_impressions) AS impressions,
                SUM(api_clicks) AS clicks,
                SUM(api_revenue) AS revenue
            FROM adsterra_api_sync
            WHERE id IN (
                SELECT MAX(id) FROM adsterra_api_sync GROUP BY domain, date
            )
            GROUP BY date
            ORDER BY date ASC
            """
        ).fetchall()

        series: List[Dict[str, Any]] = []
        for r in rows:
            imps = int(r["impressions"] or 0)
            rev = float(r["revenue"] or 0.0)
            ecpm = (rev / imps) * 1000.0 if imps > 0 else 0.0
            series.append(
                {
                    "date": str(r["date"])[:10],
                    "domains": str(r["domains"] or ""),
                    "impressions": imps,
                    "clicks": int(r["clicks"] or 0),
                    "revenue": round(rev, 6),
                    "ecpm": round(ecpm, 6),
                    "source": "adsterra_api_sync",
                }
            )
        return series
    finally:
        conn.close()


async def enrich_with_live_today(
    series: List[Dict[str, Any]],
    feed: AdsterraFeedAdapter,
) -> Dict[str, Any]:
    """Fetch live Adsterra stats for today and merge into ``series`` if real records exist."""
    today = datetime.date.today().isoformat()
    if not feed.has_live_credentials():
        return {"live_credentials": False, "today_enriched": False, "items_count": 0}

    stats = await feed.fetch_domain_stats(start_date=today, finish_date=today, use_cache=False)
    mode = stats.get("mode") if isinstance(stats, dict) else "unknown"
    items = stats.get("items", []) if isinstance(stats, dict) else []
    if mode in ("phase3_fallback", "mock_simulated") or not isinstance(items, list):
        return {"live_credentials": True, "today_enriched": False, "mode": mode, "items_count": 0}

    total_imps = sum(int(it.get("impressions") or it.get("impression") or 0) for it in items if isinstance(it, dict))
    total_clicks = sum(int(it.get("clicks") or 0) for it in items if isinstance(it, dict))
    total_rev = sum(float(it.get("revenue") or 0.0) for it in items if isinstance(it, dict))

    if items and (total_imps > 0 or total_rev > 0.0):
        ecpm = (total_rev / total_imps) * 1000.0 if total_imps > 0 else 0.0
        existing = {row["date"]: row for row in series}
        existing[today] = {
            "date": today,
            "domains": "live_api_today",
            "impressions": total_imps,
            "clicks": total_clicks,
            "revenue": round(total_rev, 6),
            "ecpm": round(ecpm, 6),
            "source": "adsterra_live_api",
        }
        series[:] = [existing[d] for d in sorted(existing.keys())]
        return {
            "live_credentials": True,
            "today_enriched": True,
            "items_count": len(items),
            "today_impressions": total_imps,
            "today_revenue": round(total_rev, 6),
        }

    return {
        "live_credentials": True,
        "today_enriched": False,
        "items_count": len(items),
        "today_impressions": total_imps,
        "today_revenue": round(total_rev, 6),
    }


def get_table_counts(db_path: str | Path) -> Dict[str, int]:
    """Return current row counts for all Phase 3/4 tables in ``phase3.db``."""
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        tables = (
            "p3_sessions",
            "p3_decisions_rewards",
            "p3_cgnat_slots",
            "p3_forecasts",
            "p3_farm_devices",
            "p3_calibration_reports",
        )
        counts: Dict[str, int] = {}
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for tbl in tables:
            if tbl in existing:
                counts[tbl] = int(conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
            else:
                counts[tbl] = 0
        return counts
    finally:
        conn.close()


def run_step1_baseline(
    *,
    db_path: Optional[str | Path] = None,
    legacy_db_path: str | Path = "sessions.db",
) -> Dict[str, Any]:
    """Execute Step 1.2 cleanup and Step 1.3 real A3 forecast + calibration baseline."""
    load_dotenv_into_environ(force=True)
    cfg = load_phase3_config()
    configure_json_logging(cfg.phase3.log_level)

    target_db = Path(db_path) if db_path is not None else Path(cfg.phase3.db_path)
    store = Phase3Store(target_db)

    cleanup_summary = cleanup_dummy_phase3_rows(target_db)
    real_series = load_real_adsterra_sync_history(legacy_db_path)

    feed = AdsterraFeedAdapter(cfg, auto_load_env=True)
    live_info = asyncio.run(enrich_with_live_today(real_series, feed))

    forecaster = IRLSQuantileForecaster(cfg, store=store)
    forecast_result = forecaster.forecast(real_series, horizon_days=7)

    monitor = CalibrationMonitor(db_path=target_db, legacy_db_path=legacy_db_path)
    calibration_report = monitor.run_check()

    counts = get_table_counts(target_db)
    api_key = os.environ.get("ADSTERRA_API_KEY", "")
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) >= 8 else ("<set>" if api_key else "<unset>")

    summary = {
        "db_path": str(target_db),
        "legacy_db_path": str(legacy_db_path),
        "adsterra_api_key_masked": masked_key,
        "cleanup": cleanup_summary,
        "real_history_days": len(real_series),
        "real_series": real_series,
        "live_enrichment": live_info,
        "a3_forecast": {
            "method": forecast_result.get("method"),
            "sample_count": forecast_result.get("sample_count"),
            "horizon_days": forecast_result.get("horizon_days"),
            "p10": forecast_result.get("p10"),
            "p50": forecast_result.get("p50"),
            "p90": forecast_result.get("p90"),
            "ecpm_bands": forecast_result.get("ecpm_bands"),
        },
        "calibration_report": calibration_report,
        "table_counts": counts,
    }
    log_event(
        logger,
        logging.INFO,
        "step1_baseline_completed",
        table_counts=counts,
        real_history_days=len(real_series),
        a3_method=forecast_result.get("method"),
        calibration_status=calibration_report.get("status"),
    )
    return summary


if __name__ == "__main__":
    result = run_step1_baseline()
    print(json.dumps(result, indent=2, default=str))
