"""
ua_provider.py — High-volume User-Agent manager powered by useragent.in.

Loads, caches, and rotates 27,000+ real-world user agent strings across:
- Desktop & Laptop (8,989 strings)
- Mobile Phones (15,434 strings)
- Tablets (2,680 strings)
Source: https://useragent.in/api & https://useragent.in/assets/data/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "state" / "useragents"
API_BASE = "https://useragent.in"
DATA_BASE = "https://useragent.in/assets/data"

# Fallbacks if network is completely unreachable on very first run
_FALLBACK_DESKTOP = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

_FALLBACK_MOBILE = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Samsung SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.6723.37 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; OnePlus 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
]

# In-memory cache
_desktop_pool: list[str] = []
_mobile_pool: list[str] = []
_initialized: bool = False


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def sync_from_useragent_in(timeout: float = 15.0) -> dict:
    """
    Fetch and decode all real visitor categories from useragent.in.
    Saves to local disk cache under state/useragents/.
    Returns a summary dict with counts.
    """
    global _desktop_pool, _mobile_pool, _initialized
    _ensure_cache_dir()

    desktop_file = CACHE_DIR / "desktop.json"
    mobile_file = CACHE_DIR / "mobile.json"
    meta_file = CACHE_DIR / "meta.json"

    desktop_uas: list[str] = []
    mobile_uas: list[str] = []

    logger.info("Connecting to useragent.in to synchronize user agent dataset…")
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # 1. Desktop & Laptop
        try:
            r = client.get(f"{DATA_BASE}/ua-desktop.json")
            if r.status_code == 200:
                data = r.json()
                desktop_uas = [row[0] for row in data.get("rows", []) if row and len(row) > 0]
        except Exception as exc:
            logger.warning("Failed fetching ua-desktop.json from useragent.in: %s", exc)

        # 2. Mobile Phones
        try:
            r = client.get(f"{DATA_BASE}/ua-mobile.json")
            if r.status_code == 200:
                data = r.json()
                mobile_uas.extend([row[0] for row in data.get("rows", []) if row and len(row) > 0])
        except Exception as exc:
            logger.warning("Failed fetching ua-mobile.json from useragent.in: %s", exc)

        # 3. Tablets
        try:
            r = client.get(f"{DATA_BASE}/ua-tablet.json")
            if r.status_code == 200:
                data = r.json()
                mobile_uas.extend([row[0] for row in data.get("rows", []) if row and len(row) > 0])
        except Exception as exc:
            logger.warning("Failed fetching ua-tablet.json from useragent.in: %s", exc)

    if desktop_uas:
        desktop_file.write_text(json.dumps(desktop_uas, indent=None), encoding="utf-8")
        _desktop_pool = desktop_uas
    if mobile_uas:
        mobile_file.write_text(json.dumps(mobile_uas, indent=None), encoding="utf-8")
        _mobile_pool = mobile_uas

    total = len(desktop_uas) + len(mobile_uas)
    meta = {
        "source": "https://useragent.in",
        "desktop_count": len(desktop_uas),
        "mobile_count": len(mobile_uas),
        "total": total,
    }
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _initialized = True

    logger.info("useragent.in sync complete: %d desktop, %d mobile (total %d)", len(desktop_uas), len(mobile_uas), total)
    return meta


def _load_from_disk_cache() -> bool:
    """Load cached UAs from disk if present."""
    global _desktop_pool, _mobile_pool, _initialized
    desktop_file = CACHE_DIR / "desktop.json"
    mobile_file = CACHE_DIR / "mobile.json"

    loaded = False
    if desktop_file.exists():
        try:
            _desktop_pool = json.loads(desktop_file.read_text(encoding="utf-8"))
            loaded = True
        except Exception:
            _desktop_pool = []

    if mobile_file.exists():
        try:
            _mobile_pool = json.loads(mobile_file.read_text(encoding="utf-8"))
            loaded = True
        except Exception:
            _mobile_pool = []

    if loaded:
        _initialized = True
    return loaded


def init(auto_sync: bool = True) -> None:
    """Initialize the UA pool. If local cache exists, load it; otherwise sync from API."""
    global _initialized
    if _initialized and (_desktop_pool or _mobile_pool):
        return

    if not _load_from_disk_cache() and auto_sync:
        try:
            sync_from_useragent_in()
        except Exception as exc:
            logger.warning("Initial useragent.in sync failed, using built-in pool: %s", exc)


def get_desktop_uas() -> list[str]:
    """Return all available desktop User-Agents."""
    init(auto_sync=True)
    return _desktop_pool if _desktop_pool else _FALLBACK_DESKTOP


def get_mobile_uas() -> list[str]:
    """Return all available mobile/tablet User-Agents."""
    init(auto_sync=True)
    return _mobile_pool if _mobile_pool else _FALLBACK_MOBILE


def get_stats() -> dict:
    """Return pool statistics and cache details."""
    init(auto_sync=False)
    desktop_count = len(_desktop_pool) if _desktop_pool else len(_FALLBACK_DESKTOP)
    mobile_count = len(_mobile_pool) if _mobile_pool else len(_FALLBACK_MOBILE)
    meta_file = CACHE_DIR / "meta.json"
    has_cache = meta_file.exists()
    return {
        "source": "https://useragent.in",
        "desktop_count": desktop_count,
        "mobile_count": mobile_count,
        "total": desktop_count + mobile_count,
        "cached_on_disk": has_cache,
    }


def parse_ua_via_api(ua: str, timeout: float = 6.0) -> dict:
    """
    Parse a user agent string using useragent.in's /api/parse JSON endpoint.
    Returns parsed dictionary with browser, os, engine, flags, and bot detection.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{API_BASE}/api/parse", json={"ua": ua})
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        logger.debug("parse_ua_via_api error: %s", exc)
    return {"ok": False, "ua": ua, "error": "API unreachable"}


def infer_platform(ua: str) -> str:
    """
    Infer navigator.platform from the user agent string so that
    platform is 100% coherent with the presented UA.
    """
    ua_lower = ua.lower()
    if "windows" in ua_lower:
        return "Win32"
    if "iphone" in ua_lower:
        return "iPhone"
    if "ipad" in ua_lower:
        return "iPad"
    if "macintosh" in ua_lower or "mac os x" in ua_lower:
        return "MacIntel"
    if "android" in ua_lower:
        return "Linux armv8l"
    if "linux" in ua_lower or "x11" in ua_lower:
        return "Linux x86_64"
    return "Win32"
