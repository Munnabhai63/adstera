"""
store.py — AI engine SQLite persistence layer.

Extends the existing ``sessions.db`` database with four new tables for Phase 2:

* ``ai_decisions``     — every ad interaction decision logged by the engine.
* ``ai_rewards``       — RPM / CTR reward feedback linked to decisions.
* ``ai_anomalies``     — anomaly events detected by A2.
* ``ai_safe_mode_log`` — SAFE MODE entry / exit events.

All writes are synchronous and use WAL journal mode for concurrent access
compatibility with Phase 1's existing writer.

Usage::

    from ai_engine.store import AIStore
    store = AIStore("sessions.db")
    decision_id = store.log_decision(session_id="s1", device_id="emulator-5554", ...)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Sequence, Tuple

from common.sqlite_utils import DEFAULT_BUSY_TIMEOUT_MS, sqlite_write_context

logger = logging.getLogger(__name__)

# DDL for the four new tables (IF NOT EXISTS — safe to run multiple times)
_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS ai_decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL DEFAULT '',
    device_id   TEXT    NOT NULL DEFAULT '',
    domain      TEXT    NOT NULL DEFAULT '',
    slot_type   TEXT    NOT NULL DEFAULT '',
    action      TEXT    NOT NULL DEFAULT '',
    bbox_json   TEXT    NOT NULL DEFAULT 'null',
    reason      TEXT    NOT NULL DEFAULT '',
    ts          REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS ai_rewards (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id  INTEGER NOT NULL REFERENCES ai_decisions(id),
    rpm          REAL    NOT NULL DEFAULT 0.0,
    ctr          REAL    NOT NULL DEFAULT 0.0,
    impressions  INTEGER NOT NULL DEFAULT 0,
    reward_value REAL    NOT NULL DEFAULT 0.0,
    ts           REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS ai_anomalies (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    metric    TEXT NOT NULL DEFAULT '',
    value     REAL NOT NULL DEFAULT 0.0,
    z_score   REAL NOT NULL DEFAULT 0.0,
    severity  TEXT NOT NULL DEFAULT 'OK',
    action    TEXT NOT NULL DEFAULT '',
    details   TEXT NOT NULL DEFAULT '',
    ts        REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS ai_safe_mode_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_reason  TEXT NOT NULL DEFAULT '',
    exit_reason   TEXT NOT NULL DEFAULT '',
    duration_s    REAL NOT NULL DEFAULT 0.0,
    ts            REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_ai_decisions_ts     ON ai_decisions(ts);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_domain ON ai_decisions(domain);
CREATE INDEX IF NOT EXISTS idx_ai_rewards_dec_id   ON ai_rewards(decision_id);
CREATE INDEX IF NOT EXISTS idx_ai_anomalies_ts     ON ai_anomalies(ts);
"""


class AIStore:
    """Thread-safe SQLite store for Phase 2 AI engine data.

    Args:
        db_path: Path to the SQLite database file (may be the same file used
                 by Phase 1 — tables are added non-destructively).
    """

    def __init__(self, db_path: str = "sessions.db") -> None:
        self._db_path = str(Path(db_path))
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Open a WAL-configured SQLite connection with busy_timeout=10000."""
        with sqlite_write_context(
            self._db_path,
            timeout_s=15.0,
            busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
            immediate=immediate,
            check_same_thread=False,
        ) as conn:
            yield conn

    def _init_db(self) -> None:
        """Create the four AI engine tables if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(_DDL)
        logger.debug("store: schema ensured on %s", self._db_path)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def log_decision(
        self,
        *,
        session_id: str,
        device_id: str,
        domain: str,
        slot_type: str,
        action: str,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        reason: str = "",
        ts: Optional[float] = None,
    ) -> int:
        """Insert a row into ``ai_decisions`` and return its ``id``.

        Args:
            session_id: Identifier of the browser/ADB session.
            device_id:  ADB device serial or empty string for Playwright sessions.
            domain:     Publisher domain (e.g. ``"example.com"``).
            slot_type:  Ad slot type string.
            action:     One of ``"click"``, ``"skip"``, or ``"defer"``.
            bbox:       Bounding box tuple ``(x, y, w, h)`` or ``None``.
            reason:     Human-readable justification.
            ts:         Unix timestamp; defaults to ``time.time()``.

        Returns:
            The ``id`` of the newly inserted row.
        """
        bbox_json = json.dumps(list(bbox)) if bbox is not None else "null"
        ts = ts or time.time()
        with self._connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_decisions
                    (session_id, device_id, domain, slot_type, action, bbox_json, reason, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, device_id, domain, slot_type, action, bbox_json, reason, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def log_reward(
        self,
        *,
        decision_id: int,
        rpm: float,
        ctr: float,
        impressions: int,
        reward_value: float,
        ts: Optional[float] = None,
    ) -> int:
        """Insert a row into ``ai_rewards`` and return its ``id``.

        Args:
            decision_id:  FK reference to ``ai_decisions.id``.
            rpm:          Revenue per mille impressions (USD).
            ctr:          Click-through rate for this window.
            impressions:  Total impression count in this window.
            reward_value: Scalar reward fed back to the bandit (A1).
            ts:           Unix timestamp; defaults to ``time.time()``.

        Returns:
            The ``id`` of the newly inserted row.
        """
        ts = ts or time.time()
        with self._connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_rewards
                    (decision_id, rpm, ctr, impressions, reward_value, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (decision_id, rpm, ctr, impressions, reward_value, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def log_anomaly(
        self,
        *,
        metric: str,
        value: float,
        z_score: float,
        severity: str,
        action: str = "",
        details: str = "",
        ts: Optional[float] = None,
    ) -> int:
        """Insert a row into ``ai_anomalies`` and return its ``id``.

        Args:
            metric:   Name of the anomalous metric (e.g. ``"ctr"``).
            value:    Observed metric value.
            z_score:  Computed z-score (or isolation score).
            severity: ``"WARNING"`` or ``"CRITICAL"``.
            action:   Automated action taken (e.g. ``"safe_mode_enter"``).
            details:  Free-form JSON or text with extra context.
            ts:       Unix timestamp; defaults to ``time.time()``.

        Returns:
            The ``id`` of the newly inserted row.
        """
        ts = ts or time.time()
        with self._connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_anomalies
                    (metric, value, z_score, severity, action, details, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (metric, value, z_score, severity, action, details, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def log_safe_mode(
        self,
        *,
        entry_reason: str,
        exit_reason: str = "",
        duration_s: float = 0.0,
        ts: Optional[float] = None,
    ) -> int:
        """Insert a row into ``ai_safe_mode_log`` and return its ``id``.

        Call once on **entry** (``exit_reason=''``, ``duration_s=0``), then
        update the row (or insert a new one) on **exit** using the same
        ``entry_reason``.

        Args:
            entry_reason: Why SAFE MODE was activated.
            exit_reason:  Why SAFE MODE was deactivated (empty on entry).
            duration_s:   Seconds spent in SAFE MODE (0 on entry).
            ts:           Unix timestamp; defaults to ``time.time()``.

        Returns:
            The ``id`` of the newly inserted row.
        """
        ts = ts or time.time()
        with self._connect(immediate=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_safe_mode_log
                    (entry_reason, exit_reason, duration_s, ts)
                VALUES (?, ?, ?, ?)
                """,
                (entry_reason, exit_reason, duration_s, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query_recent_ctr(self, window: int = 200) -> float:
        """Return CTR computed over the last *window* decisions with rewards.

        Args:
            window: Number of most-recent reward rows to consider.

        Returns:
            CTR as a float in ``[0.0, 1.0]``.  Returns ``0.0`` if no data.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT AVG(ctr) AS avg_ctr
                FROM (
                    SELECT ctr FROM ai_rewards
                    ORDER BY ts DESC
                    LIMIT ?
                )
                """,
                (window,),
            ).fetchone()
        if row and row["avg_ctr"] is not None:
            return float(row["avg_ctr"])
        return 0.0

    def query_recent_rpm(self, window: int = 200) -> float:
        """Return average RPM over the last *window* reward rows.

        Args:
            window: Number of most-recent reward rows to consider.

        Returns:
            Average RPM in USD.  Returns ``0.0`` if no data.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT AVG(rpm) AS avg_rpm
                FROM (
                    SELECT rpm FROM ai_rewards
                    ORDER BY ts DESC
                    LIMIT ?
                )
                """,
                (window,),
            ).fetchone()
        if row and row["avg_rpm"] is not None:
            return float(row["avg_rpm"])
        return 0.0

    def query_recent_anomalies(
        self, since_ts: float, severity: Optional[str] = None
    ) -> Sequence[sqlite3.Row]:
        """Return anomaly rows newer than *since_ts*.

        Args:
            since_ts: Minimum Unix timestamp (exclusive).
            severity: If provided, filter to only this severity level.

        Returns:
            Sequence of :class:`sqlite3.Row` objects.
        """
        with self._connect() as conn:
            if severity:
                rows = conn.execute(
                    "SELECT * FROM ai_anomalies WHERE ts > ? AND severity = ? ORDER BY ts DESC",
                    (since_ts, severity),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ai_anomalies WHERE ts > ? ORDER BY ts DESC",
                    (since_ts,),
                ).fetchall()
        return rows
