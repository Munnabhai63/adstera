# topic_intelligence.py — Aggressive 20-Topic Discovery & Top-5 High-CPC Winner Selection Engine
from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from network_registry import NETWORK_REGISTRY
from trends_fetcher import DOMAIN_NICHES, TrendsFetcher

DB_PATH = os.path.join("state", "autopublish.db")

# High-CPC & High Commercial Intent Keyword Multipliers (Fintech, Telecom, Banking, Commodities)
HIGH_CPC_KEYWORDS: Dict[str, int] = {
    # Finance & Loans (Highest AdSense/Adsterra CPC)
    "apply online": 24,
    "interest rate": 24,
    "lowest apr": 25,
    "eligibility criteria": 20,
    "instant cash": 22,
    "instant loan": 22,
    "personal loan": 22,
    "mudra loan": 22,
    "pmegp": 22,
    "msme": 18,
    "cibil score": 22,
    "zero processing fee": 22,
    "balance transfer": 22,
    "loan calculator": 18,
    "overdraft facility": 20,
    "subsidized loan": 20,
    "working capital": 20,
    "commercial vehicle": 22,
    "truck loan": 22,
    "tractor": 18,
    "foreclosure charges": 18,
    "settlement letter": 22,
    "lok adalat": 18,
    "ots settlement": 25,
    "credit card": 22,
    "credit card debt": 24,
    "consolidation": 20,
    "kisan credit card": 22,
    "gold loan": 22,
    "gold loan per gram": 24,
    # Telecom & Utilities
    "cashback offer": 20,
    "cashback": 18,
    "coupon promo code": 18,
    "prepaid plan": 18,
    "5g booster pack": 18,
    "unlimited data": 16,
    "electricity bill": 18,
    "smart meter": 18,
    "fastag": 20,
    "dth": 16,
    "direct benefit transfer": 18,
    "lpg cylinder subsidy": 18,
    "upi": 16,
    # Markets, Cards & Bullion
    "24k gold rate": 22,
    "gold rate today": 22,
    "silver price": 20,
    "mcx silver": 20,
    "sovereign gold bond": 22,
    "nifty": 18,
    "mutual fund": 20,
    "sip": 18,
    "fd rate": 20,
    "dividend": 18,
    "tax": 18,
}


def _connect_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_candidate_tables(db_path: Optional[str] = None) -> None:
    """Ensure candidate, queue, published, and pipeline state tables exist with Layer 7 columns."""
    conn = _connect_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS published_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            slug TEXT UNIQUE,
            title TEXT,
            category TEXT,
            words INTEGER,
            published_at TIMESTAMP,
            cf_deployed INTEGER DEFAULT 0,
            google_pinged INTEGER DEFAULT 0,
            quality_score REAL DEFAULT 100.0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            category TEXT,
            topic TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            priority_score REAL DEFAULT 0.0,
            created_at TIMESTAMP
        )
        """
    )
    _ensure_column(cur, "topic_queue", "priority_score", "priority_score REAL DEFAULT 0.0")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            topic TEXT,
            category TEXT,
            commercial_intent_score REAL,
            trend_velocity_score REAL,
            keyword_depth_score REAL,
            composite_score REAL,
            is_winner INTEGER DEFAULT 0,
            status TEXT DEFAULT 'candidate',
            created_at TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_state (
            domain TEXT PRIMARY KEY,
            current_stage INTEGER DEFAULT 1,
            stage_name TEXT,
            active_topic TEXT,
            words_written INTEGER DEFAULT 0,
            anti_ai_score REAL DEFAULT 0.0,
            status_message TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


init_candidate_tables()


def score_topic(topic: str, base_rank: int, trend_match: bool) -> Tuple[float, float, float, float]:
    """
    Aggressive 3-factor CPC & velocity evaluator:
    1. Commercial Intent (55% weight): prioritizes high-CPC buying/applying triggers.
    2. Trend Velocity (30% weight): search autocomplete rank + real-time trend match.
    3. Keyword Depth (15% weight): word specificity + regulator/bank entities + actionable verbs.
    Applies a multi-signal synergy boost and penalizes short vague queries.
    """
    t_lower = topic.lower()

    # 1. Commercial Intent
    comm_points = 25.0
    comm_hits = 0
    for phrase, pts in HIGH_CPC_KEYWORDS.items():
        if phrase in t_lower:
            comm_points += pts
            comm_hits += 1
    if comm_hits >= 2:
        comm_points += 10.0
    comm_score = min(100.0, comm_points)

    # 2. Trend Velocity
    trend_points = max(20.0, 92.0 - (base_rank * 3.0))
    if trend_match or "2026" in topic or "today" in t_lower or "live" in t_lower:
        trend_points += 15.0
    trend_score = min(100.0, trend_points)

    # 3. Keyword Depth
    word_count = len(topic.split())
    depth_points = 45.0
    if 6 <= word_count <= 15:
        depth_points += 25.0
    has_entity = any(
        m in topic
        for m in ["RBI", "SBI", "HDFC", "ICICI", "TRAI", "NPCI", "NABARD", "SEBI", "GST", "MCX", "RERA", "₹", "%"]
    )
    if has_entity:
        depth_points += 20.0
    if any(v in t_lower for v in ("vs", "compare", "guide", "calculator", "check", "apply", "claim", "rules")):
        depth_points += 10.0
    depth_score = min(100.0, depth_points)

    composite = (comm_score * 0.55) + (trend_score * 0.30) + (depth_score * 0.15)
    if comm_hits >= 1 and (has_entity or trend_match or "2026" in topic):
        composite += 8.0
    if comm_hits == 0 and word_count < 5:
        composite -= 15.0
    composite = max(1.0, min(100.0, round(composite, 1)))
    return round(comm_score, 1), round(trend_score, 1), round(depth_score, 1), composite


def _build_candidate_pool(
    domain_clean: str,
    existing_topics: Optional[set[str]] = None,
    fetch_live: bool = True,
) -> List[Tuple[str, int, bool]]:
    """Build up to 20 deduplicated high-intent candidates, avoiding already-queued topics."""
    niche_data = DOMAIN_NICHES.get(f"{domain_clean}.com", DOMAIN_NICHES["loanraaj.com"])
    seed_keywords = niche_data["keywords"]
    raw_candidates: List[Tuple[str, int, bool]] = []
    excluded_terms = [
        "sri lanka",
        "malaysia",
        "singapore",
        "pakistan",
        "bangladesh",
        "movie",
        "trailer",
        "song",
        "scorecard",
    ]
    finance_markers = [
        "loan",
        "bank",
        "gold",
        "silver",
        "stock",
        "tax",
        "cibil",
        "rbi",
        "budget",
        "jio",
        "airtel",
        "recharge",
        "upi",
        "credit",
        "market",
    ]

    if fetch_live:
        fetcher = TrendsFetcher(timeout=4.0)
        try:
            live_trends = fetcher.fetch_live_indian_trends_sync()
        except Exception:
            live_trends = []
        for idx, seed in enumerate(seed_keywords[:3]):
            try:
                suggestions = fetcher.fetch_suggest_queries_sync(seed)
            except Exception:
                suggestions = []
            for s_idx, sugg in enumerate(suggestions[:6]):
                if sugg and len(sugg.split()) >= 3:
                    sugg_lower = sugg.lower()
                    if not any(ex in sugg_lower for ex in excluded_terms):
                        raw_candidates.append((sugg, idx * 3 + s_idx, False))
        for t in live_trends:
            t_clean = t.strip()
            t_lower = t_clean.lower()
            if any(m in t_lower for m in finance_markers) and not any(ex in t_lower for ex in excluded_terms):
                raw_candidates.append((t_clean, 0, True))

    year = "2026"
    s0 = seed_keywords[0].title()
    s1 = seed_keywords[1 % len(seed_keywords)].title()
    s2 = seed_keywords[2 % len(seed_keywords)].title()
    s3 = seed_keywords[3 % len(seed_keywords)].title()
    high_cpc_templates = [
        f"{s0} {year}: Apply Online, Eligibility Criteria & Lowest APR Guide",
        f"How to Compare {s1} Interest Rate Slab & Zero Processing Fee ({year})",
        f"{s2} Complete Calculation, ₹ Charges & Fast Approval Checklist ({year})",
        f"SBI vs HDFC {s0}: Real Interest Rate, Cashback & Foreclosure Rules Compared",
        f"RBI Guidelines for {s1} in India: Step-by-Step Approval & Limits ({year})",
        f"{s3} {year}: Complete Documentation, Tax Rules & Direct Benefit Guide",
        f"Low CIBIL Score Options for {s0}: Eligibility Criteria & Settlement Impact",
        f"How to Claim Maximum Cashback & Fee Waiver on {s1} Online ({year})",
        f"{s2} Balance Transfer vs Top-Up Guide: Exact ₹ Annual Savings Math",
        f"Pre-Closure & Foreclosure Charges on {s0}: RBI & Bank Schedule ({year})",
        f"Step-by-Step Online Verification for {s3} with Instant Approval Status",
        f"Public vs Private Sector Benchmarks for {s1}: Effective APR & Rewards",
    ]
    for idx, fb in enumerate(high_cpc_templates):
        raw_candidates.append((fb, idx, True))

    seen = set(existing_topics or set())
    unique_candidates: List[Tuple[str, int, bool]] = []
    for cand, rank, is_tr in raw_candidates:
        c_title = cand.strip()
        if len(c_title) < 18:
            c_title = f"{c_title.title()} {year}: Interest Rate, Eligibility & Complete Guide"
        c_key = re.sub(r"[^a-z0-9]", "", c_title.lower()[:36])
        if c_key not in seen:
            seen.add(c_key)
            unique_candidates.append((c_title, rank, is_tr))
        if len(unique_candidates) >= 20:
            break
    return unique_candidates


def sync_winners_to_queue(
    domain_clean: str,
    winners: List[Dict[str, Any]],
    db_path: Optional[str] = None,
) -> int:
    """Push Top-5 aggressive winners into topic_queue with priority_score without duplicating."""
    if not winners:
        return 0
    init_candidate_tables(db_path)
    conn = _connect_db(db_path)
    cur = conn.cursor()
    existing_keys = {
        re.sub(r"[^a-z0-9]", "", str(r[0]).lower()[:36])
        for r in cur.execute("SELECT topic FROM topic_queue WHERE domain = ?", (domain_clean,)).fetchall()
        if r[0]
    }
    now_iso = datetime.now().isoformat()
    inserted = 0
    for w in winners:
        topic = str(w.get("topic") or "").strip()
        if not topic:
            continue
        t_key = re.sub(r"[^a-z0-9]", "", topic.lower()[:36])
        score = float(w.get("composite_score", 0.0) or 0.0)
        if t_key in existing_keys:
            cur.execute(
                "UPDATE topic_queue SET priority_score = MAX(COALESCE(priority_score, 0), ?) WHERE domain = ? AND topic = ? AND status = 'pending'",
                (score, domain_clean, topic),
            )
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO topic_queue (domain, category, topic, status, priority_score, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (domain_clean, w.get("category", "General"), topic, score, now_iso),
        )
        if cur.rowcount > 0:
            inserted += 1
            existing_keys.add(t_key)
    conn.commit()
    conn.close()
    return inserted


def discover_20_topics_for_domain(
    domain: str,
    min_winner_score: float = 65.0,
    sync_to_queue: bool = True,
    fetch_live: bool = True,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate a 20-topic pool for `domain`, apply aggressive Top-5 CPC scoring,
    store candidates in `topic_candidates`, update `pipeline_state`, and enqueue winners.
    """
    domain_clean = domain.replace(".com", "").strip().lower()
    init_candidate_tables(db_path)

    conn = _connect_db(db_path)
    cur = conn.cursor()
    existing_keys = {
        re.sub(r"[^a-z0-9]", "", str(r[0]).lower()[:36])
        for r in cur.execute(
            "SELECT topic FROM topic_queue WHERE domain = ? AND status IN ('published', 'processing')",
            (domain_clean,),
        ).fetchall()
        if r[0]
    }
    conn.close()

    unique_candidates = _build_candidate_pool(domain_clean, existing_topics=existing_keys, fetch_live=fetch_live)
    site_meta = NETWORK_REGISTRY.get(domain_clean, {})
    cat_keys = list(site_meta.get("categories", {}).keys()) or ["General"]

    scored_pool: List[Dict[str, Any]] = []
    for i, (topic, rank, is_tr) in enumerate(unique_candidates):
        comm, trend, depth, composite = score_topic(topic, rank, is_tr)
        scored_pool.append(
            {
                "domain": domain_clean,
                "topic": topic,
                "category": cat_keys[i % len(cat_keys)],
                "commercial_intent_score": comm,
                "trend_velocity_score": trend,
                "keyword_depth_score": depth,
                "composite_score": composite,
                "is_winner": 0,
                "status": "candidate",
            }
        )

    # Aggressive ranking: composite -> commercial intent -> trend velocity
    scored_pool.sort(
        key=lambda x: (x["composite_score"], x["commercial_intent_score"], x["trend_velocity_score"]),
        reverse=True,
    )

    winners: List[Dict[str, Any]] = []
    qualified = [c for c in scored_pool if c["composite_score"] >= min_winner_score]
    pick_source = qualified if len(qualified) >= 5 else scored_pool
    for cand in pick_source[: min(5, len(pick_source))]:
        cand["is_winner"] = 1
        cand["status"] = "winner_selected"
        winners.append(cand)

    conn = _connect_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM topic_candidates WHERE domain = ?", (domain_clean,))
    now_iso = datetime.now(timezone.utc).isoformat()
    for c in scored_pool:
        cur.execute(
            """
            INSERT INTO topic_candidates
            (domain, topic, category, commercial_intent_score, trend_velocity_score, keyword_depth_score, composite_score, is_winner, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["domain"],
                c["topic"],
                c["category"],
                c["commercial_intent_score"],
                c["trend_velocity_score"],
                c["keyword_depth_score"],
                c["composite_score"],
                c["is_winner"],
                c["status"],
                now_iso,
            ),
        )

    top_winner = winners[0]["topic"] if winners else (scored_pool[0]["topic"] if scored_pool else "N/A")
    cur.execute(
        """
        INSERT INTO pipeline_state (domain, current_stage, stage_name, active_topic, status_message, updated_at)
        VALUES (?, 2, 'Aggressive Top-5 CPC Selection', ?, ?, ?)
        ON CONFLICT(domain) DO UPDATE SET
            current_stage = 2,
            stage_name = 'Aggressive Top-5 CPC Selection',
            active_topic = ?,
            status_message = ?,
            updated_at = ?
        """,
        (
            domain_clean,
            top_winner,
            f"Aggressive Top-{len(winners)} high-CPC winners ready (top score {winners[0]['composite_score'] if winners else 0})",
            now_iso,
            top_winner,
            f"Aggressive Top-{len(winners)} high-CPC winners ready (top score {winners[0]['composite_score'] if winners else 0})",
            now_iso,
        ),
    )
    conn.commit()
    conn.close()

    if sync_to_queue and winners:
        sync_winners_to_queue(domain_clean, winners, db_path=db_path)

    return scored_pool


def update_pipeline_stage(
    domain: str,
    stage_num: int,
    stage_name: str,
    active_topic: str,
    status_message: str,
    words_written: Optional[int] = None,
    anti_ai_score: Optional[float] = None,
    db_path: Optional[str] = None,
) -> None:
    """Persist live stage progress for a domain in `pipeline_state`."""
    domain_clean = domain.replace(".com", "").strip().lower()
    init_candidate_tables(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _connect_db(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT words_written, anti_ai_score FROM pipeline_state WHERE domain = ?",
        (domain_clean,),
    )
    prev = cur.fetchone()
    prev_words = int(prev[0]) if prev and prev[0] is not None else 0
    prev_score = float(prev[1]) if prev and prev[1] is not None else 0.0
    final_words = int(words_written) if words_written is not None else prev_words
    final_score = float(anti_ai_score) if anti_ai_score is not None else prev_score
    cur.execute(
        """
        INSERT INTO pipeline_state
        (domain, current_stage, stage_name, active_topic, words_written, anti_ai_score, status_message, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(domain) DO UPDATE SET
            current_stage = excluded.current_stage,
            stage_name = excluded.stage_name,
            active_topic = excluded.active_topic,
            words_written = excluded.words_written,
            anti_ai_score = excluded.anti_ai_score,
            status_message = excluded.status_message,
            updated_at = excluded.updated_at
        """,
        (domain_clean, int(stage_num), stage_name, active_topic, final_words, final_score, status_message, now_iso),
    )
    conn.commit()
    conn.close()


def _is_stale_iso(ts_str: Optional[str], stale_minutes: int) -> bool:
    if not ts_str:
        return True
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) >= timedelta(minutes=stale_minutes)
    except Exception:
        return True


def kick_stuck_pipelines(
    stale_minutes: int = 30,
    target_domains: Optional[List[str]] = None,
    min_pending_per_domain: int = 3,
    aggressive_winners_count: int = 5,
    min_winner_score: float = 65.0,
    fetch_live: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detect and unstick domains frozen in `pipeline_state` (e.g. tazaloan, loankiseva),
    rescue stale 'processing' rows, and push Top-5 aggressive winners into `topic_queue`.
    """
    init_candidate_tables(db_path)
    conn = _connect_db(db_path)
    cur = conn.cursor()

    # 1. Rescue any topic_queue items stranded in 'processing' when kicking stuck domains
    cur.execute("SELECT id, domain FROM topic_queue WHERE status = 'processing'")
    processing_rows = cur.fetchall()
    rescued_processing = 0
    if processing_rows:
        cur.execute("UPDATE topic_queue SET status = 'pending' WHERE status = 'processing'")
        rescued_processing = cur.rowcount

    # 2. Gather current pending counts and pipeline_state across all registered domains
    pending_counts = dict(
        cur.execute("SELECT domain, COUNT(*) FROM topic_queue WHERE status = 'pending' GROUP BY domain").fetchall()
    )
    pipeline_rows = {
        r[0]: {
            "stage": r[1],
            "stage_name": r[2],
            "active_topic": r[3],
            "words_written": r[4] or 0,
            "updated_at": r[7],
        }
        for r in cur.execute("SELECT * FROM pipeline_state").fetchall()
    }
    conn.commit()
    conn.close()

    forced_targets = {d.replace(".com", "").strip().lower() for d in (target_domains or [])}
    all_domains = list(NETWORK_REGISTRY.keys())
    kicked_domains: List[str] = []
    winners_queued = 0

    for dom in all_domains:
        p_info = pipeline_rows.get(dom)
        pend = int(pending_counts.get(dom, 0))
        is_explicit = dom in forced_targets
        is_starved = pend < min_pending_per_domain
        is_stuck_stage = bool(
            p_info
            and (
                (int(p_info["stage"] or 0) <= 4 and _is_stale_iso(p_info["updated_at"], stale_minutes))
                or ("Top-5" in str(p_info["stage_name"] or "") and int(p_info["words_written"] or 0) == 0)
            )
        )
        if not (is_explicit or is_starved or is_stuck_stage or p_info is None):
            continue

        # Promote existing aggressive winners first, or re-score locally if needed
        existing_cands = get_candidates_for_domain(dom, db_path=db_path, fetch_live=fetch_live)
        top_winners = [c for c in existing_cands if c.get("is_winner") == 1][:aggressive_winners_count]
        added = sync_winners_to_queue(dom, top_winners, db_path=db_path)

        # Re-check pending after syncing cached winners; replenish aggressively if still starved
        conn = _connect_db(db_path)
        pend_after = conn.execute(
            "SELECT COUNT(*) FROM topic_queue WHERE domain = ? AND status = 'pending'",
            (dom,),
        ).fetchone()[0]
        conn.close()

        if pend_after < min_pending_per_domain:
            fresh = discover_20_topics_for_domain(
                dom,
                min_winner_score=min_winner_score,
                sync_to_queue=True,
                fetch_live=fetch_live,
                db_path=db_path,
            )
            fresh_winners = [c for c in fresh if c.get("is_winner") == 1][:aggressive_winners_count]
            added += sync_winners_to_queue(dom, fresh_winners, db_path=db_path)

        winners_queued += added

        # Update pipeline_state to Queued for Fast-Track Publish with the highest-priority pending topic
        conn = _connect_db(db_path)
        top_row = conn.execute(
            "SELECT topic FROM topic_queue WHERE domain = ? AND status = 'pending' ORDER BY COALESCE(priority_score, 0) DESC, id ASC LIMIT 1",
            (dom,),
        ).fetchone()
        new_pend = conn.execute(
            "SELECT COUNT(*) FROM topic_queue WHERE domain = ? AND status = 'pending'",
            (dom,),
        ).fetchone()[0]
        conn.close()

        active_topic = top_row[0] if top_row else (p_info["active_topic"] if p_info else "Fast-Track CPC Topic")
        update_pipeline_stage(
            domain=dom,
            stage_num=2,
            stage_name="Queued for Fast-Track Publish",
            active_topic=active_topic,
            status_message=f"Kicked unstuck -> {new_pend} pending aggressive CPC topics ready",
            db_path=db_path,
        )
        pending_counts[dom] = new_pend
        kicked_domains.append(dom)

    return {
        "kicked_domains": kicked_domains,
        "kicked_count": len(kicked_domains),
        "rescued_processing": rescued_processing,
        "winners_queued": winners_queued,
        "pending_by_domain": pending_counts,
    }


def get_candidates_for_domain(
    domain: str,
    db_path: Optional[str] = None,
    fetch_live: bool = True,
) -> List[Dict[str, Any]]:
    """Retrieve scored 20 candidates for a domain from SQLite."""
    domain_clean = domain.replace(".com", "").strip().lower()
    init_candidate_tables(db_path)
    conn = _connect_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, domain, topic, category, commercial_intent_score, trend_velocity_score, keyword_depth_score, composite_score, is_winner, status
        FROM topic_candidates
        WHERE domain = ?
        ORDER BY composite_score DESC, commercial_intent_score DESC
        """,
        (domain_clean,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return discover_20_topics_for_domain(domain_clean, fetch_live=fetch_live, db_path=db_path)

    return [
        {
            "id": r[0],
            "domain": r[1],
            "topic": r[2],
            "category": r[3],
            "commercial_intent_score": r[4],
            "trend_velocity_score": r[5],
            "keyword_depth_score": r[6],
            "composite_score": r[7],
            "is_winner": r[8],
            "status": r[9],
        }
        for r in rows
    ]


if __name__ == "__main__":
    print("[Testing] Discovering 20 aggressive topics for 'tazaloan'...")
    pool = discover_20_topics_for_domain("tazaloan", fetch_live=False)
    print(f"Discovered {len(pool)} topics. Aggressive Top 5 Winners:")
    for idx, t in enumerate(pool[:5]):
        print(f" #{idx+1} [Score: {t['composite_score']} | CPC: {t['commercial_intent_score']}] {t['topic']}")
