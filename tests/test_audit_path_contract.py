#!/usr/bin/env python3
"""
tests/test_audit_path_contract.py — Tests for audit_article path flexibility (Defect D6).
Verifies that audit_article works with:
 - Absolute Path
 - Relative Path from PROJECT_ROOT
 - Relative Path from sites/
 - String path from PROJECT_ROOT
 - String path from sites/
"""

import pytest
from pathlib import Path
from scripts.seo_onpage_audit import audit_article, PROJECT_ROOT


SAMPLE_REL_ROOT = "sites/loanraaj.com/bobtail-insurance-guide/index.html"
SAMPLE_REL_SITES = "loanraaj.com/bobtail-insurance-guide/index.html"


def test_audit_article_absolute_path():
    abs_path = (PROJECT_ROOT / SAMPLE_REL_ROOT).resolve()
    res = audit_article(abs_path)
    assert res is not None
    assert res["domain"] == "loanraaj.com"
    assert res["slug"] == "bobtail-insurance-guide"
    assert "title_length_ok" in res


def test_audit_article_relative_path_from_root():
    rel_path = Path(SAMPLE_REL_ROOT)
    res = audit_article(rel_path)
    assert res is not None
    assert res["domain"] == "loanraaj.com"
    assert res["slug"] == "bobtail-insurance-guide"


def test_audit_article_relative_path_from_sites():
    rel_path = Path(SAMPLE_REL_SITES)
    res = audit_article(rel_path)
    assert res is not None
    assert res["domain"] == "loanraaj.com"
    assert res["slug"] == "bobtail-insurance-guide"


def test_audit_article_string_from_root():
    res = audit_article(SAMPLE_REL_ROOT)
    assert res is not None
    assert res["domain"] == "loanraaj.com"
    assert res["slug"] == "bobtail-insurance-guide"


def test_audit_article_string_from_sites():
    res = audit_article(SAMPLE_REL_SITES)
    assert res is not None
    assert res["domain"] == "loanraaj.com"
    assert res["slug"] == "bobtail-insurance-guide"
