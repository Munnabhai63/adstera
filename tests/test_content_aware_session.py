"""
tests/test_content_aware_session.py — Acceptance test for Step 4.5: Content-Bot Synergy Loop (ADV-8 & ADV-9).
"""
import pytest
import random
from pathlib import Path
import content_aware_session


def test_get_latest_article():
    art = content_aware_session.get_latest_article("loanraaj.com")
    assert art is not None
    assert "slug" in art
    assert "word_count" in art
    assert art["word_count"] >= 1000
    assert "title_keyword" in art
    assert "loanraaj" in art["url"] or "loanraaj" in art["title_keyword"]


def test_get_latest_article_all_domains():
    domains = [
        "loanraaj.com", "rechargetak.com", "tazabhav.com", "tazaloan.com",
        "loankiseva.com", "karzseva.com", "loantau.com", "tazarokda.com"
    ]
    for d in domains:
        art = content_aware_session.get_latest_article(d)
        assert art["word_count"] > 0
        assert art["slug"]
