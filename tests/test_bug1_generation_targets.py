"""
tests/test_bug1_generation_targets.py — Invariant tests for BUG-1:
Verifies live generation path (generate_claude_seo_article in autopublish_engine.py)
targets 1900-2100 (part1) + 1500-1700 (part2) => 3400-3800 words,
with tokens scaled appropriately and obsolete 750 / 1400-1800 targets eliminated.
"""

import inspect
import autopublish_engine
import autopublish_daemon


def test_generate_claude_seo_article_targets_3000_to_4000():
    source = inspect.getsource(autopublish_engine.generate_claude_seo_article)

    # 1. New targets must be present
    assert "1900" in source, "Part 1 target min must be 1900"
    assert "2100" in source, "Part 1 target max must be 2100"
    assert "1500" in source, "Part 2 target min must be 1500"
    assert "1700" in source, "Part 2 target max must be 1700"
    assert "3400 to 3800" in source or "3400-3800" in source, "Combined target must reference 3400-3800"

    # 2. Obsolete targets must not appear
    assert "750" not in source, "Obsolete 750 word target must be eliminated"
    assert "950 words" not in source, "Obsolete 950 word target must be eliminated"
    assert "650" not in source, "Obsolete 650 word target must be eliminated"
    assert "850 words" not in source, "Obsolete 850 word target must be eliminated"
    assert "1400-1800" not in source, "Obsolete 1400-1800 target must be eliminated"
    assert "1,300 to 1,800" not in source, "Obsolete 1300 to 1800 target must be eliminated"

    # 3. max_tokens must be >= 6000 for part1 and >= 5000 for part2
    assert "max(6000" in source or "6000" in source, "Part 1 max_tokens must be scaled to at least 6000"
    assert "max(5000" in source or "5000" in source, "Part 2 max_tokens must be scaled to at least 5000"


def test_dead_code_generate_article_content_annotated():
    daemon_source = inspect.getsource(autopublish_daemon)
    assert "# DEAD: not called; live path is generate_claude_seo_article()" in daemon_source, (
        "Dead function generate_article_content must be clearly annotated"
    )
