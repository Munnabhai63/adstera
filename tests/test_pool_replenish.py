"""
tests/test_pool_replenish.py — Step 5.2: Proxy Pool Auto-Replenishment Tests

Covers:
1. ProxyPool.healthy_count() reflects available, dead, and over-used proxies
2. ProxyPool.add_raw_proxies() deduplicates existing proxies and rejects datacenter ASNs
3. ProxyPool.auto_replenish() returns 0 when healthy count is above threshold
4. ProxyPool.auto_replenish() fetches from API, enriches, and triggers alert when healthy count drops
5. ProxyPool.auto_replenish() handles missing or failing api_url gracefully
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pool
from pool import GeoInfo, Proxy, ProxyPool


def _make_dummy_proxy(host: str, port: int, uses: int = 0, is_dead: bool = False, is_dc: bool = False) -> Proxy:
    p = Proxy(host=host, port=port, username="u", password="p")
    p.uses_today = uses
    if is_dead:
        p.dead_until_ts = time.time() + 3600
    p.geo = GeoInfo(
        country="US",
        region="IL",
        city="Chicago",
        timezone="America/Chicago",
        locale="en-US",
        asn_name="DigitalOcean LLC" if is_dc else "Comcast Cable",
    )
    return p


def test_pool_healthy_count():
    """healthy_count accurately counts proxies available under cooldown and max_uses."""
    cfg = {
        "proxy": {
            "max_uses_per_ip": 5,
            "dead_ip_cooldown_min": 10,
            "max_concurrent_per_ip": 1,
        }
    }
    p1 = _make_dummy_proxy("1.1.1.1", 8080, uses=0)
    p2 = _make_dummy_proxy("2.2.2.2", 8080, uses=5)  # Exhausted uses
    p3 = _make_dummy_proxy("3.3.3.3", 8080, uses=1, is_dead=True)  # Dead
    p4 = _make_dummy_proxy("4.4.4.4", 8080, uses=2)

    p_pool = ProxyPool([p1, p2, p3, p4], cfg)
    assert p_pool.healthy_count() == 2
    print(f"  [OK] healthy_count evaluated 2/4 healthy proxies")


def test_pool_add_raw_proxies_dedup_and_dc_filter():
    """add_raw_proxies skips duplicates and datacenter proxies."""
    cfg = {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 10,
            "max_concurrent_per_ip": 1,
        }
    }
    existing = _make_dummy_proxy("10.0.0.1", 8080)
    p_pool = ProxyPool([existing], cfg)

    raw_lines = [
        "u:p@10.0.0.1:8080",  # Duplicate
        "u:p@10.0.0.2:8080",  # Residential
        "u:p@10.0.0.3:8080",  # Datacenter
    ]

    async def _run():
        with patch("pool._lookup_geo") as mock_geo:
            async def _fake_lookup(p):
                if p.host == "10.0.0.3":
                    return GeoInfo(asn_name="Hetzner Online GmbH")
                return GeoInfo(asn_name="AT&T Mobility")
            mock_geo.side_effect = _fake_lookup

            added = await p_pool.add_raw_proxies(raw_lines)
            return added

    added_count = asyncio.run(_run())
    assert added_count == 1
    assert len(p_pool) == 2
    assert any(p.host == "10.0.0.2" for p in p_pool.all_proxies)
    assert not any(p.host == "10.0.0.3" for p in p_pool.all_proxies)
    print(f"  [OK] add_raw_proxies added 1 clean proxy, filtered 1 dup and 1 DC")


def test_pool_auto_replenish_noop_when_above_threshold():
    """auto_replenish returns 0 immediately if healthy proxies >= threshold."""
    cfg = {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 10,
            "max_concurrent_per_ip": 1,
            "min_healthy_threshold": 2,
            "api_url": "https://example.com/proxies",
        }
    }
    p1 = _make_dummy_proxy("1.1.1.1", 8080)
    p2 = _make_dummy_proxy("2.2.2.2", 8080)
    p_pool = ProxyPool([p1, p2], cfg)

    async def _run():
        return await p_pool.auto_replenish(min_healthy_threshold=2)

    added = asyncio.run(_run())
    assert added == 0
    print("  [OK] auto_replenish is no-op when healthy >= threshold")


def test_pool_auto_replenish_triggers_fetch_and_alert():
    """auto_replenish fetches API lines, enriches, appends to pool, and fires alert."""
    cfg = {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 10,
            "max_concurrent_per_ip": 1,
            "min_healthy_threshold": 3,
            "api_url": "https://api.proxyscrape.com/v2/test",
        }
    }
    # Pool starts with only 1 healthy proxy (< 3)
    p1 = _make_dummy_proxy("1.1.1.1", 8080)
    p_pool = ProxyPool([p1], cfg)

    api_response_lines = [
        "userA:passA@50.0.0.1:9000",
        "userB:passB@50.0.0.2:9000",
    ]

    async def _run():
        with patch("pool.fetch_proxies_from_api", return_value=api_response_lines), \
             patch("pool._lookup_geo", return_value=GeoInfo(asn_name="Verizon Wireless")), \
             patch("alert_bot.TelegramAlertBot") as MockBot:

            mock_bot_instance = MagicMock()
            MockBot.return_value = mock_bot_instance

            added = await p_pool.auto_replenish(min_healthy_threshold=3)
            return added, mock_bot_instance

    added_count, bot = asyncio.run(_run())
    assert added_count == 2
    assert p_pool.healthy_count() == 3
    bot.send_pool_warning.assert_called_once()
    bot.send_pool_replenished.assert_called_once()
    print(f"  [OK] auto_replenish added {added_count} proxies and dispatched alerts")


def test_pool_auto_replenish_graceful_on_empty_api_or_failure():
    """auto_replenish returns 0 safely without crashing if api_url is empty or errors."""
    cfg_no_url = {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 10,
            "min_healthy_threshold": 5,
            "api_url": "",
        }
    }
    p_pool1 = ProxyPool([], cfg_no_url)
    assert asyncio.run(p_pool1.auto_replenish()) == 0

    cfg_error_url = {
        "proxy": {
            "max_uses_per_ip": 10,
            "dead_ip_cooldown_min": 10,
            "min_healthy_threshold": 5,
            "api_url": "https://broken-proxy-endpoint.com",
        }
    }
    p_pool2 = ProxyPool([], cfg_error_url)
    with patch("pool.fetch_proxies_from_api", side_effect=RuntimeError("Network timeout")):
        assert asyncio.run(p_pool2.auto_replenish()) == 0

    print("  [OK] auto_replenish handled empty api_url and fetch failure gracefully")


if __name__ == "__main__":
    test_pool_healthy_count()
    test_pool_add_raw_proxies_dedup_and_dc_filter()
    test_pool_auto_replenish_noop_when_above_threshold()
    test_pool_auto_replenish_triggers_fetch_and_alert()
    test_pool_auto_replenish_graceful_on_empty_api_or_failure()
    print("\nAll pool replenish tests PASSED!")
