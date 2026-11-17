"""
tests/test_bug2_h1_invariants.py — Invariant test for BUG-2:
Verifies that every single canonical article and static landing guide across sites/ has exactly one non-empty <h1> tag.
"""

from pathlib import Path
from bs4 import BeautifulSoup
from content_quality_gate import is_redirect_stub


def test_every_article_has_exactly_one_non_empty_h1():
    pages = sorted(Path("sites").glob("*/*/index.html"))
    missing_or_multiple_h1 = []

    for path in pages:
        # Ignore layouts / templates / 301 redirect stubs
        if any(x in path.parts for x in ("layouts", "_default", "category")):
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        if is_redirect_stub(html):
            continue
        soup = BeautifulSoup(html, "html.parser")
        h1s = soup.find_all("h1")

        if len(h1s) != 1 or not h1s[0].get_text().strip():
            domain = path.parts[1]
            slug = path.parent.name
            missing_or_multiple_h1.append(f"{domain}/{slug}")

    assert not missing_or_multiple_h1, (
        f"Found {len(missing_or_multiple_h1)} pages with invalid <h1> count (expected 0): {missing_or_multiple_h1}"
    )
