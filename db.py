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
    domain      TEXT    NOT NULL DEFAULT 'loanraaj.com',
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date        TEXT    PRIMARY KEY,
    sessions    INTEGER NOT NULL DEFAULT 0,
    ad_clicks   INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS domain_stats (
    domain      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    sessions    INTEGER NOT NULL DEFAULT 0,
    ad_clicks   INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (domain, date)
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
    """Create tables if they don't exist and run incremental schema migrations."""
    with _conn() as con:
        con.executescript(_DDL)
        # Incremental migration: Ensure 'domain' column exists on legacy sessions table
        cur = con.execute("PRAGMA table_info(sessions)")
        cols = [c[1] for c in cur.fetchall()]
        if "domain" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN domain TEXT NOT NULL DEFAULT 'loanraaj.com'")
            logger.info("Migrated sessions table: added 'domain' column.")
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
    domain: str = "loanraaj.com",
) -> int:
    """Insert one session row and update daily_stats and domain_stats. Returns the new row id."""
    clean_domain = (domain or "loanraaj.com").lower().strip()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO sessions (proxy_id, ua, referrer, dwell, pages, ad_clicks, impressions, status, domain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proxy_id, ua, referrer, round(dwell, 2), pages, ad_clicks, impressions, status, clean_domain),
        )
        row_id = cur.lastrowid

        # Update global daily stats
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

        # Update per-domain daily stats
        con.execute(
            """
            INSERT INTO domain_stats (domain, date, sessions, ad_clicks, impressions)
            VALUES (?, date('now'), 1, ?, ?)
            ON CONFLICT(domain, date) DO UPDATE SET
                sessions    = sessions + 1,
                ad_clicks   = ad_clicks + excluded.ad_clicks,
                impressions = impressions + excluded.impressions
            """,
            (clean_domain, ad_clicks, impressions),
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


def domain_today(domain: str) -> dict:
    """Return metrics logged for a specific domain today."""
    clean_domain = (domain or "loanraaj.com").lower().strip()
    with _conn() as con:
        row = con.execute(
            """
            SELECT sessions, ad_clicks, impressions
            FROM domain_stats
            WHERE domain = ? AND date = date('now')
            """,
            (clean_domain,),
        ).fetchone()
    if not row:
        return {"domain": clean_domain, "sessions": 0, "clicks": 0, "impressions": 0, "ctr": 0.0}
    
    sessions = int(row["sessions"])
    clicks = int(row["ad_clicks"])
    imps = int(row["impressions"])
    ctr_val = (clicks / imps * 100.0) if imps > 0 else 0.0
    return {
        "domain": clean_domain,
        "sessions": sessions,
        "clicks": clicks,
        "impressions": imps,
        "ctr": round(ctr_val, 2),
    }


def domain_ctr(domain: str, last_n: int = 100) -> float:
    """Compute CTR specifically for a single domain over its last N sessions."""
    clean_domain = (domain or "loanraaj.com").lower().strip()
    with _conn() as con:
        row = con.execute(
            """
            SELECT SUM(ad_clicks) AS clicks, SUM(impressions) AS imps
            FROM (
                SELECT ad_clicks, impressions 
                FROM sessions 
                WHERE domain = ? 
                ORDER BY id DESC LIMIT ?
            )
            """,
            (clean_domain, last_n),
        ).fetchone()
    if not row or not row["imps"]:
        return 0.0
    return round(row["clicks"] / row["imps"], 4)


def check_domain_safety(domain: str, max_ctr: float = 0.050, warning_ctr: float = 0.044) -> dict:
    """
    Evaluates independent per-domain CTR against strict anti-IVT safety bounds.
    - If CTR >= max_ctr (5.0%) and impressions >= 10: PAUSED (100% zero-click suppression).
    - If CTR >= warning_ctr (4.4%) and impressions >= 10: GUARD_ACTIVE (suppress 80% of clicks).
    - Otherwise: OPTIMAL (allow natural ad click evaluation).
    """
    import random
    clean_domain = (domain or "loanraaj.com").lower().strip()
    today_stats = domain_today(clean_domain)
    imps = today_stats["impressions"]
    clicks = today_stats["clicks"]
    current_ctr = (clicks / imps) if imps > 0 else 0.0

    if imps >= 10 and current_ctr >= max_ctr:
        return {
            "domain": clean_domain,
            "status": "PAUSED",
            "allow_click": False,
            "current_ctr": round(current_ctr * 100.0, 2),
            "reason": f"CTR {current_ctr * 100.0:.2f}% exceeds hard limit {max_ctr * 100.0:.1f}%",
        }
    elif imps >= 10 and current_ctr >= warning_ctr:
        allow = random.random() < 0.20  # throttle 80% of attempts
        return {
            "domain": clean_domain,
            "status": "GUARD_ACTIVE",
            "allow_click": allow,
            "current_ctr": round(current_ctr * 100.0, 2),
            "reason": f"CTR {current_ctr * 100.0:.2f}% in warning zone (throttled)",
        }
    else:
        return {
            "domain": clean_domain,
            "status": "OPTIMAL",
            "allow_click": True,
            "current_ctr": round(current_ctr * 100.0, 2),
            "reason": "CTR in healthy green zone",
        }


def all_domains_summary(default_cpm: float = 4.50) -> list[dict]:
    """Return aggregated today metrics for all tracked domains."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT domain, sessions, ad_clicks, impressions
            FROM domain_stats
            WHERE date = date('now')
            ORDER BY sessions DESC
            """
        ).fetchall()

    summary = []
    for r in rows:
        dom = r["domain"]
        s = int(r["sessions"])
        c = int(r["ad_clicks"])
        i = int(r["impressions"])
        ctr_val = (c / i * 100.0) if i > 0 else 0.0
        safety = check_domain_safety(dom)
        est_rev = round((i / 1000.0) * default_cpm + (c * 0.04), 2)
        summary.append({
            "domain": dom,
            "sessions": s,
            "impressions": i,
            "clicks": c,
            "ctr": round(ctr_val, 2),
            "status": safety["status"],
            "allow_click": safety["allow_click"],
            "cpm": round(default_cpm, 2),
            "estimated_revenue": est_rev,
        })
    return summary


def last_sessions(n: int = 10) -> list[dict]:
    """Return the last N session rows as dicts."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_metrics(cpm_rate: float = 2.50) -> dict:
    """Return aggregated daily metrics: impressions, clicks, CTR, CPM, and estimated revenue."""
    with _conn() as con:
        row = con.execute(
            "SELECT sessions, ad_clicks, impressions FROM daily_stats WHERE date = date('now')"
        ).fetchone()

    sessions = int(row["sessions"]) if row else 0
    clicks = int(row["ad_clicks"]) if row else 0
    imps = int(row["impressions"]) if row else 0

    ctr_val = (clicks / imps * 100.0) if imps > 0 else 0.0
    rev = round((imps / 1000.0) * cpm_rate + (clicks * 0.03), 2)

    return {
        "sessions": sessions,
        "impressions": imps,
        "clicks": clicks,
        "ctr": round(ctr_val, 2),
        "cpm": round(cpm_rate, 2),
        "revenue": rev,
    }


def export_stats_csv(filepath: str = "stats.csv", cpm_rate: float = 2.50) -> str:
    """
    Generate or update the CSV metrics report matching automation.md schema:
    Date,Impressions,Clicks,CTR,CPM,Revenue
    """
    import csv
    from datetime import datetime

    metrics = get_metrics(cpm_rate)
    target_file = Path(filepath)
    file_exists = target_file.exists() and target_file.stat().st_size > 0

    with open(target_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Impressions", "Clicks", "CTR", "CPM", "Revenue"])
        writer.writerow([
            datetime.now().strftime("%Y/%m/%d %H:%M"),
            metrics["impressions"],
            metrics["clicks"],
            f"{metrics['ctr']:.2f}%",
            f"${metrics['cpm']:.2f}",
            f"${metrics['revenue']:.2f}",
        ])
    return str(target_file)


