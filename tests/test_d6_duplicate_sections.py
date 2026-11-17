from __future__ import annotations

import re
from pathlib import Path
from bs4 import BeautifulSoup
import pytest

from content_quality_gate import (
    count_prose_words,
    merge_duplicate_sections,
    normalize_h2_key,
)
from scripts.seo_onpage_audit import get_all_article_paths, audit_article


def test_merge_collapses_duplicate_h2_titles():
    """Two identical H2s with distinct paragraphs -> one H2, all paragraphs preserved, order intact."""
    raw = """<div class="post-content">
<h2>1. First Section</h2>
<p>Paragraph 1 under first section.</p>
<h2>2. Second Section</h2>
<p>Paragraph under second section.</p>
<h2>1. First Section</h2>
<p>Paragraph 2 under first section moved from duplicate.</p>
</div>"""
    merged = merge_duplicate_sections(raw)
    soup = BeautifulSoup(merged, "html.parser")
    h2s = [h.get_text().strip() for h in soup.find_all("h2")]
    
    # Exactly 2 H2s
    assert len(h2s) == 2
    assert "First Section" in h2s[0]
    assert "Second Section" in h2s[1]
    
    # All paragraphs preserved
    paras = [p.get_text().strip() for p in soup.find_all("p")]
    assert len(paras) == 3
    assert "Paragraph 1 under first section." in paras
    assert "Paragraph under second section." in paras
    assert "Paragraph 2 under first section moved from duplicate." in paras


def test_merge_keeps_single_faq_header():
    """Three 'Frequently Asked Questions' H2s -> exactly one, all H3s retained."""
    raw = """<div class="post-content">
<h2>Frequently Asked Questions</h2>
<div class="faq-card"><h3>Question 1</h3><p>Answer 1</p></div>
<h2>3. Operational Mechanics</h2>
<p>Operational details.</p>
<h2>Frequently Asked Questions</h2>
<div class="faq-card"><h3>Question 2</h3><p>Answer 2</p></div>
<div class="faq-section">
<h2>Frequently Asked Questions</h2>
<div class="faq-card"><h3>Question 3</h3><p>Answer 3</p></div>
</div>
</div>"""
    merged = merge_duplicate_sections(raw)
    soup = BeautifulSoup(merged, "html.parser")
    faq_h2s = [h for h in soup.find_all("h2") if "frequently asked questions" in normalize_h2_key(h.get_text())]
    
    # Exactly one FAQ H2
    assert len(faq_h2s) == 1
    
    # All 3 question cards retained
    h3s = [h.get_text().strip() for h in soup.find_all("h3")]
    assert len(h3s) == 3
    assert "Question 1" in h3s
    assert "Question 2" in h3s
    assert "Question 3" in h3s


def test_merge_renumbers_h2_sequentially():
    """Input 1,2,3,4,5,4,5 -> output 1..7, no repeats."""
    raw = """<div class="post-content">
<h2>1. Alpha</h2><p>P1</p>
<h2>2. Beta</h2><p>P2</p>
<h2>3. Gamma</h2><p>P3</p>
<h2>4. Delta</h2><p>P4</p>
<h2>5. Epsilon</h2><p>P5</p>
<h2>4. Zeta</h2><p>P6</p>
<h2>5. Eta</h2><p>P7</p>
<h2>Frequently Asked Questions</h2>
<div class="faq-card"><h3>Q</h3><p>A</p></div>
</div>"""
    merged = merge_duplicate_sections(raw)
    soup = BeautifulSoup(merged, "html.parser")
    h2s = [h.get_text().strip() for h in soup.find_all("h2")]
    
    # Content headings should be numbered 1..7
    numbered = [h for h in h2s if "Frequently Asked Questions" not in h]
    assert len(numbered) == 7
    expected = [
        "1. Alpha", "2. Beta", "3. Gamma", "4. Delta",
        "5. Epsilon", "6. Zeta", "7. Eta"
    ]
    assert numbered == expected
    assert h2s[-1] == "Frequently Asked Questions"


def test_merge_is_idempotent_and_lossless():
    """Apply twice, HTML identical; prose word count drop <= 2%; zero <p>/<table>/<figure> lost."""
    raw = """<div class="post-content">
<nav class="article-toc"><ol class="toc-list"></ol></nav>
<h2>1. Overview</h2>
<p>This is a comprehensive overview of financial guidelines with multiple verified facts.</p>
<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>
<figure><img src="/img1.jpg" alt="chart"/></figure>
<h2>2. Technical Analysis</h2>
<p>Here is technical analysis covering liquidity ratios and statutory reserve requirements.</p>
<h2>1. Overview</h2>
<p>Additional overview notes extending the original section.</p>
<ol class="guide-steps"><li>Step 1</li><li>Step 2</li></ol>
<h2>Frequently Asked Questions</h2>
<div class="faq-card"><h3>What is the rate?</h3><p>The rate is 8.5%.</p></div>
<h2>Frequently Asked Questions</h2>
</div>"""
    words_orig = count_prose_words(raw)
    p_orig = len(re.findall(r"<p\b", raw))
    tbl_orig = len(re.findall(r"<table\b", raw))
    fig_orig = len(re.findall(r"<figure\b", raw))
    
    out1 = merge_duplicate_sections(raw)
    out2 = merge_duplicate_sections(out1)
    
    # 1. Idempotent: identical on second pass
    assert out1 == out2
    
    # 2. Lossless: prose words drop <= 2%
    words_after = count_prose_words(out1)
    assert words_after >= words_orig * 0.98
    
    # 3. Zero <p>, <table>, <figure> lost
    soup1 = BeautifulSoup(out1, "html.parser")
    assert len(soup1.find_all("p")) >= p_orig
    assert len(soup1.find_all("table")) == tbl_orig
    assert len(soup1.find_all("figure")) == fig_orig


def test_real_site_pages_have_unique_headings():
    """Over the in-scope expanded real site pages: assert 0 pages with duplicate H2 text or multiple FAQ H2s."""
    target_articles = [
        p for p in get_all_article_paths()
        if audit_article(p)["prose_words"] >= 3000
    ]
    assert len(target_articles) >= 12, f"Expected >= 12 articles >= 3000 words, found {len(target_articles)}"
    
    failed_pages = []
    for p in target_articles:
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        pc = soup.find("div", class_="post-content") or soup.find("article") or soup
        h2s = [re.sub(r"\s+", " ", h.get_text()).strip() for h in pc.find_all("h2")]
        
        # Check duplicate H2s
        norm_keys = [normalize_h2_key(h) for h in h2s]
        dups = [k for k in set(norm_keys) if norm_keys.count(k) > 1]
        
        # Check multiple FAQ headers
        faqs = [h for h in h2s if "frequently asked questions" in normalize_h2_key(h)]
        
        # Check number restarts
        numbers = []
        for h in h2s:
            m = re.match(r"^(\d+)[.)]\s*", h)
            if m:
                numbers.append(int(m.group(1)))
        has_restart = any(numbers[i] >= numbers[i+1] for i in range(len(numbers)-1)) if numbers else False
        
        if dups or len(faqs) > 1 or has_restart:
            failed_pages.append({
                "page": f"{p.parent.parent.name}/{p.parent.name}",
                "dups": dups,
                "faq_count": len(faqs),
                "has_restart": has_restart,
            })
            
    assert len(failed_pages) == 0, f"Found {len(failed_pages)} pages with duplicate H2s/FAQ blocks: {failed_pages}"
