"""
tests/test_failover_manager.py — Unit test suite for Layer 5: Dual-ISP Carrier Hot-Failover Engine.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from failover_manager import DualTransportManager
from pool import GeoInfo, Proxy


@pytest.fixture
def mock_cfg():
    return {
        "failover": {
            "enabled": True,
            "latency_threshold_ms": 1500,
            "recovery_check_interval_min": 10,
            "max_failures_before_failover": 2,
        },
        "network": {
            "mode": "dual_failover",
            "adb_path": "",
        },
    }


def test_failover_manager_initialization(mock_cfg):
    mgr = DualTransportManager(mock_cfg)
    assert mgr.enabled is True
    assert mgr.active_mode == DualTransportManager.MODE_PRIMARY_MOBILE
    assert mgr.primary_healthy is True
    assert mgr.latency_threshold_ms == 1500.0
    assert mgr.max_failures_before_failover == 2
    assert mgr.total_failovers == 0


def test_primary_transport_acquisition_when_healthy(mock_cfg):
    async def _run():
        mgr = DualTransportManager(mock_cfg)

        # Mock MobileTetherPool
        mock_mobile = MagicMock()
        expected_proxy = Proxy(host="192.168.43.1", port=0, geo=GeoInfo(country="US", city="Dallas"))
        mock_mobile.acquire = AsyncMock(return_value=expected_proxy)

        mgr.set_sub_pools(mobile_pool=mock_mobile, proxy_pool=None)

        proxy = await mgr.acquire_transport()
        assert proxy is expected_proxy
        assert mgr.active_mode == DualTransportManager.MODE_PRIMARY_MOBILE
        assert mgr.consecutive_primary_failures == 0

    asyncio.run(_run())


def test_automatic_hot_failover_on_primary_failure(mock_cfg):
    async def _run():
        mgr = DualTransportManager(mock_cfg)

        # Primary fails with exception
        mock_mobile = MagicMock()
        mock_mobile.acquire = AsyncMock(side_effect=RuntimeError("USB Cable disconnected"))

        # Fallback proxy succeeds
        mock_proxy_pool = MagicMock()
        fallback_proxy = Proxy(host="residential.pool.com", port=8080, geo=GeoInfo(country="US", city="New York"))
        mock_proxy_pool.acquire = AsyncMock(return_value=fallback_proxy)
        mock_proxy_pool.__len__ = MagicMock(return_value=25)

        mgr.set_sub_pools(mobile_pool=mock_mobile, proxy_pool=mock_proxy_pool)

        # Should hot-swap to fallback without throwing
        proxy = await mgr.acquire_transport()
        assert proxy is fallback_proxy
        assert mgr.active_mode == DualTransportManager.MODE_FALLBACK_PROXY
        assert mgr.primary_healthy is False
        assert mgr.total_failovers == 1

    asyncio.run(_run())


def test_check_primary_health_probe(mock_cfg):
    mgr = DualTransportManager(mock_cfg)

    # Case 1: No devices
    with patch("mobile_adb.list_devices", return_value=[]):
        res = mgr.check_primary_health()
        assert res["healthy"] is False
        assert "No USB debugging" in res["reason"]

    # Case 2: Device connected and fast HTTP response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("mobile_adb.list_devices", return_value=[{"id": "device123", "status": "device"}]), \
         patch("httpx.Client.get", return_value=mock_resp):
        res = mgr.check_primary_health()
        assert res["healthy"] is True
        assert res["devices"] == 1


def test_recovery_back_to_primary(mock_cfg):
    async def _run():
        mgr = DualTransportManager(mock_cfg)
        mgr.active_mode = DualTransportManager.MODE_FALLBACK_PROXY
        mgr.primary_healthy = False

        # Simulate health check returns healthy
        with patch.object(mgr, "check_primary_health", return_value={"healthy": True, "latency_ms": 120.0}):
            recovered = await mgr.attempt_primary_recovery()
            assert recovered is True
            assert mgr.active_mode == DualTransportManager.MODE_PRIMARY_MOBILE
            assert mgr.primary_healthy is True
            assert mgr.total_recoveries == 1
            assert mgr.last_latency_ms == 120.0

    asyncio.run(_run())


def test_report_transport_failure_threshold(mock_cfg):
    mgr = DualTransportManager(mock_cfg)
    assert mgr.active_mode == DualTransportManager.MODE_PRIMARY_MOBILE

    # 1st failure — should warn but remain in primary
    mgr.report_transport_failure(DualTransportManager.MODE_PRIMARY_MOBILE, None, "Timeout 1")
    assert mgr.consecutive_primary_failures == 1
    assert mgr.active_mode == DualTransportManager.MODE_PRIMARY_MOBILE

    # 2nd failure — trips circuit breaker to fallback
    mgr.report_transport_failure(DualTransportManager.MODE_PRIMARY_MOBILE, None, "Timeout 2")
    assert mgr.consecutive_primary_failures == 2
    assert mgr.active_mode == DualTransportManager.MODE_FALLBACK_PROXY
    assert mgr.total_failovers == 1


def test_get_status_summary(mock_cfg):
    mgr = DualTransportManager(mock_cfg)
    status = mgr.get_status()
    assert "enabled" in status
    assert "active_mode" in status
    assert "primary_healthy" in status
    assert "latency_threshold_ms" in status
    assert "total_failovers" in status


def test_primary_transport_residential_proxy_mode():
    cfg = {
        "failover": {
            "enabled": True,
            "primary_transport": "residential_proxy",
            "fallback_transport": "adb_mobile",
            "latency_threshold_ms": 1500,
        }
    }
    mgr = DualTransportManager(cfg)
    assert mgr.enabled is True
    assert mgr.active_mode == DualTransportManager.MODE_FALLBACK_PROXY
