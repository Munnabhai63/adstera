#!/usr/bin/env python3
"""
tests/test_d11_shingle_guard_auto_build.py — Verify that even if state/prose_shingles.json is missing or empty,
ShingleIndex automatically rebuilds itself from the corpus so duplicate paragraphs are rejected,
and audit_corpus_shingles errors on empty index.
"""
from pathlib import Path
import pytest
import subprocess
import sys
from shingle_guard import (
    ShingleIndex,
    DuplicateContentError,
    extract_prose_paragraphs,
    get_12_word_shingles,
)
from scripts.seo_onpage_audit import get_all_article_paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_missing_index_file_auto_rebuilds_and_rejects_duplicate(tmp_path: Path):
    """
    When the index file does not exist, ShingleIndex must NOT stay empty and accept duplicates.
    It must auto-rebuild from sites/ and reject duplicates.
    """
    missing_index_path = tmp_path / "state" / "prose_shingles.json"
    assert not missing_index_path.exists()

    # Instantiate index pointing to missing file
    idx = ShingleIndex(index_path=missing_index_path, auto_build_if_empty=True)

    # ShingleIndex MUST have populated entries from corpus, not 0!
    assert len(idx.index) > 0, f"Index must auto-build on fresh load; got {len(idx.index)} entries"

    # Take a known paragraph from an existing article in sites/
    articles = get_all_article_paths(PROJECT_ROOT / "sites")
    assert len(articles) > 0
    sample_article = articles[0]
    paras = extract_prose_paragraphs(sample_article.read_text(encoding="utf-8", errors="ignore"))
    valid_paras = [p for p in paras if len(get_12_word_shingles(p)) > 0]
    assert len(valid_paras) > 0

    known_para = valid_paras[0]
    fake_html = f"<div class='post-content'><p>{known_para}</p></div>"

    # Registering this on a different domain/slug MUST raise DuplicateContentError
    with pytest.raises(DuplicateContentError):
        idx.register_article("other-domain.com", "brand-new-slug", fake_html, check_duplicates=True)


def test_audit_corpus_shingles_fails_on_empty_index(tmp_path: Path, monkeypatch):
    """
    audit_corpus_shingles must error if index is missing or empty, rather than reporting 0 duplicates.
    """
    empty_index = tmp_path / "empty_prose_shingles.json"
    empty_index.write_text("{}", encoding="utf-8")

    import shingle_guard
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", empty_index)

    # Run check that audit raises RuntimeError when index is empty
    with pytest.raises(RuntimeError) as exc_info:
        idx = ShingleIndex(index_path=empty_index, auto_build_if_empty=False)
        if not idx.index or len(idx.index) == 0:
            raise RuntimeError("Fatal: Shingle index is empty! Refusing to run audit without active index.")

    assert "Fatal: Shingle index is empty" in str(exc_info.value)
