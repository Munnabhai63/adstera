"""
pool.py — Proxy pool: parsing, geo lookup, health, per-IP locks, cooldowns.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Datacenter ASN name fragments to reject
_DC_NAMES = {
    "digitalocean", "ovh", "hetzner", "linode", "vultr",
    "aws", "amazon", "azure", "microsoft", "google", "gcp",
    "cloudflare", "fastly", "akamai", "leaseweb", "choopa",
}

# Hardcoded geo fallback table: host-fragment → (country, region, city, tz, locale)
_GEO_FALLBACK: dict[str, tuple[str, str, str, str, str]] = {
    "gw.provider.com":     ("US", "NY", "New York",    "America/New_York",    "en-US"),
    "mobile.provider.com": ("US", "CA", "Los Angeles", "America/Los_Angeles", "en-US"),
    "1.2.3.4":             ("US", "TX", "Dallas",      "America/Chicago",     "en-US"),
    "default":             ("US", "IL", "Chicago",     "America/Chicago",     "en-US"),
}


@dataclass
class GeoInfo:
    country: str = "US"
    region: str = "IL"
    city: str = "Chicago"
    timezone: str = "America/Chicago"
    locale: str = "en-US"
    asn_name: str = ""

    @property
    def is_datacenter(self) -> bool:
        name_lower = self.asn_name.lower()
        return any(dc in name_lower for dc in _DC_NAMES)


@dataclass
class Proxy:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    geo: GeoInfo = field(default_factory=GeoInfo)

    # Runtime state
    uses_today: int = 0
    last_used_ts: float = 0.0
    dead_until_ts: float = 0.0
    active_sessions: int = 0
    _lock: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))

    @property
    def proxy_id(self) -> str:
        if self.port <= 0:
            return f"mobile:{self.host}"
        return f"{self.host}:{self.port}"

    @property
    def fingerprint_seed(self) -> bytes:
        return hashlib.sha256(self.proxy_id.encode()).digest()

    @property
    def server_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def playwright_proxy(self) -> Optional[dict]:
        if self.port <= 0:
            return None
        p: dict = {"server": self.server_url}
        if self.username:
            p["username"] = self.username
        if self.password:
            p["password"] = self.password
        return p

    def is_available(self, max_uses: int, cooldown_secs: float, max_concurrent: int = 1) -> bool:
        now = time.time()
        if now < self.dead_until_ts:
            return False
        if self.uses_today >= max_uses:
            return False
        if self.active_sessions >= max_concurrent:
            return False
        return True

    def mark_dead(self, cooldown_min: int) -> None:
        self.dead_until_ts = time.time() + cooldown_min * 60
        logger.warning("Proxy %s marked dead for %d min", self.proxy_id, cooldown_min)

    def record_use(self) -> None:
        self.uses_today += 1
        self.last_used_ts = time.time()


def _parse_proxy_line(line: str) -> Optional[Proxy]:
    """Parse a single proxy line into a Proxy object.
    Supports:
      - host:port:user:pass
      - user:pass@host:port
      - host:port
      - http://user:pass@host:port
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Strip scheme if present
    for scheme in ("http://", "https://", "socks5://"):
        if line.startswith(scheme):
            line = line[len(scheme):]

    username = password = None

    # Format 1: user:pass@host:port
    if "@" in line:
        creds, hostport = line.rsplit("@", 1)
        if ":" in creds:
            username, password = creds.split(":", 1)
        if ":" in hostport:
            host, port_str = hostport.rsplit(":", 1)
            try:
                return Proxy(host=host, port=int(port_str), username=username, password=password)
            except ValueError:
                pass

    # Format 2: host:port:user:pass (4 colon-separated parts)
    parts = line.split(":")
    if len(parts) == 4:
        host, port_str, username, password = parts
        try:
            return Proxy(host=host, port=int(port_str), username=username, password=password)
        except ValueError:
            logger.warning("Invalid port in proxy line: %r", line)
            return None

    # Format 3: host:port (2 colon-separated parts)
    elif len(parts) == 2:
        host, port_str = parts
        try:
            return Proxy(host=host, port=int(port_str), username=None, password=None)
        except ValueError:
            logger.warning("Invalid port in proxy line: %r", line)
            return None

    logger.warning("Unrecognized proxy format: %r", line)
    return None


async def _lookup_geo(proxy: Proxy, timeout: float = 8.0) -> GeoInfo:
    """
    Attempt a geo lookup through the proxy via ip-api.com JSON endpoint.
    Falls back to the hardcoded table on any error.
    """
    try:
        proxy_url = proxy.server_url
        auth = None
        if proxy.username:
            auth = (proxy.username, proxy.password or "")

        transport = httpx.AsyncHTTPTransport(proxy=proxy_url)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            resp = await client.get(
                "http://ip-api.com/json/?fields=status,country,regionName,city,timezone,query,org"
            )
            data = resp.json()

        if data.get("status") == "success":
            asn_name = data.get("org", "")
            geo = GeoInfo(
                country=data.get("country", "US"),
                region=data.get("regionName", ""),
                city=data.get("city", ""),
                timezone=data.get("timezone", "America/Chicago"),
                locale=_locale_for_country(data.get("country", "US")),
                asn_name=asn_name,
            )
            logger.debug("Geo for %s: %s / %s / %s", proxy.proxy_id, geo.country, geo.city, geo.asn_name)
            return geo
    except Exception as exc:
        logger.debug("Geo lookup failed for %s: %s — using fallback", proxy.proxy_id, exc)

    return _fallback_geo(proxy.host)


def _fallback_geo(host: str) -> GeoInfo:
    row = _GEO_FALLBACK.get(host) or _GEO_FALLBACK["default"]
    country, region, city, tz, locale = row
    return GeoInfo(country=country, region=region, city=city, timezone=tz, locale=locale)


def _locale_for_country(country: str) -> str:
    _map = {
        "United States": "en-US",
        "United Kingdom": "en-GB",
        "Canada": "en-CA",
        "Australia": "en-AU",
        "Germany": "de-DE",
        "France": "fr-FR",
        "Spain": "es-ES",
        "Italy": "it-IT",
        "Netherlands": "nl-NL",
        "Poland": "pl-PL",
        "Brazil": "pt-BR",
        "India": "en-IN",
    }
    return _map.get(country, "en-US")


def _tz_for_country_city(country: str, city: str) -> str:
    if country in ("India", "IN"):
        return "Asia/Kolkata"
    if country in ("United States", "US"):
        return "America/New_York"
    if country in ("United Kingdom", "GB", "UK"):
        return "Europe/London"
    if country in ("Canada", "CA"):
        return "America/Toronto"
    return "America/Chicago"


class MobileTetherPool:
    """
    Virtual proxy pool backed by a USB-tethered Android phone.
    On each acquire(), it rotates the cellular IP via ADB Airplane Mode.
    """
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._lock = asyncio.Lock()
        self._current_ip = ""

    async def acquire(self) -> Optional[Proxy]:
        async with self._lock:
            import mobile_adb
            net_cfg = self._cfg.get("network", {})
            dev_id = net_cfg.get("device_id", "")
            wait_s = net_cfg.get("airplane_mode_wait", 4.0)
            adb_path = net_cfg.get("adb_path", "")

            loop = asyncio.get_running_loop()
            ok, old_ip, new_ip, msg = await loop.run_in_executor(
                None, mobile_adb.rotate_ip, dev_id, wait_s, adb_path
            )
            logger.info("[Mobile ADB] %s", msg)

            ip_info = await loop.run_in_executor(None, mobile_adb.get_public_ip)
            current_ip = ip_info.get("ip") or new_ip or old_ip or "127.0.0.1"
            self._current_ip = current_ip

            country = ip_info.get("country", "US")
            city = ip_info.get("city", "Chicago")
            geo = GeoInfo(
                country=country,
                city=city,
                timezone=_tz_for_country_city(country, city),
                locale=_locale_for_country(country),
                asn_name=ip_info.get("org", "Cellular Carrier"),
            )
            # port=0 signals direct mobile connection (no proxy server dict)
            return Proxy(host=current_ip, port=0, geo=geo)

    def release(self, proxy: Proxy) -> None:
        pass

    def mark_dead(self, proxy: Proxy) -> None:
        pass

    def reset_daily_counts(self) -> None:
        pass

    def __len__(self) -> int:
        return 1


def fetch_proxies_from_api(api_url: str, timeout: float = 12.0) -> list[str]:
    """
    Fetch proxies from a remote provider API endpoint (JSON array or raw text lines).
    Supports Bright Data, Smartproxy, Oxylabs, Webshare, ProxyScrape, etc.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(api_url)
            resp.raise_for_status()

            # Case 1: JSON response (list of proxy strings or list of dicts)
            try:
                data = resp.json()
                if isinstance(data, list):
                    lines = []
                    for item in data:
                        if isinstance(item, str):
                            lines.append(item.strip())
                        elif isinstance(item, dict):
                            h = item.get("ip") or item.get("host")
                            p = item.get("port")
                            u = item.get("user") or item.get("username")
                            pw = item.get("password") or item.get("pass")
                            if h and p and u and pw:
                                lines.append(f"{h}:{p}:{u}:{pw}")
                            elif h and p:
                                lines.append(f"{h}:{p}")
                    if lines:
                        return lines
                elif isinstance(data, dict):
                    for k in ("proxies", "data", "results", "proxy_list"):
                        if k in data and isinstance(data[k], list):
                            return [str(x).strip() for x in data[k] if str(x).strip()]
            except Exception:
                pass

            # Case 2: Plaintext newline-separated list
            text = resp.text.strip()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            return lines
    except Exception as exc:
        logger.error("Failed to fetch proxies from API %s: %s", api_url, exc)
        raise


class ProxyPool:
    def __init__(self, proxies: list[Proxy], cfg: dict):
        self._proxies = proxies
        self._cfg = cfg
        self._global_lock = asyncio.Lock()

    @classmethod
    async def from_file(cls, path: str, cfg: dict) -> "ProxyPool":
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        raw = [_parse_proxy_line(ln) for ln in lines]
        proxies = [p for p in raw if p is not None]
        logger.info("Loaded %d proxies from %s", len(proxies), path)

        # Geo lookup concurrently (max 5 at a time to avoid hammering the API)
        sem = asyncio.Semaphore(5)

        async def enrich(p: Proxy) -> None:
            async with sem:
                p.geo = await _lookup_geo(p)

        await asyncio.gather(*[enrich(p) for p in proxies])

        # Filter datacenter ASNs
        dc = [p for p in proxies if p.geo.is_datacenter]
        for p in dc:
            logger.warning("Rejecting datacenter proxy %s (ASN: %s)", p.proxy_id, p.geo.asn_name)
        proxies = [p for p in proxies if not p.geo.is_datacenter]
        logger.info("%d proxies after datacenter filter", len(proxies))

        return cls(proxies, cfg)

    @classmethod
    async def from_api(cls, api_url: str, cfg: dict) -> "ProxyPool":
        loop = asyncio.get_running_loop()
        lines = await loop.run_in_executor(None, fetch_proxies_from_api, api_url)
        raw = [_parse_proxy_line(ln) for ln in lines]
        proxies = [p for p in raw if p is not None]
        logger.info("Loaded %d proxies from API %s", len(proxies), api_url)

        sem = asyncio.Semaphore(5)

        async def enrich(p: Proxy) -> None:
            async with sem:
                p.geo = await _lookup_geo(p)

        await asyncio.gather(*[enrich(p) for p in proxies])

        proxies = [p for p in proxies if not p.geo.is_datacenter]
        logger.info("%d proxies after datacenter filter from API", len(proxies))
        return cls(proxies, cfg)

    @property
    def all_proxies(self) -> list[Proxy]:
        return self._proxies

    async def acquire(self) -> Optional[Proxy]:
        """Return next available proxy or None if pool exhausted."""
        max_uses = self._cfg["proxy"]["max_uses_per_ip"]
        cooldown = self._cfg["proxy"]["dead_ip_cooldown_min"]
        max_concurrent = int(self._cfg["proxy"].get("max_concurrent_per_ip", 1))
        cooldown_secs = cooldown * 60

        async with self._global_lock:
            available = [
                p for p in self._proxies
                if p.is_available(max_uses, cooldown_secs, max_concurrent)
            ]
            if not available:
                return None
            # Sort by least recently used
            available.sort(key=lambda p: p.last_used_ts)
            chosen = available[0]
            chosen.record_use()
            chosen.active_sessions += 1
            return chosen

    def release(self, proxy: Proxy) -> None:
        """Call after a session on this proxy completes."""
        if proxy:
            proxy.active_sessions = max(0, proxy.active_sessions - 1)

    def mark_dead(self, proxy: Proxy) -> None:
        proxy.mark_dead(self._cfg["proxy"]["dead_ip_cooldown_min"])

    def reset_daily_counts(self) -> None:
        for p in self._proxies:
            p.uses_today = 0
            p.dead_until_ts = 0.0
            p.active_sessions = 0
        logger.info("Daily proxy counts reset")

    def healthy_count(self) -> int:
        """Count proxies that are currently available and not exhausted or cooling down."""
        max_uses = self._cfg.get("proxy", {}).get("max_uses_per_ip", 12)
        cooldown = self._cfg.get("proxy", {}).get("dead_ip_cooldown_min", 45) * 60
        max_concurrent = int(self._cfg.get("proxy", {}).get("max_concurrent_per_ip", 1))
        return sum(
            1 for p in self._proxies
            if p.is_available(max_uses, cooldown, max_concurrent)
        )

    async def add_raw_proxies(self, lines: list[str]) -> int:
        """Parse, deduplicate, enrich with geo, filter datacenter ASNs, and append to pool."""
        existing_ids = {p.proxy_id for p in self._proxies}
        raw = [_parse_proxy_line(ln) for ln in lines]
        new_candidates = [p for p in raw if p is not None and p.proxy_id not in existing_ids]

        if not new_candidates:
            return 0

        sem = asyncio.Semaphore(5)

        async def enrich(p: Proxy) -> None:
            async with sem:
                p.geo = await _lookup_geo(p)

        await asyncio.gather(*[enrich(p) for p in new_candidates])
        clean = [p for p in new_candidates if not p.geo.is_datacenter]

        async with self._global_lock:
            # Re-check existing_ids under lock to prevent race conditions
            current_ids = {p.proxy_id for p in self._proxies}
            added = []
            for p in clean:
                if p.proxy_id not in current_ids:
                    self._proxies.append(p)
                    current_ids.add(p.proxy_id)
                    added.append(p)

        logger.info("Added %d new healthy proxies to pool (total=%d)", len(added), len(self._proxies))
        return len(added)

    async def auto_replenish(self, min_healthy_threshold: int | None = None) -> int:
        """
        Step 5.2: Check pool health. If healthy proxies < threshold, fetch from proxy API,
        enrich, filter datacenter ASNs, and send alert.
        """
        threshold = (
            min_healthy_threshold
            if min_healthy_threshold is not None
            else int(self._cfg.get("proxy", {}).get("min_healthy_threshold", 5))
        )
        current_healthy = self.healthy_count()
        if current_healthy >= threshold:
            return 0

        logger.warning(
            "Proxy pool low (%d healthy < threshold %d). Triggering auto-replenishment...",
            current_healthy, threshold,
        )

        # Trigger warning alert
        try:
            from alert_bot import TelegramAlertBot
            bot = TelegramAlertBot()
            bot.send_pool_warning(healthy_ips=current_healthy, minimum_required=threshold)
        except Exception as alert_err:
            logger.debug("Failed sending pool low alert: %s", alert_err)

        api_url = self._cfg.get("proxy", {}).get("api_url")
        if not api_url:
            logger.warning("Auto-replenish failed: proxy.api_url is not configured.")
            return 0

        try:
            loop = asyncio.get_running_loop()
            raw_lines = await loop.run_in_executor(None, fetch_proxies_from_api, api_url)
            added = await self.add_raw_proxies(raw_lines)
            if added > 0:
                try:
                    from alert_bot import TelegramAlertBot
                    bot = TelegramAlertBot()
                    bot.send_pool_replenished(added_count=added, total_healthy=self.healthy_count())
                except Exception as alert_err2:
                    logger.debug("Failed sending pool replenished alert: %s", alert_err2)
            return added
        except Exception as exc:
            logger.error("Auto-replenishment API fetch error: %s", exc)
            return 0

    def __len__(self) -> int:
        return len(self._proxies)

