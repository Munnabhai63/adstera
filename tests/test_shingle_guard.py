#!/usr/bin/env python3
"""
tests/test_shingle_guard.py — Tests for shingle indexing and domain vocabulary blocklists
"""

import pytest
from pathlib import Path
from shingle_guard import (
    ShingleIndex,
    DuplicateContentError,
    JargonViolationError,
    QualityPatternError,
    validate_domain_vocabulary,
    validate_text_quality
)


def test_clean_fixture_passes(tmp_path):
    index_file = tmp_path / "shingles.json"
    guard = ShingleIndex(index_path=index_file)

    clean_html_1 = """
    <div class="post-content">
        <p>This is an authoritative analysis of modern commercial supply chain infrastructure and financial credit benchmarks in India.</p>
        <p>Evaluating multiple institutional providers ensures borrowers identify competitive annual percentage rates while avoiding undisclosed servicing charges.</p>
    </div>
    """
    count1 = guard.register_article("loanraaj.com", "clean-article-1", clean_html_1)
    assert count1 > 0
    assert len(guard.index) > 0


def test_duplicate_12_word_shingle_fails(tmp_path):
    index_file = tmp_path / "shingles.json"
    guard = ShingleIndex(index_path=index_file)

    shared_text = "evaluating multiple institutional providers ensures borrowers identify competitive annual percentage rates while avoiding undisclosed"
    html_1 = f'<div class="post-content"><p>{shared_text} charges across all public sector banks.</p></div>'
    html_2 = f'<div class="post-content"><p>{shared_text} fees across private commercial lenders.</p></div>'

    guard.register_article("loanraaj.com", "article-1", html_1)

    with pytest.raises(DuplicateContentError) as exc_info:
        guard.register_article("loankiseva.com", "article-2", html_2)
    assert "Duplicate 12-word shingle found" in str(exc_info.value)


def test_telecom_domain_blocklist_rejects_lending_jargon():
    # recharge* must not have KFS, APR, CIBIL, NBFC, foreclosure
    telecom_text = "Check the latest prepaid recharge plan with 84 days validity and high-speed data."
    validate_domain_vocabulary("rechargekar.com", telecom_text)

    bad_telecom_text = "Check your CIBIL score before taking a recharge plan under KFS disclosure."
    with pytest.raises(JargonViolationError) as exc:
        validate_domain_vocabulary("rechargekar.com", bad_telecom_text)
    assert "Forbidden jargon" in str(exc.value)


def test_commodity_domain_blocklist_rejects_lending_jargon():
    # tazabhav must not have personal loan, home loan, NBFC, CIBIL
    clean_commodity = "Today hallmarked 24 karat gold bullion rates opened steady across MCX trading sessions."
    validate_domain_vocabulary("tazabhav.com", clean_commodity)

    bad_commodity = "Apply for a quick personal loan against today gold bullion rate."
    with pytest.raises(JargonViolationError) as exc:
        validate_domain_vocabulary("tazabhav.com", bad_commodity)
    assert "Forbidden jargon" in str(exc.value)


def test_loan_domain_blocklist_rejects_telecom_jargon():
    # loan*, karz* must not have unlimited 5g, 28 days validity, data booster, sim porting
    clean_loan = "Business term loan documentation requires audited financial balance sheets and tax returns."
    validate_domain_vocabulary("loanraaj.com", clean_loan)

    bad_loan = "Get an instant loan with unlimited 5g data booster and 28 days validity."
    with pytest.raises(JargonViolationError) as exc:
        validate_domain_vocabulary("loanraaj.com", bad_loan)
    assert "Forbidden jargon" in str(exc.value)


def test_quality_guard_rejects_lorem_ipsum_and_looping():
    with pytest.raises(QualityPatternError):
        validate_text_quality("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")

    with pytest.raises(QualityPatternError):
        validate_text_quality("instant loan approval fast instant loan approval fast instant loan approval fast for everyone.")


def test_quality_gate_finish_gate_rejects_corpus_duplicate_paragraph(tmp_path, monkeypatch):
    """NEGATIVE TEST: article containing an existing corpus paragraph is rejected by quality gate."""
    import shingle_guard
    from content_quality_gate import ContentQualityFinishGate

    test_index = tmp_path / "test_prose_shingles.json"
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", test_index)

    # 1. Register an existing published article in the corpus
    existing_html = """
    <div class="post-content">
        <p>Commercial vehicle owners must thoroughly examine bobtail insurance deductibles and comprehensive physical damage endorsements before signing annual fleet agreements.</p>
        <p>Operating without verified non-trucking liability coverage exposes independent owner-operators to catastrophic personal liability during deadhead and bobtail transit.</p>
    </div>
    """
    ContentQualityFinishGate.verify_shingle_guard("loanraaj.com", "bobtail-insurance-guide", existing_html)

    # 2. Attempt to publish a new article that copies an exact 12-word paragraph from the corpus
    new_incoming_html = """
    <div class="post-content">
        <p>Commercial vehicle owners must thoroughly examine bobtail insurance deductibles and comprehensive physical damage endorsements before signing annual fleet agreements.</p>
        <p>A fresh unique section about statutory interstate licensing requirements under federal motor carrier guidelines.</p>
    </div>
    """
    with pytest.raises(DuplicateContentError) as exc_info:
        ContentQualityFinishGate.verify_shingle_guard("tazaloan.com", "new-fleet-guide", new_incoming_html)

    assert "Duplicate 12-word shingle found in tazaloan.com/new-fleet-guide" in str(exc_info.value)
    assert "already in loanraaj.com/bobtail-insurance-guide" in str(exc_info.value)

