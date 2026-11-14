#!/usr/bin/env python3
"""
tests/test_d8_word_target_invariants.py — Test D8 invariants:
1. Unified constants: ARTICLE_TARGET_MIN=3000, ARTICLE_TARGET_MAX=4000, ARTICLE_WORD_COUNT_FLOOR=3000.
2. Word count floor check: 2999 words rejected with "prose 2999 < 3000, regeneration required", 3001 accepted.
3. Standardized prose word counting: counts only <p> in content, excludes non-prose and shared 19-word boilerplate.
4. Autopublish daemon prompt aligns with 3000-4000 target and eliminates 1400-1800.
"""
from pathlib import Path
import pytest
from content_quality_gate import (
    ARTICLE_TARGET_MIN,
    ARTICLE_TARGET_MAX,
    ARTICLE_WORD_COUNT_FLOOR,
    SHARED_BOILERPLATE_PROSE,
    check_word_count_floor,
    count_prose_words,
    ContentQualityFinishGate,
)


def test_d8_constants_unified():
    assert ARTICLE_TARGET_MIN == 3000
    assert ARTICLE_TARGET_MAX == 4000
    assert ARTICLE_WORD_COUNT_FLOOR == 3000


def test_d8_word_count_floor_rejection_and_acceptance():
    # 2999 words reject with exact required error message
    passed_2999, msg_2999 = check_word_count_floor(2999)
    assert not passed_2999
    assert msg_2999 == "prose 2999 < 3000, regeneration required"

    # 3000 words accept
    passed_3000, _ = check_word_count_floor(3000)
    assert passed_3000

    # 3001 words accept
    passed_3001, msg_3001 = check_word_count_floor(3001)
    assert passed_3001
    assert "target met" in msg_3001


def test_d8_gate_format_editorial_layout_floor_evaluation():
    # Exactly 2999 words across paragraphs
    words_2990 = ["word"] * 2990
    paras_2990 = " ".join(words_2990)
    html_2999 = f"""
    <div class="post-content">
        <h2>Section One</h2>
        <p>{paras_2990}</p>
        <h2>Section Two</h2>
        <p>Three more words.</p>
        <h2>Section Three</h2>
        <p>Three more words.</p>
        <h2>Section Four</h2>
        <p>Three final words.</p>
    </div>
    """
    # 2990 + 3 + 3 + 3 = 2999 words!
    _, _, meta_2999 = ContentQualityFinishGate.format_editorial_layout(
        clean_html=html_2999,
        title="Test Title Optimization",
        domain_key="loanraaj",
        primary_kw="test primary keyword",
        category="Loans",
        site_name="LoanRaaj",
    )
    assert meta_2999["word_count"] == 2999
    assert not meta_2999["passed_floor"]
    assert "prose 2999 < 3000, regeneration required" in meta_2999["floor_message"]

    # 3001 words HTML
    words_3001 = ["word"] * 3001
    paras_3001 = " ".join(words_3001)
    html_3001 = f"""
    <div class="post-content">
        <h2>Section One</h2>
        <p>{paras_3001}</p>
        <h2>Section Two</h2>
        <p>Additional context.</p>
        <h2>Section Three</h2>
        <p>Further analysis.</p>
        <h2>Section Four</h2>
        <p>Final considerations.</p>
    </div>
    """
    _, _, meta_3001 = ContentQualityFinishGate.format_editorial_layout(
        clean_html=html_3001,
        title="Test Title Optimization",
        domain_key="loanraaj",
        primary_kw="test primary keyword",
        category="Loans",
        site_name="LoanRaaj",
    )
    assert meta_3001["passed_floor"]
    assert "regeneration required" not in meta_3001["floor_message"]


def test_d8_count_prose_words_excludes_boilerplate_and_metadata():
    # Verify the boilerplate string is exactly 19 words
    assert len(SHARED_BOILERPLATE_PROSE.split()) == 19

    # HTML containing 50 content words + 19 boilerplate words in an author card or paragraph
    html = f"""
    <div class="post-content">
        <p>{"word " * 50}</p>
        <div class="author-card">
            <p>This author card text has ten words that should be excluded completely.</p>
        </div>
        <aside class="sidebar-col">
            <p>Sidebar text should also be excluded.</p>
        </aside>
        <div class="ad-slot">
            <p>Ad slot text should be excluded.</p>
        </div>
        <p>{SHARED_BOILERPLATE_PROSE}</p>
    </div>
    """
    # Prose count should be exactly 50 words (author card, sidebar, ad slot excluded; boilerplate subtracted)
    prose_count = count_prose_words(html)
    assert prose_count == 50


def test_d8_autopublish_daemon_prompt_no_1400_1800():
    daemon_path = Path("autopublish_daemon.py")
    assert daemon_path.exists()
    content = daemon_path.read_text(encoding="utf-8")
    assert "1400-1800" not in content
    assert "{ARTICLE_TARGET_MIN}-{ARTICLE_TARGET_MAX}" in content
