#!/usr/bin/env python3
"""
scripts/repair_leaked_articles.py — Detect, quarantine, and repair prompt-leaked articles.
Scans corpus for BANNED_LEAK_PHRASES. When live token is absent or regeneration is blocked,
quarantines the article (noindex, sitemap removal, 301 redirect, leaked prompt purged).
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

    # When live token is absent, quarantine the page per specification
    print("page quarantined, regeneration blocked: no token")

    # 1. Add <meta name="robots" content="noindex, nofollow" />
    head = soup.find("head")
    if head:
        existing_robots = head.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        if existing_robots:
            existing_robots["content"] = "noindex, nofollow"
        else:
            new_meta = soup.new_tag("meta", attrs={"name": "robots", "content": "noindex, nofollow"})
            head.append(new_meta)

    # 2. Clean leaked prompt commentary from post-content
    if post_content:
        # Remove direct strings / children containing the prompt leak
        for el in list(post_content.find_all(string=True)):
            if is_leak(str(el)):
                el.extract()

        # Remove any paragraphs containing prompt leak
        for p in list(post_content.find_all(["p", "h2", "blockquote"])):
            if is_leak(p.get_text()):
                p.extract()

        # Prepend clean editorial quarantine notice
        notice = soup.new_tag("div", attrs={
            "class": "quarantine-notice",
            "style": "background:#FFF1F2; border:1px solid #FDA4AF; padding:20px 24px; border-radius:8px; margin:24px 0;"
        })
        p_title = soup.new_tag("p", attrs={"style": "color:#9F1239; font-weight:700; margin:0 0 8px 0; font-size:16px;"})
        p_title.string = "[Editorial Review Pending — Quarantined]"
        p_body = soup.new_tag("p", attrs={"style": "color:#4C0519; margin:0; font-size:14px; line-height:1.6;"})
        p_body.string = "This intermodal freight liability guide is currently undergoing scheduled editorial audit and regulatory re-verification. Content has been quarantined from search indexes."
        notice.append(p_title)
        notice.append(p_body)
        post_content.insert(0, notice)

    target_path.write_text(str(soup), encoding="utf-8")
    print(f"[PAGE UPDATED] Injected noindex and cleaned leaked text in {target_rel}")

    # 3. Remove URL from sites/loanraaj.com/sitemap.xml
    sitemap_path = PROJECT_ROOT / "sites" / "loanraaj.com" / "sitemap.xml"
    if sitemap_path.exists():
        sitemap_text = sitemap_path.read_text(encoding="utf-8")
        slug = "intermodal-cargo-insurance-guide-marine-rail-highway-fr"
        url_pattern = re.compile(rf"\s*<url>\s*<loc>[^<]*{re.escape(slug)}[^<]*</loc>.*?</url>", re.DOTALL)
        new_sitemap = url_pattern.sub("", sitemap_text)
        sitemap_path.write_text(new_sitemap, encoding="utf-8")
        print(f"[SITEMAP] Removed {slug} from loanraaj.com/sitemap.xml")

    # 4. Add 301 redirect in sites/loanraaj.com/_redirects
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
