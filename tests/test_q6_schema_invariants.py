#!/usr/bin/env python3
"""
tests/test_q6_schema_invariants.py — Verify Q6 schema invariants:
1. Every page has at most one Article node in its JSON-LD.
2. mainEntityOfPage matches canonical URL exactly (no .html).
3. Total Article nodes across corpus equals total articles (279).
"""

from __future__ import annotations

import json
from pathlib import Path
from bs4 import BeautifulSoup
from scripts.fix_article_images import get_all_articles

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_article_schema_invariants():
    base = PROJECT_ROOT / "sites"
    articles = get_all_articles(base)
    assert len(articles) in (278, 279), f"Expected 278-279 articles, found {len(articles)}"

    total_article_nodes = 0
    multi_article_pages = []
    stale_meop_pages = []

    for p in articles:
        text = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        canonical_link = soup.find("link", rel="canonical")
        assert canonical_link is not None, f"Missing canonical link in {p}"
        canonical_url = canonical_link.get("href", "").strip()
        assert not canonical_url.endswith(".html"), f"Canonical ends with .html in {p}: {canonical_url}"

        scripts = soup.find_all("script", type="application/ld+json")
        page_article_nodes = []

        for s in scripts:
            try:
                data = json.loads(s.string or "")
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if isinstance(item, dict) and item.get("@type") in ("Article", "BlogPosting", "NewsArticle"):
                    page_article_nodes.append(item)
                    total_article_nodes += 1

        assert len(page_article_nodes) <= 1, f"Multiple article nodes in {p}: {len(page_article_nodes)}"
        if len(page_article_nodes) > 1:
            multi_article_pages.append(str(p))

        if len(page_article_nodes) == 1:
            meop = page_article_nodes[0].get("mainEntityOfPage", "")
            meop_url = meop.get("@id", "") if isinstance(meop, dict) else meop
            if meop_url != canonical_url or meop_url.endswith(".html"):
                stale_meop_pages.append((str(p), meop_url, canonical_url))

    assert len(multi_article_pages) == 0, f"Found multi-article pages: {multi_article_pages}"
    assert len(stale_meop_pages) == 0, f"Found stale mainEntityOfPage: {stale_meop_pages}"
    assert total_article_nodes == len(articles), f"Total Article nodes ({total_article_nodes}) != total articles ({len(articles)})"
    print(f"\n[Q6 PROVE SUCCESS] Total articles: {len(articles)} | Total Article nodes: {total_article_nodes} | Stale MEOP: 0 | Multi-Article pages: 0")
