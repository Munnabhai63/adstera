"""Phase 3 SQLite migration runner and persistence store."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from common.sqlite_utils import DEFAULT_BUSY_TIMEOUT_MS, sqlite_write_context


MIGRATIONS_DIR = Path(__file__).resolve().parent


def apply_migrations(db_path: str | Path, migrations_dir: Path = MIGRATIONS_DIR) -> List[str]:
    """Apply all unapplied ``*.sql`` migrations in lexical order (idempotent)."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    applied: List[str] = []

    with sqlite_write_context(
        db_file,
        timeout_s=15.0,
        busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
        immediate=False,
        foreign_keys=True,
    ) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at REAL NOT NULL);"
        )
        existing = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            version = sql_file.stem
            if version in existing:
                continue
            sql_text = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql_text)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, time.time()),
            )
            conn.commit()
            applied.append(version)
    return applied


class Phase3Store:
    """Thread-safe SQLite store for Phase 3 sessions, rewards, CGNAT slots, forecasts, and farm devices."""

    def __init__(self, db_path: str | Path = "state/phase3/phase3.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        apply_migrations(self.db_path)

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            with sqlite_write_context(
                self.db_path,
                timeout_s=15.0,
                busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
                immediate=immediate,
                foreign_keys=True,
            ) as conn:
                yield conn

    def start_session(
        self,
        *,
        session_id: str,
        correlation_id: str,
        device_id: str,
        mode: str,
        domain: str,
        ip_address: str = "",
        subnet_24: str = "",
        subnet_20: str = "",
        started_at: Optional[float] = None,
    ) -> None:
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO p3_sessions
                (session_id, correlation_id, device_id, mode, domain, ip_address,
                 subnet_24, subnet_20, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'started', ?)
                """,
                (
                    session_id,
                    correlation_id,
                    device_id,
                    mode,
                    domain,
                    ip_address,
                    subnet_24,
                    subnet_20,
                    started_at if started_at is not None else time.time(),
                ),
            )

    def finish_session(
        self,
        session_id: str,
        *,
        status: str = "completed",
        dwell_seconds: float = 0.0,
        error: str = "",
        ended_at: Optional[float] = None,
    ) -> None:
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                UPDATE p3_sessions
                SET status = ?, dwell_seconds = ?, error = ?, ended_at = ?
                WHERE session_id = ?
                """,
                (
                    status,
                    float(dwell_seconds),
                    error,
                    ended_at if ended_at is not None else time.time(),
                    session_id,
                ),
            )

    def log_decision_reward(
        self,
        *,
        session_id: str,
        correlation_id: str,
        device_id: str,
        domain: str,
        slot_type: str,
        action: str,
        executed_touch: bool,
        bbox: Optional[Tuple[int, int, int, int]],
        a4_source: str,
        a4_confidence: float,
        a2_severity: str,
        safe_mode: bool,
        rpm: float,
        ctr: float,
        reward_value: float,
        reason: str,
        ts: Optional[float] = None,
    ) -> int:
        bbox_json = json.dumps(list(bbox)) if bbox is not None else "null"
        with self.connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO p3_decisions_rewards
                (session_id, correlation_id, device_id, domain, slot_type, action,
                 executed_touch, bbox_json, a4_source, a4_confidence, a2_severity,
                 safe_mode, rpm, ctr, reward_value, reason, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    correlation_id,
                    device_id,
                    domain,
                    slot_type,
                    action,
                    1 if executed_touch else 0,
                    bbox_json,
                    a4_source,
                    float(a4_confidence),
                    a2_severity,
                    1 if safe_mode else 0,
                    float(rpm),
                    float(ctr),
                    float(reward_value),
                    reason,
                    ts if ts is not None else time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    def log_forecast(
        self,
        *,
        horizon_days: int,
        sample_count: int,
        method: str,
        p10_revenue: float,
        p50_revenue: float,
        p90_revenue: float,
        p10_ecpm: float,
        p50_ecpm: float,
        p90_ecpm: float,
        created_at: Optional[float] = None,
    ) -> int:
        with self.connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO p3_forecasts
                (horizon_days, sample_count, method, p10_revenue, p50_revenue, p90_revenue,
                 p10_ecpm, p50_ecpm, p90_ecpm, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(horizon_days),
                    int(sample_count),
                    method,
                    float(p10_revenue),
                    float(p50_revenue),
                    float(p90_revenue),
                    float(p10_ecpm),
                    float(p50_ecpm),
                    float(p90_ecpm),
                    created_at if created_at is not None else time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    def upsert_farm_device(
        self,
        *,
        device_id: str,
        usb_port: str = "",
        cdp_port: int = 0,
        b1_port: int = 0,
        status: str = "healthy",
        consecutive_failures: int = 0,
        quarantined_until: float = 0.0,
        total_sessions: int = 0,
        total_clicks: int = 0,
        last_seen_at: Optional[float] = None,
    ) -> None:
        with self.connect(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO p3_farm_devices
                (device_id, usb_port, cdp_port, b1_port, status, consecutive_failures,
                 quarantined_until, total_sessions, total_clicks, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    usb_port=excluded.usb_port,
                    cdp_port=excluded.cdp_port,
                    b1_port=excluded.b1_port,
                    status=excluded.status,
                    consecutive_failures=excluded.consecutive_failures,
                    quarantined_until=excluded.quarantined_until,
                    total_sessions=excluded.total_sessions,
                    total_clicks=excluded.total_clicks,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    device_id,
                    usb_port,
                    int(cdp_port),
                    int(b1_port),
                    status,
                    int(consecutive_failures),
                    float(quarantined_until),
                    int(total_sessions),
                    int(total_clicks),
                    last_seen_at if last_seen_at is not None else time.time(),
                ),
            )

    def count_sessions(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM p3_sessions").fetchone()
            return int(row[0]) if row else 0

    def count_decisions(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM p3_decisions_rewards").fetchone()
            return int(row[0]) if row else 0

    def count_executed_touches(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM p3_decisions_rewards WHERE executed_touch = 1"
            ).fetchone()
            return int(row[0]) if row else 0

    def recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM p3_decisions_rewards ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]

    def check_ctr_cap_atomic(
        self,
        *,
        device_id: str = "",
        hard_cap: float = 0.045,
        window_size: int = 20,
        candidate_click: bool = True,
    ) -> bool:
        """Atomically verify candidate click would not breach CTR hard cap using BEGIN IMMEDIATE."""
        with self.connect(immediate=True) as conn:
            query = "SELECT action FROM p3_decisions_rewards "
            params: List[Any] = []
            if device_id:
                query += "WHERE device_id = ? "
                params.append(device_id)
            query += "ORDER BY id DESC LIMIT ?"
            params.append(int(window_size))
            rows = conn.execute(query, tuple(params)).fetchall()
            if not rows or len(rows) < 10:
                return True
            clicks = sum(1 for r in rows if r["action"] in ("click", "paper_click"))
            if candidate_click:
                clicks += 1
            ctr = clicks / max(1, len(rows) + (1 if candidate_click else 0))
            return ctr <= hard_cap
