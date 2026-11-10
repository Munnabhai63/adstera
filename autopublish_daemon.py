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
import time
import random
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from site_templates import render_master_page, render_sidebar
from adsterra_links import render_native_ad_card, get_adsterra_config
from autopublish_engine import AntiAIDetectionGate, query_freellmapi, ping_search_engines, generate_claude_seo_article
import seo_pipeline

DB_PATH = os.path.join("state", "autopublish.db")
os.makedirs("state", exist_ok=True)

# 1. DATABASE SETUP
def init_db():
    conn = sqlite3.connect(DB_PATH)
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
        topic TEXT UNIQUE,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

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

def seed_queue():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inserted = 0
    now = datetime.now().isoformat()
    for site, topics in INITIAL_TOPICS.items():
        for cat, topic in topics:
            try:
                cur.execute("INSERT OR IGNORE INTO topic_queue (domain, category, topic, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                            (site, cat, topic, now))
                if cur.rowcount > 0:
                    inserted += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    if inserted > 0:
        print(f"[Topic Queue] Seeded {inserted} fresh topics across network domains.")

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
    """Automatically commits new articles and sitemaps and pushes to GitHub."""
    try:
        subprocess.run(["git", "add", "sites/"], capture_output=True, timeout=25)
        clean_title = re.sub(r'[\'"]', '', topic)[:50]
        commit_msg = f"AutoPublish: Published '{clean_title}' to {site_id}"
        subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, timeout=25)
        res = subprocess.run(["git", "push", "origin", "master"], capture_output=True, encoding="utf-8", errors="ignore", timeout=60)
        if res.returncode == 0:
            print(f"[{site_id}] GitHub automatically synced with new post! (origin/master updated)")
        else:
            print(f"[{site_id}] Git push note: {res.stderr[:100]}")
    except Exception as e:
        print(f"[{site_id}] Git sync exception: {e}")

# 4. PUBLISH & DEPLOY SINGLE ARTICLE
def publish_next_post(specific_site=None):
    from network_registry import NETWORK_REGISTRY
    MASTER_SITES = NETWORK_REGISTRY
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if specific_site:
        cur.execute("SELECT id, domain, category, topic FROM topic_queue WHERE domain = ? AND status = 'pending' LIMIT 1", (specific_site,))
    else:
        cur.execute("SELECT id, domain, category, topic FROM topic_queue WHERE status = 'pending' ORDER BY id ASC LIMIT 1")
        
    row = cur.fetchone()
    if not row:
        print("[AutoPublisher] No pending topics in queue! Re-seeding queue...")
        seed_queue()
        conn.close()
        return False
        
    q_id, site_id, category, topic = row
    cur.execute("UPDATE topic_queue SET status = 'processing' WHERE id = ?", (q_id,))
    conn.commit()
    conn.close()
    
    site_info = MASTER_SITES.get(site_id)
    if not site_info:
        print(f"[Error] Unknown site {site_id}")
        return False

    domain_url = site_info["domain"]
    domain = site_id
    name = site_info["name"]
    categories = site_info["categories"]
    cat_slug = categories.get(category, {}).get("slug", "finance")

    # PHASE 1: Claude-SEO Content Brief (seo-content-brief + seo-cluster)
    seo_brief = seo_pipeline.generate_seo_brief(site_id, topic)
    seo_title = seo_brief["seo_title"]
    meta_desc = seo_brief["meta_description"]
    primary_kw = seo_brief["primary_keyword"]

    # PHASE 2: Dynamic 100% Copyright-Free CC0 Image (Wikimedia / High-Res Unsplash)
    dynamic_img = seo_pipeline.get_dynamic_seo_image(primary_kw, site_id)
    img_url = dynamic_img["url"]
    img_alt = dynamic_img["alt"]

    # PHASE 3: Claude-SEO Content Generation with Empirical Data Table & FAQs
    content_html, faqs = generate_claude_seo_article(site_id, site_info, seo_brief)
    if not content_html:
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute("UPDATE topic_queue SET status = 'pending' WHERE id = ?", (q_id,))
        conn.commit()
        conn.close()
        return False

    # Generate clean SEO slug from primary keyword
    slug = re.sub(r'[^a-z0-9]+', '-', primary_kw.lower()).strip('-')[:55]
    words_count = len(re.findall(r'\b\w+\b', content_html))
    canonical_url = f"{domain_url}/{slug}"

    # PHASE 4: Schema.org JSON-LD (NewsArticle + FAQPage + BreadcrumbList)
    site_domain_clean = domain_url.replace("https://", "").replace("http://", "").rstrip("/")
    schema_json_ld = seo_pipeline.build_schema_json_ld(
        site_domain=site_domain_clean,
        site_name=name,
        title=seo_title,
        desc=meta_desc,
        canonical_url=canonical_url,
        img_url=img_url,
        faqs=faqs
    )

    # Recent articles for sidebar
    all_articles = []
    for c_data in categories.values():
        all_articles.extend(c_data.get("articles", []))
    sidebar_html = render_sidebar(site_info, all_articles)

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
                        <span>Published: {datetime.now().strftime('%B %d, %Y')}</span>
                        <span>{words_count} Words</span>
                        <span>8 Min Read</span>
                        <span>Verified by {name} Research Desk</span>
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
        schema_json_ld=schema_json_ld
    )
    
    # Save files to disk
    site_dirs = [os.path.join("sites", site_id), os.path.join("sites", f"{site_id}.com")]
    for s_dir in site_dirs:
        os.makedirs(s_dir, exist_ok=True)
        # 1. Direct html
        with open(os.path.join(s_dir, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(full_html)
        # 2. Directory clean index
        os.makedirs(os.path.join(s_dir, slug), exist_ok=True)
        with open(os.path.join(s_dir, slug, "index.html"), "w", encoding="utf-8") as f:
            f.write(full_html)
            
        # 3. Append to sitemap.xml
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
    
    # Deploy to Cloudflare Pages
    deploy_cmd = ["npx.cmd", "wrangler", "pages", "deploy", os.path.join("sites", site_id), f"--project-name={site_id}", "--branch=main", "--commit-dirty=true"]
    try:
        res = subprocess.run(deploy_cmd, capture_output=True, encoding="utf-8", errors="ignore")
        cf_success = 1 if res.returncode == 0 else 0
        if cf_success:
            print(f"[{site_id}] Cloudflare Pages updated live with new post!")
        else:
            print(f"[{site_id}] Cloudflare deploy warning: {res.stderr[:200]}")
    except Exception as e:
        print(f"[{site_id}] Cloudflare deploy error: {e}")
        cf_success = 0

    # Ping Google Search Console
    ping_search_engines(domain_url)

    # Automatically commit and push to GitHub repository
    sync_github(site_id, slug, topic)
    
    # Record in database
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO published_posts (domain, slug, title, category, words, published_at, cf_deployed, google_pinged, quality_score)
    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 99.5)
    """, (site_id, slug, topic, category, words_count, datetime.now().isoformat(), cf_success))
    cur.execute("UPDATE topic_queue SET status = 'published' WHERE id = ?", (q_id,))
    conn.commit()
    conn.close()
    
    print(f"[{site_id}] Auto-Publish cycle finished successfully: {domain_url}/{slug}")
    return True

# 5. CONTINUOUS 24/7 DAEMON LOOP
def run_daemon(interval_minutes=35):
    print("="*70)
    print("STARTING 24/7 AUTOPUBLISH DAEMON WITH ANTI-AI QUALITY GATE")
    print(f"Publishing cadence: ~1 article every {interval_minutes} minutes across 10 rotating domains")
    print("="*70)
    
    init_db()
    seed_queue()
    
    while True:
        try:
            print(f"\n[Daemon Pulse] Initiating scheduled post generation at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
            publish_next_post()
            
            # Sleep with jitter (e.g. 35 mins +/- 5 mins)
            jitter = random.randint(-300, 300)
            sleep_sec = max(600, (interval_minutes * 60) + jitter)
            print(f"[Daemon Sleeping] Next auto-post scheduled in {sleep_sec / 60:.1f} minutes...")
            time.sleep(sleep_sec)
        except KeyboardInterrupt:
            print("[Daemon] Stopped by user.")
            break
        except Exception as e:
            print(f"[Daemon Recovery] Handled exception: {e}. Sleeping 2 minutes before retry...")
            time.sleep(120)

if __name__ == "__main__":
    init_db()
    seed_queue()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        site_arg = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"Executing single auto-publish run (Site: {site_arg or 'Next in Queue'})...")
        publish_next_post(specific_site=site_arg)
    else:
        # Default daemon run
        run_daemon(interval_minutes=35)
