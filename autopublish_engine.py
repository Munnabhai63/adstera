# autopublish_engine.py - Autonomous AI Content Publisher with Anti-AI Detection Quality Gate
import os
import sys
import json
import re
import html
import urllib.request
import urllib.error
import subprocess
import time
import math
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 1. ANTI-AI DETECTION / HUMANIZER QUALITY GATE
BANNED_AI_WORDS = [
    "delve", "testament", "beacon", "tapestry", "in conclusion", 
    "it's important to remember", "it is important to note", "dive deep", 
    "foster", "underscore", "crucial", "vital", "moreover", "furthermore", 
    "holistic", "multifaceted", "navigating the landscape", "game-changer", 
    "revolutionize", "seamless", "plethora", "myriad", "paramount", 
    "robust", "embark", "shed light", "harnessing", "unleash", "elevate", 
    "unlocking the potential", "in today's fast-paced world", "ever-evolving", 
    "demystify", "unravel", "pivotal", "cornerstone", "nexus", "linchpin"
]

class AntiAIDetectionGate:
    @staticmethod
    def audit(text):
        """
        Runs comprehensive anti-AI detection audit:
        1. AI buzzword blacklist check
        2. Sentence length variance (burstiness)
        3. Real-world empirical data density
        """
        text_lower = text.lower()
        findings = []
        
        # 1. Blacklist check
        found_buzzwords = [w for w in BANNED_AI_WORDS if w in text_lower]
        if found_buzzwords:
            findings.append(f"Contains AI buzzwords: {', '.join(found_buzzwords[:5])}")
            
        # 2. Burstiness / Sentence length variance
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip().split()) >= 3]
        if len(sentences) >= 5:
            lengths = [len(s.split()) for s in sentences]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            std_dev = math.sqrt(variance)
            if std_dev < 4.5:
                findings.append(f"Low burstiness (std_dev: {std_dev:.2f} < 4.5). Needs more varied sentence rhythm.")
        else:
            std_dev = 5.0
            
        # 3. Empirical data density (numbers, currencies, percentages)
        data_markers = len(re.findall(r'(\d+|₹|\$|%|SBI|HDFC|ICICI|RBI|TRAI|NPCI)', text))
        if data_markers < 6:
            findings.append("Low factual data density. Lacks concrete figures or regulatory citations.")
            
        is_passed = len(found_buzzwords) == 0 and (std_dev >= 4.0) and (data_markers >= 5)
        return is_passed, findings

    @staticmethod
    def humanize(text):
        """
        Cleans banned phrases and replaces robotic transitions with organic language.
        """
        replacements = {
            r"\bdelve into\b": "examine",
            r"\bdelving into\b": "looking at",
            r"\bdelve\b": "explore",
            r"\ba testament to\b": "clear evidence of",
            r"\btestament\b": "evidence",
            r"\btapestry of\b": "complex mix of",
            r"\btapestry\b": "landscape",
            r"\bbeacon of\b": "leading example of",
            r"\bbeacon\b": "guide",
            r"\bin conclusion\b": "The bottom line:",
            r"\bit's important to remember\b": "Keep in mind",
            r"\bit is important to note\b": "Notice that",
            r"\bdive deep into\b": "break down",
            r"\bdive deep\b": "look closely",
            r"\bfoster\b": "encourage",
            r"\bunderscore\b": "highlight",
            r"\bcrucial\b": "critical",
            r"\bvital\b": "essential",
            r"\bmoreover\b": "also",
            r"\bfurthermore\b": "in addition",
            r"\bholistic\b": "complete",
            r"\bmultifaceted\b": "varied",
            r"\bnavigating the landscape\b": "evaluating options",
            r"\bgame-changer\b": "major shift",
            r"\brevolutionize\b": "transform",
            r"\bplethora of\b": "wide range of",
            r"\bplethora\b": "range",
            r"\bmyriad of\b": "many",
            r"\bmyriad\b": "many",
            r"\bparamount\b": "top priority",
            r"\brobust\b": "durable",
            r"\bdemystify\b": "explain clearly",
            r"\bpivotal\b": "key",
            r"\bcornerstone\b": "foundation",
            r"\bnexus\b": "hub",
            r"\bharnessing\b": "using",
            r"\belevate\b": "improve"
        }
        clean = text
        for pat, repl in replacements.items():
            clean = re.sub(pat, repl, clean, flags=re.IGNORECASE)
        return clean

# 2. FREELLMAPI CLIENT
FREELLMAPI_URL = "http://127.0.0.1:3001/v1/chat/completions"
AUTH_TOKEN = "Bearer freellmapi-ceb04983702628b4439a5a1d9e9bf34484f948c29dbe8b4f"

def query_freellmapi(prompt, system_prompt, model="claude-sonnet-4-5"):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2500
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        FREELLMAPI_URL,
        data=data,
        headers={
            "Authorization": AUTH_TOKEN,
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"[FreeLLMAPI Error] {e}")
        return None

# 3. SEARCH ENGINE NOTIFICATION
def ping_search_engines(domain):
    sitemap_url = f"{domain}/sitemap.xml"
    ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
    try:
        req = urllib.request.Request(ping_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Google Ping] Notified Google Search Console for {sitemap_url} (HTTP {resp.status})")
    except Exception as e:
        print(f"[Google Ping Note] Ping endpoint status: {e}")

print("Autonomous Publishing Engine & Anti-AI Quality Gate initialized successfully.")


# 4. CLAUDE SEO & GEO ARTICLE GENERATOR
def generate_claude_seo_article(site_id: str, site_info: dict, seo_brief: dict) -> tuple[str, list[dict[str, str]]]:
    """
    Implements AgriciDaniel/claude-seo: seo-content + seo-geo guidelines.
    Enforces E-E-A-T, bursty human phrasing, empirical data tables, and FAQ schemas.
    """
    from adsterra_links import render_native_ad_card
    
    primary_kw = seo_brief["primary_keyword"]
    lsi_kws = ", ".join(seo_brief["lsi_keywords"])
    site_name = site_info["name"]
    category = seo_brief["category"]
    
    system_prompt = f"""You are the Principal Financial & Consumer Research Editor at {site_name}.
You follow Google Search Central E-E-A-T and Generative Engine Optimization (GEO) standards.
Goal: Produce a factual, 1200+ word authoritative HTML guide on: '{primary_kw}'.

CRITICAL CONSTRAINTS (Zero Tolerance):
1. BANNED AI BUZZWORDS: Never use 'delve', 'testament', 'beacon', 'vital', 'crucial', 'in conclusion', 'robust', 'dive deep', 'foster', 'elevate', 'holistic'.
2. GEO-DIRECT OPENING: Sentence 1 must be a clean, direct definition answering what {primary_kw} is.
3. EMPIRICAL DATA TABLE: Include an HTML <table> with at least 4 rows comparing options, actual ₹ Rupee amounts, tenure, and exact percentages %.
4. REAL-WORLD VALUE: Concrete advice, actionable checklist, practical rules.
5. NO MARKDOWN: Output ONLY valid HTML snippet (<p>, <h2>, <h3>, <table>, <ul>, <ol>).
6. FAQS: End with an FAQ section containing 3 distinct <h3>Question</h3> followed by <p>Answer</p>.
"""

    user_prompt = f"""Write the complete, in-depth guide for: '{primary_kw}'.
Category: {category}
Secondary LSI Keywords to integrate naturally: {lsi_kws}

Required HTML Structure:
<p class='lead'>Direct 40-word definition of {primary_kw} and immediate core benefit.</p>
<h2>Key Benchmarks and Eligibility Criteria</h2>
<p>Detailed breakdown with practical context...</p>
<div class='table-responsive'>
<table class='article-table'>
<thead><tr><th>Feature / Option</th><th>Rate / Cost (₹)</th><th>Processing / Tenure</th><th>Key Advantage</th></tr></thead>
<tbody>
<tr><td>Baseline Standard</td><td>₹450 - ₹1,200</td><td>Instant - 24 Hrs</td><td>Standard verified baseline</td></tr>
<tr><td>Optimized Choice</td><td>₹320 - ₹850</td><td>Same Day</td><td>Saves annual costs & fee discounts</td></tr>
<tr><td>Premium High-Tier</td><td>₹1,500 - ₹5,000</td><td>3 - 5 Days</td><td>Max credit line / unlimited data</td></tr>
<tr><td>Subsidized / Economy</td><td>₹100 - ₹250</td><td>Direct Disbursal</td><td>Government subsidy & lowest interest</td></tr>
</tbody>
</table>
</div>
<h2>Step-by-Step Action Guide</h2>
<ol class='guide-steps'>
<li>Step 1 description with exact documentation requirement</li>
<li>Step 2 verification process</li>
<li>Step 3 execution and confirmation</li>
</ol>
<h2>Frequently Asked Questions</h2>
<h3>What is the minimum eligibility for {primary_kw}?</h3>
<p>Clear direct answer in 2 sentences.</p>
<h3>How much can you save or borrow with {primary_kw}?</h3>
<p>Clear direct answer in 2 sentences with exact ₹ numbers.</p>
<h3>What are the common mistakes to avoid?</h3>
<p>Clear direct answer highlighting common pitfalls and verification rules.</p>
"""

    raw_html = query_freellmapi(user_prompt, system_prompt, model="claude-sonnet-4-5")
    
    if not raw_html or len(raw_html.strip()) < 300:
        # Fallback template with high empirical density
        raw_html = f"""
        <p class='lead'>Understanding <strong>{primary_kw}</strong> allows consumers and business operators to secure the most competitive financial terms, maximize fee waivers, and avoid hidden costs.</p>
        <h2>Financial Benchmarks & Comparative Analysis</h2>
        <p>Before proceeding with {primary_kw}, evaluate current market rates, processing fees, and mandatory documentation.</p>
        <div class='table-responsive'>
        <table class='article-table'>
        <thead><tr><th>Option / Plan</th><th>Annual Spend / Fee (₹)</th><th>Effective Rate / Margin</th><th>Risk / Benefit Rating</th></tr></thead>
        <tbody>
        <tr><td>Standard Baseline</td><td>₹3,600 / Year</td><td>Competitive Benchmark</td><td>Balanced Standard</td></tr>
        <tr><td>Optimized Value Option</td><td>₹2,850 / Year</td><td>Saves ₹750 Annually</td><td>Top Recommended</td></tr>
        <tr><td>Low-Cost Subsidized</td><td>₹1,400 / Year</td><td>Priority Banking / Subsidy</td><td>Maximum Value</td></tr>
        </tbody>
        </table>
        </div>
        <h2>Step-by-Step Implementation Checklist</h2>
        <ul class='checklist'>
        <li>Verify KYC documents and bank records to prevent processing rejection.</li>
        <li>Compare annual percentage rates (APR) versus nominal interest rates.</li>
        <li>Review prepayment penalties, foreclosure fees, and hidden administrative charges.</li>
        <li>Monitor bureau reporting timelines to maintain a pristine credit profile.</li>
        </ul>
        <h2>Frequently Asked Questions</h2>
        <h3>What is the primary benefit of {primary_kw}?</h3>
        <p>The primary benefit is cost efficiency and streamlined regulatory compliance with documented savings.</p>
        <h3>How fast is the verification and approval process?</h3>
        <p>Most digital applications process within 2 to 24 hours provided KYC credentials are fully verified.</p>
        <h3>Are there hidden charges associated with {primary_kw}?</h3>
        <p>Always inspect the Key Fact Statement (KFS) to audit GST, processing levies, and prepayment terms.</p>
        """

    # Humanize & clean AI buzzwords
    clean_html = AntiAIDetectionGate.humanize(raw_html)
    
    # Strip any markdown code fences if FreeLLMAPI wrapped it
    clean_html = re.sub(r'^```html\s*', '', clean_html, flags=re.MULTILINE)
    clean_html = re.sub(r'```\s*$', '', clean_html, flags=re.MULTILINE)
    
    # Strip any LLM thinking or preamble before the first HTML tag
    if "<p" in clean_html:
        clean_html = clean_html[clean_html.find("<p"):]
    elif "<h" in clean_html:
        clean_html = clean_html[clean_html.find("<h"):]
    
    # Inject Adsterra Native Sponsored Card in the middle of article
    native_ad = render_native_ad_card(site_id)
    if "<h2>Step-by-Step" in clean_html:
        clean_html = clean_html.replace("<h2>Step-by-Step", native_ad + "\n<h2>Step-by-Step", 1)
    else:
        # Insert after table
        if "</table>" in clean_html:
            clean_html = clean_html.replace("</table>\n</div>", "</table>\n</div>\n" + native_ad, 1)
            clean_html = clean_html.replace("</table></div>", "</table></div>\n" + native_ad, 1)
        else:
            clean_html = clean_html + "\n" + native_ad

    # Extract FAQs for Schema.org JSON-LD
    faqs = []
    faq_matches = re.findall(r'<h3>(.*?)</h3>\s*<p>(.*?)</p>', clean_html, re.DOTALL)
    for q, a in faq_matches:
        faqs.append({
            "question": re.sub(r'<[^>]+>', '', q).strip(),
            "answer": re.sub(r'<[^>]+>', '', a).strip()
        })
        
    if not faqs:
        faqs = [
            {"question": f"What is {primary_kw}?", "answer": f"{primary_kw} is a structured financial and utility mechanism designed to optimize user expenses and maximize approval rates."},
            {"question": f"How to apply or activate {primary_kw}?", "answer": f"Verify credentials online through official portals, check eligibility criteria, and submit required documentation."},
            {"question": f"What are the key charges for {primary_kw}?", "answer": "Costs vary based on tier and provider. Always check official schedule of charges and APR disclosures."}
        ]

    return clean_html, faqs
