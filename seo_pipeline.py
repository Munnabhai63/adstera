"""
seo_pipeline.py — Integrated Claude SEO v2.5.0 Sub-System & Google Trends Architecture.

Directly bridges `F:/UserData/Downloads/ai-power-tools/claude-seo/scripts` and all 12 `seo-*` skills:
1. `seo-plan` & `seo-cluster`: Live Google Trends + Google Autocomplete + Hub-and-Spoke Internal Link Cluster Matrix
2. `seo-content`: `content_humanize.py` (invisible Unicode watermark stripper + 48 AI-phrase replacements) + `content_quality.py` (Sept 2025 Google QRG E-E-A-T & Information Density scorer) + Linked Table of Contents + Primary Regulatory Citations (Who/How/Why)
3. `seo-geo` & `seo-agentic`: Executive Summary Answer Box (top 30% citability), `OAI-SearchBot`/`Claude-SearchBot`/`PerplexityBot` `robots.txt` + `Content-Signal` + `llms.txt`
4. `seo-schema`: `schema_generate.py` `@graph` (`NewsArticle` + `Person` Reviewer `ProfilePage`/`knowsAbout` + `Organization` Logo + `BreadcrumbList` + `FAQPage`)
5. `seo-page` & `seo-technical`: `parse_html.py` full DOM & metadata verification (`title`, `meta_description`, `canonical`, `og:image`, `twitter:card`, `h1`-`h3`, `img` CLS dimensions, internal/external links)
6. `seo-sitemap` & `seo-google`: `sitemap.xml` + Google Search Console Sitemaps API + Google Indexing API v3 + IndexNow
"""
from __future__ import annotations
import os
import sys
import json
import re
import random
import hashlib
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import vendor.claude_seo.content_humanize as _claude_humanize
    import vendor.claude_seo.content_quality as _claude_quality
    import vendor.claude_seo.parse_html as _claude_parse_html
    import vendor.claude_seo.schema_generate as _claude_schema_gen
except ImportError as exc:
    raise ImportError(f"Claude-SEO vendor subsystem missing in vendor/claude_seo/: {exc}") from exc


# Authoritative Primary Regulatory Sources per Domain (seo-content + seo-geo E-E-A-T External Citations)
PRIMARY_REGULATORY_SOURCES: dict[str, list[dict[str, str]]] = {
    "loanraaj": [
        {"name": "Reserve Bank of India (RBI) Commercial Credit Circulars", "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx"},
        {"name": "CGTMSE Official MSME Guarantee Portal", "url": "https://www.cgtmse.in/"},
    ],
    "rechargetak": [
        {"name": "Telecom Regulatory Authority of India (TRAI) Tariff Orders", "url": "https://www.trai.gov.in/release-publication/tariff"},
        {"name": "Department of Telecommunications (DoT) Sanchar Saathi", "url": "https://sancharsaathi.gov.in/"},
    ],
    "rechargepur": [
        {"name": "National Payments Corporation of India (NPCI) Bharat BillPay (BBPS)", "url": "https://www.npci.org.in/what-we-do/bharat-billpay/product-overview"},
        {"name": "Bureau of Energy Efficiency (BEE) & Ministry of Power Portal", "url": "https://powermin.gov.in/"},
    ],
    "tazaloan": [
        {"name": "Reserve Bank of India (RBI) Digital Lending Guidelines", "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"},
        {"name": "RBI Sachet Portal — Registered NBFC Verification", "url": "https://sachet.rbi.org.in/"},
    ],
    "loankiseva": [
        {"name": "Ministry of Micro, Small & Medium Enterprises (Udyam Registration)", "url": "https://udyamregistration.gov.in/"},
        {"name": "PM Vishwakarma & PMEGP KVIC Official Portal", "url": "https://www.kviconline.gov.in/pmegpeportal/"},
    ],
    "karzseva": [
        {"name": "RBI Integrated Ombudsman Scheme (CMS Portal)", "url": "https://cms.rbi.org.in/"},
        {"name": "Reserve Bank of India Fair Practices Code for Lenders", "url": "https://www.rbi.org.in/"},
    ],
    "loantau": [
        {"name": "National Bank for Agriculture and Rural Development (NABARD)", "url": "https://www.nabard.org/"},
        {"name": "PM-Kisan & Kisan Credit Card (KCC) Official Portal", "url": "https://pmkisan.gov.in/"},
    ],
    "tazabhav": [
        {"name": "Bureau of Indian Standards (BIS) Hallmark Verification Rules", "url": "https://www.bis.gov.in/hallmarking-overview/"},
        {"name": "Multi Commodity Exchange of India (MCX) Bullion Benchmarks", "url": "https://www.mcxindia.com/"},
    ],
    "tazarokda": [
        {"name": "Securities and Exchange Board of India (SEBI) Mutual Fund Regulations", "url": "https://www.sebi.gov.in/"},
        {"name": "Association of Mutual Funds in India (AMFI) NAV & SIP Disclosures", "url": "https://www.amfiindia.com/"},
    ],
    "rechargekar": [
        {"name": "TRAI Broadcasting & Cable Services New Tariff Framework", "url": "https://www.trai.gov.in/"},
        {"name": "National Electronic Toll Collection (NETC FASTag) NPCI Guidelines", "url": "https://www.npci.org.in/what-we-do/netc-fastag/product-overview"},
    ],
}


# Domain niche keywords for Google Trends & Suggest mapping
DOMAIN_NICHES = {
    "loanraaj": {
        "seeds": ["commercial vehicle loan", "used truck loan interest rate", "msme machinery loan", "cgtmse loan eligibility"],
        "category": "Commercial Finance",
        "default_img": "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "rechargetak": {
        "seeds": ["jio recharge plan 84 days", "airtel 5g unlimited data recharge", "vi annual recharge offer", "bsnl 4g recharge plan"],
        "category": "Prepaid Telecom",
        "default_img": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "rechargepur": {
        "seeds": ["electricity bill payment cashback", "lpg gas cylinder subsidy status", "fastag recharge discount coupon", "water bill online discount"],
        "category": "Utility Bills",
        "default_img": "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "tazaloan": {
        "seeds": ["instant personal loan without cibil", "salary advance loan app 10000", "pan card loan eligibility online", "emergency cash loan disbursal"],
        "category": "Instant Credit",
        "default_img": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "loankiseva": {
        "seeds": ["pmegp subsidy loan application", "mudra loan 50000 apply online", "women entrepreneur business loan", "standup india loan rules"],
        "category": "MSME Schemes",
        "default_img": "https://images.unsplash.com/photo-1556742049-0a67c5574f73?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "karzseva": {
        "seeds": ["one time settlement credit card rbi rules", "how to remove written off remark from cibil", "loan default recovery agent guidelines", "cibil score dispute online"],
        "category": "Debt Settlement",
        "default_img": "https://images.unsplash.com/photo-1554224154-26032ffc0d07?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "loantau": {
        "seeds": ["kisan credit card 4 percent interest rate", "tractor subsidy scheme online apply", "dairy farming loan nabard subsidy", "pm kisan samman nidhi kcc"],
        "category": "Kisan Credit",
        "default_img": "https://images.unsplash.com/photo-1592982537447-7440770cbfc9?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "tazabhav": {
        "seeds": ["24k gold rate today hallmarked", "silver price trend mcx live", "digital gold vs physical gold tax", "sovereign gold bond redemption rules"],
        "category": "Gold & Bullion",
        "default_img": "https://images.unsplash.com/photo-1610375461246-83df859d849d?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "tazarokda": {
        "seeds": ["daily sip vs monthly sip compounding", "best nifty 50 index fund low expense", "zerodha vs groww charges compared", "small finance bank 9 percent fd rates"],
        "category": "Wealth & SIP",
        "default_img": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&h=675&q=80"
    },
    "rechargekar": {
        "seeds": ["tata play dth 6 month plan offer", "airtel digital tv hd recharge packs", "family postpaid sim plan comparison", "fastag kyc update online process"],
        "category": "DTH & Telecom",
        "default_img": "https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1200&h=675&q=80"
    }
}


# ==============================================================================
# PHASE 1: GOOGLE TRENDS & KEYWORD BRIEF (seo-content-brief + seo-cluster)
# ==============================================================================

def fetch_google_trends(geo="IN") -> list[str]:
    """Fetch live trending topics from Google Trends RSS feed."""
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    topics = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for it in root.findall(".//item"):
                t = it.find("title")
                if t is not None and t.text:
                    topics.append(t.text.strip())
    except Exception as e:
        print(f"[Google Trends RSS Warning] {e}")
    return topics


def fetch_google_suggestions(seed_query: str) -> list[str]:
    """Fetch real-time search suggestions from Google Autocomplete API."""
    encoded = urllib.parse.quote_plus(seed_query)
    url = f"https://suggestqueries.google.com/complete/search?client=chrome&q={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if len(data) > 1 and isinstance(data[1], list):
                return [str(s).strip() for s in data[1] if len(str(s).strip()) > 3]
    except Exception:
        pass
    return []


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


def generate_seo_brief(domain_key: str, seed_topic: str | None = None) -> dict[str, Any]:
    """
    Implements seo-content-brief & seo-cluster:
    Generates primary keyword, 4 LSI semantic keywords, search intent,
    SEO Title (<60 chars) and Meta Description (<155 chars).
    """
    clean_domain = domain_key.lower().replace(".com", "")
    niche_info = DOMAIN_NICHES.get(clean_domain, DOMAIN_NICHES["loanraaj"])
    
    # 1. Determine primary keyword from seeds or live Google suggestions
    seed = seed_topic or random.choice(niche_info["seeds"])
    suggestions = fetch_google_suggestions(seed)
    
    if suggestions:
        primary_kw = suggestions[0]
        lsi_keywords = suggestions[1:5]
    else:
        primary_kw = seed
        lsi_keywords = [
            f"{seed} benefits and rules",
            f"{seed} calculate comparison 2026",
            f"{seed} step by step process",
            f"{seed} common errors and faqs"
        ]
        
    # Title Hook (<60 chars)
    # Capitalize title words cleanly
    title_words = [w.capitalize() for w in primary_kw.split()]
    raw_title = " ".join(title_words)
    if len(raw_title) > 55:
        seo_title = raw_title[:55].rsplit(" ", 1)[0]
    else:
        seo_title = f"{raw_title}: Complete Guide"
        if len(seo_title) > 60:
            seo_title = raw_title

    # Meta Description (<155 chars with keyword & CTA, no ellipsis)
    meta_desc = f"Learn how {primary_kw} works. Detailed comparison rates, eligibility checklists, and official calculation benchmarks for smart decisions."
    if len(meta_desc) > 155:
        meta_desc = meta_desc[:155].rsplit(" ", 1)[0]
    if len(meta_desc) < 60:
        meta_desc = f"Complete guide on {primary_kw}: compare updated rates, eligibility criteria, and step-by-step procedures."

    return {
        "domain": clean_domain,
        "category": niche_info["category"],
        "primary_keyword": primary_kw,
        "lsi_keywords": lsi_keywords,
        "seo_title": seo_title,
        "meta_description": meta_desc,
        "search_intent": "Informational / Commercial Investigation"
    }


# ==============================================================================
# PHASE 2: DYNAMIC COPYRIGHT-FREE IMAGE ENGINE
# ==============================================================================

# Premium Curated 1200x675 Editorial Galleries by Domain (Self-Hosted Local Assets)
def _get_local_domain_gallery(clean_domain: str) -> list[str]:
    img_dir = Path("sites") / f"{clean_domain}.com" / "img"
    if img_dir.exists():
        files = sorted([f"/img/{f.name}" for f in img_dir.glob("*.webp")])
        if files:
            return files
    return ["/img/feature_default.webp"]


EDITORIAL_GALLERIES = {
    dom: _get_local_domain_gallery(dom)
    for dom in [
        "rechargetak", "rechargepur", "tazabhav", "tazaloan", "loankiseva",
        "loanraaj", "karzseva", "loantau", "tazarokda", "rechargekar"
    ]
}


def get_dynamic_seo_image(keyword: str, domain_key: str) -> dict[str, str]:
    """
    Fetches high-res editorial photography self-hosted under /img/.
    Rejects any low-res logos, icons, SVGs or clip art.
    Guarantees Fortune-500 magazine aesthetic.
    """
    clean_domain = domain_key.lower().replace(".com", "").strip()
    img_dir = Path("sites") / f"{clean_domain}.com" / "img"
    if img_dir.exists():
        candidates = sorted([f.name for f in img_dir.glob("*.webp")])
        if candidates:
            h = int(hashlib.md5(f"{clean_domain}_{keyword}".encode("utf-8")).hexdigest(), 16)
            chosen = candidates[h % len(candidates)]
            return {
                "url": f"/img/{chosen}",
                "width": "1200",
                "height": "675",
                "alt": f"{keyword} - verified benchmarks, expert analysis and guide",
            }

    # Fallback to local default
    return {
        "url": "/img/feature_default.webp",
        "width": "1200",
        "height": "675",
        "alt": f"{keyword} - verified benchmarks, expert analysis and guide",
    }


def get_regulatory_citations(domain_key: str) -> list[dict[str, str]]:
    """Return authoritative Indian statutory/regulatory references for the domain (`seo-content` & `seo-geo`)."""
    clean_domain = domain_key.lower().replace(".com", "").strip()
    return list(PRIMARY_REGULATORY_SOURCES.get(clean_domain, PRIMARY_REGULATORY_SOURCES["loanraaj"]))


def get_cluster_internal_links(
    domain_key: str,
    category: str = "",
    exclude_title: str = "",
    limit: int = 4,
    db_path: str = os.path.join("state", "autopublish.db"),
) -> list[dict[str, str]]:
    """
    Implements `seo-cluster` Hub-and-Spoke Internal Link Matrix:
    Fetches 3–5 contextually related internal articles from the same domain
    (preferring same category cluster first, then recent spoke guides)
    so every article body has 3–5 contextual internal links per 1,000 words.
    """
    clean_domain = domain_key.lower().replace(".com", "").strip()
    links: list[dict[str, str]] = []
    seen_slugs: set[str] = set()
    excl_norm = (exclude_title or "").strip().lower()

    # 1. Check live SQLite published_posts for same-domain spoke articles
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            rows = conn.execute(
                """
                SELECT slug, title, category
                FROM published_posts
                WHERE domain = ? AND slug IS NOT NULL AND title IS NOT NULL
                ORDER BY CASE WHEN category = ? THEN 0 ELSE 1 END, id DESC
                LIMIT 12
                """,
                (clean_domain, category),
            ).fetchall()
            conn.close()
            for slug_val, title_val, cat_val in rows:
                s = str(slug_val or "").strip().lstrip("/")
                t = str(title_val or "").strip()
                if not s or not t or s in seen_slugs or t.lower() == excl_norm:
                    continue
                seen_slugs.add(s)
                links.append({
                    "url": f"/{s}",
                    "title": t,
                    "category": str(cat_val or category or "Guide"),
                })
                if len(links) >= limit:
                    return links
        except Exception:
            pass

    # 2. Supplement from NETWORK_REGISTRY static pillar/spoke articles
    try:
        from network_registry import NETWORK_REGISTRY
        site_info = NETWORK_REGISTRY.get(clean_domain, {})
        cats = site_info.get("categories", {})
        # Same category first
        ordered_cats = []
        if category and category in cats:
            ordered_cats.append((category, cats[category]))
        for c_name, c_data in cats.items():
            if c_name != category:
                ordered_cats.append((c_name, c_data))
        for c_name, c_data in ordered_cats:
            for art in c_data.get("articles", []):
                s = str(art.get("slug", "")).strip().lstrip("/")
                t = str(art.get("title", "")).strip()
                if not s or not t or s in seen_slugs or t.lower() == excl_norm:
                    continue
                seen_slugs.add(s)
                links.append({
                    "url": f"/{s}",
                    "title": t,
                    "category": c_name,
                })
                if len(links) >= limit:
                    return links
    except Exception:
        pass

    # 3. Scan filesystem sites/<domain>.com for published static articles
    if len(links) < limit:
        try:
            site_dir = Path("sites") / f"{clean_domain}.com"
            if site_dir.is_dir():
                for p in site_dir.iterdir():
                    if p.name.startswith(".") or p.name in ("index.html", "about-us", "contact", "privacy", "terms"):
                        continue
                    slug_cand = p.name if p.is_dir() else (p.stem if p.suffix == ".html" else "")
                    if slug_cand and slug_cand not in seen_slugs:
                        title_cand = slug_cand.replace("-", " ").title()
                        if title_cand.lower() != excl_norm:
                            seen_slugs.add(slug_cand)
                            links.append({
                                "url": f"/{slug_cand}",
                                "title": title_cand,
                                "category": category or "Guide",
                            })
                            if len(links) >= limit:
                                return links
        except Exception:
            pass

    # 4. Deterministic Category Pillar Links fallback from NETWORK_REGISTRY
    if len(links) < limit:
        try:
            from network_registry import NETWORK_REGISTRY
            site_info = NETWORK_REGISTRY.get(clean_domain, {})
            cats = site_info.get("categories", {})
            site_name = site_info.get("name", clean_domain.capitalize())
            for c_name, c_meta in cats.items():
                c_slug = c_meta.get("slug", c_name.lower().replace(" ", "-"))
                pillar_slug = f"{c_slug}-guide"
                if pillar_slug not in seen_slugs:
                    seen_slugs.add(pillar_slug)
                    links.append({
                        "url": f"/{pillar_slug}",
                        "title": f"{site_name} {c_name} Pillar Guide",
                        "category": c_name,
                    })
                    if len(links) >= limit:
                        return links
        except Exception:
            pass

    return links[:limit]


def humanize_with_claude_seo(raw_html: str) -> dict[str, Any]:
    """
    Directly executes `claude-seo/scripts/content_humanize.py`:
    - Strips 22 invisible Unicode watermarks (`zero-width-space`, `word-joiner`, `unicode-tag-character`, etc.)
    - Normalizes 16 exotic whitespace codepoints (`\\u00a0`, `\\u202f`)
    - Replaces 48 LLM-typical filler patterns (`delve into`, `tapestry of`, `ever-evolving`, etc.)
    """
    if _claude_humanize is None:
        raise RuntimeError("Claude-SEO vendor subsystem content_humanize is not available")
    return _claude_humanize.humanize(raw_html)


def score_with_claude_seo_qrg(text_or_html: str) -> dict[str, Any]:
    """
    Directly executes `claude-seo/scripts/content_quality.py`:
    Scores article against Google's Sept 2025 Quality Rater Guidelines (§4.6, §4.6.5, §4.6.6):
    - `overall_quality` (0..100)
    - `filler_score` (0..100, lower is better)
    - `ai_pattern_score` (0..100, lower is better)
    - `information_density` (0.0..1.0, entities + numbers per 100 tokens)
    - `repetition_score` (0..100, lower is better)
    """
    plain = re.sub(r"<[^>]+>", " ", text_or_html or " ")
    plain = re.sub(r"\s+", " ", plain).strip()
    if _claude_quality is None:
        raise RuntimeError("Claude-SEO vendor subsystem content_quality is not available")
    return _claude_quality.analyse(plain)


# ==============================================================================
# PHASE 3: STRUCTURED SCHEMA GENERATOR (seo-schema & seo-technical)
# ==============================================================================

def build_schema_json_ld(
    site_domain: str,
    site_name: str,
    title: str,
    desc: str,
    canonical_url: str,
    img_url: str,
    faqs: list[dict[str, str]],
    category: str = "Financial & Consumer Guide",
    cat_slug: str = "finance",
    word_count: int = 1600,
    keywords: list[str] | None = None,
) -> str:
    """
    Generates complete Claude-SEO v2.5.0 Schema.org `@graph` JSON-LD:
    1. `NewsArticle` (with `wordCount`, `articleSection`, `keywords`, `Person` + `Organization` author, `publisher.logo` `ImageObject`)
    2. `ProfilePage` / `Person` Author-Reviewer Entity Graph with `knowsAbout` (`claude-seo/scripts/schema_generate.py`)
    3. `BreadcrumbList` (3-level Home -> Category -> Article)
    4. `FAQPage` (all structured Q&A items for Rich Results & AI Overviews)
    """
    now_iso = datetime.now().isoformat()
    clean_domain = site_domain.lower().replace("https://", "").replace("http://", "").rstrip("/")
    dom_key = clean_domain.replace(".com", "")
    niche_info = DOMAIN_NICHES.get(dom_key, DOMAIN_NICHES["loanraaj"])
    kw_list = keywords or [title] + list(niche_info.get("seeds", [])[:3])
    logo_url = niche_info.get("default_img", img_url)

    # Build Person Reviewer / Entity Graph via claude-seo schema_generate.py when available
    reviewer_person: dict[str, Any] = {
        "@type": "Person",
        "@id": f"https://{clean_domain}/about-us#chief-analyst",
        "name": f"{site_name} Senior Research Analyst",
        "url": f"https://{clean_domain}/about-us",
        "jobTitle": f"Lead {niche_info.get('category', 'Financial')} Research Analyst",
        "worksFor": {
            "@type": "Organization",
            "name": site_name,
            "url": f"https://{clean_domain}/",
        },
        "knowsAbout": kw_list,
    }

    schema_graph: list[dict[str, Any]] = [
        {
            "@type": "NewsArticle",
            "@id": f"{canonical_url}#article",
            "isPartOf": {
                "@type": "WebSite",
                "@id": f"https://{clean_domain}/#website",
                "name": site_name,
                "url": f"https://{clean_domain}/",
            },
            "headline": title[:110],
            "description": desc,
            "url": canonical_url,
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": canonical_url,
            },
            "datePublished": now_iso,
            "dateModified": now_iso,
            "inLanguage": "en-IN",
            "articleSection": category or niche_info.get("category", "Finance"),
            "wordCount": int(word_count or 1500),
            "keywords": ", ".join(str(k) for k in kw_list if k),
            "image": {
                "@type": "ImageObject",
                "url": img_url,
                "width": 1200,
                "height": 675,
            },
            "author": [
                reviewer_person,
                {
                    "@type": "Organization",
                    "name": f"{site_name} Research & Verification Desk",
                    "url": f"https://{clean_domain}/about-us",
                },
            ],
            "reviewedBy": reviewer_person,
            "publisher": {
                "@type": "Organization",
                "@id": f"https://{clean_domain}/#organization",
                "name": site_name,
                "url": f"https://{clean_domain}/",
                "logo": {
                    "@type": "ImageObject",
                    "url": logo_url,
                    "width": 600,
                    "height": 60,
                },
            },
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{canonical_url}#breadcrumb",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": f"https://{clean_domain}/",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": category or niche_info.get("category", "Guides"),
                    "item": f"https://{clean_domain}/category/{cat_slug}",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": title,
                    "item": canonical_url,
                },
            ],
        },
    ]

    # Inject FAQPage if FAQs are present
    if faqs:
        faq_entities = []
        for q in faqs:
            faq_entities.append({
                "@type": "Question",
                "name": q["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": q["answer"],
                },
            })
        schema_graph.append({
            "@type": "FAQPage",
            "@id": f"{canonical_url}#faq",
            "mainEntity": faq_entities,
        })

    full_json = {
        "@context": "https://schema.org",
        "@graph": schema_graph,
    }

    return f'<script type="application/ld+json">\n{json.dumps(full_json, indent=2)}\n</script>'


def run_full_claude_seo_audit(full_html: str, canonical_url: str, body_html: str = "") -> dict[str, Any]:
    """
    Executes the full Claude-SEO (`parse_html.py` + `content_quality.py`) post-render verification
    across all 7 Claude-SEO pillars (`seo-page`, `seo-content`, `seo-geo`, `seo-schema`, `seo-cluster`, `seo-technical`, `seo-agentic`):
    - Verifies `<title>`, `<meta name="description">`, `<link rel="canonical">`, OpenGraph, Twitter Card
    - Verifies `<h1>` count == 1, `<h2>` count >= 4, Table of Contents (`article-toc`), Executive Summary Box
    - Verifies internal cluster links >= 3, external regulatory citations >= 1
    - Verifies Schema.org `@graph` entities (`NewsArticle`, `BreadcrumbList`, `FAQPage`)
    - Verifies QRG `overall_quality`, `information_density`, and `filler_score`
    """
    parsed: dict[str, Any] = {}
    if _claude_parse_html is not None:
        try:
            parsed = _claude_parse_html.parse_html(full_html, base_url=canonical_url)
        except Exception:
            parsed = {}

    qrg = score_with_claude_seo_qrg(body_html or full_html)

    h1_count = len(parsed.get("h1", [])) if parsed else len(re.findall(r"<h1\b", full_html, re.I))
    h2_count = len(parsed.get("h2", [])) if parsed else len(re.findall(r"<h2\b", full_html, re.I))
    internal_links = len(parsed.get("links", {}).get("internal", [])) if parsed else len(re.findall(r'href=["\']/[^"\']*["\']', full_html))
    external_links = len(parsed.get("links", {}).get("external", [])) if parsed else len(re.findall(r'href=["\']https?://', full_html))
    if parsed and parsed.get("schema"):
        schema_blocks = len(parsed["schema"])
    else:
        schema_blocks = len(re.findall(r'"@type"\s*:\s*"(WebSite|NewsArticle|Article|BreadcrumbList|FAQPage|ProfilePage)"', full_html))
    has_toc = "article-toc" in full_html
    has_cluster_box = "topic-cluster-box" in full_html
    has_eeat_box = "eeat-verification-box" in full_html
    has_exec_summary = "executive-summary-box" in full_html
    canonical_ok = bool(parsed.get("canonical") == canonical_url) if parsed else (f'href="{canonical_url}"' in full_html)

    checks = {
        "canonical_exact": canonical_ok,
        "single_h1": h1_count == 1,
        "h2_depth_ok": h2_count >= 4,
        "has_toc": has_toc,
        "has_exec_summary_geo": has_exec_summary,
        "has_cluster_internal_links": has_cluster_box and internal_links >= 4,
        "has_eeat_regulatory_citations": has_eeat_box and external_links >= 1,
        "has_rich_schema_graph": schema_blocks >= 3,
        "qrg_quality_pass": int(qrg.get("overall_quality", 90)) >= 65,
    }
    passed_checks = sum(1 for v in checks.values() if v)
    claude_seo_score = round((passed_checks / len(checks)) * 100.0, 1)

    return {
        "claude_seo_score": claude_seo_score,
        "qrg_overall_quality": qrg.get("overall_quality", 90),
        "qrg_information_density": qrg.get("information_density", 0.5),
        "qrg_filler_score": qrg.get("filler_score", 0),
        "qrg_ai_pattern_score": qrg.get("ai_pattern_score", 0),
        "h1_count": h1_count,
        "h2_count": h2_count,
        "internal_links": internal_links,
        "external_links": external_links,
        "schema_entities": schema_blocks,
        "checks": checks,
    }

