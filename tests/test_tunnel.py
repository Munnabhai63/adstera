"""
tests/test_tunnel.py — Unit tests for Cloudflare Tunnel configuration & supervisor.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from setup_tunnel import route_dns_to_tunnel, TUNNEL_ID, TUNNEL_TARGET, DOMAIN


def test_tunnel_constants() -> None:
    assert TUNNEL_ID == "3fd601c7-288f-496c-9f93-db0d37822076"
    assert DOMAIN == "rechargekar.com"
    assert TUNNEL_TARGET == f"{TUNNEL_ID}.cfargotunnel.com"


@patch("httpx.Client.get")
@patch("httpx.Client.delete")
@patch("httpx.Client.post")
def test_route_dns_to_tunnel_mock(mock_post: MagicMock, mock_delete: MagicMock, mock_get: MagicMock) -> None:
    # Mock GET existing records
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {
        "result": [
            {"id": "rec_1", "name": "rechargekar.com", "type": "A", "content": "148.113.0.192"},
            {"id": "rec_2", "name": "www.rechargekar.com", "type": "CNAME", "content": "rechargekar.com"},
        ]
    }
    mock_get.return_value = get_resp

    # Mock DELETE
    del_resp = MagicMock()
    del_resp.status_code = 200
    mock_delete.return_value = del_resp

    # Mock POST
    post_resp = MagicMock()
    post_resp.status_code = 200
    post_resp.json.return_value = {"success": True}
    mock_post.return_value = post_resp

    with patch("cloudflare_manager._load_env", return_value=("dummy_tok", "dummy_acc")):
        route_dns_to_tunnel()

    assert mock_delete.call_count == 2
    assert mock_post.call_count == 2
