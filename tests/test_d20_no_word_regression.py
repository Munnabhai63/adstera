"""Corpus-wide guard against silent deletion (D20-B).

Enforces:
- Every article's current prose_words >= its value in tests/data/word_baseline.json.
- Zero word regression across the corpus.
"""

import json
import re
from pathlib import Path
import pytest

from scripts.seo_onpage_audit import audit_article

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITES_ROOT = PROJECT_ROOT / "sites"
BASELINE_PATH = PROJECT_ROOT / "tests" / "data" / "word_baseline.json"


def test_no_article_word_regression():
    assert BASELINE_PATH.exists(), f"Missing baseline file at {BASELINE_PATH}"
    
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)
        
    assert len(baseline) == 278, f"Expected 278 baseline articles, found {len(baseline)}"
    
    regressions = []
    for rel_path, min_words in baseline.items():
        # Assert key is relative, not absolute
        assert not re.match(r"^[a-zA-Z]:", rel_path) and not rel_path.startswith("/"), (
            f"Baseline key must be relative POSIX path, got absolute path: {rel_path}"
        )
        
        normalized_rel = rel_path.replace("\\", "/")
        file_path = SITES_ROOT / Path(normalized_rel)
        assert file_path.exists(), f"Article missing: {rel_path} -> {file_path}"
        
        current_words = audit_article(file_path).get("prose_words") or 0
        if current_words < min_words:
            regressions.append((rel_path, f"current={current_words} < baseline={min_words} (lost {min_words - current_words})"))
            
    assert len(regressions) == 0, f"Found {len(regressions)} articles with word count regressions: {regressions[:5]}"
