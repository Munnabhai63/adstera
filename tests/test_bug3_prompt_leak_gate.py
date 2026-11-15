"""
tests/test_bug3_prompt_leak_gate.py — Invariant test for BUG-3 & BUG-3b:
1. Verifies that prompt leaks in generated content are caught by BANNED_LEAK_PHRASES,
   deducting 30 points and failing the no_leaks check.
2. Verifies that the quarantined page has no leaked prompt commentary, carries noindex,
   is removed from sitemap.xml, and is routed via 301 redirect.
3. Verifies that the quarantined page contains no banned leak phrases and word count is under 200 words.
"""

from pathlib import Path
from bs4 import BeautifulSoup
from content_quality_gate import ContentQualityFinishGate, BANNED_LEAK_PHRASES


def test_banned_leak_phrases_trigger_gate_failure():
    sample_leak_html = """
    <p class="lead">We need to produce an article on Intermodal Cargo Insurance. Must be 1400-1800 words. Must include clear lead paragraph.</p>
    <h2>1. Regulatory Overview</h2>
    <p>Critical rules require full disclosure of freight liability under statutory guidelines.</p>
    """
    _, _, audit_meta = ContentQualityFinishGate.format_editorial_layout(
        clean_html=sample_leak_html,
        title="Intermodal Cargo Insurance",
        domain_key="loanraaj.com",
        primary_kw="intermodal cargo insurance",
    )

    assert audit_meta["no_leaks"] is False, "Leaked prompt commentary must trigger no_leaks=False"
    assert audit_meta["score"] <= 70.0, "Prompt leak must deduct 30 points from gate score"


def test_quarantined_article_invariants():
    article_path = Path("sites/loanraaj.com/intermodal-cargo-insurance-guide-marine-rail-highway-fr/index.html")
    assert article_path.exists(), "Article file must exist"
    html = article_path.read_text(encoding="utf-8")

    # 1. No leaked prompt text
    assert "We need to produce" not in html, "Leaked prompt phrase 'We need to produce' must be eliminated"
    assert "Must be 1400-1800" not in html, "Leaked prompt phrase 'Must be 1400-1800' must be eliminated"

    # 2. Must carry noindex
    soup = BeautifulSoup(html, "html.parser")
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    assert robots_meta is not None, "Quarantined page must have a robots meta tag"
    assert "noindex" in str(robots_meta.get("content", "")).lower(), "Robots tag must specify noindex"

    # 3. Must be excluded from sitemap.xml
    sitemap = Path("sites/loanraaj.com/sitemap.xml").read_text(encoding="utf-8")
    assert "intermodal-cargo-insurance-guide-marine-rail-highway-fr" not in sitemap, "Quarantined page must be removed from sitemap.xml"

    # 4. Must be redirected in _redirects
    redirects = Path("sites/loanraaj.com/_redirects").read_text(encoding="utf-8")
    assert "/intermodal-cargo-insurance-guide-marine-rail-highway-fr" in redirects, "Quarantined page must be mapped in _redirects"


def test_quarantined_stub_word_count_and_no_leak_phrases():
    """BUG-3b invariant: Quarantined stub must be clean of leak phrases and < 200 words."""
    article_path = Path("sites/loanraaj.com/intermodal-cargo-insurance-guide-marine-rail-highway-fr/index.html")
    html = article_path.read_text(encoding="utf-8")
    html_lower = html.lower()

    for phrase in BANNED_LEAK_PHRASES:
        assert phrase.lower() not in html_lower, f"Banned leak phrase '{phrase}' found in quarantined stub"

    # Check common leaked instruction strings
    assert "Include 3-4 detailed" not in html
    assert "Include a structured comparison table" not in html
    assert "Include actionable step-by-step checklist" not in html

    soup = BeautifulSoup(html, "html.parser")
    words = len(soup.get_text().split())
    assert words < 200, f"Quarantined stub must have < 200 words, found {words}"
