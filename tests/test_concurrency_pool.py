"""
tests/test_concurrency_pool.py — Verification of Step 1.3 Concurrency & Per-IP Lock.
Verifies that:
1. max_concurrent_per_ip prevents two concurrent sessions on the same IP.
2. Multiple concurrent workers get distinct proxies.
3. Releasing a proxy restores its availability.
"""
import asyncio
import pytest
from pool import Proxy, ProxyPool, GeoInfo


@pytest.fixture
def mock_pool_cfg():
    return {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 45,
            "max_concurrent_per_ip": 1,
        },
        "scheduler": {
            "concurrency": 4,
            "sessions_per_hour": 150,
            "daily_cap": 2000,
        }
    }


def test_proxy_active_sessions_locking(mock_pool_cfg):
    async def _run():
        p1 = Proxy(host="1.1.1.1", port=8001, geo=GeoInfo(country="US", city="New York"))
        p2 = Proxy(host="2.2.2.2", port=8002, geo=GeoInfo(country="US", city="Chicago"))
        p3 = Proxy(host="3.3.3.3", port=8003, geo=GeoInfo(country="US", city="Dallas"))
        p4 = Proxy(host="4.4.4.4", port=8004, geo=GeoInfo(country="US", city="Miami"))

        pool = ProxyPool([p1, p2, p3, p4], mock_pool_cfg)

        # 4 concurrent workers acquire proxies
        acquired_1 = await pool.acquire()
        acquired_2 = await pool.acquire()
        acquired_3 = await pool.acquire()
        acquired_4 = await pool.acquire()

        # All 4 should be distinct proxies
        all_hosts = {acquired_1.host, acquired_2.host, acquired_3.host, acquired_4.host}
        assert len(all_hosts) == 4, "All 4 concurrent acquisitions must be on distinct IPs"

        # 5th acquisition should return None (all 4 IPs are currently in use)
        acquired_5 = await pool.acquire()
        assert acquired_5 is None, "5th acquisition must be None when pool is fully locked"

        # Release p1
        pool.release(acquired_1)
        assert acquired_1.active_sessions == 0

        # Now p1 should be available again
        reacquired = await pool.acquire()
        assert reacquired is not None
        assert reacquired.host == acquired_1.host
        assert reacquired.active_sessions == 1

        # Release all
        pool.release(acquired_2)
        pool.release(acquired_3)
        pool.release(acquired_4)
        pool.release(reacquired)

        assert p1.active_sessions == 0
        assert p2.active_sessions == 0
        assert p3.active_sessions == 0
        assert p4.active_sessions == 0

    asyncio.run(_run())


def test_reset_daily_counts_clears_active_sessions(mock_pool_cfg):
    p = Proxy(host="9.9.9.9", port=8080)
    p.active_sessions = 3
    p.uses_today = 10
    pool = ProxyPool([p], mock_pool_cfg)

    pool.reset_daily_counts()
    assert p.active_sessions == 0
    assert p.uses_today == 0
    assert p.dead_until_ts == 0.0
