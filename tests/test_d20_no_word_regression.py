"""Corpus-wide guard against silent deletion (D20-B).

Enforces:
- Every article's current prose_words >= its value in tests/data/word_baseline.json.
- Zero word regression across the corpus.
"""

import json
from pathlib import Path
import pytest

from scripts.seo_onpage_audit import audit_article

PROJECT_ROOT = Path(__file__).parent.parent
BASELINE_PATH = PROJECT_ROOT / "tests" / "data" / "word_baseline.json"


def test_no_article_word_regression():
    assert BASELINE_PATH.exists(), f"Missing baseline file at {BASELINE_PATH}"
    
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)
        
    assert len(baseline) == 278, f"Expected 278 baseline articles, found {len(baseline)}"
    
    regressions = []
    for rel_path, min_words in baseline.items():
        file_path = PROJECT_ROOT / "sites" / rel_path
        assert file_path.exists(), f"Article missing: {file_path}"
        
        current_words = audit_article(file_path).get("prose_words") or 0
        if current_words < min_words:
            regressions.append((rel_path, f"current={current_words} < baseline={min_words} (lost {min_words - current_words})"))
            
    assert len(regressions) == 0, f"Found {len(regressions)} articles with word count regressions: {regressions[:5]}"
