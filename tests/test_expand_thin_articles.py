"""
tests/test_expand_thin_articles.py — Unit Tests for scripts/expand_thin_articles.py
"""

from pathlib import Path
import pytest
from unittest.mock import patch
import content_quality_gate

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


def _mock_claude_seo_article(site_id, site_info, seo_brief):
    faqs = [
        {"q": f"What are the interest rates for {site_id} loans?", "a": "Interest rates range from 10.5% to 14.5% based on CIBIL verification score and underwriting guidelines."},
        {"q": "What is the minimum CIBIL score required?", "a": "A minimum credit score of 750 is required for preferential interest rates and zero foreclosure fees."},
        {"q": "Are there any hidden processing charges?", "a": "No, all processing fees and statutory GST charges are transparently listed in the Key Fact Statement."},
        {"q": "How long does digital sanction take?", "a": "Paperless e-KYC approval via Aadhaar and DigiLocker takes between 15 and 45 minutes."},
        {"q": "Can I prepay or foreclose early?", "a": "Under RBI guidelines, floating-rate personal credit facilities incur zero prepayment or foreclosure penalty."},
    ]
    paragraphs = []
    for i in range(1, 14):
        paragraphs.append(
            f"<h2>Comprehensive Analysis Section {i}: Regulatory Framework and Financial Underwriting</h2>\n"
            f"<p>Evaluating personal loan options requires careful assessment of statutory compliance, APR schedules, and total cost of credit. In 2026, Indian financial guidelines mandate transparent disclosure of all applicable charges, repayment tenures ranging from 12 to 84 months, and automated risk scoring mechanisms. Lenders must provide a standardized Key Fact Statement detailing annualized percentage rates before sanction.</p>\n"
            f"<p>Prospective borrowers must also inspect prepayment flexibility, debt-to-income benchmarks, and digital verification norms to ensure financial security across all official channels. Credit risk committees evaluate debt obligations, historical repayment discipline, and CIBIL report disputes before approving unsecured facilities.</p>"
        )
    table = """
    <div class="table-responsive">
        <table class="article-table">
            <thead><tr><th>Lender</th><th>APR</th><th>Tenure</th></tr></thead>
            <tbody><tr><td>State Bank of India</td><td>10.30%</td><td>60 Months</td></tr></tbody>
        </table>
    </div>
    """
    raw_html = "\n\n".join(paragraphs) + "\n\n" + table
    return raw_html, faqs


def test_expand_single_article_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Monkeypatch floor to 1000: D7 legacy test was designed for 1000 floor; production floor is 3000.
    monkeypatch.setattr(content_quality_gate, "ARTICLE_WORD_COUNT_FLOOR", 1000)
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

    with patch("scripts.expand_thin_articles.generate_claude_seo_article", side_effect=_mock_claude_seo_article):
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


def test_expand_single_article_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Monkeypatch floor to 1000: D7 legacy test was designed for 1000 floor; production floor is 3000.
    monkeypatch.setattr(content_quality_gate, "ARTICLE_WORD_COUNT_FLOOR", 1000)
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

    with patch("scripts.expand_thin_articles.generate_claude_seo_article", side_effect=_mock_claude_seo_article):
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
    with patch("scripts.expand_thin_articles.generate_claude_seo_article", return_value=("<p>body</p>", [])):
        with patch("scripts.expand_thin_articles.ContentQualityFinishGate.format_editorial_layout", return_value=("<p>body</p>", [], fake_meta)):
            with pytest.raises(ValueError, match="Content quality gate refused article"):
                expand_single_article(
                    path=article_path,
                    domain="loanraaj.com",
                    slug="test-loan-guide",
                    dry_run=False,
                )


def test_expand_single_article_refusal_when_prose_below_floor(tmp_path: Path):
    site_dir = tmp_path / "sites" / "loanraaj.com"
    slug_dir = site_dir / "test-loan-guide"
    slug_dir.mkdir(parents=True)
    article_path = slug_dir / "index.html"

    original_text = "<!DOCTYPE html><html><body><article><h1>Test</h1><div class=\"post-content\"><p>Short.</p></div></article></body></html>"
    article_path.write_text(original_text, encoding="utf-8")

    short_content = "<h2>1. Heading</h2><p>Very short content that only has a few words.</p>"
    short_faqs = []
    fake_meta = {"score": 100.0, "reasons": []}
    with patch("scripts.expand_thin_articles.generate_claude_seo_article", return_value=(short_content, short_faqs)):
        with patch("scripts.expand_thin_articles.ContentQualityFinishGate.format_editorial_layout", return_value=(short_content, short_faqs, fake_meta)):
            with pytest.raises(ValueError, match="is below ARTICLE_WORD_COUNT_FLOOR"):
                expand_single_article(
                    path=article_path,
                    domain="loanraaj.com",
                    slug="test-loan-guide",
                    dry_run=False,
                )
    # Ensure file was not written, leaving disk byte-identical
    assert article_path.read_text(encoding="utf-8") == original_text


def test_run_batch_expansion_selects_articles_in_gap(tmp_path: Path):
    from scripts.expand_thin_articles import run_batch_expansion
    sites_dir = tmp_path / "sites"
    dom_dir = sites_dir / "loanraaj.com"

    # Article 1: 300 words (thin)
    a1_dir = dom_dir / "a1-thin"
    a1_dir.mkdir(parents=True)
    (a1_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body><article><h1>A1</h1><div class='post-content'><p>" + " ".join(["word"] * 300) + "</p></div></article></body></html>",
        encoding="utf-8",
    )

    # Article 2: 1200 words (in the 600-2999 gap)
    a2_dir = dom_dir / "a2-gap"
    a2_dir.mkdir(parents=True)
    (a2_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body><article><h1>A2</h1><div class='post-content'><p>" + " ".join(["word"] * 1200) + "</p></div></article></body></html>",
        encoding="utf-8",
    )

    # Article 3: 3500 words (above floor)
    a3_dir = dom_dir / "a3-thick"
    a3_dir.mkdir(parents=True)
    (a3_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body><article><h1>A3</h1><div class='post-content'><p>" + " ".join(["word"] * 3500) + "</p></div></article></body></html>",
        encoding="utf-8",
    )

    # With default threshold=3000, both a1 (300) and a2 (1200) must be selected (thin_count == 2)
    res = run_batch_expansion(sites_dir=sites_dir, dry_run=True, limit=0, threshold=3000)
    assert res["thin_count"] == 2

    # With threshold=600, only a1 (300) is selected
    res_600 = run_batch_expansion(sites_dir=sites_dir, dry_run=True, limit=0, threshold=600)
    assert res_600["thin_count"] == 1
