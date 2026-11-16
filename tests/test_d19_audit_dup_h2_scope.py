"""Regression test suite for Gap A (D19): Duplicate H2 audit scope across all articles.

Ensures that audit_article() enforces the duplicate-H2 invariant universally,
flagging duplicate H2s even on short (< 3000 words) pages, while cleanly passing
short pages with distinct headings.
"""
from pathlib import Path
import pytest
from scripts.seo_onpage_audit import audit_article


def test_short_page_with_duplicate_h2_is_flagged(tmp_path: Path):
    """A short (< 300 words) page with duplicate H2 headings must fail dup_headings_ok."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Short Loan Guide for Daily Expenses Today | LoanRaaj</title>
  <meta name="description" content="Short loan guide for daily expenses today with eligibility criteria and fast approval online.">
  <link rel="canonical" href="https://loanraaj.com/short-loan-guide/">
</head>
<body>
  <h1>Short Loan Guide for Daily Expenses Today</h1>
  <div class="post-content">
    <h2>1. Eligibility Requirements</h2>
    <p>Basic criteria for short loans including identity proof, age eligibility, and residence address.</p>
    <h2>1. Eligibility Requirements</h2>
    <p>Repeated heading block with additional documentation guidelines and banking details.</p>
  </div>
</body>
</html>
"""
    test_file = tmp_path / "index.html"
    test_file.write_text(html_content, encoding="utf-8")

    res = audit_article(str(test_file))
    assert res["prose_words"] < 3000, f"Expected short page, got {res['prose_words']} words"
    assert res["dup_headings_ok"] is False, "Duplicate H2 on short page was not flagged!"


def test_short_page_with_distinct_h2_passes(tmp_path: Path):
    """A short (< 300 words) page with unique H2 headings must pass dup_headings_ok."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Short Loan Guide for Daily Expenses Today | LoanRaaj</title>
  <meta name="description" content="Short loan guide for daily expenses today with eligibility criteria and fast approval online.">
  <link rel="canonical" href="https://loanraaj.com/short-loan-guide/">
</head>
<body>
  <h1>Short Loan Guide for Daily Expenses Today</h1>
  <div class="post-content">
    <h2>1. Eligibility Requirements</h2>
    <p>Basic criteria for short loans including identity proof, age eligibility, and residence address.</p>
    <h2>2. Document Verification</h2>
    <p>Distinct heading block with additional documentation guidelines and banking details.</p>
  </div>
</body>
</html>
"""
    test_file = tmp_path / "index.html"
    test_file.write_text(html_content, encoding="utf-8")

    res = audit_article(str(test_file))
    assert res["prose_words"] < 3000, f"Expected short page, got {res['prose_words']} words"
    assert res["dup_headings_ok"] is True, "Clean short page failed dup_headings_ok unexpectedly!"
