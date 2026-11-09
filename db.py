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
    error_reason TEXT   DEFAULT '',
    geo_country TEXT    DEFAULT '',
    geo_tier    TEXT    DEFAULT '',
    ad_network  TEXT    DEFAULT 'adsterra',
    variant_id  TEXT    DEFAULT 'default',
    ts          TEXT    NOT NULL DEFAULT (datetime('now', '+5 hours', '30 minutes'))
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

CREATE TABLE IF NOT EXISTS adsterra_api_sync (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    domain            TEXT NOT NULL,
    date              TEXT NOT NULL,
    api_impressions   INTEGER NOT NULL,
    api_clicks        INTEGER NOT NULL,
    api_ctr           REAL NOT NULL,
    api_cpm           REAL NOT NULL,
    api_revenue       REAL NOT NULL,
    local_impressions INTEGER NOT NULL,
    discrepancy_pct   REAL NOT NULL,
    synced_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lead_conversions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT NOT NULL,
    advertiser_url  TEXT NOT NULL,
    email           TEXT NOT NULL,
    persona_name    TEXT NOT NULL,
    fields_filled   INTEGER NOT NULL DEFAULT 0,
    dwell_sec       REAL NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'submitted',
    bounty_est      REAL NOT NULL DEFAULT 2.50,
    ts              TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alert_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type  TEXT NOT NULL,
    level       TEXT NOT NULL,
    domain      TEXT DEFAULT '',
    message     TEXT NOT NULL,
    sent_live   INTEGER NOT NULL DEFAULT 0,
    ts          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ecpm_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    ecpm        REAL NOT NULL DEFAULT 0.0,
    impressions INTEGER NOT NULL DEFAULT 0,
    revenue     REAL NOT NULL DEFAULT 0.0,
    weight      REAL NOT NULL DEFAULT 1.0,
    synced_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_id        TEXT    NOT NULL,
    domain          TEXT    NOT NULL DEFAULT 'loanraaj.com',
    action          TEXT    NOT NULL DEFAULT 'skipped',
    delay_s         REAL    NOT NULL DEFAULT 0.0,
    geo_country     TEXT    DEFAULT '',
    geo_tier        TEXT    DEFAULT '',
    session_id      INTEGER DEFAULT NULL,
    ts              TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cpa_conversions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id        TEXT    NOT NULL,
    network         TEXT    NOT NULL DEFAULT 'direct',
    niche           TEXT    NOT NULL DEFAULT 'loan',
    proxy_id        TEXT    NOT NULL,
    domain          TEXT    NOT NULL DEFAULT 'loanraaj.com',
    geo_country     TEXT    DEFAULT '',
    geo_tier        TEXT    DEFAULT '',
    payout_usd      REAL    NOT NULL DEFAULT 0.0,
    landing_url     TEXT    DEFAULT '',
    session_id      INTEGER DEFAULT NULL,
    dwell_s         REAL    NOT NULL DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT 'submitted',
    ts              TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS competitor_intel (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT    NOT NULL,
    domain              TEXT    NOT NULL,
    detected_networks   TEXT    NOT NULL,
    ad_unit_count       INTEGER NOT NULL DEFAULT 0,
    word_count          INTEGER NOT NULL DEFAULT 0,
    ad_density          REAL    NOT NULL DEFAULT 0.0,
    top_keywords        TEXT    NOT NULL DEFAULT '[]',
    scanned_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS published_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    title       TEXT NOT NULL,
    slug        TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    word_count  INTEGER NOT NULL,
    ai_score    REAL NOT NULL DEFAULT 5.0,
    url         TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT (datetime('now', '+5 hours', '30 minutes'))
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
    """Create tables if they don't exist, enable WAL mode (DB-1), IST timestamps (DB-2),
    and indexes (DB-3). Run incremental schema migrations."""
    with _conn() as con:
        # DB-1: Full WAL + performance PRAGMAs — no more lock errors at concurrency=6
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA cache_size=10000")
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA temp_store=MEMORY")

        con.executescript(_DDL)

        # DB-3: Indexes on hot query columns — fast queries at scale
        con.executescript("""
            CREATE INDEX IF NOT EXISTS idx_sessions_ts
                ON sessions(ts);
            CREATE INDEX IF NOT EXISTS idx_sessions_domain_ts
                ON sessions(domain, ts);
            CREATE INDEX IF NOT EXISTS idx_sessions_proxy_ts
                ON sessions(proxy_id, ts);
            CREATE INDEX IF NOT EXISTS idx_sessions_status
                ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_published_domain_ts
                ON published_posts(domain, published_at);
        """)

        # Incremental migration: Ensure columns exist on legacy sessions table
        cur = con.execute("PRAGMA table_info(sessions)")
        cols = [c[1] for c in cur.fetchall()]
        if "domain" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN domain TEXT NOT NULL DEFAULT 'loanraaj.com'")
            logger.info("Migrated sessions table: added 'domain' column.")
        if "error_reason" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN error_reason TEXT DEFAULT ''")
            logger.info("Migrated sessions table: added 'error_reason' column.")
        if "geo_country" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN geo_country TEXT DEFAULT ''")
            logger.info("Migrated sessions table: added 'geo_country' column.")
        if "geo_tier" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN geo_tier TEXT DEFAULT ''")
            logger.info("Migrated sessions table: added 'geo_tier' column.")
        if "ad_network" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN ad_network TEXT DEFAULT 'adsterra'")
            logger.info("Migrated sessions table: added 'ad_network' column.")
        if "variant_id" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN variant_id TEXT DEFAULT 'default'")
            logger.info("Migrated sessions table: added 'variant_id' column.")
    logger.debug("DB initialised at %s (WAL+IST+indexed)", _DB_PATH)


def log_push_event(
    proxy_id: str,
    domain: str,
    action: str,
    delay_s: float = 0.0,
    geo_country: str = "",
    geo_tier: str = "",
    session_id: int | None = None,
) -> int:
    """
    Log a push notification permission event.
    action: 'allow' | 'block' | 'skipped' | 'eu_skip' | 'allow_failed'
    Returns the new row id.
    """
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO push_subscriptions
                (proxy_id, domain, action, delay_s, geo_country, geo_tier, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (proxy_id, domain or "loanraaj.com", action, delay_s, geo_country, geo_tier, session_id),
        )
        logger.debug(
            "Push event logged: domain=%s action=%s proxy=%s delay=%.1fs",
            domain, action, proxy_id, delay_s,
        )
        return cur.lastrowid or 0


def push_allow_rate(domain: str = "", last_n: int = 200) -> float:
    """
    Returns the push allow rate (0-1) for the given domain over the last N events.
    Used for monitoring in UI dashboard.
    """
    with _conn() as con:
        if domain:
            rows = con.execute(
                """
                SELECT action FROM push_subscriptions
                WHERE domain = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (domain, last_n),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT action FROM push_subscriptions
                ORDER BY ts DESC LIMIT ?
                """,
                (last_n,),
            ).fetchall()
    if not rows:
        return 0.0
    allowed = sum(1 for r in rows if r[0] == "allow")
    return allowed / len(rows)


def push_today_count() -> dict:
    """Returns today's push event counts by action type."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT action, COUNT(*) as cnt
            FROM push_subscriptions
            WHERE DATE(ts) = DATE('now')
            GROUP BY action
            """,
        ).fetchall()
    result = {"allow": 0, "block": 0, "skipped": 0, "eu_skip": 0, "allow_failed": 0}
    for row in rows:
        action = row[0] if row[0] in result else "skipped"
        result[action] = row[1]
    return result


def log_cpa_conversion(
    offer_id: str,
    network: str,
    niche: str,
    proxy_id: str,
    domain: str,
    geo_country: str = "",
    geo_tier: str = "",
    payout_usd: float = 0.0,
    landing_url: str = "",
    session_id: int | None = None,
    dwell_s: float = 0.0,
    status: str = "submitted",
) -> int:
    """
    Log a CPA conversion event.
    status: 'submitted' | 'confirmed' | 'rejected' | 'pending'
    Returns the new row id.
    """
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO cpa_conversions
                (offer_id, network, niche, proxy_id, domain, geo_country, geo_tier,
                 payout_usd, landing_url, session_id, dwell_s, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer_id, network, niche, proxy_id,
                domain or "loanraaj.com", geo_country, geo_tier,
                round(payout_usd, 4), landing_url, session_id,
                round(dwell_s, 2), status,
            ),
        )
        logger.debug(
            "CPA conversion logged: offer=%s network=%s payout=$%.2f domain=%s",
            offer_id, network, payout_usd, domain,
        )
        return cur.lastrowid or 0


def cpa_today_count(offer_id: str = "") -> int:
    """Returns today's CPA conversion count for a specific offer (or all if empty)."""
    with _conn() as con:
        if offer_id:
            row = con.execute(
                "SELECT COUNT(*) FROM cpa_conversions WHERE offer_id=? AND DATE(ts)=DATE('now')",
                (offer_id,),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT COUNT(*) FROM cpa_conversions WHERE DATE(ts)=DATE('now')"
            ).fetchone()
    return int(row[0]) if row else 0


def cpa_today_count_by_proxy(proxy_id: str) -> int:
    """Returns today's CPA attempt count for a specific proxy."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM cpa_conversions WHERE proxy_id=? AND DATE(ts)=DATE('now')",
            (proxy_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def cpa_today_revenue() -> float:
    """Returns estimated today's total CPA revenue in USD."""
    with _conn() as con:
        row = con.execute(
            """
            SELECT COALESCE(SUM(payout_usd), 0.0)
            FROM cpa_conversions
            WHERE DATE(ts) = DATE('now') AND status NOT IN ('rejected')
            """
        ).fetchone()
    return float(row[0]) if row else 0.0


def cpa_network_summary(last_days: int = 7) -> list[dict]:
    """Returns per-network conversion summary for last N days."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT network, niche,
                   COUNT(*) as conversions,
                   ROUND(SUM(payout_usd), 2) as revenue_usd
            FROM cpa_conversions
            WHERE DATE(ts) >= DATE('now', ?)
              AND status NOT IN ('rejected')
            GROUP BY network, niche
            ORDER BY revenue_usd DESC
            """,
            (f"-{last_days} days",),
        ).fetchall()
    return [
        {
            "network": r[0],
            "niche": r[1],
            "conversions": r[2],
            "revenue_usd": r[3],
        }
        for r in rows
    ]


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
    error_reason: str = "",
    geo_country: str = "",
    geo_tier: str = "",
    ad_network: str = "adsterra",
    variant_id: str = "default",
) -> int:
    """Insert one session row and update daily_stats and domain_stats. Returns the new row id."""
    clean_domain = (domain or "loanraaj.com").lower().strip()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO sessions (proxy_id, ua, referrer, dwell, pages, ad_clicks, impressions, status, domain, error_reason, geo_country, geo_tier, ad_network, variant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proxy_id, ua, referrer, round(dwell, 2), pages, ad_clicks, impressions, status, clean_domain, error_reason or "", geo_country or "", geo_tier or "", ad_network or "adsterra", variant_id or "default"),
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


def get_ab_test_metrics(last_n: int = 500) -> dict[str, dict[str, Any]]:
    """
    Step 5.3: Compute aggregated metrics for each A/B testing strategy variant.
    Returns: {
        variant_id: {
            'sessions': int,
            'degraded': int,
            'degraded_pct': float,
            'clicks': int,
            'impressions': int,
            'ctr': float,
            'avg_dwell': float,
        }
    }
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT COALESCE(variant_id, 'default') AS var_id,
                   COUNT(*) AS sessions,
                   SUM(CASE WHEN status='degraded' THEN 1 ELSE 0 END) AS degraded,
                   SUM(ad_clicks) AS clicks,
                   SUM(impressions) AS impressions,
                   AVG(dwell) AS avg_dwell
            FROM (SELECT * FROM sessions ORDER BY id DESC LIMIT ?)
            GROUP BY var_id
            """,
            (last_n,),
        ).fetchall()

    metrics = {}
    for r in rows:
        var_id = str(r["var_id"])
        sess = int(r["sessions"] or 0)
        deg = int(r["degraded"] or 0)
        clicks = int(r["clicks"] or 0)
        imps = int(r["impressions"] or 0)
        avg_dwell = float(r["avg_dwell"] or 0.0)
        ctr_val = round(clicks / imps, 4) if imps > 0 else 0.0
        deg_pct = round(deg / sess, 4) if sess > 0 else 0.0
        metrics[var_id] = {
            "sessions": sess,
            "degraded": deg,
            "degraded_pct": deg_pct,
            "clicks": clicks,
            "impressions": imps,
            "ctr": ctr_val,
            "avg_dwell": round(avg_dwell, 1),
        }
    return metrics


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


def all_domains_summary(default_cpm: float = 4.50, configured_domains: list | None = None, date_str: str | None = None) -> list[dict]:
    """Return aggregated today metrics for all tracked domains, merging configured domains."""
    with _conn() as con:
        if date_str:
            rows = con.execute(
                """
                SELECT domain, sessions, ad_clicks, impressions
                FROM domain_stats
                WHERE date = ?
                ORDER BY sessions DESC
                """,
                (date_str,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT domain, sessions, ad_clicks, impressions
                FROM domain_stats
                WHERE date = date('now')
                ORDER BY sessions DESC
                """
            ).fetchall()

    summary = []
    seen_domains = set()
    for r in rows:
        dom = r["domain"]
        seen_domains.add(dom)
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

    if configured_domains:
        for item in configured_domains:
            dom = item.get("domain") if isinstance(item, dict) else str(item)
            if dom and dom not in seen_domains:
                seen_domains.add(dom)
                cpm = item.get("target_cpm", default_cpm) if isinstance(item, dict) else default_cpm
                summary.append({
                    "domain": dom,
                    "sessions": 0,
                    "impressions": 0,
                    "clicks": 0,
                    "ctr": 0.0,
                    "status": "OPTIMAL",
                    "allow_click": True,
                    "cpm": round(float(cpm), 2),
                    "estimated_revenue": 0.0,
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


def record_adsterra_sync(
    domain: str,
    date: str,
    api_impressions: int,
    api_clicks: int,
    api_ctr: float,
    api_cpm: float,
    api_revenue: float,
    local_impressions: int,
    discrepancy_pct: float,
) -> int:
    """Record an Adsterra API sync row comparing API data to local stats."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO adsterra_api_sync (
                domain, date, api_impressions, api_clicks, api_ctr, api_cpm,
                api_revenue, local_impressions, discrepancy_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                date,
                int(api_impressions),
                int(api_clicks),
                float(api_ctr),
                float(api_cpm),
                float(api_revenue),
                int(local_impressions),
                float(discrepancy_pct),
            ),
        )
        return int(cur.lastrowid)


def get_latest_adsterra_sync(domain: str | None = None, limit: int = 20) -> list[dict]:
    """Retrieve the most recent Adsterra API sync reconciliation rows."""
    with _conn() as con:
        if domain:
            rows = con.execute(
                """
                SELECT * FROM adsterra_api_sync
                WHERE domain = ?
                ORDER BY id DESC LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT * FROM adsterra_api_sync
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def record_lead_conversion(
    domain: str,
    advertiser_url: str,
    email: str,
    persona_name: str,
    fields_filled: int = 0,
    dwell_sec: float = 0.0,
    status: str = "submitted",
    bounty_est: float = 2.50,
) -> int:
    """Record a post-click CPL lead form submission into sessions.db."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO lead_conversions (
                domain, advertiser_url, email, persona_name, fields_filled,
                dwell_sec, status, bounty_est
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                advertiser_url,
                email,
                persona_name,
                int(fields_filled),
                float(dwell_sec),
                status,
                float(bounty_est),
            ),
        )
        return int(cur.lastrowid)


def get_lead_conversions(domain: str | None = None, limit: int = 20) -> list[dict]:
    """Retrieve recent lead conversions."""
    with _conn() as con:
        if domain:
            rows = con.execute(
                """
                SELECT * FROM lead_conversions
                WHERE domain = ?
                ORDER BY id DESC LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT * FROM lead_conversions
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def today_leads_summary() -> dict:
    """Return aggregated lead conversion metrics for today."""
    with _conn() as con:
        row = con.execute(
            """
            SELECT COUNT(*) as total_leads, COALESCE(SUM(bounty_est), 0.0) as total_bounty
            FROM lead_conversions
            WHERE date(ts) = date('now') AND status = 'submitted'
            """
        ).fetchone()
    total = int(row["total_leads"]) if row else 0
    bounty = float(row["total_bounty"]) if row else 0.0
    return {
        "today_leads": total,
        "estimated_bounty": round(bounty, 2),
    }


def record_alert_log(
    alert_type: str,
    level: str,
    message: str,
    domain: str = "",
    sent_live: bool = False,
) -> int:
    """Record an alert notification event in alert_logs."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO alert_logs (alert_type, level, domain, message, sent_live)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert_type, level, domain, message, 1 if sent_live else 0),
        )
        return int(cur.lastrowid)


def get_recent_alerts(limit: int = 25) -> list[dict]:
    """Retrieve recent alert notifications."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM alert_logs
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_alert_summary_today() -> dict:
    """Return count of alerts by level for today."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT level, COUNT(*) as count
            FROM alert_logs
            WHERE date(ts) = date('now')
            GROUP BY level
            """
        ).fetchall()
    counts = {r["level"]: r["count"] for r in rows}
    return {
        "INFO": counts.get("INFO", 0),
        "WARNING": counts.get("WARNING", 0),
        "CRITICAL": counts.get("CRITICAL", 0),
        "SUCCESS": counts.get("SUCCESS", 0),
        "total": sum(counts.values()),
    }


def record_ecpm_snapshot(snapshots: list[dict]) -> None:
    """Insert domain eCPM and weight snapshots into ecpm_history (Step 4.2)."""
    with _conn() as con:
        for s in snapshots:
            con.execute(
                """
                INSERT INTO ecpm_history (domain, ecpm, impressions, revenue, weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    s.get("domain", "").lower().strip(),
                    float(s.get("ecpm", 0.0)),
                    int(s.get("impressions", 0)),
                    float(s.get("revenue", 0.0)),
                    float(s.get("weight", 1.0)),
                ),
            )


def get_latest_ecpm_weights() -> dict[str, float]:
    """Return dictionary of {domain: weight} from the most recent ecpm_history entries."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT domain, weight FROM ecpm_history
            WHERE id IN (
                SELECT MAX(id) FROM ecpm_history GROUP BY domain
            )
            """
        ).fetchall()
    return {r["domain"]: float(r["weight"]) for r in rows}


def get_daily_revenue_history(days: int = 30, fallback_cpm: float = 2.50) -> list[dict]:
    """
    Step 5.5: Return daily revenue breakdown for the last N days.
    Combines daily impressions (multiplied by actual or estimated CPM) with CPA conversion payouts.
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT d.date,
                   d.sessions,
                   d.impressions,
                   d.ad_clicks,
                   COALESCE(
                       (SELECT SUM(a.api_revenue) FROM adsterra_api_sync a WHERE a.date = d.date),
                       (d.impressions * ? / 1000.0)
                   ) AS ad_revenue,
                   COALESCE(
                       (SELECT SUM(c.payout_usd) FROM cpa_conversions c WHERE DATE(c.ts) = d.date AND c.status != 'rejected'),
                       0.0
                   ) AS cpa_revenue
            FROM daily_stats d
            WHERE d.date >= DATE('now', ?)
            ORDER BY d.date ASC
            """,
            (fallback_cpm, f"-{days} days"),
        ).fetchall()

    history = []
    for r in rows:
        ad_rev = float(r["ad_revenue"] or 0.0)
        cpa_rev = float(r["cpa_revenue"] or 0.0)
        history.append({
            "date": str(r["date"]),
            "sessions": int(r["sessions"] or 0),
            "impressions": int(r["impressions"] or 0),
            "ad_clicks": int(r["ad_clicks"] or 0),
            "ad_revenue": round(ad_rev, 4),
            "cpa_revenue": round(cpa_rev, 4),
            "total_revenue": round(ad_rev + cpa_rev, 4),
        })
    return history


def record_competitor_intel(
    url: str,
    domain: str,
    detected_networks: list[str] | str,
    ad_unit_count: int,
    word_count: int,
    ad_density: float,
    top_keywords: list[str] | str,
) -> int:
    """Record competitor ad intelligence analysis into SQLite."""
    import json
    init()
    net_str = json.dumps(detected_networks) if isinstance(detected_networks, list) else str(detected_networks)
    kw_str = json.dumps(top_keywords) if isinstance(top_keywords, list) else str(top_keywords)

    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO competitor_intel (url, domain, detected_networks, ad_unit_count, word_count, ad_density, top_keywords, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (url, domain, net_str, ad_unit_count, word_count, ad_density, kw_str),
        )
        return int(cur.lastrowid or 0)


def get_competitor_intel(limit: int = 10) -> list[dict]:
    """Retrieve recent competitor intelligence records."""
    import json
    init()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT id, url, domain, detected_networks, ad_unit_count, word_count, ad_density, top_keywords, scanned_at
            FROM competitor_intel
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    out = []
    for r in rows:
        try:
            nets = json.loads(r["detected_networks"])
        except Exception:
            nets = [r["detected_networks"]]
        try:
            kws = json.loads(r["top_keywords"])
        except Exception:
            kws = [r["top_keywords"]]
        out.append({
            "id": r["id"],
            "url": r["url"],
            "domain": r["domain"],
            "detected_networks": nets,
            "ad_unit_count": r["ad_unit_count"],
            "word_count": r["word_count"],
            "ad_density": round(float(r["ad_density"] or 0.0), 2),
            "top_keywords": kws,
            "scanned_at": r["scanned_at"],
        })
    return out








def log_published_post(
    domain: str,
    title: str,
    slug: str,
    file_path: str,
    word_count: int,
    ai_score: float,
    url: str,
) -> int:
    """Log a published article to database."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO published_posts
                (domain, title, slug, file_path, word_count, ai_score, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (domain, title, slug, file_path, word_count, ai_score, url),
        )
        return cur.lastrowid or 0


def get_published_count_today(domain: str = "") -> int:
    """Count articles published today (IST) for a domain or all domains."""
    with _conn() as con:
        if domain:
            row = con.execute(
                """
                SELECT COUNT(*) as c FROM published_posts
                WHERE domain = ? AND date(published_at) = date('now', '+5 hours', '30 minutes')
                """,
                (domain,),
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT COUNT(*) as c FROM published_posts
                WHERE date(published_at) = date('now', '+5 hours', '30 minutes')
                """
            ).fetchone()
        return int(row["c"]) if row else 0


def get_latest_published_posts(domain: str = "", limit: int = 5) -> list[dict]:
    """Retrieve the latest published articles."""
    with _conn() as con:
        if domain:
            rows = con.execute(
                """
                SELECT id, domain, title, slug, file_path, word_count, ai_score, url, published_at
                FROM published_posts
                WHERE domain = ?
                ORDER BY published_at DESC LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT id, domain, title, slug, file_path, word_count, ai_score, url, published_at
                FROM published_posts
                ORDER BY published_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def archive_old_sessions(retention_days: int = 30, archive_dir: str | Path | None = None) -> dict[str, Any]:
    """
    INFRA-3: Monthly archive rotation for sessions.db.
    Moves records older than retention_days into an archive database in archive_dir.
    Runs PRAGMA incremental_vacuum on the active database.
    """
    import datetime
    import sqlite3

    if archive_dir is None:
        target_dir = Path(__file__).parent / "archives"
    else:
        target_dir = Path(archive_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    month_str = datetime.datetime.now().strftime("%Y_%m")
    archive_db_path = target_dir / f"sessions_archive_{month_str}.db"

    cutoff_ts = (datetime.datetime.now() - datetime.timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")

    archived_count = 0
    with _conn() as con:
        rows = con.execute("SELECT * FROM sessions WHERE ts < ?", (cutoff_ts,)).fetchall()
        if rows:
            arch_con = sqlite3.connect(str(archive_db_path))
            try:
                cur = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'")
                create_sql = cur.fetchone()[0]
                arch_con.execute(create_sql)
            except Exception:
                pass

            cols = [desc[0] for desc in con.execute("SELECT * FROM sessions LIMIT 1").description]
            placeholders = ",".join(["?"] * len(cols))
            arch_con.executemany(
                f"INSERT OR REPLACE INTO sessions ({','.join(cols)}) VALUES ({placeholders})",
                [tuple(r) for r in rows]
            )
            arch_con.commit()
            arch_con.close()

            con.execute("DELETE FROM sessions WHERE ts < ?", (cutoff_ts,))
            archived_count = len(rows)

        try:
            con.execute("PRAGMA incremental_vacuum")
        except Exception:
            pass

    return {
        "archived_count": archived_count,
        "archive_path": str(archive_db_path),
        "cutoff_ts": cutoff_ts,
    }
