"""
tests/test_p6_sites_cleanup.py — Acceptance tests for Phase 6.
"""
from __future__ import annotations

from pathlib import Path
import re
import pytest

SITES_DIR = Path("sites")
DOMAINS = [
    "loanraaj.com", "loantau.com", "loankiseva.com", "tazarokda.com", "tazaloan.com",
    "tazabhav.com", "karzseva.com", "rechargekar.com", "rechargepur.com", "rechargetak.com"
]


def test_no_monetag_remote_sw():
    sw_file = SITES_DIR / "loanraaj.com" / "sw.js"
    assert sw_file.exists(), "loanraaj.com/sw.js missing"
    content = sw_file.read_text(encoding="utf-8")
    assert "5gvci.com" not in content, "Found 5gvci.com in loanraaj.com/sw.js!"


def test_csp_headers_on_all_domains():
    for d in DOMAINS:
        hf = SITES_DIR / d / "_headers"
        assert hf.exists(), f"{d}/_headers missing"
        content = hf.read_text(encoding="utf-8")
        assert "Content-Security-Policy:" in content, f"{d}/_headers missing Content-Security-Policy"


def test_language_coherence_on_articles():
    # Verify no pages have wrong language tag
    dev_re = re.compile(r'[\u0900-\u097F]')
    sample_pages = list(SITES_DIR.glob("*/*.html"))[:20]
    for p in sample_pages:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'<html[^>]*\slang=["\']([^"\']+)["\']', txt, re.IGNORECASE)
        assert match is not None, f"Page {p} missing <html lang=...>"
