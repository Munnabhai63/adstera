#!/usr/bin/env python3
"""
scripts/enforce_d7_thin_page_invariants.py — Enforce D7:
Any article page with prose words < 300 MUST NOT render ad slots
('adsterra' or 'container-') or Article/FAQPage JSON-LD schema.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import re
import json

SITES_DIR = Path("sites")
STATIC_SLUGS = {
    "about-us",
    "contact-us",
    "privacy-policy",
    "terms-and-conditions",
    "disclaimer",
    "calculator",
    "emi-calculator",
    "gold-calculator",
    "fd-calculator",
    "sip-calculator",
}

def clean_thin_page(html_file: Path) -> bool:
    raw = html_file.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    
    # Calculate word count
    temp_soup = BeautifulSoup(raw, "html.parser")
    for tag in temp_soup.find_all(["aside", "nav", "header", "footer"]):
        tag.decompose()
    for tag in temp_soup.find_all(class_=re.compile(r"widget|sidebar|author-card|eeat")):
        tag.decompose()
        
    content = (
        temp_soup.find("div", class_="post-body")
        or temp_soup.find("div", class_="post-content")
        or temp_soup.find("article")
    )
    text = content.get_text().strip() if content else ""
    words = len(text.split())
    
    if words >= 300:
        return False  # Substantive page, keep ads and schema
        
    # 1. Remove adsterra wrappers, container divs, and slots
    for el in soup.find_all(class_=re.compile(r"adsterra|container-[a-f0-9]|ad-unit|ad-slot")):
        el.decompose()
        
    for el in soup.find_all(id=re.compile(r"container-[a-f0-9]")):
        el.decompose()
        
    for el in soup.find_all(attrs={"data-ad-slot": True}):
        el.decompose()

    # Remove adsterra scripts
    for s in soup.find_all("script"):
        src = s.get("src", "")
        content_txt = s.string or ""
        if "bauval.org" in src or "atOptions" in content_txt or "adsterra" in content_txt.lower():
            s.decompose()

    # 2. Remove Article and FAQPage from JSON-LD scripts
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except Exception:
            continue
            
        if isinstance(data, dict):
            if data.get("@type") in ("Article", "BlogPosting", "NewsArticle", "FAQPage"):
                s.decompose()
                continue
            elif "@graph" in data:
                filtered_graph = [
                    item for item in data["@graph"]
                    if item.get("@type") not in ("Article", "BlogPosting", "NewsArticle", "FAQPage")
                ]
                if not filtered_graph:
                    s.decompose()
                elif len(filtered_graph) != len(data["@graph"]):
                    data["@graph"] = filtered_graph
                    s.string = json.dumps(data, indent=2)
        elif isinstance(data, list):
            filtered_list = [
                item for item in data
                if item.get("@type") not in ("Article", "BlogPosting", "NewsArticle", "FAQPage")
            ]
            if not filtered_list:
                s.decompose()
            elif len(filtered_list) != len(data):
                s.string = json.dumps(filtered_list, indent=2)

    # 3. Clean raw HTML of comments and CSS mentions of adsterra/container-
    final_raw = str(soup)
    final_raw = re.sub(r'<!--\s*/?ADSTERRA[^\n>]*-->', '', final_raw, flags=re.I)
    final_raw = re.sub(r'<!--\s*Adsterra[^\n>]*-->', '', final_raw, flags=re.I)
    final_raw = re.sub(r'\.adsterra[^{]*\{[^}]*\}', '', final_raw)
    final_raw = re.sub(r'/\*\s*Adsterra[^*]*\*/', '', final_raw, flags=re.I)
    final_raw = re.sub(r'container-[a-f0-9]{8,}', '', final_raw)
    final_raw = re.sub(r'adsterra', '', final_raw, flags=re.I)

    html_file.write_text(final_raw, encoding="utf-8")
    return True

def main():
    cleaned = 0
    total_articles = 0
    for p in sorted(SITES_DIR.glob("*/*/index.html")):
        if p.parent.name in STATIC_SLUGS:
            continue
        total_articles += 1
        if clean_thin_page(p):
            cleaned += 1
            
    print(f"Total articles scanned: {total_articles}, Cleaned thin pages: {cleaned}")

if __name__ == "__main__":
    main()
