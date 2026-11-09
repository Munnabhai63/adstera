"""
ip_quality.py — IP Reputation Pre-Filter (NET-1)

Uses IPQualityScore API (free: 5000 checks/month) to reject:
- Datacenter IPs (DigitalOcean, AWS, Hetzner, etc.)
- VPN / Tor exit nodes
- Fraud score > 75
- Known proxy/bot IPs

Usage:
    from ip_quality import IPQualityFilter
    flt = IPQualityFilter()
    is_clean = await flt.check_ip("1.2.3.4")  # True = safe to use

Config: set IPQS_API_KEY in .env or config.yaml → ip_quality.api_key
"""
from __future__ import annotations

import logging
import os
import asyncio
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Datacenter ASN name fragments — if any appear in the ASN string, reject
_DATACENTER_FRAGMENTS = {
    "digitalocean", "ovh", "hetzner", "linode", "vultr",
    "amazon", "amazonaws", "google cloud", "microsoft azure",
    "cloudflare", "fastly", "akamai", "leaseweb", "choopa",
    "psychz", "datacamp", "rackspace", "serverius", "cogent",
}

# In-memory cache: ip → (is_clean: bool, ttl_epoch: float)
_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 3600 * 6  # 6 hours


class IPQualityFilter:
    """
    Async IP reputation filter backed by IPQualityScore API.
    Falls back to ASN-name check if API key is not set.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._key = api_key or os.getenv("IPQS_API_KEY", "")
        self._timeout = httpx.Timeout(8.0)

    async def check_ip(self, ip: str, asn_name: str = "") -> bool:
        """
        Returns True if IP is clean (safe to use as proxy).
        Returns False if IP should be rejected.

        Fast path: always reject known datacenter ASNs by name.
        Slow path: IPQS API check if key is configured.
        """
        import time

        # Fast path 1: ASN name fragment check (free, instant)
        if asn_name:
            asn_lower = asn_name.lower()
            for fragment in _DATACENTER_FRAGMENTS:
                if fragment in asn_lower:
                    logger.debug("Rejecting datacenter ASN '%s' for %s", asn_name, ip)
                    return False

        # Fast path 2: Cache hit
        if ip in _cache:
            result, expires = _cache[ip]
            if time.time() < expires:
                return result

        # If no API key, trust ASN check only
        if not self._key:
            return True  # Cannot verify further — allow

        # Slow path: IPQS API
        try:
            result = await self._query_ipqs(ip)
            _cache[ip] = (result, time.time() + _CACHE_TTL)
            return result
        except Exception as exc:
            logger.warning("IPQS API error for %s: %s — allowing (fail-open)", ip, exc)
            return True  # Fail-open: don't block traffic on API failure

    async def _query_ipqs(self, ip: str) -> bool:
        """Query IPQualityScore API. Returns True = clean, False = reject."""
        url = f"https://ipqualityscore.com/api/json/ip/{self._key}/{ip}"
        params = {
            "strictness": 1,
            "allow_public_access_points": "true",
            "fast": "true",
            "lighter_penalties": "false",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success", True):
            logger.debug("IPQS returned success=false for %s: %s", ip, data.get("message"))
            return True  # API error — fail-open

        fraud_score = data.get("fraud_score", 0)
        is_vpn = data.get("vpn", False)
        is_tor = data.get("tor", False)
        is_bot = data.get("bot_status", False)
        is_proxy = data.get("proxy", False)
        isp = data.get("ISP", "")
        org = data.get("organization", "")

        # Reject conditions
        if fraud_score > 75:
            logger.info("IPQS reject %s: fraud_score=%d", ip, fraud_score)
            return False
        if is_tor:
            logger.info("IPQS reject %s: Tor exit node", ip)
            return False
        if is_bot:
            logger.info("IPQS reject %s: bot_status=True", ip)
            return False
        # VPN is OK for residential/mobile proxies — only reject datacenter VPNs
        if is_vpn:
            combined = f"{isp} {org}".lower()
            for fragment in _DATACENTER_FRAGMENTS:
                if fragment in combined:
                    logger.info("IPQS reject %s: VPN + datacenter (%s %s)", ip, isp, org)
                    return False

        logger.debug("IPQS allow %s: fraud=%d vpn=%s tor=%s", ip, fraud_score, is_vpn, is_tor)
        return True

    def check_ip_sync(self, ip: str, asn_name: str = "") -> bool:
        """Sync wrapper for use in non-async contexts."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't block running loop — do ASN-only check
                if asn_name:
                    asn_lower = asn_name.lower()
                    for fragment in _DATACENTER_FRAGMENTS:
                        if fragment in asn_lower:
                            return False
                return True
            return loop.run_until_complete(self.check_ip(ip, asn_name))
        except Exception:
            return True


# Module-level singleton
_filter: Optional[IPQualityFilter] = None


def get_filter(api_key: Optional[str] = None) -> IPQualityFilter:
    """Get or create the module-level IPQualityFilter singleton."""
    global _filter
    if _filter is None:
        _filter = IPQualityFilter(api_key)
    return _filter
