"""
tests/test_cloudflare_manager.py — Unit tests for Cloudflare fleet orchestrator.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from cloudflare_manager import CloudflareFleetManager, DOMAINS_FLEET


def test_fleet_manager_initialization():
    mgr = CloudflareFleetManager(token="test_tok", account_id="test_acc")
    assert mgr.token == "test_tok"
    assert mgr.account_id == "test_acc"
    assert "Bearer test_tok" in mgr.headers["Authorization"]
    assert len(DOMAINS_FLEET) == 10


def test_list_existing_zones_mock():
    mgr = CloudflareFleetManager(token="test_tok", account_id="test_acc")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "result": [
            {"id": "z1", "name": "rechargetak.com", "status": "active", "name_servers": ["josh.ns.cloudflare.com", "kiki.ns.cloudflare.com"]},
            {"id": "z2", "name": "loanraaj.com", "status": "active", "name_servers": ["josh.ns.cloudflare.com", "kiki.ns.cloudflare.com"]},
        ]
    }
    with patch("httpx.Client.get", return_value=mock_resp):
        zones = mgr.list_existing_zones()
        assert "rechargetak.com" in zones
        assert "loanraaj.com" in zones
        assert zones["rechargetak.com"]["id"] == "z1"


def test_create_zone_mock():
    mgr = CloudflareFleetManager(token="test_tok", account_id="test_acc")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "result": {"id": "new_zone_id", "name": "tazaloan.com", "status": "pending"}
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        res = mgr.create_zone("tazaloan.com")
        assert res is not None
        assert res["id"] == "new_zone_id"
        assert res["name"] == "tazaloan.com"
