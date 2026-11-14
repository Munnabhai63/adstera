"""
tests/test_backfill_article_schema.py — DEFECT S2-C verification:
Tests for scripts/backfill_article_schema.py:
1. Compliance detection for Article-type JSON-LD with datePublished and author.
2. Schema injection with headline, author, datePublished, dateModified, publisher.
3. Idempotency across multiple passes on a temporary directory.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.backfill_article_schema import (
    _is_article_compliant,
    inject_article_schema,
    process_articles,
)


def test_is_article_compliant_detection() -> None:
    non_compliant = "<html><head><title>No Schema</title></head><body>Content</body></html>"
    assert _is_article_compliant(non_compliant) is False

    partial_schema = """
    <html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "WebSite", "name": "Test"}
    </script>
    </head></html>
    """
    assert _is_article_compliant(partial_schema) is False

    compliant_schema = """
    <html><head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Test Title",
        "datePublished": "2026-11-01T08:00:00+05:30",
        "author": {"@type": "Person", "name": "Editor"}
    }
    </script>
    </head></html>
    """
    assert _is_article_compliant(compliant_schema) is True


def test_inject_article_schema_structure() -> None:
    raw_html = """<!DOCTYPE html>
<html>
<head>
    <title>Personal Loans Guide | LoanRaaj</title>
    <meta name="description" content="Detailed guide to personal loans.">
    <link rel="canonical" href="https://loanraaj.com/personal-loans-guide">
</head>
<body>
    <h1>Personal Loans Guide</h1>
    <p>Body text here.</p>
</body>
</html>"""

    result = inject_article_schema(raw_html, "loanraaj.com", "personal-loans-guide")
    assert _is_article_compliant(result) is True
    assert "SCHEMA_ARTICLE_INJECTED_START" in result
    assert "LoanRaaj Editorial Team" in result
    assert "datePublished" in result
    assert "dateModified" in result


def test_process_articles_idempotent_tmp_dir(tmp_path: Path) -> None:
    fake_sites = tmp_path / "sites"
    domain_dir = fake_sites / "testbrand.com" / "sample-guide"
    domain_dir.mkdir(parents=True)

    test_file = domain_dir / "index.html"
    test_file.write_text("<html><head><title>Guide</title></head><body>Guide body</body></html>", encoding="utf-8")

    # Pass 1: should update 1 file
    res1 = process_articles(fake_sites, dry_run=False)
    assert res1["updated_files"] == 1
    assert _is_article_compliant(test_file.read_text(encoding="utf-8")) is True

    # Pass 2: should update 0 files (idempotent)
    res2 = process_articles(fake_sites, dry_run=False)
    assert res2["updated_files"] == 0
