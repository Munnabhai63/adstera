"""
tests/test_instant_indexer_s1.py — DEFECT S1-A verification:
Tests for ping_google_sitemap structured results across all four states:
1. skipped (no credentials)
2. failed (submitter error/rejection)
3. submitted & verified (GSC Sitemaps API accepted)
4. submitted & unverified (deprecated endpoint fallback)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

import gsc_auth
import gsc_submitter
import instant_indexer


def test_s1_a_ping_google_sitemap_skipped_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GSC is unconfigured and fallback_deprecated=False, status must be 'skipped'."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: False)
    
    res = instant_indexer.ping_google_sitemap("loanraaj.com", fallback_deprecated=False)
    assert isinstance(res, dict)
    assert res["status"] == "skipped"
    assert res.get("reason") == "no credentials"
    assert res.get("verified") is not True


def test_s1_a_ping_google_sitemap_failed_when_submitter_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GSC is configured but submitter fails/rejects, status must be 'failed'."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: True)
    
    mock_submit_sitemap = AsyncMock(return_value=False)
    monkeypatch.setattr(gsc_submitter.GoogleIndexingSubmitter, "submit_sitemap", mock_submit_sitemap)

    res = instant_indexer.ping_google_sitemap("loanraaj.com")
    assert isinstance(res, dict)
    assert res["status"] == "failed"
    assert "rejected" in res.get("reason", "").lower()
    assert res.get("verified") is not True


def test_s1_a_ping_google_sitemap_submitted_verified_when_submitter_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GSC is configured and submitter succeeds, status must be 'submitted' with verified=True."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: True)
    
    mock_submit_sitemap = AsyncMock(return_value=True)
    monkeypatch.setattr(gsc_submitter.GoogleIndexingSubmitter, "submit_sitemap", mock_submit_sitemap)

    res = instant_indexer.ping_google_sitemap("loanraaj.com")
    assert isinstance(res, dict)
    assert res["status"] == "submitted"
    assert res.get("verified") is True


def test_s1_a_ping_google_sitemap_deprecated_fallback_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    """When fallback_deprecated=True and legacy endpoint returns 200, status must be 'submitted' with verified=False."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: False)
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: mock_resp)

    res = instant_indexer.ping_google_sitemap("loanraaj.com", fallback_deprecated=True)
    assert isinstance(res, dict)
    assert res["status"] == "submitted"
    assert res.get("verified") is False
    assert res.get("reason") == "deprecated endpoint"


def test_s1_a_broadcast_new_post_logs_skipped_not_success_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """broadcast_new_post must not claim Google indexing success when credentials are skipped."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: False)
    monkeypatch.setattr(instant_indexer, "provision_verification_keys", lambda: None)
    monkeypatch.setattr(instant_indexer, "update_sitemap_xml", lambda site_id, url: None)
    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", lambda dom, urls: False)

    res = instant_indexer.broadcast_new_post("loanraaj", "https://loanraaj.com/test-article")
    # Both IndexNow and Google unconfigured/failed, so return value must be False
    assert res is False


def test_s1_a_broadcast_all_network_sites_logs_skipped_without_crashing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """broadcast_all_network_sites runs over sites and handles skipped Google sitemap gracefully."""
    monkeypatch.setattr(gsc_auth.GSCAuthManager, "is_configured", lambda self: False)
    monkeypatch.setattr(instant_indexer, "provision_verification_keys", lambda: None)
    monkeypatch.setattr(instant_indexer, "submit_to_indexnow", lambda dom, urls: True)
    
    # Restrict to 1 domain in test to keep it fast
    with patch.dict(instant_indexer.NETWORK_REGISTRY, {"loanraaj": {"domain": "loanraaj.com"}}, clear=True):
        res = instant_indexer.broadcast_all_network_sites()
        assert "loanraaj.com" in res
        captured = capsys.readouterr()
        assert "[GSC Sitemap Notice] Google sitemap submission skipped for loanraaj.com: no credentials" in captured.out

