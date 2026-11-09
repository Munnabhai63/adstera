"""
competitor_intel.py — Layer 7: Competitive Intelligence Scraper.

Scrapes and audits competitor publisher sites to extract ad network tags (Adsterra, AdSense,
PropellerAds, Ezoic, etc.), count ad unit density, inspect banner placement layouts,
and surface high-paying commercial intent keywords across the finance and utility verticals.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
import db

# Ensure clean UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("competitor_intel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REPORT_DIR = Path("reports")

# Known High-Paying Commercial Keywords (Finance, Loans, Utilities)
COMMERCIAL_KEYWORDS = {
    "personal loan": {"cpc_tier": "HIGH", "est_cpc": 12.50},
    "instant personal loan": {"cpc_tier": "ULTRA", "est_cpc": 18.00},
    "cash advance": {"cpc_tier": "HIGH", "est_cpc": 14.00},
    "credit repair": {"cpc_tier": "ULTRA", "est_cpc": 22.00},
    "debt consolidation": {"cpc_tier": "ULTRA", "est_cpc": 24.50},
    "bad credit loan": {"cpc_tier": "HIGH", "est_cpc": 15.00},
    "low interest loan": {"cpc_tier": "MEDIUM", "est_cpc": 9.50},
    "instant approval loan": {"cpc_tier": "HIGH", "est_cpc": 13.50},
    "fast approval": {"cpc_tier": "MEDIUM", "est_cpc": 8.00},
    "business loan": {"cpc_tier": "ULTRA", "est_cpc": 28.00},
    "mortgage refinance": {"cpc_tier": "ULTRA", "est_cpc": 32.00},
    "mobile recharge": {"cpc_tier": "UTILITY", "est_cpc": 2.50},
    "cashback offer": {"cpc_tier": "UTILITY", "est_cpc": 3.00},
    "upi deal": {"cpc_tier": "UTILITY", "est_cpc": 2.80},
    "salary advance": {"cpc_tier": "HIGH", "est_cpc": 11.50},
}

# Network Signatures Regex
AD_NETWORK_SIGNATURES = {
    "google_adsense": [
        r"ca-pub-\d+",
        r"adsbygoogle\.js",
        r"pagead2\.googlesyndication\.com",
        r"class=[\"'][^\"']*adsbygoogle",
    ],
    "adsterra": [
        r"profitablegatecpm\.com",
        r"highperformancegate\.com",
        r"profitablecpmrate\.com",
        r"alwingulla\.com",
        r"atrakter\.com",
        r"pl\d+\.(?:profitablegatecpm|profitablecpmrate)",
    ],
    "propellerads": [
        r"propellerads",
        r"monetag",
        r"zoneid",
        r"pushedge",
    ],
    "ezoic": [
        r"ezoic\.net",
        r"ezstandalone",
    ],
    "taboola": [
        r"cdn\.taboola\.com",
        r"trc\.taboola\.com",
    ],
    "outbrain": [
        r"widgets\.outbrain\.com",
    ],
    "media_net": [
        r"contextual\.media\.net",
    ],
    "hilltopads": [
        r"hilltopads",
    ],
}


class CompetitorIntelScraper:
    """
    Analyzes competitor websites, ad monetization density, and content patterns.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_html(self, target: str) -> str:
        """
        Fetches HTML from a live URL or reads from a local file path.
        """
        path = Path(target)
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(target)
            resp.raise_for_status()
            return resp.text

    def detect_ad_networks(self, html: str) -> List[str]:
        """
        Scans HTML source for signatures of major ad networks.
        """
        detected: List[str] = []
        for network, patterns in AD_NETWORK_SIGNATURES.items():
            for pat in patterns:
                if re.search(pat, html, re.IGNORECASE):
                    if network not in detected:
                        detected.append(network)
                    break
        return detected

    def analyze_ad_units(self, html: str) -> Dict[str, Any]:
        """
        Detects ad unit count, formats, and placement locations in the page.
        """
        # Count explicit ad ins tags (AdSense)
        adsense_tags = len(re.findall(r"<ins\s+[^>]*class=[\"'][^\"']*adsbygoogle", html, re.IGNORECASE))

        # Count ad iframes
        ad_iframes = len(re.findall(r"<iframe\s+[^>]*(?:ad|zone|banner|profitable|cpm)", html, re.IGNORECASE))

        # Count banner containers
        ad_containers = len(re.findall(r"class=[\"'][^\"']*(?:ad-unit|ad-banner|fake-ad|ad-container|advertisement)", html, re.IGNORECASE))

        # Placements detected
        placements = []
        if re.search(r"(?:banner-top|top-banner|header-ad|leaderboard)", html, re.IGNORECASE):
            placements.append("above_the_fold_header")
        if re.search(r"(?:in-article|in-content|mid-post|content-ad)", html, re.IGNORECASE):
            placements.append("in_content")
        if re.search(r"(?:sticky-footer|bottom-bar|floating-banner)", html, re.IGNORECASE):
            placements.append("sticky_footer")
        if re.search(r"(?:sidebar-ad|right-rail|side-widget)", html, re.IGNORECASE):
            placements.append("sidebar")

        # Estimate total distinct ad units
        total_units = max(adsense_tags + ad_iframes, ad_containers, 1 if (adsense_tags or ad_iframes or ad_containers) else 0)

        return {
            "total_ad_units": total_units,
            "adsense_tags": adsense_tags,
            "ad_iframes": ad_iframes,
            "ad_containers": ad_containers,
            "placements_detected": placements or ["standard_body"],
        }

    def extract_keywords_and_metadata(self, html: str) -> Dict[str, Any]:
        """
        Extracts title, meta description, word count, and commercial intent keywords.
        """
        # Title
        title_m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).strip() if title_m else ""

        # Meta description
        desc_m = re.search(r"<meta\s+name=[\"']description[\"']\s+content=[\"'](.*?)[\"']", html, re.IGNORECASE)
        description = desc_m.group(1).strip() if desc_m else ""

        # Headings
        h1s = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)]
        h2s = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.IGNORECASE | re.DOTALL)]

        # Body text & word count (strip scripts, styles, tags)
        cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        raw_text = re.sub(r"<[^>]+>", " ", cleaned)
        words = [w for w in re.findall(r"\b[A-Za-z0-9_-]{2,}\b", raw_text)]
        word_count = len(words)
        lower_text = raw_text.lower()

        # Match commercial intent keywords
        matched_keywords: Dict[str, int] = {}
        for kw in COMMERCIAL_KEYWORDS:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\b", lower_text))
            if count > 0:
                matched_keywords[kw] = count

        return {
            "title": title,
            "description": description,
            "headings_h1": h1s,
            "headings_h2": h2s,
            "word_count": word_count,
            "commercial_keywords": matched_keywords,
        }

    def analyze(self, target: str) -> Dict[str, Any]:
        """
        Performs full audit of target page or fixture and returns comprehensive report.
        """
        html = self.fetch_html(target)
        parsed = urlparse(target)
        domain = parsed.netloc if parsed.netloc else Path(target).name

        networks = self.detect_ad_networks(html)
        ads_info = self.analyze_ad_units(html)
        content_info = self.extract_keywords_and_metadata(html)

        # Ad Density (Ads per 1,000 words)
        word_count = content_info["word_count"]
        ad_count = ads_info["total_ad_units"]
        density = (ad_count / max(word_count, 1)) * 1000.0

        if density < 2.0:
            monetization_rating = "CONSERVATIVE (Safe from IVT / High User Experience)"
        elif density <= 4.5:
            monetization_rating = "OPTIMAL (Balanced High Yield & Plausibility)"
        else:
            monetization_rating = "AGGRESSIVE (High Ad Clustering Risk)"

        # High-value keyword summary
        top_kws = sorted(
            content_info["commercial_keywords"].items(),
            key=lambda x: (COMMERCIAL_KEYWORDS.get(x[0], {}).get("est_cpc", 0), x[1]),
            reverse=True,
        )

        report = {
            "target": target,
            "domain": domain,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "detected_ad_networks": networks,
            "ad_unit_count": ad_count,
            "ad_breakdown": ads_info,
            "word_count": word_count,
            "ad_density_per_1k_words": round(density, 2),
            "monetization_strategy": monetization_rating,
            "metadata": {
                "title": content_info["title"],
                "description": content_info["description"],
                "headings_h1": content_info["headings_h1"],
                "headings_h2": content_info["headings_h2"],
            },
            "top_commercial_keywords": [
                {"keyword": k, "count": c, **COMMERCIAL_KEYWORDS.get(k, {})}
                for k, c in top_kws[:6]
            ],
        }

        # Save record to database
        try:
            db.record_competitor_intel(
                url=target,
                domain=domain,
                detected_networks=networks,
                ad_unit_count=ad_count,
                word_count=word_count,
                ad_density=density,
                top_keywords=[k for k, _ in top_kws[:6]],
            )
        except Exception as exc:
            logger.debug("Could not record competitor intel to db: %s", exc)

        # Save JSON artifact report
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        clean_domain = re.sub(r"[^a-zA-Z0-9_-]", "_", domain)
        report_file = REPORT_DIR / f"competitor_intel_{clean_domain}_{ts_slug}.json"
        try:
            report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to write competitor report: %s", exc)

        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="MAHI Layer 7: Competitor Intelligence Scraper")
    parser.add_argument("--url", type=str, help="Live competitor URL to scrape")
    parser.add_argument("--fixture", type=str, help="Local HTML file path fixture to analyze")
    parser.add_argument("--history", action="store_true", help="Show past scanned competitor records")
    args = parser.parse_args()

    scraper = CompetitorIntelScraper()

    if args.history:
        records = db.get_competitor_intel(limit=10)
        print("==================================================================")
        print("  MAHI LAYER 7: COMPETITOR INTELLIGENCE AUDIT HISTORY")
        print(f"  Total Scans Recorded: {len(records)}")
        print("==================================================================")
        for r in records:
            print(f" • [{r['domain']}] Ads: {r['ad_unit_count']} | Networks: {r['detected_networks']} | Density: {r['ad_density']}/1k words")
            print(f"   Keywords: {r['top_keywords']}")
            print(f"   Scanned: {r['scanned_at']}")
            print("------------------------------------------------------------------")
        return

    target = args.url or args.fixture or "tests/fixtures/competitor_page.html"
    print(f"Scraping competitor intelligence for: {target}")
    res = scraper.analyze(target)

    print("==================================================================")
    print("  COMPETITOR INTELLIGENCE AUDIT REPORT")
    print(f"  Target: {res['domain']}")
    print(f"  Detected Networks: {', '.join(res['detected_ad_networks']) or 'None'}")
    print(f"  Total Ad Units: {res['ad_unit_count']}")
    print(f"  Ad Placements: {', '.join(res['ad_breakdown']['placements_detected'])}")
    print(f"  Word Count: {res['word_count']} words")
    print(f"  Ad Density: {res['ad_density_per_1k_words']} ads / 1,000 words")
    print(f"  Monetization Posture: {res['monetization_strategy']}")
    print("  Top High-Paying Commercial Keywords:")
    for kw in res["top_commercial_keywords"]:
        print(f"   • \"{kw['keyword']}\" (Found {kw['count']}x, Tier: {kw.get('cpc_tier', 'N/A')}, Est CPC: ${kw.get('est_cpc', 0):.2f})")
    print("==================================================================")


if __name__ == "__main__":
    main()
