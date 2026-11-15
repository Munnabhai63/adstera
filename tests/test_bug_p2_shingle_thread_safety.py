"""
tests/test_bug_p2_shingle_thread_safety.py — Comprehensive Thread-Safety Tests for ShingleIndex.
Verifies:
1. Concurrent registration across 8 threads x 40 articles without exceptions.
2. Every registered article is persisted to disk (no lost writes/overwrites).
3. Atomic duplicate detection under concurrent race conditions.
4. Process-level singleton identity and path-based cache isolation.
5. Lock attributes are strictly excluded from serialized JSON.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import shingle_guard
from shingle_guard import (
    DuplicateContentError,
    ShingleIndex,
    clear_shared_index,
    get_shared_index,
)


def _seed_test_index(path: Path) -> dict:
    """Pre-seed index file with one dummy entry to avoid triggering slow 21.7MB corpus rebuild in unit tests."""
    seed = {
        "test seed shingle initialization for thread safety unit testing across network": {
            "domain": "loanraaj.com",
            "slug": "seed-article",
            "page_id": "loanraaj.com/seed-article",
            "first_seen": "2026-11-15T00:00:00",
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    return seed


def _make_article_html(article_id: int) -> str:
    """Construct an article with >=17 words where word index 6 is unique,
    ensuring every 12-word sliding window includes the unique token.
    """
    return (
        "<div class='post-content'><p>"
        f"Market operational standard verification protocol sequence {article_id} "
        "yields certified financial safety parameters across institutional portfolio assets today."
        "</p></div>"
    )


def test_concurrent_register_article_does_not_raise(tmp_path, monkeypatch):
    """8 threads x 40 distinct articles against one get_shared_index(),
    all must complete with no exception; assert index grew by expected unique shingles.
    """
    test_index_path = tmp_path / "concurrent_shingles.json"
    _seed_test_index(test_index_path)
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", test_index_path)
    clear_shared_index()

    idx = get_shared_index()
    initial_shingle_count = len(idx.index)

    num_threads = 8
    articles_per_thread = 40
    total_articles = num_threads * articles_per_thread  # 320 articles

    errors: list[Exception] = []

    def _worker(thread_idx: int):
        for i in range(articles_per_thread):
            art_id = thread_idx * articles_per_thread + i
            slug = f"concurrent-article-{art_id}"
            html = _make_article_html(art_id)
            try:
                idx.register_article("loanraaj.com", slug, html)
            except Exception as exc:
                errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(t,))
        for t in range(num_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent registration raised exceptions: {errors[:5]}"

    # Each article has 17 words -> 6 shingles per article
    # Since each shingle covers word index 6 (the unique art_id), all shingles are distinct.
    expected_new_shingles = total_articles * 6
    actual_new_shingles = len(idx.index) - initial_shingle_count
    assert actual_new_shingles == expected_new_shingles, (
        f"Expected index to grow by {expected_new_shingles} shingles, grew by {actual_new_shingles}"
    )
    clear_shared_index()


def test_concurrent_register_persists_every_article(tmp_path, monkeypatch):
    """After concurrent registration threads join, reload from disk and
    assert every registered page_id is present on disk (catches lost writes).
    """
    test_index_path = tmp_path / "persisted_shingles.json"
    _seed_test_index(test_index_path)
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", test_index_path)
    clear_shared_index()

    idx = get_shared_index()
    num_threads = 8
    articles_per_thread = 40
    total_articles = num_threads * articles_per_thread
    expected_page_ids = set()

    def _worker(thread_idx: int):
        for i in range(articles_per_thread):
            art_id = thread_idx * articles_per_thread + i
            slug = f"persisted-article-{art_id}"
            html = _make_article_html(art_id)
            idx.register_article("loanraaj.com", slug, html)

    threads = [
        threading.Thread(target=_worker, args=(t,))
        for t in range(num_threads)
    ]
    for t in range(num_threads):
        for i in range(articles_per_thread):
            art_id = t * articles_per_thread + i
            expected_page_ids.add(f"loanraaj.com/persisted-article-{art_id}")

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Read directly from disk
    assert test_index_path.exists(), "Index file was not created on disk"
    disk_data = json.loads(test_index_path.read_text(encoding="utf-8"))
    disk_page_ids = {item["page_id"] for item in disk_data.values()}

    missing_page_ids = expected_page_ids - disk_page_ids
    assert not missing_page_ids, (
        f"Missing {len(missing_page_ids)} page_ids from disk: {list(missing_page_ids)[:5]}"
    )
    assert len(expected_page_ids) == total_articles
    clear_shared_index()


def test_duplicate_detection_still_atomic(tmp_path, monkeypatch):
    """Two threads register the same article simultaneously:
    exactly one succeeds, the other raises DuplicateContentError.
    """
    test_index_path = tmp_path / "dup_shingles.json"
    _seed_test_index(test_index_path)
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", test_index_path)
    clear_shared_index()

    idx = get_shared_index()
    shared_html = _make_article_html(99999)

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def _register(slug: str):
        barrier.wait()
        try:
            idx.register_article("loanraaj.com", slug, shared_html)
            with lock:
                results.append("success")
        except DuplicateContentError:
            with lock:
                results.append("duplicate")
        except Exception as exc:
            with lock:
                results.append(f"unexpected_error: {exc}")

    t1 = threading.Thread(target=_register, args=("first-attempt",))
    t2 = threading.Thread(target=_register, args=("second-attempt",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count("success") == 1, f"Expected exactly 1 success, got: {results}"
    assert results.count("duplicate") == 1, f"Expected exactly 1 duplicate error, got: {results}"
    clear_shared_index()


def test_shared_index_singleton_identity(tmp_path, monkeypatch):
    """get_shared_index() is get_shared_index(), and a changed SHINGLE_INDEX_PATH
    yields a different object (maintains monkeypatch isolation).
    """
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _seed_test_index(path_a)
    _seed_test_index(path_b)

    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", path_a)
    clear_shared_index()

    idx1 = get_shared_index()
    idx2 = get_shared_index()
    assert idx1 is idx2, "get_shared_index() did not return the exact same instance"

    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", path_b)
    idx3 = get_shared_index()
    assert idx3 is not idx1, "Changing SHINGLE_INDEX_PATH must yield a new ShingleIndex instance"
    assert idx3.index_path == path_b.resolve()
    clear_shared_index()


def test_lock_not_serialised(tmp_path, monkeypatch):
    """Load the JSON written by the index and assert no key name contains _lock."""
    test_index_path = tmp_path / "lock_check.json"
    _seed_test_index(test_index_path)
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", test_index_path)
    clear_shared_index()

    idx = get_shared_index()
    idx.register_article(
        "loanraaj.com",
        "lock-test-article",
        _make_article_html(12345),
    )

    raw_json = test_index_path.read_text(encoding="utf-8")
    assert "_lock" not in raw_json, "Internal _lock attribute leaked into saved JSON"

    parsed = json.loads(raw_json)
    for shingle, meta in parsed.items():
        assert "_lock" not in shingle
        assert "_lock" not in meta
        for k in meta.keys():
            assert "_lock" not in k
    clear_shared_index()
