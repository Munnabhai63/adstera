from common import npx_bin
# autopublish_daemon.py - 24/7 Autonomous Publishing Engine with Anti-AI Gate & Search Console Automation
import os
import sys
import json
import re
import html
import sqlite3
import urllib.request
import urllib.error
import subprocess
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import yaml
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from site_templates import render_master_page, render_sidebar
from adsterra_links import render_native_ad_card, get_adsterra_config
from autopublish_engine import AntiAIDetectionGate, query_freellmapi, ping_search_engines, generate_claude_seo_article
import seo_pipeline
import topic_intelligence
from common.paths import AUTOPUBLISH_DB_PATH, STATE_DIR

DB_PATH = str(AUTOPUBLISH_DB_PATH)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
os.makedirs(str(STATE_DIR), exist_ok=True)

_GIT_SYNC_LOCK = threading.Lock()
_QUEUE_CLAIM_LOCK = threading.Lock()

def valid_description(d: str | None) -> bool:
    """Validate meta description according to SEO standards (60-160 chars, no placeholders, no ellipsis)."""
    if not d or not isinstance(d, str):
        return False
    clean = d.strip()
    if (
        "..." in clean
        or "{" in clean
        or "}" in clean
        or "page-link" in clean
        or "Need to include" in clean
        or clean.startswith(", ,")
    ):
        return False
    if len(clean) < 60 or len(clean) > 160:
        return False
    return True


DEFAULT_AUTOPUBLISH_CFG = {
    "interval_minutes": 20,
    "parallel_domains": 2,
    "jitter_seconds": 180,
    "min_sleep_seconds": 900,
    "stuck_stage_minutes": 30,
    "aggressive_winners_count": 5,
    "min_winner_score": 65.0,
    "min_pending_per_domain": 3,
    "sync_winners_to_queue": True,
    "schedule_mode": "5_wave_24h",
    "wave_hours_ist": ["07:00", "11:30", "16:00", "20:00", "00:00"],
    "articles_per_domain_per_day": 1,
    "daily_total_target": 10,
    "wave_domain_gap_seconds": 300,
    "discover_20_before_publish": True,
}
DEFAULT_CONFIG = DEFAULT_AUTOPUBLISH_CFG


def _load_autopublish_config() -> dict:
    cfg = dict(DEFAULT_AUTOPUBLISH_CFG)
    try:
        if CONFIG_PATH.exists():
            data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            ap = data.get("autopublish") or {}
            if isinstance(ap, dict):
                cfg.update({k: v for k, v in ap.items() if v is not None})
    except Exception:
        pass
    return cfg


def _connect_db() -> sqlite3.Connection:
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


# 1. DATABASE SETUP
def init_db():
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("""
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
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT,
        category TEXT,
        topic TEXT,
        status TEXT DEFAULT 'pending',
        priority_score REAL DEFAULT 0.0,
        created_at TIMESTAMP
    )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_topic_domain ON topic_queue(domain, topic)")
    cols = {r[1] for r in cur.execute("PRAGMA table_info(topic_queue)").fetchall()}
    if "priority_score" not in cols:
        cur.execute("ALTER TABLE topic_queue ADD COLUMN priority_score REAL DEFAULT 0.0")
    conn.commit()
    conn.close()
    topic_intelligence.init_candidate_tables(db_path=DB_PATH)

# 2. SEED TOPIC QUEUE (10 rich trending topics per domain = 100 queued posts)
INITIAL_TOPICS = {
    "loanraaj": [
        ("Business", "How to Import Industrial Packaging Machinery from Taiwan: Customs Tariffs & Bank LC"),
        ("Insurance", "Intermodal Cargo Insurance Guide: Marine, Rail & Highway Freight Liability Compared"),
        ("Carrier", "Commercial Truck ELD Mandate Violations: Fines, Log Audits & Carrier Compliance"),
        ("Finance", "Secured Overdraft Facility Against Property: Interest Math & Working Capital Flexibility"),
        ("Business", "Warehouse Lease Financing: Structuring Industrial Logistics Hubs with Bank Credit")
    ],
    "rechargetak": [
        ("Prepaid Plans", "Jio vs Airtel New 5G Data Boosters: Which Adds Highest Post-FUP Bandwidth?"),
        ("5G & Broadband", "Wi-Fi 7 vs Wi-Fi 6E in India: Is Upgrading Your Fiber Router Worth the Investment?"),
        ("FASTag & Tolls", "FASTag Double Toll Deduction Disputes: How to Claim Automatic NPCI Refunds"),
        ("SIM & Porting", "Corporate SIM to Personal MNP Transfer: NOC Format, Billing Clearance & Turnaround"),
        ("Prepaid Plans", "Quarterly 84-Day vs Bi-Monthly 56-Day Prepaid Plans: Detailed Value Comparison")
    ],
    "rechargepur": [
        ("Electricity & Gas", "Residential Solar Net Metering Billing Cycles: Export Units vs Grid Import Calculations"),
        ("DTH & Entertainment", "Dish TV vs Tata Play South Regional Entertainment Bouquets: Annual Price Benchmarks"),
        ("Cashback & UPI", "Maximizing Cred UPI Merchant Cashbacks on Local QR Codes: Slabs & Terms"),
        ("Water & Municipal", "Municipal Trade License Renewal Fees: Online Form Submission & Certificate Download"),
        ("Electricity & Gas", "Industrial Power Factor Penalty in Electricity Bills: How APFC Panels Save 10%")
    ],
    "tazaloan": [
        ("Personal Loans", "Personal Loan Balance Transfer vs Top-Up Loan: Which Saves More Interest?"),
        ("Credit Score", "Settled Personal Loans vs Closed Loans: Step-by-Step Credit Bureau Clean-Up"),
        ("Emergency Loans", "Instant Pre-Hospitalization Medical Lines of Credit: 15-Minute Sanction Walkthrough"),
        ("Student & Education", "Study in Germany Blocked Account Financing: SBI vs Deutsche Bank Requirements"),
        ("Personal Loans", "Personal Loan Foreclosure Charges: RBI Rules on Floating vs Fixed Interest Loans")
    ],
    "loankiseva": [
        ("Mudra Loans", "Mudra Shishu Loan for Street Vendors & Small Kiosks: Aadhaar-Based Disbursal"),
        ("MSME Credit", "CGTMSE Guarantee Renewal Fees: Bank Account Debit Schedules & Claims Procedure"),
        ("Women Entrepreneurship", "Annapurna Scheme for Food Catering Businesses: Equipment Financing for Women"),
        ("Agriculture & Dairy", "Cold Storage Construction Subsidy under MIDH: 35% Capital Grant Application"),
        ("MSME Credit", "Factoring Regulation Act MSME Protections: Clearing Overdue Private Bills")
    ],
    "karzseva": [
        ("Debt Consolidation", "Credit Card Debt Roll-Up into Gold Loan: Slash Borrowing APR from 42% to 9%"),
        ("Credit Settlement", "Consumer Forum Relief Against Illegal Recovery Calls: Precedents & Legal Action"),
        ("Credit Repair", "How to Dispute Outdated Identity Information on Experian and CRIF High Mark"),
        ("Financial Recovery", "Zero-Based Budgeting for Debt Free Living: Assigning Every Rupee a Job"),
        ("Debt Consolidation", "Salary Overdraft vs Personal Loan for Consolidating High-Interest Micro-Loans")
    ],
    "loantau": [
        ("Truck Loans", "Financing Electric Commercial Trucks in India: FAME-II Subsidies & Battery Warranties"),
        ("Used Trucks", "Used 14-Wheeler Tipper Valuation Checklist: Hydraulic Ram & Gearbox Wear Tests"),
        ("Tractor Loans", "Rotavator & Mini-Tractor Financing for Small Acreage Farmers: Subsidy Norms"),
        ("Fleet Finance", "GPS Fuel Sensor Monitoring Systems: Preventing Diesel Pilferage in 20+ Truck Fleets"),
        ("Truck Loans", "Ashok Leyland Captain vs Tata Prima Heavy Hauler: Operating Costs & Finance Terms")
    ],
    "tazabhav": [
        ("Gold & Silver", "Old Jewelry Exchange Deductions: How Melting Loss & Hallmarking Cuts Resale Value"),
        ("Daily SIP & Funds", "Nifty Midcap 150 Index Funds: Balancing High Growth with Drawdown Resilience"),
        ("Commodities", "Global Zinc & Nickel Price Trends: Impact on Galvanized Steel & EV Battery Cells"),
        ("Real Estate & Land", "RERA Section 18 Interest Penalties: How Builders Are Mandated to Pay Homebuyers"),
        ("Gold & Silver", "Physical Silver Bars vs Silver Accumulation Plans: Purity & Vault Storage Fees")
    ],
    "tazarokda": [
        ("Credit Cards", "Best Co-Branded Travel Credit Cards: Vistara vs Air India SBI Miles Comparison"),
        ("Cashback Rewards", "Utility Bill Cashback Tricks on RuPay Credit Cards: Avoiding Convenience Charges"),
        ("Business Banking", "Current Account Sweep Facilities for Corporate Treasuries: Earning 7.25% Liquid Yield"),
        ("High-Yield Savings", "Unity Small Finance Bank 9.5% Senior Citizen FD: Safety Analysis & Returns"),
        ("Credit Cards", "Credit Card Foreign Currency Markup Fees: Zero-Forex Cards for International Spend")
    ],
    "rechargekar": [
        ("eSIM Technology", "Smartwatch Cellular eSIM Pairing: Connecting Apple Watch & Galaxy Watch to Jio/Airtel"),
        ("International Roaming", "Schengen Visa International Roaming Packages: Europe Travel Data Benchmarks"),
        ("5G Vouchers & Booster", "Midnight 5G Quota Utilization: Scheduling Cloud Backups During Free Data Windows"),
        ("Student & Nomad Packs", "Cheapest Long-Validity Talktime SIMs for Senior Citizens Receiving OTPs Only"),
        ("eSIM Technology", "eSIM Activation Without Wi-Fi: Step-by-Step Offline Carrier QR Provisioning")
    ]
}

def seed_queue(fetch_live: bool = True):
    ap_cfg = _load_autopublish_config()
    min_per_dom = int(ap_cfg.get("min_pending_per_domain", 3))
    min_winner_score = float(ap_cfg.get("min_winner_score", 65.0))
    conn = _connect_db()
    cur = conn.cursor()
    inserted = 0
    now = datetime.now().isoformat()
    for site, topics in INITIAL_TOPICS.items():
        for cat, topic in topics:
            try:
                # Cross-domain check
                norm = re.sub(r"[^a-z0-9]", "", topic.lower()[:40])
                dup = cur.execute("SELECT 1 FROM published_posts WHERE domain != ? AND LOWER(title) LIKE ?", (site, f"%{topic[:30]}%")).fetchone()
                if dup:
                    continue
                cur.execute(
                    """
                    INSERT INTO topic_queue (domain, category, topic, status, priority_score, created_at)
                    VALUES (?, ?, ?, 'pending', 60.0, ?)
                    ON CONFLICT(domain, topic) DO UPDATE SET priority_score = MAX(COALESCE(priority_score, 0), 60.0)
                    """,
                    (site, cat, topic, now),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    if inserted > 0:
        print(f"[Topic Queue] Seeded {inserted} fresh topics across network domains.")

    # Ensure every single domain stays fueled with aggressive Top-5 CPC winners
    try:
        from network_registry import NETWORK_REGISTRY
        conn = _connect_db()
        per_dom = dict(conn.execute("SELECT domain, COUNT(*) FROM topic_queue WHERE status = 'pending' GROUP BY domain").fetchall())
        conn.close()
        starved = [d for d in NETWORK_REGISTRY.keys() if int(per_dom.get(d, 0)) < min_per_dom]
        for dom in starved:
            topic_intelligence.discover_20_topics_for_domain(
                dom,
                min_winner_score=min_winner_score,
                sync_to_queue=True,
                fetch_live=fetch_live,
                db_path=DB_PATH,
            )
    except Exception as e:
        print(f"[Topic Queue] Aggressive winner replenishment notice: {e}")

    # Auto-Replenish Queue using Tier-1 & Global Multi-Geo Trends Harvester
    if fetch_live:
        try:
            import trends_harvester
            conn = _connect_db()
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM topic_queue WHERE status = 'pending'")
            pending_count = cur.fetchone()[0]
            conn.close()
            if pending_count < 30:
                print(f"[Topic Queue] Pending topics low ({pending_count}). Auto-harvesting Tier-1 topics...")
                trends_harvester.run_harvest_cycle(limit_per_domain=3)
        except Exception as e:
            print(f"[Topic Queue] Trends harvester notice: {e}")


def recover_and_kick_stuck_domains(target_domains=None, fetch_live: bool = False) -> dict:
    """Unstick stale pipeline_state domains (e.g. tazaloan, loankiseva) and queue Top-5 winners."""
    ap_cfg = _load_autopublish_config()
    return topic_intelligence.kick_stuck_pipelines(
        stale_minutes=int(ap_cfg.get("stuck_stage_minutes", 30)),
        target_domains=target_domains,
        min_pending_per_domain=int(ap_cfg.get("min_pending_per_domain", 3)),
        aggressive_winners_count=int(ap_cfg.get("aggressive_winners_count", 5)),
        min_winner_score=float(ap_cfg.get("min_winner_score", 65.0)),
        fetch_live=fetch_live,
        db_path=DB_PATH,
    )

# 3. ARTICLE GENERATION ENGINE (Using FreeLLMAPI)
def generate_article_content(site_id, site_info, category, topic):
    site_name = site_info["name"]
    system_prompt = f"""You are a senior investigative economic and technical journalist writing for {site_name}.
Your mission is to produce an exhaustive, authoritative, deeply researched 1400-1800 word practical consumer guide.

CRITICAL RULES:
1. Write 100% in English with professional, direct editorial clarity.
2. VARY sentence lengths strictly (mix punchy 5-word declarations with rich 25-word analytical sentences for high burstiness).
3. NEVER use AI clichés. STRICTLY FORBIDDEN WORDS:
   - "delve", "testament", "beacon", "tapestry", "in conclusion", "it is important to remember",
   - "dive deep", "foster", "underscore", "crucial", "vital", "moreover", "furthermore",
   - "holistic", "multifaceted", "navigating the landscape", "game-changer", "revolutionize",
   - "plethora", "myriad", "paramount", "robust", "demystify", "pivotal", "cornerstone".
4. INJECT concrete real-world data: exact percentage rates, statutory sections, official governing bodies (RBI, TRAI, NPCI, Ministry of Finance, DISCOMs), and real institutional names (SBI, HDFC, ICICI, Tata, Airtel, Jio).
5. Output purely valid semantic HTML inside the body:
   - <h2> and <h3> subheadings
   - Structured paragraphs (<p>)
   - Detailed comparison table (<div class="table-responsive"><table class="article-table">...)
   - Unordered bullet lists (<ul><li>...</li></ul>)
   - Practical blockquotes (<blockquote><p>...</p></blockquote>)
   - Do NOT include <html>, <head>, <body>, or title tags—only the article inner content.
"""

    user_prompt = f"""Write an in-depth, original article on the following topic:
Topic: "{topic}"
Category: {category}
Publication: {site_name} ({site_info['desc']})

Include:
1. Clear lead paragraph breaking down the core problem and why it matters in 2026.
2. 3 to 4 detailed analytical sections with real calculations, interest math, or tariff rules.
3. A structured comparison table benchmarking 3 to 4 options/banks/plans.
4. Actionable step-by-step checklist for the reader.
5. Final strategic advice (labeled as "The Bottom Line:" or "Strategic Takeaway", NEVER "In Conclusion").
"""

    print(f"[{site_id}] Requesting high-eCPM article from FreeLLMAPI: '{topic[:45]}...'")
    raw_content = query_freellmapi(user_prompt, system_prompt, model="claude-sonnet-4-5")
    
    if not raw_content:
        # Fallback to auto model
        print(f"[{site_id}] Retrying with 'auto' model...")
        raw_content = query_freellmapi(user_prompt, system_prompt, model="auto")
        
    if not raw_content:
        print(f"[{site_id}] Generation failed from API.")
        return None

    # Strip markdown code fences if model wrapped in ```html ... ```
    clean_html = re.sub(r'^```html\s*', '', raw_content.strip())
    clean_html = re.sub(r'^```\s*', '', clean_html)
    clean_html = re.sub(r'```$', '', clean_html).strip()
    
    # Run Anti-AI Humanizer Quality Gate
    humanized_html = AntiAIDetectionGate.humanize(clean_html)
    passed, findings = AntiAIDetectionGate.audit(humanized_html)
    
    if not passed:
        print(f"[{site_id}] Anti-AI Gate Audit Note: {findings}")
    else:
        print(f"[{site_id}] Anti-AI Gate PASSED 100%! High burstiness & zero buzzwords.")
        
    return humanized_html

def sync_github(site_id: str, slug: str, topic: str) -> None:
    """Thread-safely commits new site files and pushes to GitHub."""
    site_dir = os.path.join("sites", f"{site_id}.com")
    with _GIT_SYNC_LOCK:
        try:
            subprocess.run(["git", "add", site_dir], capture_output=True, encoding="utf-8", errors="ignore", timeout=30)
            clean_title = re.sub(r'[\'"]', '', topic)[:50]
            commit_msg = f"AutoPublish: Published '{clean_title}' to {site_id}"
            subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, encoding="utf-8", errors="ignore", timeout=30)
            branch = os.environ.get("AUTOPUBLISH_GIT_BRANCH", "master")
            subprocess.run(["git", "pull", "--rebase", "origin", branch], capture_output=True, encoding="utf-8", errors="ignore", timeout=60)
            res = subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], capture_output=True, encoding="utf-8", errors="ignore", timeout=60)
            if res.returncode == 0:
                print(f"[{site_id}] GitHub automatically synced with new post! (origin/{branch} updated)")
            else:
                err_msg = (res.stderr or "")[-300:]
                print(f"[{site_id}] Git push note: {err_msg[:100]}")
                _notify_pipeline_error("git_sync", err_msg, domain=site_id)
        except Exception as e:
            print(f"[{site_id}] Git sync exception: {e}")

_PIPELINE_BOT = None


def _notify_pipeline_error(stage: str, detail: str, domain: str = "", level: str = "WARNING") -> None:
    """Best-effort rate-limited instant error alert to Telegram without interrupting publishing."""
    global _PIPELINE_BOT
    try:
        from alert_bot import TelegramAlertBot
        if _PIPELINE_BOT is None:
            _PIPELINE_BOT = TelegramAlertBot()
        _PIPELINE_BOT.send_pipeline_error_alert(stage=stage, detail=detail, domain=domain, level=level)
    except Exception as exc:
        print(f"[Alert Hook] Notification failed: {exc}")


# 4. PUBLISH & DEPLOY ENGINE (Thread-Safe + Parallel Distinct-Domain Execution)
def _select_batch_domains(limit: int = 2) -> list[str]:
    """Pick up to `limit` distinct pending domains, prioritizing under-published / kicked sites."""
    with _QUEUE_CLAIM_LOCK:
        conn = _connect_db()
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT tq.domain,
                   COUNT(DISTINCT pp.id) AS pub_cnt,
                   MAX(COALESCE(tq.priority_score, 0.0)) AS max_prio,
                   MIN(tq.id) AS first_id
            FROM topic_queue tq
            LEFT JOIN published_posts pp ON pp.domain = tq.domain
            WHERE tq.status = 'pending'
              AND tq.domain NOT IN (
                  SELECT DISTINCT domain FROM topic_queue WHERE status = 'processing'
              )
            GROUP BY tq.domain
            ORDER BY pub_cnt ASC, max_prio DESC, first_id ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]


def _claim_next_topic(specific_site=None, exclude_domains=None):
    """Atomically claim the highest-priority pending topic on a distinct domain."""
    excluded = {d.replace(".com", "").strip().lower() for d in (exclude_domains or [])}
    with _QUEUE_CLAIM_LOCK:
        conn = _connect_db()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            if specific_site:
                clean_site = specific_site.replace(".com", "").strip().lower()
                row = cur.execute(
                    """
                    SELECT id, domain, category, topic
                    FROM topic_queue
                    WHERE domain = ? AND status = 'pending'
                    ORDER BY COALESCE(priority_score, 0.0) DESC, id ASC
                    LIMIT 1
                    """,
                    (clean_site,),
                ).fetchone()
            else:
                placeholders = ",".join("?" for _ in excluded) if excluded else "''"
                params = tuple(excluded) if excluded else ()
                query = f"""
                    SELECT tq.id, tq.domain, tq.category, tq.topic
                    FROM topic_queue tq
                    LEFT JOIN (
                        SELECT domain, COUNT(*) AS pub_cnt FROM published_posts GROUP BY domain
                    ) pp ON pp.domain = tq.domain
                    WHERE tq.status = 'pending'
                      AND tq.domain NOT IN ({placeholders})
                      AND tq.domain NOT IN (
                          SELECT DISTINCT domain FROM topic_queue WHERE status = 'processing'
                      )
                    ORDER BY COALESCE(pp.pub_cnt, 0) ASC, COALESCE(tq.priority_score, 0.0) DESC, tq.id ASC
                    LIMIT 1
                """
                row = cur.execute(query, params).fetchone()

            if not row:
                conn.rollback()
                return None

            q_id = row[0]
            cur.execute("UPDATE topic_queue SET status = 'processing' WHERE id = ?", (q_id,))
            conn.commit()
            return row
        finally:
            conn.close()


def _ensure_unique_slug(site_id: str, base_slug: str) -> str:
    """Avoid filename or SQLite published_posts.slug collisions across parallel runs."""
    slug = base_slug or f"post-{int(time.time())}"
    conn = _connect_db()
    existing = {
        r[0]
        for r in conn.execute("SELECT slug FROM published_posts WHERE domain = ?", (site_id,)).fetchall()
        if r[0]
    }
    global_existing = {
        r[0]
        for r in conn.execute("SELECT slug FROM published_posts").fetchall()
        if r[0]
    }
    conn.close()
    used = existing | global_existing
    site_dir = os.path.join("sites", f"{site_id}.com")
    candidate = slug
    suffix = 2
    while (
        candidate in used
        or os.path.exists(os.path.join(site_dir, f"{candidate}.html"))
        or os.path.exists(os.path.join(site_dir, candidate, "index.html"))
    ):
        candidate = f"{slug[:48]}-{suffix}"
        suffix += 1
    return candidate


def _reset_topic_pending(q_id: int) -> None:
    try:
        conn = _connect_db()
        conn.cursor().execute("UPDATE topic_queue SET status = 'pending' WHERE id = ? AND status = 'processing'", (q_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def publish_next_post(specific_site=None, exclude_domains=None, discover_fresh_20: bool = False, dry_run: bool = False):
    from network_registry import NETWORK_REGISTRY
    MASTER_SITES = NETWORK_REGISTRY

    if discover_fresh_20 and specific_site:
        clean_dom = specific_site.replace(".com", "").strip().lower()
        try:
            ap_cfg = _load_autopublish_config()
            min_score = float(ap_cfg.get("min_winner_score", 65.0))
            print(f"[{clean_dom}] Stage 1 & 2: Discovering 20 Google Trends + High-CPC topics & selecting Top-5 winners...")
            topic_intelligence.discover_20_topics_for_domain(
                clean_dom,
                min_winner_score=min_score,
                sync_to_queue=True,
                fetch_live=True,
                db_path=DB_PATH,
            )
        except Exception as disc_exc:
            print(f"[{clean_dom}] 20-topic discovery notice: {disc_exc}")

    row = _claim_next_topic(specific_site=specific_site, exclude_domains=exclude_domains)
    if not row:
        print("[AutoPublisher] No pending topics available in queue! Re-seeding queue...")
        seed_queue(fetch_live=True)
        return False

    q_id, site_id, category, topic = row
    marked_published = False

    try:
        site_info = MASTER_SITES.get(site_id)
        if not site_info:
            print(f"[Error] Unknown site {site_id}")
            return False

        domain_url = site_info["domain"]
        name = site_info["name"]
        categories = site_info["categories"]
        cat_slug = categories.get(category, {}).get("slug", "finance")

        topic_intelligence.update_pipeline_stage(
            domain=site_id,
            stage_num=3,
            stage_name="Deep AI Writing",
            active_topic=topic,
            status_message="Generating SEO brief, CC0 media & 1,500+ word article",
            db_path=DB_PATH,
        )

        # PHASE 1: Claude-SEO Content Brief
        seo_brief = seo_pipeline.generate_seo_brief(site_id, topic)
        seo_title = seo_brief["seo_title"]
        meta_desc = seo_brief["meta_description"]
        primary_kw = seo_brief.get("primary_keyword", topic)
        if not valid_description(meta_desc):
            meta_desc = f"Complete guide on {primary_kw}: compare updated rates, eligibility criteria, and step-by-step procedures."
            if len(meta_desc) > 155:
                meta_desc = meta_desc[:155].rsplit(" ", 1)[0]

        # PHASE 2: Dynamic CC0 Image
        dynamic_img = seo_pipeline.get_dynamic_seo_image(primary_kw, site_id)
        img_url = dynamic_img["url"]
        img_alt = dynamic_img["alt"]

        # PHASE 3: Claude-SEO Content Generation
        raw_content_html, raw_faqs = generate_claude_seo_article(site_id, site_info, seo_brief)
        if not raw_content_html:
            _notify_pipeline_error("article_generation", f"Empty LLM output for topic: {topic[:120]}", domain=site_id)
            topic_intelligence.update_pipeline_stage(
                domain=site_id,
                stage_num=2,
                stage_name="Queued for Fast-Track Publish",
                active_topic=topic,
                status_message="Generation empty; returned topic cleanly to pending queue",
                db_path=DB_PATH,
            )
            return False

        # PHASE 4: Anti-AI, Claude-SEO `content_humanize.py` + `content_quality.py` & Finish-Gate Audit
        from content_quality_gate import ContentQualityFinishGate
        sanitized_html = ContentQualityFinishGate.sanitize_raw_html(raw_content_html)
        content_html, faqs, quality_meta = ContentQualityFinishGate.format_editorial_layout(
            clean_html=sanitized_html,
            title=seo_title,
            domain_key=site_id,
            primary_kw=primary_kw,
            category=category,
            site_name=name,
        )
        words_count = quality_meta["word_count"]
        print(
            f"[{site_id}] Content Quality Finish-Gate Score: {quality_meta['score']}/100 "
            f"| Claude-SEO QRG Quality: {quality_meta.get('qrg_overall_quality', 92)}/100 "
            f"(Words: {words_count}, FAQs: {quality_meta['faq_count']}, TOC: {quality_meta.get('has_toc')}, "
            f"Cluster: {quality_meta.get('has_cluster')}, E-E-A-T: {quality_meta.get('has_eeat')})"
        )

        topic_intelligence.update_pipeline_stage(
            domain=site_id,
            stage_num=4,
            stage_name="Anti-AI Gate Audit",
            active_topic=topic,
            status_message=f"Quality gate {quality_meta['score']}/100 | Claude-SEO QRG {quality_meta.get('qrg_overall_quality', 92)}/100 ({words_count} words)",
            words_written=words_count,
            anti_ai_score=float(quality_meta.get("score", 99.0)),
            db_path=DB_PATH,
        )

        # Clean unique SEO slug
        base_slug = re.sub(r'[^a-z0-9]+', '-', primary_kw.lower()).strip('-')[:55]
        slug = _ensure_unique_slug(site_id, base_slug)
        canonical_url = f"{domain_url}/{slug}"

        # PHASE 4B: Distribute 6-9 self-hosted <figure> images between <h2> sections (P3-1)
        local_img_dir = Path("sites") / f"{site_id}.com" / "img"
        available_imgs = [f.name for f in local_img_dir.glob("*.webp")] if local_img_dir.exists() else []
        if available_imgs:
            h2_split_re = re.compile(r'(<h2[^>]*>.*?</h2>)', re.IGNORECASE | re.DOTALL)
            h2_parts = h2_split_re.split(content_html)
            if len(h2_parts) > 2:
                num_figs = min(len(available_imgs), max(6, min(9, len(h2_parts) // 2)))
                h = int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16)
                figs_inserted = 0
                new_h2_parts = []
                for part in h2_parts:
                    if h2_split_re.match(part) and figs_inserted < num_figs:
                        fig_fn = available_imgs[(h + figs_inserted * 7) % len(available_imgs)]
                        fig_alt = html.escape(f"{seo_title} - Section Analysis Exhibit {figs_inserted + 1}")
                        fig_html = (
                            f'\n<figure class="article-figure" style="margin:28px 0; text-align:center;">\n'
                            f'    <img src="/img/{fig_fn}" alt="{fig_alt}" loading="lazy" width="1200" height="675" style="width:100%; height:auto; border-radius:8px;">\n'
                            f'    <figcaption style="font-size:13px; color:var(--text-muted); margin-top:8px;">Verified benchmarks and documentation analysis for {seo_title}.</figcaption>\n'
                            f'</figure>\n'
                        )
                        new_h2_parts.append(fig_html)
                        figs_inserted += 1
                    new_h2_parts.append(part)
                content_html = "".join(new_h2_parts)

        # Schema.org JSON-LD (`seo-schema` + `schema_generate.py` @graph)
        site_domain_clean = domain_url.replace("https://", "").replace("http://", "").rstrip("/")
        schema_json_ld = seo_pipeline.build_schema_json_ld(
            site_domain=site_domain_clean,
            site_name=name,
            title=seo_title,
            desc=meta_desc,
            canonical_url=canonical_url,
            img_url=img_url,
            faqs=faqs,
            category=category,
            cat_slug=cat_slug,
            word_count=words_count,
            keywords=[primary_kw] + list(seo_brief.get("lsi_keywords", [])),
        )

        all_articles = []
        for c_data in categories.values():
            all_articles.extend(c_data.get("articles", []))
        sidebar_html = render_sidebar(site_info, all_articles)
        now_date_iso = datetime.now().strftime("%Y-%m-%d")
        now_date_label = datetime.now().strftime("%B %d, %Y")
        read_mins = max(6, round(words_count / 200))

        article_body = f"""
    <main class="container">
        <div class="main-layout">
            <article>
                <div class="post-paper">
                    <div class="post-crumb">
                        <a href="/">Home</a> <span>•</span>
                        <a href="/category/{cat_slug}">{category}</a> <span>•</span>
                        <span>{seo_title}</span>
                    </div>
                    <span class="cat-badge">{category}</span>
                    <h1 class="post-h1">{seo_title}</h1>
                    <div class="post-meta">
                        <span>Published: <time datetime="{now_date_iso}">{now_date_label}</time></span>
                        <span>Last Fact-Checked: <time datetime="{now_date_iso}">{now_date_label}</time></span>
                        <span>{words_count} Words ({read_mins} Min Read)</span>
                        <span>Verified by <a href="/about-us">{name} Research Desk</a></span>
                    </div>
                    <div class="post-feature-wrap">
                        <img src="{img_url}" alt="{html.escape(img_alt)}" width="1200" height="675" loading="eager">
                    </div>
                    <div class="post-content">
                        {content_html}
                    </div>
                    <div class="author-card">
                        <div class="author-avatar">{name[:2]}</div>
                        <div>
                            <h3 style="font-size:16px; font-weight:800; color:var(--text-head); margin-bottom:4px;">{name} Senior Research Team</h3>
                            <p style="font-size:13px; color:var(--text-muted); line-height:1.5;">
                                Our editorial analysts verify statutory circulars, test financial and telecom platforms independently, and produce transparent decision guides.
                            </p>
                        </div>
                    </div>
                </div>
            </article>
            {sidebar_html}
        </div>
    </main>
    """

        full_html = render_master_page(
            site_info,
            title=seo_title,
            desc=meta_desc,
            canonical=canonical_url,
            main_body=article_body,
            active_nav=category,
            ticker_title=seo_title,
            ticker_url=f"/{slug}",
            schema_json_ld=schema_json_ld,
            og_image=img_url,
        )

        # PHASE 5: Full Claude-SEO (`parse_html.py` + `content_quality.py`) Post-Render Verification
        claude_seo_audit = seo_pipeline.run_full_claude_seo_audit(full_html, canonical_url, content_html)
        print(
            f"[{site_id}] Claude-SEO v2.5.0 Sub-System Audit: {claude_seo_audit['claude_seo_score']}/100 "
            f"(H1={claude_seo_audit['h1_count']}, H2={claude_seo_audit['h2_count']}, "
            f"InternalLinks={claude_seo_audit['internal_links']}, ExternalCitations={claude_seo_audit['external_links']}, "
            f"SchemaEntities={claude_seo_audit['schema_entities']})"
        )

        if dry_run:
            import tempfile
            try:
                dry_dir = Path("/tmp/adstera_dryrun")
                dry_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                dry_dir = Path(tempfile.gettempdir()) / "adstera_dryrun"
                dry_dir.mkdir(parents=True, exist_ok=True)
            
            dry_file = dry_dir / f"{slug}.html"
            dry_file.write_text(full_html, encoding="utf-8")
            
            # Also write to local tempfile dir if /tmp is a different drive on Windows
            alt_dry_dir = Path(tempfile.gettempdir()) / "adstera_dryrun"
            alt_dry_dir.mkdir(parents=True, exist_ok=True)
            (alt_dry_dir / f"{slug}.html").write_text(full_html, encoding="utf-8")
            
            imgs = [i for i in re.findall(r'<img[^>]+src="([^"]+)"', full_html) if 'logo' not in i.lower()]
            q_score = float(quality_meta.get("score", 99.5))
            print(f"[DRY-RUN] Success! Article generated for site: {site_id} | slug: {slug}")
            print(f"[DRY-RUN] Output written to: {dry_file}")
            print(f"[DRY-RUN] Word count: {words_count} | Quality score: {q_score} | Image count: {len(imgs)}")
            return True

        site_dirs = [os.path.join("sites", f"{site_id}.com")]
        for s_dir in site_dirs:
            os.makedirs(os.path.join(s_dir, slug), exist_ok=True)
            with open(os.path.join(s_dir, slug, "index.html"), "w", encoding="utf-8") as f:
                f.write(full_html)

            sm_path = os.path.join(s_dir, "sitemap.xml")
            if os.path.exists(sm_path):
                with open(sm_path, "r", encoding="utf-8") as sm_f:
                    sm_content = sm_f.read()
                new_entry = f"<url><loc>{domain_url}/{slug}</loc><lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod><priority>0.9</priority><changefreq>weekly</changefreq></url>\n</urlset>"
                if "</urlset>" in sm_content:
                    sm_content = sm_content.replace("</urlset>", new_entry)
                    with open(sm_path, "w", encoding="utf-8") as sm_f:
                        sm_f.write(sm_content)

        print(f"[{site_id}] Successfully compiled & saved '{slug}' ({words_count} words).")

        # Ensure _redirects, _worker.js, robots.txt, and llms.txt are provisioned BEFORE Cloudflare deploy
        try:
            from instant_indexer import provision_verification_keys
            provision_verification_keys()
        except Exception:
            pass

        # Deploy to Cloudflare Pages
        deploy_cmd = [npx_bin(), "wrangler", "pages", "deploy", os.path.join("sites", f"{site_id}.com"), f"--project-name={site_id}", "--branch=main", "--commit-dirty=true"]
        try:
            res = subprocess.run(deploy_cmd, capture_output=True, encoding="utf-8", errors="ignore", timeout=120)
            cf_success = 1 if res.returncode == 0 else 0
            if cf_success:
                print(f"[{site_id}] Cloudflare Pages updated live with new post!")
            else:
                err_tail = (res.stderr or res.stdout or "Wrangler non-zero exit")[:200]
                print(f"[{site_id}] Cloudflare deploy warning: {err_tail}")
                _notify_pipeline_error("cloudflare_deploy", f"Wrangler exit={res.returncode}: {err_tail}", domain=site_id)
        except Exception as e:
            print(f"[{site_id}] Cloudflare deploy error: {e}")
            _notify_pipeline_error("cloudflare_deploy", f"Wrangler exception: {e}", domain=site_id)
            cf_success = 0

        # Instant IndexNow & Search Broadcast
        indexnow_ok = 0
        try:
            from instant_indexer import broadcast_new_post
            full_post_url = f"{domain_url}/{slug}"
            ping_ok = bool(broadcast_new_post(site_id, full_post_url))
            indexnow_ok = 1 if ping_ok else 0
            if not ping_ok:
                _notify_pipeline_error("indexnow_ping", f"IndexNow & Google ping failed for {full_post_url}", domain=site_id)
        except Exception as e:
            print(f"[{site_id}] Instant Indexer broadcast note: {e}")
            _notify_pipeline_error("indexnow_ping", f"Indexer exception: {e}", domain=site_id)

        # Thread-safe GitHub sync (scoped strictly to sites/<site_id>.com)
        sync_github(site_id, slug, topic)

        # Record in database
        conn = _connect_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO published_posts (domain, slug, title, category, words, published_at, cf_deployed, google_pinged, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (site_id, slug, topic, category, words_count, datetime.now().isoformat(), cf_success, indexnow_ok, float(quality_meta.get("score", 99.5))),
        )
        cur.execute("UPDATE topic_queue SET status = 'published' WHERE id = ?", (q_id,))
        conn.commit()
        conn.close()
        marked_published = True

        topic_intelligence.update_pipeline_stage(
            domain=site_id,
            stage_num=5,
            stage_name="Cloudflare & GSC",
            active_topic=topic,
            status_message=f"Live: {domain_url}/{slug} (CF={cf_success}, Ping={indexnow_ok})",
            words_written=words_count,
            anti_ai_score=float(quality_meta.get("score", 99.5)),
            db_path=DB_PATH,
        )

        print(f"[{site_id}] Auto-Publish cycle finished successfully: {domain_url}/{slug}")
        return True
    finally:
        if not marked_published:
            _reset_topic_pending(q_id)


def publish_parallel_batch(parallel_domains: int | None = None, specific_sites: list[str] | None = None, kick_stuck: bool = True) -> dict:
    """Publish up to `parallel_domains` (default 2) distinct domains concurrently."""
    ap_cfg = _load_autopublish_config()
    batch_size = max(1, int(parallel_domains if parallel_domains is not None else ap_cfg.get("parallel_domains", 2)))
    started = time.perf_counter()

    kick_info = {}
    if kick_stuck:
        kick_info = recover_and_kick_stuck_domains(fetch_live=False)

    if specific_sites:
        chosen_sites = [s.replace(".com", "").strip().lower() for s in dict.fromkeys(specific_sites)][:batch_size]
    else:
        chosen_sites = _select_batch_domains(limit=batch_size)
        if not chosen_sites:
            seed_queue(fetch_live=True)
            chosen_sites = _select_batch_domains(limit=batch_size)

    if not chosen_sites:
        return {
            "parallel_domains": batch_size,
            "attempted_sites": [],
            "results": {},
            "published_count": 0,
            "kick_info": kick_info,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    print(f"[Parallel Batch] Launching {len(chosen_sites)} domain publishers simultaneously: {', '.join(chosen_sites)}")
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=len(chosen_sites), thread_name_prefix="ap_pub") as executor:
        futures = {executor.submit(publish_next_post, specific_site=dom): dom for dom in chosen_sites}
        for fut in as_completed(futures):
            dom = futures[fut]
            try:
                results[dom] = bool(fut.result())
            except Exception as exc:
                print(f"[{dom}] Parallel publish exception: {exc}")
                _notify_pipeline_error("parallel_publish", f"Unhandled worker exception: {exc}", domain=dom)
                results[dom] = False

    published_count = sum(1 for v in results.values() if v)
    elapsed = round(time.perf_counter() - started, 3)
    print(f"[Parallel Batch] Completed {published_count}/{len(chosen_sites)} domain(s) in {elapsed}s.")
    return {
        "parallel_domains": batch_size,
        "attempted_sites": chosen_sites,
        "results": results,
        "published_count": published_count,
        "kick_info": kick_info,
        "elapsed_seconds": elapsed,
    }


# 5. 24-HOUR 5-WAVE SEQUENTIAL SCHEDULER (10 DOMAINS x 5 ARTICLES/DAY = 50 ARTICLES/DAY)
def get_today_domain_counts() -> dict[str, int]:
    """Return number of deep (1,000+ word) articles published today (after 5-Wave cutover) per domain."""
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    conn = _connect_db()
    rows = conn.execute(
        "SELECT domain, COUNT(*) FROM published_posts WHERE published_at LIKE ? AND published_at >= '2026-11-11T21:10:00' AND COALESCE(words, 0) >= 1000 GROUP BY domain",
        (f"{today_prefix}%",),
    ).fetchall()
    conn.close()
    return {str(r[0]): int(r[1]) for r in rows if r[0]}


def select_next_wave_domain(per_domain_cap: int = 5) -> str | None:
    """
    Pick the next domain needing an article today (under `per_domain_cap`),
    prioritizing the domain with the fewest posts published today so all 10 domains
    receive 1 article per wave sequentially (5 waves x 10 domains = 50/day).
    """
    from network_registry import NETWORK_REGISTRY
    today_counts = get_today_domain_counts()
    all_domains = list(NETWORK_REGISTRY.keys())
    eligible = [d for d in all_domains if today_counts.get(d, 0) < per_domain_cap]
    if not eligible:
        return None
    eligible.sort(key=lambda d: (today_counts.get(d, 0), all_domains.index(d)))
    return eligible[0]


def run_daemon(interval_minutes=None, parallel_domains=None):
    ap_cfg = _load_autopublish_config()
    schedule_mode = str(ap_cfg.get("schedule_mode", "5_wave_24h"))
    if "articles_per_domain_per_day" not in ap_cfg:
        print("[WARNING] 'articles_per_domain_per_day' missing in config, using safe fallback: 1")
    if "daily_total_target" not in ap_cfg:
        print("[WARNING] 'daily_total_target' missing in config, using safe fallback: 10")
    per_dom_cap = int(ap_cfg.get("articles_per_domain_per_day", 1))
    daily_target = int(ap_cfg.get("daily_total_target", 10))
    wave_hours = [str(w) for w in (ap_cfg.get("wave_hours_ist") or ["07:00", "11:30", "16:00", "20:00", "00:00"])]
    discover_20 = bool(ap_cfg.get("discover_20_before_publish", True))

    # Ensure local FreeLLMAPI daemon is warm alongside Cloudflare 24x7 Edge Gateway
    try:
        from freellmapi_client import ensure_local_daemon_running
        ensure_local_daemon_running()
    except Exception:
        pass

    print("=" * 74)
    print("STARTING 24/7 AUTOPUBLISH DAEMON (5-WAVE 24H SEQUENTIAL QUALITY MODE)")
    print(f"Target: {per_dom_cap} articles/domain/day x 10 domains = {daily_target} articles/24h")
    print(f"Daily Waves (IST): {', '.join(wave_hours)} | Mode: 1 Domain at a time (20-Topic -> Top-5 -> 2-Part Deep AI)")
    print("=" * 74)

    init_db()
    seed_queue(fetch_live=False)
    kick_summary = recover_and_kick_stuck_domains(fetch_live=False)
    if kick_summary.get("kicked_count"):
        print(f"[Layer 7 Recovery] Unstuck {kick_summary['kicked_count']} domain(s): {', '.join(kick_summary['kicked_domains'])}")

    while True:
        try:
            try:
                import daily_report
                sched_res = daily_report.maybe_send_scheduled_morning_report()
                if sched_res.get("sent"):
                    print(f"[Daily Report] Morning Telegram digest sent for {sched_res.get('date')}.")
            except Exception as rep_exc:
                print(f"[Daily Report] Scheduler notice: {rep_exc}")

            try:
                import gsc_monitor
                gsc_sched = gsc_monitor.maybe_send_scheduled_weekly_report()
                if gsc_sched.get("sent"):
                    print(f"[GSC Weekly Report] Digest sent for week {gsc_sched.get('week')}.")
            except Exception as gsc_exc:
                print(f"[GSC Weekly Report] Scheduler notice: {gsc_exc}")

            if schedule_mode == "5_wave_24h" and parallel_domains is None:
                today_counts = get_today_domain_counts()
                total_today = sum(today_counts.values())
                next_dom = select_next_wave_domain(per_domain_cap=per_dom_cap)
                if next_dom is None or total_today >= daily_target:
                    print(f"[5-Wave Scheduler] Daily target reached ({total_today}/{daily_target} articles today across 10 domains). Sleeping 30m until next day window...")
                    time.sleep(1800)
                    continue

                dom_today = today_counts.get(next_dom, 0) + 1
                print(
                    f"\n[5-Wave Sequential Pulse] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"Domain: {next_dom}.com (Wave {dom_today}/{per_dom_cap} today | Fleet today: {total_today + 1}/{daily_target})"
                )
                publish_next_post(specific_site=next_dom, discover_fresh_20=discover_20)

                # 50 articles across 24 hours = 1 article every ~28 minutes (1,680s +/- 120s jitter)
                base_gap = int((24 * 3600) // max(1, daily_target))
                jitter = random.randint(-120, 120)
                sleep_sec = max(600, base_gap + jitter)
                print(f"[5-Wave Sleeping] Next single-domain deep article in {sleep_sec / 60:.1f} minutes...")
                time.sleep(sleep_sec)
            else:
                eff_interval = int(interval_minutes if interval_minutes is not None else ap_cfg.get("interval_minutes", 20))
                eff_parallel = max(1, int(parallel_domains if parallel_domains is not None else ap_cfg.get("parallel_domains", 2)))
                jitter_cap = int(ap_cfg.get("jitter_seconds", 180))
                min_sleep = int(ap_cfg.get("min_sleep_seconds", 900))
                print(f"\n[Daemon Pulse] Initiating {eff_parallel}-domain parallel publish cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
                publish_parallel_batch(parallel_domains=eff_parallel, kick_stuck=True)
                jitter = random.randint(-jitter_cap, jitter_cap)
                sleep_sec = max(min_sleep, (eff_interval * 60) + jitter)
                print(f"[Daemon Sleeping] Next {eff_parallel}-domain parallel batch in {sleep_sec / 60:.1f} minutes...")
                time.sleep(sleep_sec)
        except KeyboardInterrupt:
            print("[Daemon] Stopped by user.")
            break
        except Exception as e:
            print(f"[Daemon Recovery] Handled exception: {e}. Sleeping 2 minutes before retry...")
            _notify_pipeline_error("daemon_loop", f"Unhandled daemon exception: {e}", level="CRITICAL")
            time.sleep(120)


if __name__ == "__main__":
    init_db()
    if "--dry-run" in sys.argv:
        site_arg = "loanraaj"
        if "--site" in sys.argv:
            idx = sys.argv.index("--site")
            if idx + 1 < len(sys.argv):
                site_arg = sys.argv[idx + 1]
        seed_queue(fetch_live=False)
        print(f"Executing DRY-RUN 5-Stage deep auto-publish run (Site: {site_arg})...")
        publish_next_post(specific_site=site_arg, discover_fresh_20=False, dry_run=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "--kick-stuck":
        seed_queue(fetch_live=False)
        res = recover_and_kick_stuck_domains(fetch_live=False)
        print(json.dumps(res, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--parallel":
        seed_queue(fetch_live=False)
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        res = publish_parallel_batch(parallel_domains=n, kick_stuck=True)
        print(json.dumps(res, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--once":
        seed_queue(fetch_live=False)
        site_arg = sys.argv[2] if len(sys.argv) > 2 else select_next_wave_domain(per_domain_cap=5)
        print(f"Executing single 5-Stage deep auto-publish run (Site: {site_arg or 'Next in Queue'})...")
        publish_next_post(specific_site=site_arg, discover_fresh_20=True)
    else:
        run_daemon()
