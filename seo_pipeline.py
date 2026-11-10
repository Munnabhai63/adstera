"""
seo_pipeline.py — Integrated Claude SEO 35-Skill Engine & Google Trends Architecture.

Implements the 3-Phase Publishing Workflow:
PHASE 1: Trend Discovery & Keyword Brief (seo-content-brief + seo-cluster)
PHASE 2: Content Generation & E-E-A-T / GEO Optimization (seo-content + seo-geo)
PHASE 3: Structured Data & Technical Schema (seo-schema + seo-technical + seo-sitemap)
"""
from __future__ import annotations
import os
import sys
import json
import re
import random
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

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

    # Meta Description (<155 chars with keyword & CTA)
    meta_desc = f"Learn how {primary_kw} works. Detailed comparison rates, eligibility checklists, and official calculation benchmarks for smart decisions."
    if len(meta_desc) > 155:
        meta_desc = meta_desc[:152] + "..."

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

def get_dynamic_seo_image(keyword: str, domain_key: str) -> dict[str, str]:
    """
    Fetches topic-relevant 100% CC0 / Public-Domain high-res image.
    1. Tries Wikipedia Open REST API for verified encyclopedic lead photo.
    2. Falls back to niche-curated high-res 1200x675 Unsplash photography.
    """
    clean_domain = domain_key.lower().replace(".com", "")
    niche_info = DOMAIN_NICHES.get(clean_domain, DOMAIN_NICHES["loanraaj"])
    
    # Attempt Wikipedia API for top term
    search_term = keyword.split()[0].capitalize()
    wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(search_term)}"
    req = urllib.request.Request(wiki_url, headers={"User-Agent": "TazaNetworkSEO/1.0 (contact@rechargetak.com)"})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            img = data.get("originalimage") or data.get("thumbnail")
            if img and img.get("source") and img.get("width", 0) >= 400:
                return {
                    "url": img["source"],
                    "width": "1200",
                    "height": "675",
                    "alt": f"{keyword} illustrative overview and guide"
                }
    except Exception:
        pass
        
    return {
        "url": niche_info["default_img"],
        "width": "1200",
        "height": "675",
        "alt": f"{keyword} financial guide and comparison benchmark"
    }


# ==============================================================================
# PHASE 3: STRUCTURED SCHEMA GENERATOR (seo-schema & seo-technical)
# ==============================================================================

def build_schema_json_ld(site_domain: str, site_name: str, title: str, desc: str, canonical_url: str, img_url: str, faqs: list[dict[str, str]]) -> str:
    """
    Generates valid Schema.org NewsArticle / BlogPosting + FAQPage + BreadcrumbList JSON-LD.
    Enables rich snippets, expandable FAQ questions, and high search click-through.
    """
    now_iso = datetime.now().isoformat()
    
    schema_graph = [
        {
            "@type": "NewsArticle",
            "@id": f"{canonical_url}#article",
            "isPartOf": {
                "@type": "WebSite",
                "@id": f"https://{site_domain}/#website",
                "name": site_name,
                "url": f"https://{site_domain}/"
            },
            "headline": title,
            "description": desc,
            "url": canonical_url,
            "mainEntityOfPage": canonical_url,
            "datePublished": now_iso,
            "dateModified": now_iso,
            "inLanguage": "en-US",
            "image": {
                "@type": "ImageObject",
                "url": img_url,
                "width": 1200,
                "height": 675
            },
            "author": {
                "@type": "Organization",
                "name": f"{site_name} Research & Verification Desk",
                "url": f"https://{site_domain}/about-us"
            },
            "publisher": {
                "@type": "Organization",
                "name": site_name,
                "url": f"https://{site_domain}/"
            }
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{canonical_url}#breadcrumb",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": f"https://{site_domain}/"
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": title,
                    "item": canonical_url
                }
            ]
        }
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
                    "text": q["answer"]
                }
            })
        schema_graph.append({
            "@type": "FAQPage",
            "@id": f"{canonical_url}#faq",
            "mainEntity": faq_entities
        })
        
    full_json = {
        "@context": "https://schema.org",
        "@graph": schema_graph
    }
    
    return f'<script type="application/ld+json">\n{json.dumps(full_json, indent=2)}\n</script>'
