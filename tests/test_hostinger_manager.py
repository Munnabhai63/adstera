"""
tests/test_hostinger_manager.py — Unit tests for HostingerFleetManager.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from hostinger_manager import HostingerFleetManager, TARGET_NS1, TARGET_NS2


def test_hostinger_manager_initialization() -> None:
    mgr = HostingerFleetManager(token="test_token_123")
    assert mgr.token == "test_token_123"
    assert "Bearer test_token_123" in mgr.headers["Authorization"]


@patch("httpx.Client.get")
def test_list_portfolio_mock(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"domain": "loanraaj.com", "status": "active"},
        {"domain": "rechargetak.com", "status": "active"},
    ]
    mock_get.return_value = mock_resp

    mgr = HostingerFleetManager(token="dummy")
    portfolio = mgr.list_portfolio()
    assert len(portfolio) == 2
    assert portfolio[0]["domain"] == "loanraaj.com"


@patch("httpx.Client.put")
def test_update_nameservers_mock(mock_put: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"message": "Request accepted"}
    mock_put.return_value = mock_resp

    mgr = HostingerFleetManager(token="dummy")
    res = mgr.update_nameservers("loanraaj.com")
    assert res["success"] is True
    assert res["domain"] == "loanraaj.com"
    assert res["message"] == "Request accepted"


@patch("httpx.Client.get")
@patch("httpx.Client.put")
def test_sync_all_fleet_mock(mock_put: MagicMock, mock_get: MagicMock) -> None:
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = [
        {"domain": "loanraaj.com"},
        {"domain": "rechargetak.com"},
    ]
    mock_get.return_value = get_resp

    put_resp = MagicMock()
    put_resp.status_code = 200
    put_resp.json.return_value = {"message": "Request accepted"}
    mock_put.return_value = put_resp

    mgr = HostingerFleetManager(token="dummy")
    results = mgr.sync_all_fleet()
    assert len(results) == 10
    # The two registered in mock should succeed
    loanraaj_res = next(r for r in results if r["domain"] == "loanraaj.com")
    assert loanraaj_res["success"] is True
