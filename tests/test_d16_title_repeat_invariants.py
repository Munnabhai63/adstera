"""
tests/test_d16_title_repeat_invariants.py — Acceptance verification for D15/D16 title repeated-word invariants.
"""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seo_onpage_audit import audit_article, run_full_onpage_audit
from scripts.verify_round_claims import verify_claim_12_no_repeated_word_titles


def test_d16_audit_detects_consecutive_repeated_words(tmp_path: Path):
    """Verify that title with consecutive repeated word fails audit, while clean title passes."""
    bad_html = tmp_path / "bad.html"
    bad_html.write_text(
        "<!DOCTYPE html><html><head><title>Pm Mudra Loan 2026 Guide Guide Tips | LoanKiSeva</title>"
        "<meta name=\"description\" content=\"Verified 2026 guide on Pm Mudra Loan: Compare interest rates, eligibility criteria, documentation rules, and statutory Reserve Bank benchmarks in India.\">"
        "<link rel=\"canonical\" href=\"https://loankiseva.com/pm-mudra-loan-apply-online-2026-sbi\">"
        "</head><body><h1 class=\"post-h1\">Pm Mudra Loan</h1><div class=\"post-content\">"
        "<figure><img src=\"1.jpg\" alt=\"Alt 1\"></figure><figure><img src=\"2.jpg\" alt=\"Alt 2\"></figure>"
        "<figure><img src=\"3.jpg\" alt=\"Alt 3\"></figure><figure><img src=\"4.jpg\" alt=\"Alt 4\"></figure>"
        "<figure><img src=\"5.jpg\" alt=\"Alt 5\"></figure></div></body></html>",
        encoding="utf-8",
    )

    r_bad = audit_article(bad_html)
    assert r_bad["title_repeated_words_ok"] is False, "Expected title with 'Guide Guide' to fail title_repeated_words check"

    good_html = tmp_path / "good.html"
    good_html.write_text(
        "<!DOCTYPE html><html><head><title>SBI PM Mudra Loan Apply Online 2026 Guide | LoanKiSeva</title>"
        "<meta name=\"description\" content=\"SBI PM Mudra Loan apply online 2026: Compare interest rates, eligibility criteria, required documents, and subsidy benefits under PMMY in India.\">"
        "<link rel=\"canonical\" href=\"https://loankiseva.com/pm-mudra-loan-apply-online-2026-sbi\">"
        "</head><body><h1 class=\"post-h1\">SBI PM Mudra Loan Apply Online 2026: Complete Guide</h1><div class=\"post-content\">"
        "<figure><img src=\"1.jpg\" alt=\"Alt 1\"></figure><figure><img src=\"2.jpg\" alt=\"Alt 2\"></figure>"
        "<figure><img src=\"3.jpg\" alt=\"Alt 3\"></figure><figure><img src=\"4.jpg\" alt=\"Alt 4\"></figure>"
        "<figure><img src=\"5.jpg\" alt=\"Alt 5\"></figure></div></body></html>",
        encoding="utf-8",
    )

    r_good = audit_article(good_html)
    assert r_good["title_repeated_words_ok"] is True, "Expected clean title without repeated words to pass"


def test_d16_corpus_zero_repeated_word_titles():
    """Verify that across the real corpus, zero articles have repeated words in titles."""
    summary = run_full_onpage_audit()
    fails = summary.get("failures", {}).get("title_repeated_words", 0)
    assert fails == 0, f"Found {fails} articles with repeated words in titles"

    ok, msg = verify_claim_12_no_repeated_word_titles()
    assert ok is True, f"Claim 12 failed: {msg}"
    assert "0 verified" in msg
