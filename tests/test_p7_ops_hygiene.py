"""
tests/test_p7_ops_hygiene.py — Acceptance tests for Phase 7 (Ops Hygiene).
"""
import sqlite3
import tempfile
from pathlib import Path

import db
from common.paths import AUTOPUBLISH_DB_PATH, PROJECT_ROOT, SESSIONS_DB_PATH, STATE_DIR
import persist
import state_cleanup


def test_paths_are_absolute():
    assert PROJECT_ROOT.is_absolute()
    assert STATE_DIR.is_absolute()
    assert SESSIONS_DB_PATH.is_absolute()
    assert AUTOPUBLISH_DB_PATH.is_absolute()
    assert db._DB_PATH.is_absolute()


def test_protected_state_files():
    assert "profile.json" in state_cleanup.PROTECTED_STATE_FILES
    assert "circuit_breaker.json" in state_cleanup.PROTECTED_STATE_FILES
    assert "autopublish.db" in state_cleanup.PROTECTED_STATE_FILES


def test_proxy_state_regex_unification():
    sample_files = [
        "1.2.3.4_8080.json",
        "1.2.3.4_8080_meta.json",
        "mobile_device1.json",
        "user_pass_gw.provider.com_8000.json",
    ]
    for sf in sample_files:
        assert persist.PROXY_STATE_FILE_RE.match(sf), f"persist regex failed for {sf}"
        assert state_cleanup.PROXY_STATE_RE.match(sf), f"state_cleanup regex failed for {sf}"

    non_proxy_files = ["profile.json", "circuit_breaker.json", "adsterra_banners.json"]
    for npf in non_proxy_files:
        assert not persist.PROXY_STATE_FILE_RE.match(npf)
        assert not state_cleanup.PROXY_STATE_RE.match(npf)


def test_published_posts_unified_query():
    # Insert a test post via db.log_published_post
    test_slug = "test-p7-slug-check"
    db.log_published_post(
        domain="loanraaj.com",
        title="Test Title P7",
        slug=test_slug,
        file_path="sites/loanraaj.com/test-p7-slug-check/index.html",
        word_count=1350,
        ai_score=94.5,
        url="https://loanraaj.com/test-p7-slug-check",
    )

    latest = db.get_latest_published_posts("loanraaj.com", limit=5)
    assert any(p["slug"] == test_slug for p in latest)
    count = db.get_published_count_today("loanraaj.com")
    assert count >= 1


def test_incremental_vacuum_and_archive():
    # incremental vacuum executes cleanly
    db.incremental_vacuum(50)

    # test archive_old_sessions with temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        res = db.archive_old_sessions(days=365, batch_size=10, archive_dir=tmpdir)
        assert "archived_count" in res
        assert "archive_path" in res

