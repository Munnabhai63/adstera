"""
db.py — SQLite wrapper: session logging, daily counts, CTR tracking.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path("sessions.db")

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_id    TEXT    NOT NULL,
    ua          TEXT    NOT NULL,
    referrer    TEXT    NOT NULL DEFAULT '',
    dwell       REAL    NOT NULL,
    pages       INTEGER NOT NULL DEFAULT 1,
    ad_clicks   INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'ok',
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date        TEXT    PRIMARY KEY,
    sessions    INTEGER NOT NULL DEFAULT 0,
    ad_clicks   INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(str(_DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript(_DDL)
    logger.debug("DB initialised at %s", _DB_PATH)


def log_session(
    proxy_id: str,
    ua: str,
    referrer: str,
    dwell: float,
    pages: int = 1,
    ad_clicks: int = 0,
    impressions: int = 0,
    status: str = "ok",
) -> int:
    """Insert one session row and update daily_stats. Returns the new row id."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO sessions (proxy_id, ua, referrer, dwell, pages, ad_clicks, impressions, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proxy_id, ua, referrer, round(dwell, 2), pages, ad_clicks, impressions, status),
        )
        row_id = cur.lastrowid

        con.execute(
            """
            INSERT INTO daily_stats (date, sessions, ad_clicks, impressions)
            VALUES (date('now'), 1, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                sessions    = sessions + 1,
                ad_clicks   = ad_clicks + excluded.ad_clicks,
                impressions = impressions + excluded.impressions
            """,
            (ad_clicks, impressions),
        )
    return row_id


def today() -> int:
    """Return total sessions logged today."""
    with _conn() as con:
        row = con.execute(
            "SELECT sessions FROM daily_stats WHERE date = date('now')"
        ).fetchone()
    return int(row["sessions"]) if row else 0


def per_ip_today(proxy_id: str) -> int:
    """Return sessions logged for a specific proxy_id today."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE proxy_id=? AND date(ts)=date('now')",
            (proxy_id,),
        ).fetchone()
    return int(row["n"]) if row else 0


def ctr(last_n: int = 100) -> float:
    """Compute CTR (ad_clicks / impressions) over last N sessions."""
    with _conn() as con:
        row = con.execute(
            """
            SELECT SUM(ad_clicks) AS clicks, SUM(impressions) AS imps
            FROM (SELECT ad_clicks, impressions FROM sessions ORDER BY id DESC LIMIT ?)
            """,
            (last_n,),
        ).fetchone()
    if not row or not row["imps"]:
        return 0.0
    return round(row["clicks"] / row["imps"], 4)


def last_sessions(n: int = 10) -> list[dict]:
    """Return the last N session rows as dicts."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]

