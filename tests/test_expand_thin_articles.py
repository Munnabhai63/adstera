"""
tests/test_expand_thin_articles.py — Unit Tests for scripts/expand_thin_articles.py
"""

from pathlib import Path
import pytest
from unittest.mock import patch

from scripts.expand_thin_articles import (
    count_visible_words,
    expand_single_article,
    update_sitemap_lastmod,
)


def test_count_visible_words():
    html_sample = """
    <html>
      <head>
        <style>body { color: red; }</style>
        <script>console.log("hello");</script>
      </head>
      <body>
        <h1>Hello World</h1>
        <p>This is a test article with seven words.</p>
      </body>
    </html>
    """
    words = count_visible_words(html_sample)
    assert words == 10


def test_update_sitemap_lastmod(tmp_path: Path):
    sitemap = tmp_path / "sitemap.xml"
    sitemap.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://loanraaj.com/test-guide</loc>
    <lastmod>2026-01-01</lastmod>
  </url>
</urlset>""",
        encoding="utf-8",
    )
    ok = update_sitemap_lastmod(sitemap, "loanraaj.com", "test-guide", "2026-11-14")
    assert ok is True
    content = sitemap.read_text(encoding="utf-8")
    assert "<lastmod>2026-11-14</lastmod>" in content


def test_expand_single_article_end_to_end(tmp_path: Path):
    site_dir = tmp_path / "sites" / "loanraaj.com"
    slug_dir = site_dir / "test-loan-guide"
    slug_dir.mkdir(parents=True)
    article_path = slug_dir / "index.html"
    sitemap_path = site_dir / "sitemap.xml"

    article_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>Test Loan Guide | LoanRaaj</title>
  <link rel="canonical" href="https://loanraaj.com/test-loan-guide/">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Test Loan Guide",
    "dateModified": "2026-01-01T00:00:00+05:30"
  }
  </script>
</head>
<body>
  <article>
    <span class="cat-badge">Personal Finance</span>
    <h1>Test Loan Guide</h1>
    <div class="post-content">
      <p>This is a thin article about personal loans.</p>
    </div>
  </article>
</body>
</html>"""
    article_path.write_text(article_content, encoding="utf-8")

    sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://loanraaj.com/test-loan-guide</loc>
    <lastmod>2026-01-01</lastmod>
  </url>
</urlset>"""
    sitemap_path.write_text(sitemap_content, encoding="utf-8")

    before, after, score = expand_single_article(
        path=article_path,
        domain="loanraaj.com",
        slug="test-loan-guide",
        dry_run=False,
    )

    assert before < 600
    assert after >= 1200
    assert score == 100.0

    updated_text = article_path.read_text(encoding="utf-8")
    assert "<title>Test Loan Guide | LoanRaaj</title>" in updated_text
    assert "https://loanraaj.com/test-loan-guide/" in updated_text
    assert 'dateModified": "2026-11-14T12:00:00+05:30"' in updated_text

    updated_sitemap = sitemap_path.read_text(encoding="utf-8")
    assert "<lastmod>2026-11-14</lastmod>" in updated_sitemap


def test_expand_single_article_dry_run(tmp_path: Path):
    site_dir = tmp_path / "sites" / "loanraaj.com"
    slug_dir = site_dir / "test-loan-guide"
    slug_dir.mkdir(parents=True)
    article_path = slug_dir / "index.html"

    original_text = """<!DOCTYPE html>
<html><body><article>
<h1>Test Loan</h1>
<div class="post-content"><p>Short.</p></div>
</article></body></html>"""
    article_path.write_text(original_text, encoding="utf-8")

    before, after, score = expand_single_article(
        path=article_path,
        domain="loanraaj.com",
        slug="test-loan-guide",
        dry_run=True,
    )
    assert before < 600
    assert after >= 1200
    assert score == 100.0
    # Text should remain unchanged
    assert article_path.read_text(encoding="utf-8") == original_text


def test_expand_single_article_refusal_when_score_low(tmp_path: Path):
    site_dir = tmp_path / "sites" / "loanraaj.com"
    slug_dir = site_dir / "test-loan-guide"
    slug_dir.mkdir(parents=True)
    article_path = slug_dir / "index.html"

    article_path.write_text("<!DOCTYPE html><html><body><article><h1>Test</h1><div class=\"post-content\"><p>Short.</p></div></article></body></html>", encoding="utf-8")

    fake_meta = {"score": 85.0, "reasons": ["Incomplete TOC"]}
    with patch("scripts.expand_thin_articles.ContentQualityFinishGate.format_editorial_layout", return_value=("<p>body</p>", [], fake_meta)):
        with pytest.raises(ValueError, match="Content quality gate refused article"):
            expand_single_article(
                path=article_path,
                domain="loanraaj.com",
                slug="test-loan-guide",
                dry_run=False,
            )
