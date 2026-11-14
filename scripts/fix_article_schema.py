#!/usr/bin/env python3
"""
scripts/fix_article_schema.py — Consolidate single Article node per page & fix mainEntityOfPage
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup
from scripts.fix_article_images import get_all_articles


def fix_page_schema(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    canonical_link = soup.find("link", rel="canonical")
    if not canonical_link:
        return False
    canonical_url = canonical_link.get("href", "").strip().removesuffix(".html")
    canonical_link["href"] = canonical_url

    scripts = soup.find_all("script", type="application/ld+json")
    if not scripts:
        return False

    modified = False

    # Check for multiple script tags with Article nodes
    parsed_scripts = []
    for s in scripts:
        try:
            d = json.loads(s.string or "")
            parsed_scripts.append((s, d))
        except Exception:
            continue

    # Identify all Article nodes across scripts
    article_nodes = []
    for s, data in parsed_scripts:
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "@graph" in data:
            items = data["@graph"]
        for item in items:
            if isinstance(item, dict) and item.get("@type") in ("Article", "BlogPosting", "NewsArticle"):
                article_nodes.append((s, data, item))

    # Case 1: Multiple Article nodes found (e.g. the 7 pages with duplicate scripts)
    if len(article_nodes) > 1:
        # Keep the one in @graph (usually first script), merge rich fields from the standalone one
        primary_s, primary_data, primary_art = article_nodes[0]
        for sec_s, sec_data, sec_art in article_nodes[1:]:
            for k in ("author", "datePublished", "dateModified", "image", "publisher"):
                if k in sec_art and (k not in primary_art or not primary_art[k]):
                    primary_art[k] = sec_art[k]
            # If secondary article was standalone script, remove that script tag
            if sec_s != primary_s:
                sec_s.decompose()
                modified = True

        # Ensure primary article has correct mainEntityOfPage
        primary_art["mainEntityOfPage"] = {
            "@type": "WebPage",
            "@id": canonical_url
        }
        if "url" in primary_art:
            primary_art["url"] = canonical_url

        primary_s.string = json.dumps(primary_data, indent=2, ensure_ascii=False)
        modified = True

    # Case 2: Exactly 1 Article node, but mainEntityOfPage might be stale or empty
    elif len(article_nodes) == 1:
        s, data, art = article_nodes[0]
        meop = art.get("mainEntityOfPage", "")
        current_url = meop.get("@id", "") if isinstance(meop, dict) else meop

        if current_url != canonical_url or not current_url:
            art["mainEntityOfPage"] = {
                "@type": "WebPage",
                "@id": canonical_url
            }
            if "url" in art:
                art["url"] = canonical_url
            s.string = json.dumps(data, indent=2, ensure_ascii=False)
            modified = True

    # Clean any BreadcrumbList in scripts to remove .html
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "")
        except Exception:
            continue
        items = d.get("@graph", []) if isinstance(d, dict) and "@graph" in d else ([d] if isinstance(d, dict) else d)
        b_mod = False
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "BreadcrumbList":
                for elem in it.get("itemListElement", []):
                    item_url = elem.get("item", "")
                    if item_url.endswith(".html"):
                        elem["item"] = item_url.removesuffix(".html")
                        b_mod = True
        if b_mod:
            s.string = json.dumps(d, indent=2, ensure_ascii=False)
            modified = True

    if modified:
        path.write_text(str(soup), encoding="utf-8")
        return True
    return False


def main():
    articles = get_all_articles(PROJECT_ROOT / "sites")
    print(f"Auditing and repairing schema on {len(articles)} articles...")
    fixed = 0
    for p in articles:
        if fix_page_schema(p):
            fixed += 1
    print(f"Fixed schema on {fixed} pages.")


if __name__ == "__main__":
    main()
