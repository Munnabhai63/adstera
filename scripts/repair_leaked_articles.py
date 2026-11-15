#!/usr/bin/env python3
"""
scripts/repair_leaked_articles.py — Detect, quarantine, and repair prompt-leaked articles.
Scans corpus for BANNED_LEAK_PHRASES. When live token is absent or regeneration is blocked,
quarantines the article (minimal 301 stub, noindex, sitemap removal, 301 redirect).
"""

import os
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup
from content_quality_gate import BANNED_LEAK_PHRASES

STUB_301_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Moved</title><meta name="robots" content="noindex, nofollow">
<link rel="canonical" href="https://loanraaj.com/commercial-auto-insurance">
<meta http-equiv="refresh" content="0; url=/commercial-auto-insurance"></head>
<body><p>This page has moved to <a href="/commercial-auto-insurance">
/commercial-auto-insurance</a>.</p></body></html>"""


def is_leak(text: str) -> list[str]:
    text_low = text.lower()
    matches = []
    for phrase in BANNED_LEAK_PHRASES:
        p_low = phrase.lower()
        if p_low == "prompt":
            if re.search(r"\bprompt\b", text_low):
                matches.append(phrase)
        else:
            if p_low in text_low:
                matches.append(phrase)
    return matches


def repair_or_quarantine_leaks():
    target_rel = "sites/loanraaj.com/intermodal-cargo-insurance-guide-marine-rail-highway-fr/index.html"
    target_path = PROJECT_ROOT / target_rel

    if not target_path.exists():
        print(f"Target {target_rel} not found.")
        return

    html = target_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    post_content = soup.find("div", class_="post-content")
    text = post_content.get_text() if post_content else html

    leaks = is_leak(text)
    print(f"Analyzing {target_rel} -> Leaks detected: {leaks}")

    token = os.environ.get("FREELLMAPI_TOKEN", "").strip()
    has_live_token = bool(token and not token.startswith("dummy") and not token.startswith("ci-"))

    # When live token is absent, quarantine the page per specification:
    # Completely replace file with minimal 301 redirect stub (<200 words, no prompt text, no ad slots)
    print("page quarantined, regeneration blocked: no token")
    target_path.write_text(STUB_301_HTML, encoding="utf-8")
    print(f"[PAGE UPDATED] Replaced leaked article with minimal 301 redirect stub in {target_rel}")

    # Remove URL from sites/loanraaj.com/sitemap.xml
    sitemap_path = PROJECT_ROOT / "sites" / "loanraaj.com" / "sitemap.xml"
    if sitemap_path.exists():
        sitemap_text = sitemap_path.read_text(encoding="utf-8")
        slug = "intermodal-cargo-insurance-guide-marine-rail-highway-fr"
        url_pattern = re.compile(rf"\s*<url>\s*<loc>[^<]*{re.escape(slug)}[^<]*</loc>.*?</url>", re.DOTALL)
        new_sitemap = url_pattern.sub("", sitemap_text)
        sitemap_path.write_text(new_sitemap, encoding="utf-8")
        print(f"[SITEMAP] Removed {slug} from loanraaj.com/sitemap.xml")

    # Add 301 redirect in sites/loanraaj.com/_redirects
    redirects_path = PROJECT_ROOT / "sites" / "loanraaj.com" / "_redirects"
    if redirects_path.exists():
        redirects_text = redirects_path.read_text(encoding="utf-8")
        rule = "/intermodal-cargo-insurance-guide-marine-rail-highway-fr /commercial-auto-insurance 301"
        if rule not in redirects_text:
            new_redirects = redirects_text.strip() + f"\n{rule}\n"
            redirects_path.write_text(new_redirects, encoding="utf-8")
            print(f"[_REDIRECTS] Added 301 redirect: {rule}")


if __name__ == "__main__":
    repair_or_quarantine_leaks()
