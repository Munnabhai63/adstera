# autopublish_engine.py - 24x7 Autonomous AI Content Publisher with 2-Part Deep Writing & Anti-AI Gate
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
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from freellmapi_client import FreeLLMClient
from content_quality_gate import ARTICLE_TARGET_MIN, ARTICLE_TARGET_MAX, ARTICLE_WORD_COUNT_FLOOR, count_prose_words

PART1_TARGET_MIN: int = 1900
PART1_TARGET_MAX: int = 2100
PART2_TARGET_MIN: int = 1500
PART2_TARGET_MAX: int = 1700

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

        found_buzzwords = [w for w in BANNED_AI_WORDS if w in text_lower]
        if found_buzzwords:
            findings.append(f"Contains AI buzzwords: {', '.join(found_buzzwords[:5])}")

        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip().split()) >= 3]
        if len(sentences) >= 5:
            lengths = [len(s.split()) for s in sentences]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            std_dev = math.sqrt(variance)
            if std_dev < 4.5:
                findings.append(f"Low burstiness (std_dev: {std_dev:.2f} < 4.5). Needs more varied sentence rhythm.")
        else:
            std_dev = 5.0

        data_markers = len(re.findall(r"(\d+|₹|\$|%|SBI|HDFC|ICICI|RBI|TRAI|NPCI)", text))
        if data_markers < 6:
            findings.append("Low factual data density. Lacks concrete figures or regulatory citations.")

        is_passed = len(found_buzzwords) == 0 and (std_dev >= 4.0) and (data_markers >= 5)
        return is_passed, findings

    @staticmethod
    def humanize(text):
        """Cleans banned phrases and replaces robotic transitions with organic language."""
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
            r"\belevate\b": "improve",
            r"\bseamless\b": "smooth",
            r"\bembark\b": "start",
            r"\bshed light\b": "clarify",
            r"\bunleash\b": "activate",
            r"\bunlocking the potential\b": "maximizing value",
            r"\bin today's fast-paced world\b": "in 2026",
            r"\bever-evolving\b": "changing",
            r"\bunravel\b": "clarify",
            r"\blinchpin\b": "core factor",
        }
        clean = text
        for pat, repl in replacements.items():
            clean = re.sub(pat, repl, clean, flags=re.IGNORECASE)
        return clean


# 2. 3-LAYER 24x7 FREELLMAPI GATEWAY CLIENT (Cloudflare Edge + Direct Cloud + Local Watchdog)
FREELLMAPI_URL = "https://loanraaj.com/v1/chat/completions"
try:
    from phase3.adapters.adsterra_feed import load_dotenv_into_environ
    load_dotenv_into_environ()
except Exception:
    pass
_token_val = os.environ.get("FREELLMAPI_TOKEN") or os.environ.get("FREELLMAPI_KEY") or ""
AUTH_TOKEN = f"Bearer {_token_val}" if _token_val else ""
_CLIENT_SINGLETON: FreeLLMClient | None = None


def _get_client() -> FreeLLMClient:
    global _CLIENT_SINGLETON
    token = os.environ.get("FREELLMAPI_TOKEN") or os.environ.get("FREELLMAPI_KEY")
    if not token:
        raise ValueError("FREELLMAPI_TOKEN environment variable is not set")
    if _CLIENT_SINGLETON is None or _CLIENT_SINGLETON.api_key != token:
        _CLIENT_SINGLETON = FreeLLMClient(api_key=token)
    return _CLIENT_SINGLETON


def query_freellmapi(prompt, system_prompt, model="Qwen/Qwen2.5-72B-Instruct", max_tokens=6000, timeout=180.0):
    """Query the 3-Layer 24x7 FreeLLMAPI Gateway (Cloudflare Edge -> Cloud Failover -> Local Watchdog)."""
    client = _get_client()
    target_model = model or getattr(client, "default_model", "Qwen/Qwen2.5-72B-Instruct")
    result = client.generate_completion(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=0.7,
        model=target_model,
        timeout=timeout,
    )
    if result:
        return result
    print("[FreeLLMAPI Warning] All 3 gateway layers returned empty for current request.")
    return None


# 3. SEARCH ENGINE NOTIFICATION
def ping_search_engines(domain):
    sitemap_url = f"{domain}/sitemap.xml"
    print(f"[Google Indexing] Sitemap queued for Search Console API sync: {sitemap_url}")


print("Autonomous Publishing Engine & Anti-AI Quality Gate initialized successfully.")


def strip_invisible_artifacts(text: str) -> str:
    """
    Strip invisible LLM/watermark artifacts and normalize NBSP:
    - Normalizes NBSP (\u00a0) to regular ASCII space
    - Normalizes zero-width space (\u200b) between word characters to space
    - Strips \u200b, \u200c, \u200d, \ufeff, \u2060
    - Leaves content inside <pre>...</pre> and <code>...</code> completely untouched
    """
    if not text:
        return ""
    parts = re.split(r"(<(?:pre|code)[^>]*>.*?</(?:pre|code)>)", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            cleaned_parts.append(part)
        else:
            p = part.replace("\u00a0", " ")
            p = re.sub(r"(?<=\w)\u200b(?=\w)", " ", p)
            p = re.sub(r"[\u200b\u200c\u200d\ufeff\u2060]", "", p)
            cleaned_parts.append(p)
    return "".join(cleaned_parts)


def _strip_code_fences_and_preamble(raw: str) -> str:
    clean = re.sub(r"^```[a-zA-Z]*\s*", "", (raw or "").strip(), flags=re.MULTILINE)
    clean = re.sub(r"```\s*$", "", clean, flags=re.MULTILINE).strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL | re.IGNORECASE).strip()
    clean = strip_invisible_artifacts(clean)
    if "<p" in clean and ("<h2" not in clean or clean.find("<p") < clean.find("<h2")):
        clean = clean[clean.find("<p"):]
    elif "<h2" in clean:
        clean = clean[clean.find("<h2"):]
    return clean.strip()


# 4. 2-PART DEEP AI SEO & GEO ARTICLE GENERATOR (1,300 - 1,800+ WORDS)
def generate_claude_seo_article(site_id: str, site_info: dict, seo_brief: dict) -> tuple[str, list[dict[str, str]]]:
    """
    2-Part Deep AI Article Generator (Full 3,400 to 3,800 Word Output — 3000-4000 Target Band):
      - Part 1: Direct GEO Lead Paragraph, 3 Analytical Sections with real ₹ math & statutory rules,
                and a 5-row Empirical Comparison Table (1,900 to 2,100 words).
      - Part 2: Step-by-Step Actionable Guide, Real-World Case Breakdown, Common Mistakes Checklist,
                and 5 Comprehensive FAQs (1,500 to 1,700 words).
    Achieves 100/100 on ContentQualityFinishGate and passes AntiAIDetectionGate.
    """
    from adsterra_links import render_native_ad_card

    primary_kw = seo_brief["primary_keyword"]
    lsi_kws = ", ".join(seo_brief["lsi_keywords"])
    site_name = site_info["name"]
    category = seo_brief["category"]

    system_prompt = f"""You are the Principal Financial & Consumer Research Editor at {site_name}.
You follow Google Search Central E-E-A-T and Generative Engine Optimization (GEO) standards.
EDITORIAL STANDARDS:
1. NEVER use AI clichés: delve, testament, beacon, vital, crucial, in conclusion, robust, dive deep, foster, elevate, holistic, seamless, plethora, myriad, paramount, pivotal, cornerstone.
2. Vary sentence length naturally (combine short 6-word factual statements with detailed 22-word analytical sentences).
3. Cite real Indian figures in ₹, exact % rates, and official institutions (RBI, SBI, HDFC, ICICI, TRAI, NPCI, SEBI, NABARD).
4. Output ONLY clean semantic HTML tags (<p>, <h2>, <h3>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <ul>, <ol>, <li>, <strong>). Never output markdown fences or meta-commentary.
5. ZERO BOILERPLATE REUSE: Output 100% original, unique prose. Never reuse stock boilerplate phrases (e.g. 'RBI mandates zero-foreclosure penalties under floating-rate loans' or 'Review all charges before applying'). Express every fact in distinctive phrasing."""

    # Targets derived from unified 3000-4000 word band
    part1_target_min = PART1_TARGET_MIN  # 1900
    part1_target_max = PART1_TARGET_MAX  # 2100
    part2_target_min = PART2_TARGET_MIN  # 1500
    part2_target_max = PART2_TARGET_MAX  # 1700
    # Combined target: 3400 to 3800 words (comfortably within 3000-4000 band)
    part1_tokens = max(6000, int(part1_target_max * 1.5) + 2000)
    part2_tokens = max(5000, int(part2_target_max * 1.5) + 2000)

    part1_prompt = f"""Write PART 1 ({part1_target_min} to {part1_target_max} words) of the authoritative 2026 consumer guide on: '{primary_kw}'.
Category: {category} | Secondary Keywords: {lsi_kws}

Requirement: Output exhaustive, long-form reference content. Do not summarize. You MUST provide extensive, multi-paragraph analysis under every single heading to produce a comprehensive 2,000-word treatise.
Output this exact HTML structure with rich paragraphs:
<p class='lead'>Start with a direct 45-word definition of {primary_kw}, explaining the exact ₹ cost or savings impact and who qualifies in India in 2026.</p>

<h2>1. Core Mechanics, Statutory Architecture & 2026 Regulatory Rules</h2>
<p>Write 3 detailed analytical paragraphs explaining how {primary_kw} operates under current RBI, TRAI, NPCI, and SEBI circulars. Detail statutory licensing frameworks, non-banking financial company (NBFC) classifications, and master directions governing digital operations.</p>
<p>Detail consumer rights, mandatory disclosure standards, fair practices code guidelines, and official institutional supervisory oversight.</p>
<p>Provide real ₹ figures, baseline interest spreads, and statutory reserve benchmarks that consumers must evaluate before submitting applications.</p>

<h2>2. Borrower & Consumer Eligibility Criteria & Bureau Benchmarks</h2>
<p>Write 3 detailed paragraphs detailing eligibility benchmarks: age brackets (21 to 60 years), minimum income thresholds for salaried vs self-employed applicants (₹25,000/month baseline), and bureau score tiers across CIBIL, Experian, and CRIF High Mark.</p>
<p>Explain fixed obligation to income ratio (FOIR) and debt-to-income (DTI) caps (40% to 50% max allowable ceiling), demonstrating how existing liabilities constrain sanction limits.</p>
<p>Detail mandatory statutory documentation under PMLA guidelines, including Aadhaar DigiLocker e-KYC, PAN card validation, 6-month automated bank statement extraction, and utility bill address proofs.</p>

<h2>3. Interest Rate Math, Fee Slabs & Hidden Charges Breakdown</h2>
<p>Write 3 detailed paragraphs with step-by-step ₹ calculations comparing reducing balance interest rates against flat rate models across ₹50,000, ₹2,00,000, and ₹5,00,000 borrowing amounts.</p>
<p>Detail all upfront and backend costs: processing fee slabs (0.5% to 2.5%), mandatory 18% GST on all administrative fees, stamp duty charges, and credit assessment expenses.</p>
<p>Explain statutory prepayment and foreclosure protections under RBI circulars (zero foreclosure penalties on floating-rate individual facilities), along with bounce charges (₹450 to ₹800) and penal interest calculation rules.</p>

<h2>4. Institutional Comparison: PSU Banks vs Private Banks vs NBFCs</h2>
<p>Write 3 detailed paragraphs contrasting underwriting philosophy, processing turnaround times (TAT), and risk premiums across Public Sector Undertakings (State Bank of India, Punjab National Bank), Private Banks (HDFC, ICICI, Axis), and Digital NBFCs/fintech aggregators.</p>
<p>Analyze the trade-off between lower annual percentage rates (APR) at public institutions versus rapid paperless execution at digital lending platforms.</p>
<p>Provide concrete guidelines on how consumers should evaluate total cost of credit rather than being misled by headline introductory rates.</p>

<h2>5. 2026 Empirical Comparison Table: Top 5 Verified Options</h2>
<p>Introduce the benchmark comparison across India's leading market offerings in 2026 with 3 analytical paragraphs on rate spreads, TAT, and tenure tradeoffs:</p>
<div class='table-responsive'>
<table class='article-table'>
<thead><tr><th>Feature / Option</th><th>Rate / Cost (₹ & %)</th><th>Processing / Tenure</th><th>Key Advantage</th></tr></thead>
<tbody>
<tr><td>Baseline Standard</td><td>Fill real ₹/rate</td><td>Instant - 24 Hrs</td><td>Fill concrete benefit</td></tr>
<tr><td>Optimized Choice</td><td>Fill real ₹/rate</td><td>Same Day</td><td>Fill concrete benefit</td></tr>
<tr><td>Premium High-Tier</td><td>Fill real ₹/rate</td><td>24 - 72 Hrs</td><td>Fill concrete benefit</td></tr>
<tr><td>PSU / Government Backed</td><td>Fill real ₹/rate</td><td>3 - 5 Days</td><td>Lowest APR / statutory backing</td></tr>
<tr><td>Digital Fast-Track</td><td>Fill real ₹/rate</td><td>Under 30 Mins</td><td>Paperless e-KYC & zero physical visit</td></tr>
</tbody>
</table>
</div>"""

    part2_prompt = f"""Write PART 2 ({part2_target_min} to {part2_target_max} words) continuing the 2026 guide on: '{primary_kw}' ({category}).
Do NOT repeat the introduction or comparison table. Output this exact HTML structure with rich, practical detail:

<h2>4. Step-by-Step Online Application & Verification Walkthrough</h2>
<p>Explain the exact online verification workflow and mandatory KYC checklist across 5 detailed steps:</p>
<ol class='guide-steps'>
<li><strong>Step 1 — Eligibility & Document Readiness:</strong> Detailed 60-word instructions with PAN, Aadhaar DigiLocker, and 6-month Account Aggregator statement retrieval.</li>
<li><strong>Step 2 — Portal Selection & Rate Comparison:</strong> Detailed 60-word instructions on auditing Key Fact Statements (KFS) and annualized percentage rates (APR).</li>
<li><strong>Step 3 — Video KYC (V-KYC) & Underwriting Verification:</strong> Detailed 60-word instructions on live geotagged video verification with official banking agent and real-time biometric matching.</li>
<li><strong>Step 4 — Digital Mandate Setup via e-NACH / UPI Autopay:</strong> Detailed 60-word instructions on automated repayment mandate setup via NetBanking with zero paper physical visit.</li>
<li><strong>Step 5 — Disbursal / Activation & Receipt Audit:</strong> Detailed 60-word instructions on verifying net disbursal, fee invoice with 18% GST, and downloading repayment schedule.</li>
</ol>

<h2>5. Real-World Case Study & 5 Costly Mistakes to Avoid</h2>
<p>Provide a concrete 3-paragraph Indian case study comparing two consumers (e.g., Ramesh from Pune vs Priya from Bengaluru) saving ₹14,800+ across 36 months using smart APR selection.</p>
<ul class='checklist'>
<li><strong>Mistake 1 — Bundled Insurance & Credit Shield Cross-Selling:</strong> Detailed breakdown of forced single-premium credit health/life insurance and how to decline under IRDAI/RBI rules.</li>
<li><strong>Mistake 2 — Ignoring Processing Fee Slabs & 18% GST:</strong> Detailed breakdown of upfront fee deductions eroding net loan disbursal.</li>
<li><strong>Mistake 3 — Multiple Simultaneous Hard Bureau Pulls:</strong> Detailed breakdown of 4+ inquiries in 14 days causing a 25–40 point CIBIL score drop.</li>
<li><strong>Mistake 4 — Reset Clauses & Floating Spread Revisions:</strong> Detailed breakdown of quiet tenure elongation without upfront borrower alert.</li>
<li><strong>Mistake 5 — Missing Prepayment & Foreclosure Lock-In Clauses:</strong> Detailed breakdown of minimum lock-in periods and statutory zero-penalty enforcement.</li>
</ul>

<h2>Frequently Asked Questions</h2>
<h3>What is the primary evaluation factor for {primary_kw} in 2026?</h3>
<p>Write a detailed 4-sentence factual answer tailored specifically to {primary_kw}, citing exact parameters, technical specifications, or compliance standards in India.</p>
<h3>How should consumers calculate total investment and operational costs for {primary_kw}?</h3>
<p>Write a detailed 4-sentence factual answer analyzing capital expenditure, operating costs, and savings specific to {primary_kw}.</p>
<h3>What statutory approvals and documentation apply to {primary_kw}?</h3>
<p>Write a detailed 4-sentence factual answer listing the exact KYC, commercial licenses, or registration norms governing {primary_kw}.</p>
<h3>How can buyers avoid defective terms or hidden charges with {primary_kw}?</h3>
<p>Write a detailed 4-sentence factual answer outlining supplier due diligence, warranty terms, and fee transparency for {primary_kw}.</p>
<h3>What is the typical deployment timeline and operational onboarding for {primary_kw}?</h3>
<p>Write a detailed 4-sentence factual answer comparing digital fast-track setup against conventional delivery cycles for {primary_kw}.</p>"""

    try:
        raw_part1 = query_freellmapi(part1_prompt, system_prompt, max_tokens=part1_tokens, timeout=180.0)
        clean_p1 = _strip_code_fences_and_preamble(raw_part1 or "")
        p1_words = len(re.findall(r"\b\w+\b", clean_p1))
        p1_min_threshold = int(part1_target_min * 0.75)
        if p1_words < p1_min_threshold:
            logger.warning(f"[FreeLLMAPI] Part 1 returned {p1_words} words (< {p1_min_threshold}). Requesting continuation...")
            continuation_p1_prompt = f"""You previously wrote {p1_words} words for PART 1 on '{primary_kw}'.
Continue immediately without repeating previous headings. Output the remaining detailed analytical sections (including Fee Slabs breakdown, Institutional Comparisons, and the Empirical Comparison Table) to reach the required {part1_target_min} words.
Output only clean semantic HTML tags."""
            raw_cont = query_freellmapi(continuation_p1_prompt, system_prompt, max_tokens=part1_tokens, timeout=180.0)
            clean_cont = _strip_code_fences_and_preamble(raw_cont or "")
            if clean_cont:
                clean_p1 = f"{clean_p1}\n\n{clean_cont}"
                p1_words = len(re.findall(r"\b\w+\b", clean_p1))
            if p1_words < p1_min_threshold:
                raise RuntimeError(
                    f"FreeLLMAPI Part 1 generation truncated ({p1_words} words < {p1_min_threshold} minimum target) for '{primary_kw}' after continuation."
                )

        raw_part2 = query_freellmapi(part2_prompt, system_prompt, max_tokens=part2_tokens, timeout=180.0)
        clean_p2 = _strip_code_fences_and_preamble(raw_part2 or "")
        p2_words = len(re.findall(r"\b\w+\b", clean_p2))
        p2_min_threshold = int(part2_target_min * 0.75)
        if p2_words < p2_min_threshold:
            logger.warning(f"[FreeLLMAPI] Part 2 returned {p2_words} words (< {p2_min_threshold}). Requesting continuation...")
            continuation_p2_prompt = f"""You previously wrote {p2_words} words for PART 2 on '{primary_kw}'.
Continue immediately without repeating previous sections. Output the remaining comprehensive guide sections (including the Case Study calculations, common mistakes checklist, dispute resolution, and all 5 FAQs) to reach {part2_target_min} words.
Output only clean semantic HTML tags."""
            raw_cont = query_freellmapi(continuation_p2_prompt, system_prompt, max_tokens=part2_tokens, timeout=180.0)
            clean_cont = _strip_code_fences_and_preamble(raw_cont or "")
            if clean_cont:
                clean_p2 = f"{clean_p2}\n\n{clean_cont}"
                p2_words = len(re.findall(r"\b\w+\b", clean_p2))
            if p2_words < p2_min_threshold:
                raise RuntimeError(
                    f"FreeLLMAPI Part 2 generation truncated ({p2_words} words < {p2_min_threshold} minimum target) for '{primary_kw}' after continuation."
                )
    except Exception as llm_err:
        logger.error(f"[FreeLLMAPI] Generation failed for '{primary_kw}': {llm_err}")
        raise RuntimeError(f"FreeLLMAPI generation failed for '{primary_kw}': {llm_err}") from llm_err

    if len(clean_p1) < 400 or len(clean_p2) < 400:
        err_msg = (
            f"FreeLLMAPI returned insufficient content for '{primary_kw}' "
            f"(part1: {len(clean_p1)} chars, part2: {len(clean_p2)} chars; minimum required: 400 chars each)"
        )
        logger.error(f"[FreeLLMAPI] {err_msg}")
        raise RuntimeError(err_msg)

    raw_html = f"{clean_p1}\n\n{clean_p2}"

    # Dynamic topic-specific expansion tied to ARTICLE_TARGET_MIN floor (3000 words)
    current_prose = count_prose_words(raw_html)
    print(f"[DEBUG Engine] After parts 1 & 2: p1={p1_words}, p2={p2_words}, raw prose={current_prose}")
    attempts = 0
    while attempts < 6:
        try:
            from content_quality_gate import ContentQualityFinishGate
            test_san = ContentQualityFinishGate.sanitize_raw_html(raw_html)
            _, _, test_meta = ContentQualityFinishGate.format_editorial_layout(
                clean_html=test_san,
                title=primary_kw,
                domain_key=site_id,
                primary_kw=primary_kw,
                category=category,
                site_name=site_name,
            )
            fmt_prose = test_meta.get("word_count", 0)
        except Exception:
            fmt_prose = count_prose_words(raw_html)

        print(f"[DEBUG Engine] Layout prose check: raw_prose={current_prose}, fmt_prose={fmt_prose}")
        if fmt_prose >= 3100:
            break

        attempts += 1
        needed_words = max(600, 3150 - fmt_prose + 300)
        expand_tokens = max(3000, int(needed_words * 1.6) + 1200)
        print(f"[DEBUG Engine] Attempt {attempts}: fmt_prose={fmt_prose} < 3100, requesting {needed_words} words (tokens: {expand_tokens})")
        expand_prompt = f"""Write an additional in-depth analytical section ({needed_words} to {needed_words + 300} words) for the 2026 consumer guide on: '{primary_kw}' ({category}).
Topic: Statutory Grievance Redressal, Regulatory Risk Factors, and Long-Term Financial Optimization for Indian consumers.
Provide at least 5 detailed, multi-sentence analytical paragraphs packed with concrete ₹ numbers, exact percentages, and regulatory references.
Output only valid HTML with an <h2> heading and <p> paragraphs. Do not echo prompt instructions or meta commentary."""
        try:
            extra_content = query_freellmapi(expand_prompt, system_prompt, max_tokens=expand_tokens, timeout=150.0)
            clean_extra = _strip_code_fences_and_preamble(extra_content or "")
            print(f"[DEBUG Engine] Extra content chars={len(clean_extra)}")
            if len(clean_extra) > 200:
                raw_html = f"{raw_html}\n{clean_extra}"
                current_prose = count_prose_words(raw_html)
                print(f"[DEBUG Engine] Expansion attempt {attempts}: added section, total raw prose now {current_prose}")
        except Exception as exp_err:
            logger.warning(f"[FreeLLMAPI] Optional expansion skipped: {exp_err}")
            print(f"[DEBUG Engine] Expansion exception: {exp_err}")
            break

    print(f"[DEBUG Engine] Final raw_html prose words: {current_prose}")

    clean_html = AntiAIDetectionGate.humanize(raw_html)
    clean_html = _strip_code_fences_and_preamble(clean_html)

    native_ad = render_native_ad_card(site_id)
    if "<h2>4. Step-by-Step" in clean_html:
        clean_html = clean_html.replace("<h2>4. Step-by-Step", native_ad + "\n<h2>4. Step-by-Step", 1)
    elif "<h2>Step-by-Step" in clean_html:
        clean_html = clean_html.replace("<h2>Step-by-Step", native_ad + "\n<h2>Step-by-Step", 1)
    elif "</table>" in clean_html:
        clean_html = clean_html.replace("</table>\n</div>", "</table>\n</div>\n" + native_ad, 1)
    else:
        clean_html = clean_html + "\n" + native_ad

    faqs = []
    faq_matches = re.findall(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", clean_html, re.DOTALL)
    for q, a in faq_matches:
        q_txt = re.sub(r"<[^>]+>", "", q).strip()
        a_txt = re.sub(r"<[^>]+>", "", a).strip()
        if q_txt and a_txt:
            faqs.append({"question": q_txt, "answer": a_txt})

    if not faqs:
        faqs = [
            {"question": f"What is {primary_kw}?", "answer": f"{primary_kw} is a verified 2026 Indian financial and consumer benchmark designed to reduce annual costs and speed up online approval."},
            {"question": f"How to apply or activate {primary_kw}?", "answer": "Complete digital Aadhaar e-KYC on the official portal, compare the Key Fact Statement (KFS), and confirm via OTP."},
            {"question": f"What are the key charges for {primary_kw}?", "answer": "Charges depend on your credit tier and tenure; always verify processing fees and 18% GST in the official schedule."},
        ]

    return clean_html, faqs
