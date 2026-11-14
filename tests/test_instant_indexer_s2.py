"""
tests/test_instant_indexer_s2.py — DEFECT S2-E Verification:
Tests for broadcast_all_network_sites nested article layout discovery,
URL deduplication, --limit, and --dry-run support.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

import instant_indexer


def test_s2_e_broadcast_all_network_sites_collects_nested_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert broadcast_all_network_sites() collects > 20 URLs per domain from nested layout."""
    submitted_calls: dict[str, list[str]] = {}

    def mock_submit(domain: str, urls: list[str]) -> bool:
        submitted_calls[domain] = urls
        return True

    monkeypatch.setattr(instant_indexer, "provision_verification_keys", lambda: None)
    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", mock_submit)
    monkeypatch.setattr(instant_indexer, "ping_google_sitemap", lambda domain: {"status": "skipped", "reason": "test"})

    results = instant_indexer.broadcast_all_network_sites()

    # All 10 domains should be present and have > 20 URLs submitted
    assert len(results) == 10
    for dom, count in results.items():
        assert count > 20, f"Domain {dom} only collected {count} URLs, expected > 20 from nested layout"
        assert dom in submitted_calls
        urls = submitted_calls[dom]
        assert len(urls) == count
        
        # Verify root and sitemap are present
        assert f"https://{dom}/" in urls
        assert f"https://{dom}/sitemap.xml" in urls
        
        # Verify static slugs and calculator.html are excluded
        assert not any(url.endswith("/calculator.html") for url in urls)
        assert not any(url.endswith("/about-us/") or url.endswith("/about-us") for url in urls)
        assert not any(url.endswith("/privacy-policy/") or url.endswith("/privacy-policy") for url in urls)
        
        # Verify nested article patterns exist (e.g., https://<domain>/<slug>/)
        article_nested = [u for u in urls if u.startswith(f"https://{dom}/") and u.endswith("/") and u != f"https://{dom}/"]
        assert len(article_nested) >= 20, f"Domain {dom} expected at least 20 nested article URLs, found {len(article_nested)}"


def test_s2_e_broadcast_all_network_sites_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert limit parameter properly caps URLs per domain."""
    submitted_calls: dict[str, list[str]] = {}

    def mock_submit(domain: str, urls: list[str]) -> bool:
        submitted_calls[domain] = urls
        return True

    monkeypatch.setattr(instant_indexer, "provision_verification_keys", lambda: None)
    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", mock_submit)
    monkeypatch.setattr(instant_indexer, "ping_google_sitemap", lambda domain: {"status": "skipped"})

    results = instant_indexer.broadcast_all_network_sites(limit=5)
    assert len(results) == 10
    for dom, count in results.items():
        assert count == 5
        assert len(submitted_calls[dom]) == 5


def test_s2_e_broadcast_all_network_sites_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert dry_run=True returns discovered counts without calling submit_to_indexnow."""
    submitted_called = False

    def mock_submit(domain: str, urls: list[str]) -> bool:
        nonlocal submitted_called
        submitted_called = True
        return True

    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", mock_submit)

    results = instant_indexer.broadcast_all_network_sites(dry_run=True)
    assert len(results) == 10
    assert not submitted_called
    for dom, count in results.items():
        assert count > 20
