#!/usr/bin/env python3
"""
scripts/fix_d10_breadcrumbs.py — Standardize breadcrumbs on 13 affected pages to 2-level (Home > Article)
and add 301 redirect rules for the 12 dead category URLs in site _redirects files.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import json
import re

SITES_DIR = Path("sites")

DEAD_CATEGORIES = {
    "karzseva.com": ["consolidation", "cibil-repair"],
    "loankiseva.com": ["msme-schemes", "subsidies", "working-capital"],
    "loantau.com": ["rural-schemes", "tractor-agri"],
    "rechargekar.com": ["promotions"],
    "tazabhav.com": ["mandi-rates"],
    "tazaloan.com": ["low-interest", "instant-cash"],
    "tazarokda.com": ["dividends-cash"],
}

DEAD_URLS = [
    "https://karzseva.com/category/consolidation",
    "https://karzseva.com/category/cibil-repair",
    "https://loankiseva.com/category/msme-schemes",
    "https://loankiseva.com/category/subsidies",
    "https://loankiseva.com/category/working-capital",
    "https://loantau.com/category/rural-schemes",
    "https://loantau.com/category/tractor-agri",
    "https://rechargekar.com/category/promotions",
    "https://tazabhav.com/category/mandi-rates",
    "https://tazaloan.com/category/low-interest",
    "https://tazaloan.com/category/instant-cash",
    "https://tazarokda.com/category/dividends-cash",
]


def update_breadcrumbs():
    fixed_count = 0
    for html_file in SITES_DIR.glob("*/*/index.html"):
        raw = html_file.read_text(encoding="utf-8", errors="ignore")
        if not any(u in raw for u in DEAD_URLS):
            continue

        soup = BeautifulSoup(raw, "html.parser")
        changed = False

        # 1. Fix JSON-LD BreadcrumbList
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
            except Exception:
                continue

            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if isinstance(item, dict) and item.get("@type") == "BreadcrumbList":
                    elements = item.get("itemListElement", [])
                    new_elements = []
                    pos = 1
                    for el in elements:
                        item_url = el.get("item", "")
                        if any(u == item_url for u in DEAD_URLS):
                            changed = True
                            continue  # drop dead category
                        el["position"] = pos
                        pos += 1
                        new_elements.append(el)
                    item["itemListElement"] = new_elements

            if changed:
                s.string = json.dumps(data, indent=2, ensure_ascii=False)

        # 2. Fix HTML post-crumb
        for crumb in soup.find_all("div", class_="post-crumb"):
            for a in crumb.find_all("a"):
                href = a.get("href", "")
                if any(u.endswith(href) or href in u for u in DEAD_URLS):
                    # remove separator dot following this anchor if present
                    nxt = a.next_sibling
                    if nxt and "•" in str(nxt):
                        nxt.extract()
                    a.decompose()
                    changed = True

        if changed:
            html_file.write_text(str(soup), encoding="utf-8")
            fixed_count += 1
            print(f"Fixed breadcrumb in: {html_file}")

    print(f"Total files updated: {fixed_count}")

    # 3. Add 301 redirects to site _redirects files
    for domain, cat_list in DEAD_CATEGORIES.items():
        redirects_file = SITES_DIR / domain / "_redirects"
        if redirects_file.exists():
            content = redirects_file.read_text(encoding="utf-8")
        else:
            content = ""

        lines = content.splitlines()
        for cat in cat_list:
            rule = f"/category/{cat} / 301"
            if rule not in content and f"/category/{cat}" not in content:
                lines.append(rule)
                print(f"Added redirect to {domain}/_redirects: {rule}")

        redirects_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    update_breadcrumbs()
