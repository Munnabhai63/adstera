"""
tests/test_bug7_unified_floor_invariants.py — Unified 3000-Word Floor Invariant Tests

Verifies that:
1. content_quality_gate.ARTICLE_WORD_COUNT_FLOOR == 3000 (single source of truth)
2. scripts/seo_onpage_audit.py imports and uses the exact 3000 floor
3. autopublish_engine.py targets sum to >= 3000 words (PART1_TARGET_MIN + PART2_TARGET_MIN >= 3000)
4. All subsystems are strictly synced with content_quality_gate.ARTICLE_WORD_COUNT_FLOOR
"""

from __future__ import annotations

import content_quality_gate
import scripts.seo_onpage_audit as seo_audit
import autopublish_engine


def test_content_quality_gate_word_floor():
    assert content_quality_gate.ARTICLE_WORD_COUNT_FLOOR == 3000
    assert content_quality_gate.ARTICLE_TARGET_MIN == 3000
    assert content_quality_gate.ARTICLE_TARGET_MAX == 4000


def test_seo_onpage_audit_floor_sync():
    # seo_onpage_audit must use the single source of truth floor
    assert seo_audit.ARTICLE_WORD_COUNT_FLOOR == content_quality_gate.ARTICLE_WORD_COUNT_FLOOR
    assert seo_audit.ARTICLE_WORD_COUNT_FLOOR == 3000


def test_autopublish_engine_targets_meet_floor():
    # Generation path targets must meet or exceed the word floor
    assert autopublish_engine.ARTICLE_WORD_COUNT_FLOOR == content_quality_gate.ARTICLE_WORD_COUNT_FLOOR
    assert autopublish_engine.PART1_TARGET_MIN >= 1900
    assert autopublish_engine.PART2_TARGET_MIN >= 1500
    combined_min = autopublish_engine.PART1_TARGET_MIN + autopublish_engine.PART2_TARGET_MIN
    assert combined_min >= content_quality_gate.ARTICLE_WORD_COUNT_FLOOR
    assert combined_min >= 3000
