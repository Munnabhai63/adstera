#!/usr/bin/env python3
"""
scripts/fix_breadcrumbs.py — Injects valid Schema.org BreadcrumbList on article pages missing it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup

from scripts.seo_onpage_audit import get_all_article_paths, audit_article
from network_registry import NETWORK_REGISTRY


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)


def determine_category_for_page(soup: BeautifulSoup, domain: str, slug: str, title: str) -> tuple[str, str]:
    """Extract category name and cat_slug from page or domain registry fallback."""
    # 1. Look in post-crumb
    crumb = soup.find(class_="post-crumb")
    if crumb:
        for a in crumb.find_all("a"):
            href = a.get("href", "")
            if "/category/" in href:
                cat_slug = href.split("/category/")[-1].strip("/")
                cat_name = clean_text(a.get_text())
                if cat_name and cat_slug:
                    return cat_name, cat_slug

    # 2. Look for cat-badge
    cat_badge = soup.find(class_="cat-badge")
    if cat_badge:
        cat_name = clean_text(cat_badge.get_text())
        if cat_name:
            return cat_name, slugify(cat_name)

    # 3. Look for any category link in main/article
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "/category/" in href:
            cat_slug = href.split("/category/")[-1].strip("/")
            cat_name = clean_text(a.get_text())
            if cat_name and cat_slug:
                return cat_name, cat_slug

    # 4. Fallback to domain registry
    dom_key = domain.replace(".com", "").strip().lower()
    reg = NETWORK_REGISTRY.get(dom_key, {})
    categories = reg.get("categories", {})

    slug_lower = slug.lower()
    title_lower = title.lower()

    if dom_key == "loanraaj":
        if any(w in slug_lower or w in title_lower for w in ("insurance", "bobtail", "truck", "semi", "commercial-auto")):
            return "Insurance", "insurance"
        if any(w in slug_lower or w in title_lower for w in ("cdl", "trucking", "carrier")):
            return "Carrier", "carrier"
        if any(w in slug_lower or w in title_lower for w in ("business", "machine", "pmegp", "uyegp", "job")):
            return "Business", "business"
        return "Finance", "finance"

    if categories:
        # Check if category name/slug appears in slug or title
        for cat_name, cat_meta in categories.items():
            c_slug = cat_meta.get("slug", slugify(cat_name))
            if c_slug in slug_lower or cat_name.lower() in title_lower:
                return cat_name, c_slug
        # Return first category as default
        first_name = list(categories.keys())[0]
        return first_name, categories[first_name].get("slug", slugify(first_name))

    return "Guides", "guides"


def fix_breadcrumbs_corpus(sites_dir: Path | None = None, dry_run: bool = False) -> tuple[int, int]:
    articles = get_all_article_paths(sites_dir)
    fixed_count = 0
    already_valid = 0

    for path in articles:
        audit_res = audit_article(path)
        if audit_res["breadcrumbs_ok"]:
            already_valid += 1
            continue

        html_text = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "html.parser")

        domain = audit_res["domain"]
        slug = audit_res["slug"]

        # Canonical
        canon_tag = soup.find("link", rel="canonical")
        canonical_url = canon_tag["href"] if (canon_tag and canon_tag.get("href")) else f"https://{domain}/{slug}"

        # Headline
        h1 = soup.find("h1")
        headline = clean_text(h1.get_text()) if h1 else clean_text(audit_res["title"])

        # Category
        cat_name, cat_slug = determine_category_for_page(soup, domain, slug, headline)

        # Build BreadcrumbList JSON-LD
        breadcrumb_data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": f"https://{domain}/",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": cat_name,
                    "item": f"https://{domain}/category/{cat_slug}",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": headline,
                    "item": canonical_url,
                },
            ],
        }

        breadcrumb_json = json.dumps(breadcrumb_data, indent=2, ensure_ascii=False)
        breadcrumb_script = f'\n    <script type="application/ld+json">\n{breadcrumb_json}\n    </script>\n'

        if "</head>" in html_text:
            new_html = html_text.replace("</head>", f"{breadcrumb_script}</head>", 1)
        elif "<body" in html_text:
            new_html = re.sub(r"(<body[^>]*>)", f"{breadcrumb_script}\\1", html_text, count=1)
        else:
            new_html = html_text + breadcrumb_script

        if not dry_run:
            path.write_text(new_html, encoding="utf-8")

        fixed_count += 1

    return fixed_count, already_valid


def main():
    parser = argparse.ArgumentParser(description="Inject valid BreadcrumbList schema on articles missing it.")
    parser.add_argument("--dry-run", action="store_true", help="Report count of files to fix without writing.")
    args = parser.parse_args()

    fixed, valid = fix_breadcrumbs_corpus(dry_run=args.dry_run)
    mode = "DRY-RUN: Would fix" if args.dry_run else "Fixed"
    print(f"[Breadcrumbs] {mode} {fixed} articles; {valid} already had valid breadcrumb schema.")


if __name__ == "__main__":
    main()
