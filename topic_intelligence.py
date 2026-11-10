# topic_intelligence.py — 20-Topic Discovery & Top-5 High-CPC Winner Selection Engine
import os
import sys
import re
import json
import sqlite3
import random
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from trends_fetcher import DOMAIN_NICHES, TrendsFetcher
from network_registry import NETWORK_REGISTRY
from autopublish_engine import query_freellmapi

DB_PATH = os.path.join("state", "autopublish.db")

# High-CPC & High Commercial Intent Keyword Multipliers (Fintech, Telecom, Banking, Commodities)
HIGH_CPC_KEYWORDS = {
    # Finance & Loans (Highest AdSense/Adsterra CPC)
    "apply online": 25, "interest rate": 25, "lowest apr": 25, "eligibility criteria": 20,
    "instant cash": 22, "cibil score": 20, "zero processing fee": 22, "loan calculator": 18,
    "overdraft facility": 20, "subsidized loan": 20, "working capital": 20, "commercial vehicle": 22,
    "foreclosure charges": 18, "settlement letter": 22, "lok adalat": 18, "ots settlement": 25,
    "credit card debt": 22, "consolidation": 20, "kisan credit card": 22, "gold loan per gram": 22,
    # Telecom & Utilities
    "cashback offer": 18, "coupon promo code": 18, "5g booster pack": 18, "unlimited data": 15,
    "electricity bill rebate": 18, "smart meter billing": 18, "fastag toll refund": 20,
    "multi-room dth pack": 16, "direct benefit transfer": 18, "lpg cylinder subsidy": 18,
    # Markets & Bullion
    "24k gold rate today": 22, "mcx silver contract": 20, "sovereign gold bond": 22,
    "nifty index fund sip": 22, "high dividend yield": 20, "ltcg tax harvesting": 22
}

def init_candidate_tables():
    """Ensure candidate topics and pipeline state tables exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    conn.commit()
    conn.close()

init_candidate_tables()

def score_topic(topic: str, base_rank: int, trend_match: bool) -> Tuple[float, float, float, float]:
    """
    Evaluates a candidate topic across 3 factors:
    1. Commercial Intent Score (1-100): High-CPC buying/applying triggers.
    2. Trend Velocity Score (1-100): Rank order in Google Suggest + Google Trends boost.
    3. Keyword Depth Score (1-100): Specificity, length, presence of current year/regulator.
    Composite = (Commercial * 0.45) + (Trend * 0.35) + (Depth * 0.20)
    """
    t_lower = topic.lower()
    
    # 1. Commercial Intent
    comm_points = 30.0  # Base score
    for phrase, pts in HIGH_CPC_KEYWORDS.items():
        if phrase in t_lower:
            comm_points += pts
    comm_score = min(100.0, comm_points)
    
    # 2. Trend Velocity
    # Earlier rank in suggest query means higher real search volume
    trend_points = max(20.0, 95.0 - (base_rank * 3.5))
    if trend_match or "2026" in topic or "today" in t_lower:
        trend_points += 15.0
    trend_score = min(100.0, trend_points)
    
    # 3. Keyword Depth
    word_count = len(topic.split())
    depth_points = 50.0
    if 6 <= word_count <= 14:
        depth_points += 25.0
    if any(m in topic for m in ["RBI", "SBI", "HDFC", "TRAI", "NPCI", "GST", "MCX", "₹"]):
        depth_points += 20.0
    depth_score = min(100.0, depth_points)
    
    composite = round((comm_score * 0.45) + (trend_score * 0.35) + (depth_score * 0.20), 1)
    return round(comm_score, 1), round(trend_score, 1), round(depth_score, 1), composite

def discover_20_topics_for_domain(domain: str) -> List[Dict[str, Any]]:
    """
    Generates a pool of 20 high-value candidate topics for the domain,
    scores each one with our 3-factor matrix, selects the Top 5 WINNERS,
    and records them into the SQLite database.
    """
    domain_clean = domain.replace(".com", "")
    fetcher = TrendsFetcher()
    
    # 1. Fetch live trends from Google Trends India
    live_trends = fetcher.fetch_live_indian_trends_sync()
    
    # 2. Get domain niche keywords
    niche_data = DOMAIN_NICHES.get(f"{domain_clean}.com", DOMAIN_NICHES["loanraaj.com"])
    seed_keywords = niche_data["keywords"]
    niche_label = niche_data["niche"]
    
    raw_candidates = []
    
    # Filter out irrelevant international queries or pure entertainment queries
    EXCLUDED_TERMS = ["sri lanka", "malaysia", "singapore", "pakistan", "bangladesh", "movie", "trailer", "song", "scorecard", "vs "]
    
    # Generate Google Autocomplete queries across domain seeds
    for idx, seed in enumerate(seed_keywords):
        suggestions = fetcher.fetch_suggest_queries_sync(seed)
        for s_idx, sugg in enumerate(suggestions[:6]):
            if sugg and len(sugg.split()) >= 3:
                sugg_lower = sugg.lower()
                if not any(ex in sugg_lower for ex in EXCLUDED_TERMS):
                    raw_candidates.append((sugg, idx * 3 + s_idx, False))
                
    # If any live trend from Google Trends India specifically relates to finance/tech/telecom/business, add it
    FINANCE_MARKERS = ["loan", "bank", "gold", "silver", "stock", "tax", "cibil", "rbi", "budget", "jio", "airtel", "recharge", "upi", "credit", "market"]
    for t in live_trends:
        t_clean = t.strip()
        t_lower = t_clean.lower()
        if any(m in t_lower for m in FINANCE_MARKERS) and not any(ex in t_lower for ex in EXCLUDED_TERMS):
            raw_candidates.append((t_clean, 0, True))
            
    # Guarantee at least 25 formatted candidates to pick the best 20
    year = "2026"
    fallback_templates = [
        f"{seed_keywords[0].title()} {year}: Online Application, Documents & Approval Limits",
        f"How to Compare {seed_keywords[1].title()} with Lowest APR & Zero Hidden Charges",
        f"{seed_keywords[2].title()}: Complete Interest Rate Slab & Repayment Schedule ({year})",
        f"Best Alternatives for {seed_keywords[0].title()} for Self-Employed & Salaried in India",
        f"Avoiding High Penalties on {seed_keywords[1].title()}: RBI Rules & Borrower Rights",
        f"{seed_keywords[0].title()} vs Bank Overdraft: Which Offers More Working Liquidity?",
        f"Instant Eligibility Check for {seed_keywords[2].title()} with Direct Bank Disbursal",
        f"Step-by-Step Guide to Claim Maximum Benefits on {seed_keywords[1].title()} ({year})",
        f"{seed_keywords[0].title()} for Low CIBIL Score Borrowers: Verified RBI Guidelines",
        f"Emergency Cash Needs: How to Fast-Track {seed_keywords[2].title()} Online",
        f"Top 5 Public vs Private Scheduled Banks for {seed_keywords[1].title()} Compared",
        f"Understanding Pre-Closure & Foreclosure Charges for {seed_keywords[0].title()}"
    ]
    for fb in fallback_templates:
        raw_candidates.append((fb, 3, True))
        
    # Deduplicate and trim to 20 unique high-quality candidate topics
    seen = set()
    unique_candidates = []
    for cand, rank, is_tr in raw_candidates:
        c_title = cand.strip()
        if len(c_title) < 15:
            # Expand short query into an editorial title
            c_title = f"{c_title.title()} {year}: Complete Step-by-Step Guide & Eligibility"
        c_key = re.sub(r'[^a-z0-9]', '', c_title.lower()[:30])
        if c_key not in seen:
            seen.add(c_key)
            unique_candidates.append((c_title, rank, is_tr))
        if len(unique_candidates) >= 20:
            break
            
    # Score each of the 20 topics
    scored_pool = []
    site_meta = NETWORK_REGISTRY.get(domain_clean, {})
    cat_keys = list(site_meta.get("categories", {}).keys()) or ["General"]
    
    for i, (topic, rank, is_tr) in enumerate(unique_candidates):
        comm, trend, depth, composite = score_topic(topic, rank, is_tr)
        category = cat_keys[i % len(cat_keys)]
        scored_pool.append({
            "domain": domain_clean,
            "topic": topic,
            "category": category,
            "commercial_intent_score": comm,
            "trend_velocity_score": trend,
            "keyword_depth_score": depth,
            "composite_score": composite,
            "is_winner": 0,
            "status": "candidate"
        })
        
    # Sort pool descending by composite_score
    scored_pool.sort(key=lambda x: x["composite_score"], reverse=True)
    
    # Mark Top 5 as WINNERS!
    for i in range(min(5, len(scored_pool))):
        scored_pool[i]["is_winner"] = 1
        scored_pool[i]["status"] = "winner_selected"
        
    # Save to SQLite topic_candidates
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Clear previous candidates for this domain to keep it fresh
    cur.execute("DELETE FROM topic_candidates WHERE domain = ?", (domain_clean,))
    now_iso = datetime.now(timezone.utc).isoformat()
    for c in scored_pool:
        cur.execute("""
        INSERT INTO topic_candidates 
        (domain, topic, category, commercial_intent_score, trend_velocity_score, keyword_depth_score, composite_score, is_winner, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c["domain"], c["topic"], c["category"], 
            c["commercial_intent_score"], c["trend_velocity_score"], c["keyword_depth_score"], 
            c["composite_score"], c["is_winner"], c["status"], now_iso
        ))
        
    # Update pipeline_state table
    top_winner = scored_pool[0]["topic"] if scored_pool else "N/A"
    cur.execute("""
    INSERT INTO pipeline_state (domain, current_stage, stage_name, active_topic, status_message, updated_at)
    VALUES (?, 2, 'Top-5 CPC Selection', ?, 'Top 5 high-cpc winners selected out of 20 pool', ?)
    ON CONFLICT(domain) DO UPDATE SET
        current_stage = 2,
        stage_name = 'Top-5 CPC Selection',
        active_topic = ?,
        status_message = 'Top 5 high-cpc winners selected out of 20 pool',
        updated_at = ?
    """, (domain_clean, top_winner, now_iso, top_winner, now_iso))
    
    conn.commit()
    conn.close()
    
    return scored_pool

def get_candidates_for_domain(domain: str) -> List[Dict[str, Any]]:
    """Retrieve scored 20 candidates for a domain from SQLite."""
    domain_clean = domain.replace(".com", "")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT id, domain, topic, category, commercial_intent_score, trend_velocity_score, keyword_depth_score, composite_score, is_winner, status
    FROM topic_candidates
    WHERE domain = ?
    ORDER BY composite_score DESC
    """, (domain_clean,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        # Discover and populate if empty
        return discover_20_topics_for_domain(domain_clean)
        
    return [{
        "id": r[0],
        "domain": r[1],
        "topic": r[2],
        "category": r[3],
        "commercial_intent_score": r[4],
        "trend_velocity_score": r[5],
        "keyword_depth_score": r[6],
        "composite_score": r[7],
        "is_winner": r[8],
        "status": r[9]
    } for r in rows]

if __name__ == "__main__":
    print("[Testing] Discovering 20 topics for 'tazaloan'...")
    pool = discover_20_topics_for_domain("tazaloan")
    print(f"Discovered {len(pool)} topics. Top 5 Winners:")
    for idx, t in enumerate(pool[:5]):
        print(f" #{idx+1} [Score: {t['composite_score']} | CPC: {t['commercial_intent_score']}] {t['topic']}")
