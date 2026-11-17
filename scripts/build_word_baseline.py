#!/usr/bin/env python3
"""Build word count baseline JSON with repo-relative POSIX keys for D20 regression guard."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seo_onpage_audit import get_all_article_paths, audit_article

BASELINE_PATH = PROJECT_ROOT / "tests" / "data" / "word_baseline.json"
SITES_ROOT = PROJECT_ROOT / "sites"


def build_baseline() -> dict[str, int]:
    articles = get_all_article_paths(SITES_ROOT)
    baseline: dict[str, int] = {}

    for path in sorted(articles):
        key = str(path.relative_to(SITES_ROOT)).replace("\\", "/")
        words = audit_article(path).get("prose_words") or 0
        baseline[key] = words

    assert len(baseline) == 278, f"Expected 278 articles, found {len(baseline)}"
    return baseline


def main() -> int:
    baseline = build_baseline()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Strictly LF line endings and formatted JSON
    content = json.dumps(baseline, indent=2) + "\n"
    BASELINE_PATH.write_text(content, encoding="utf-8", newline="\n")
    
    total_words = sum(baseline.values())
    print(f"Generated {len(baseline)} entries in {BASELINE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Total corpus prose words: {total_words}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
