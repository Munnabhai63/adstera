"""
trends_harvester.py — Tier-1 & Global Multi-Geo Google Trends & Real-Time Keyword Harvester
=============================================================================================
Powered by:
  1. Google Trends Daily RSS (geo=US, geo=CA, geo=GB, geo=AU, geo=IN)
  2. Google Search Autocomplete API (Live Tier-1 & Worldwide Commercial Intent)
  3. Public-APIs Zero-Auth Currency Engine (Frankfurter live Forex rates)

Automatically harvests, filters, classifies, and populates `topic_queue` in
`state/autopublish.db` across all 10 network domains with 100% hands-free automation.
"""

from __future__ import annotations
import os
import re
import sys
import time
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
import httpx

DB_PATH = os.path.join("state", "autopublish.db")

# 1. TIER-1 + GLOBAL GEOS
GEOS = ["US", "CA", "GB", "AU", "IN"]

# 2. COMMERCIAL INTENT SEED KEYWORDS BY DOMAIN (Tier-1 + Global Focus)
DOMAIN_SEEDS: dict[str, dict[str, Any]] = {
    "karzseva": {
        "category": "Debt Relief",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "credit card debt relief programs",
            "debt settlement vs bankruptcy pros and cons",
            "hardship debt management program eligibility",
            "medical debt forgiveness act rules",
            "how to dispute charge off with credit bureaus",
            "unsecured loan settlement letter template",
        ]
    },
    "loanraaj": {
        "category": "Business",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "commercial vehicle financing interest rates",
            "semi truck leasing with bad credit",
            "small business fleet financing calculator",
            "sba 7a working capital loan requirements",
            "equipment leasing vs commercial bank loan",
            "commercial box truck loan tax deduction section 179",
        ]
    },
    "tazaloan": {
        "category": "Instant Cash",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "best low apr personal loans",
            "emergency cash loans no hard credit check",
            "debt consolidation loan calculator low interest",
            "unsecured personal installment loan approval rate",
            "online personal loan interest rate comparison",
        ]
    },
    "rechargetak": {
        "category": "5G & Broadband",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "best esim for international travel and roaming",
            "t-mobile vs verizon vs at&t 5g home internet",
            "unlimited mobile hotspot plans no throttling",
            "cheapest prepaid wireless mvno plans",
            "5g stand alone vs non stand alone network speeds",
        ]
    },
    "rechargekar": {
        "category": "Family Telecom",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "wifi 7 router vs wifi 6e real world speed comparison",
            "fiber optic internet provider prices per month",
            "mesh wifi system for multi story home coverage",
            "gigabit fiber broadband upload vs download latency",
            "best streaming bundle deals with home internet",
        ]
    },
    "rechargepur": {
        "category": "Electricity & Gas",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "residential clean energy solar tax credit eligibility",
            "heat pump rebate program inflation reduction act",
            "smart thermostat electricity bill savings percentage",
            "time of use electricity rates peak hours guide",
            "smart electric meter net metering compensation",
        ]
    },
    "tazarokda": {
        "category": "Tax & Wealth",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "best high yield savings account hysa rates",
            "sp 500 index fund vs dividend aristocrat etfs",
            "roth ira contribution limit and income ceiling",
            "treasury bill yields vs certificate of deposit cd",
            "zero fee index funds long term compound growth",
        ]
    },
    "tazabhav": {
        "category": "Gold & Bullion",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "spot gold xau usd price forecast interest rate cuts",
            "silver bullion spot price vs physical coin premium",
            "central bank gold reserve buying trends",
            "gold etf vs physical gold bars storage costs",
            "crude oil brent spot price inflation hedge",
        ]
    },
    "loankiseva": {
        "category": "MSME Schemes",
        "geo_focus": ["US", "CA", "GB", "IN"],
        "seeds": [
            "small business grants for women and minority founders",
            "startup equipment financing zero down payment",
            "commercial working capital revolving credit line",
            "government technology grant application checklist",
        ]
    },
    "loantau": {
        "category": "Tractor & Agri",
        "geo_focus": ["US", "CA", "AU", "IN"],
        "seeds": [
            "farm tractor equipment financing interest rates",
            "agricultural solar pump subsidy eligibility",
            "rural business development grant usda guidelines",
            "farm operating loan low interest repayment terms",
        ]
    },
}

# 3. JUNK / ENTERTAINMENT FILTER
JUNK_KEYWORDS = {
    "movie", "trailer", "box office", "actor", "actress", "celebrity", "dating",
    "divorce", "gossip", "cricket", "ipl", "match score", "highlights", "football",
    "soccer", "premier league", "nba", "nfl score", "concert", "singer", "album",
    "grammy", "oscar", "horoscope", "astrology", "viral video", "tiktok drama",
    "murder", "shooting", "stabbing", "arrested", "gta vi", "leak", "cheat codes"
}

COMMERCIAL_TERMS = {
    "loan", "credit", "rate", "interest", "finance", "debt", "recharge", "5g",
    "fiber", "broadband", "wifi", "router", "bill", "electricity", "solar",
    "tax", "rebate", "subsidy", "gold", "bullion", "silver", "savings", "hysa",
    "invest", "etf", "stock", "fund", "grant", "tractor", "equipment", "bank",
    "settlement", "inflation", "mortgage", "esim", "mobile", "tariff", "apr"
}


def get_live_forex_rates() -> dict[str, float]:
    """Fetch live Tier-1 forex rates from Frankfurter API (zero-auth public API)."""
    try:
        r = httpx.get("https://api.frankfurter.app/latest?from=USD", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get("rates", {})
    except Exception:
        pass
    # Fallback offline benchmarks
    return {"CAD": 1.38, "GBP": 0.79, "EUR": 0.92, "AUD": 1.54, "INR": 85.50}


def fetch_google_trends_rss(geo: str = "US") -> list[dict[str, str]]:
    """Fetch daily trending queries from Google Trends RSS feed."""
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    results = []
    try:
        resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=8)
        if resp.status_code != 200:
            return results
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            traffic_el = item.find("{https://trends.google.com/trending/rss}approx_traffic")
            
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            traffic = traffic_el.text.strip() if traffic_el is not None and traffic_el.text else ""
            
            if title:
                results.append({"title": title, "desc": desc, "traffic": traffic, "geo": geo})
    except Exception as e:
        print(f"[Trends Harvester] Note: RSS fetch for geo={geo} skipped: {e}")
    return results


def fetch_google_search_suggestions(query: str) -> list[str]:
    """Fetch real-time high-intent autocomplete suggestions from Google Search."""
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={query}"
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1 and isinstance(data[1], list):
                return [s for s in data[1] if isinstance(s, str)]
    except Exception:
        pass
    return []


def is_valuable_commercial_query(text: str) -> bool:
    """Filter out noise, drama, entertainment; retain purely commercial queries."""
    lower = text.lower()
    for junk in JUNK_KEYWORDS:
        if junk in lower:
            return False
    for comm in COMMERCIAL_TERMS:
        if comm in lower:
            return True
    return False


def format_editorial_title(raw_query: str, domain: str) -> str:
    """Transform raw search queries into compelling, magazine-grade editorial titles."""
    clean = re.sub(r'[^a-zA-Z0-9\s\$\%\&\-\–]', '', raw_query).strip()
    words = [w.capitalize() if not w.isupper() else w for w in clean.split()]
    title = " ".join(words)
    
    # Enrich with year if not already present
    year = "2026"
    if year not in title:
        title = f"{title}: {year} Comprehensive Guide & Rates"
    else:
        title = f"{title}: What Consumers Need to Know"
        
    return title[:95]


def harvest_tier1_topics(limit_per_domain: int = 3) -> dict[str, list[dict[str, str]]]:
    """
    Harvest fresh high-intent topics across all 10 network domains
    combining Google Trends RSS and Google Autocomplete.
    """
    harvested: dict[str, list[dict[str, str]]] = {d: [] for d in DOMAIN_SEEDS.keys()}
    
    # 1. Harvest from Google Trends RSS across 5 Geos
    print("[Trends Harvester] Scanning Google Trends RSS (US, CA, GB, AU, IN)...")
    for geo in GEOS:
        trends = fetch_google_trends_rss(geo)
        for item in trends:
            t = item["title"]
            if is_valuable_commercial_query(t):
                # Classify into domain
                for d, info in DOMAIN_SEEDS.items():
                    if any(term in t.lower() for term in COMMERCIAL_TERMS):
                        formatted_t = format_editorial_title(t, d)
                        harvested[d].append({
                            "domain": d,
                            "category": info["category"],
                            "topic": formatted_t,
                            "source": f"Google Trends RSS ({geo})",
                            "traffic": item.get("traffic", "Spike")
                        })
                        break

    # 2. Harvest from Google Autocomplete for High-Intent Tier-1 seeds
    print("[Trends Harvester] Expanding High-Intent Commercial Autocomplete across 10 Domains...")
    for domain, info in DOMAIN_SEEDS.items():
        needed = limit_per_domain - len(harvested[domain])
        if needed <= 0:
            continue
        
        category = info["category"]
        for seed in info["seeds"]:
            suggestions = fetch_google_search_suggestions(seed)
            for s in suggestions:
                if len(s) > 10 and is_valuable_commercial_query(s):
                    formatted_t = format_editorial_title(s, domain)
                    # Check if already in harvested
                    if not any(h["topic"] == formatted_t for h in harvested[domain]):
                        harvested[domain].append({
                            "domain": domain,
                            "category": category,
                            "topic": formatted_t,
                            "source": "Google Autocomplete (Tier-1 Live)",
                            "traffic": "High Search Demand"
                        })
                if len(harvested[domain]) >= limit_per_domain:
                    break
            if len(harvested[domain]) >= limit_per_domain:
                break
                
    return harvested


def inject_into_db(harvested_data: dict[str, list[dict[str, str]]]) -> int:
    """Safely inject fresh harvested topics into SQLite topic_queue."""
    if not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Ensure table exists
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT,
        category TEXT,
        topic TEXT UNIQUE,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP
    )
    """)
    
    inserted_count = 0
    now = datetime.now().isoformat()
    
    for domain, topics in harvested_data.items():
        for t_info in topics:
            topic = t_info["topic"]
            cat = t_info["category"]
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                    (domain, cat, topic, now)
                )
                if cur.rowcount > 0:
                    inserted_count += 1
            except Exception as e:
                print(f"[Trends Harvester] DB Insert error: {e}")
                
    conn.commit()
    conn.close()
    return inserted_count


def run_harvest_cycle(limit_per_domain: int = 3) -> int:
    """Full execution cycle: Harvest -> Filter -> Enrich -> Inject."""
    forex = get_live_forex_rates()
    print(f"[Trends Harvester] Live Public Forex Benchmarks: USD/CAD={forex.get('CAD')}, USD/GBP={forex.get('GBP')}, USD/INR={forex.get('INR')}")
    
    harvested = harvest_tier1_topics(limit_per_domain=limit_per_domain)
    total_found = sum(len(v) for v in harvested.values())
    print(f"[Trends Harvester] Extracted {total_found} high-intent commercial topics across 10 network domains.")
    
    inserted = inject_into_db(harvested)
    print(f"[Trends Harvester] Successfully injected {inserted} brand new unique topics into topic_queue!")
    return inserted


if __name__ == "__main__":
    count = run_harvest_cycle(limit_per_domain=3)
    print(f"Cycle completed. Injected: {count} topics.")
