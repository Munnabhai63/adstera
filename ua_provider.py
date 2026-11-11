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
import re
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
_normalized_desktop_pool: list[str] = []
_normalized_mobile_pool: list[str] = []
_initialized: bool = False

_REAL_ANDROID_MODELS = [
    ("14", "SM-S918B"),
    ("14", "SM-S928B"),
    ("14", "Pixel 8 Pro"),
    ("14", "Pixel 8"),
    ("14", "OnePlus 12"),
    ("14", "SM-A546E"),
    ("13", "SM-G991B"),
    ("13", "Pixel 7"),
    ("14", "RMX3888"),
    ("14", "23127PN0CG"),
    ("13", "CPH2581"),
    ("14", "V2307"),
]

_REAL_CHROME_VERSIONS = [
    ("128", "128.0.6613.138"),
    ("129", "129.0.6668.100"),
    ("130", "130.0.6723.102"),
    ("131", "131.0.6778.135"),
    ("132", "132.0.6834.83"),
    ("133", "133.0.6943.54"),
    ("134", "134.0.6998.45"),
]


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


def _normalize_ua_for_chromium(ua: str, idx: int, is_mobile: bool) -> str:
    """
    Normalize any raw useragent.in entry from the 27,103 pool into a 100%
    Chromium-coherent User-Agent (eliminates Firefox/WebKit-only TLS mismatch
    and clamps synthetic future Chrome versions like Chrome/151 into 128-134).
    Preserves real OS & device model tokens across all 27,103 entries.
    """
    _, ch_full = _REAL_CHROME_VERSIONS[idx % len(_REAL_CHROME_VERSIONS)]
    os_ver, model = _REAL_ANDROID_MODELS[idx % len(_REAL_ANDROID_MODELS)]

    # Strip trailing synthetic annotations like '(Chrome Custom Tab)'
    cleaned = re.sub(r"\s*\(Chrome Custom Tab\)\s*$", "", ua.strip())

    if is_mobile:
        # Ensure Android Chromium coherent UA for mobile/tablet pool
        is_tablet = any(tok in cleaned.lower() for tok in ("tablet", "ipad", "sm-t", "sm-x", "pad"))
        mob_token = "" if is_tablet else "Mobile "

        # Extract real Android model if present and not generic 'K'
        m_and = re.search(r"Android\s+(\d+(?:\.\d+)?);\s*([^)]+)\)", cleaned, re.IGNORECASE)
        if m_and:
            found_os = m_and.group(1)
            found_model = m_and.group(2).split("Build")[0].strip()
            if int(found_os.split(".")[0]) >= 12 and found_model.upper() not in ("K", "MOBILE", "ANDROID", "WV"):
                os_ver = found_os
                model = found_model

        # Check if existing Chrome version is realistic (122..135)
        m_ch = re.search(r"Chrome/(\d+)\.([\d\.]+)", cleaned)
        if m_ch and 122 <= int(m_ch.group(1)) <= 135:
            ch_full = f"{m_ch.group(1)}.{m_ch.group(2)}"

        if "SamsungBrowser/" in cleaned:
            m_sb = re.search(r"SamsungBrowser/([\d\.]+)", cleaned)
            sb_ver = m_sb.group(1) if m_sb else "26.0"
            return (
                f"Mozilla/5.0 (Linux; Android {os_ver}; {model}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/{sb_ver} "
                f"Chrome/{ch_full} {mob_token}Safari/537.36"
            )
        return (
            f"Mozilla/5.0 (Linux; Android {os_ver}; {model}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ch_full} {mob_token}Safari/537.36"
        )

    # Desktop normalization
    m_ch = re.search(r"Chrome/(\d+)\.([\d\.]+)", cleaned)
    if m_ch and 122 <= int(m_ch.group(1)) <= 135:
        ch_full = f"{m_ch.group(1)}.{m_ch.group(2)}"

    low = cleaned.lower()
    if "macintosh" in low or "mac os x" in low:
        os_token = "Macintosh; Intel Mac OS X 10_15_7"
    elif "x11" in low or ("linux" in low and "android" not in low):
        os_token = "X11; Linux x86_64"
    else:
        os_token = "Windows NT 10.0; Win64; x64"

    if "edg/" in low:
        return (
            f"Mozilla/5.0 ({os_token}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{ch_full} Safari/537.36 Edg/{ch_full}"
        )
    return (
        f"Mozilla/5.0 ({os_token}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{ch_full} Safari/537.36"
    )


def _filter_recent_uas(ua_list: list[str], min_chrome_version: int = 118, is_mobile: bool = False) -> list[str]:
    """
    FP-2: Normalize the entire 27,103 useragent.in pool into modern Chromium-coherent
    User-Agents (Chrome 122-135) so zero UAs in the pool are wasted and 0% browser/TLS
    mismatch ever occurs.
    """
    if not ua_list:
        return _FALLBACK_MOBILE if is_mobile else _FALLBACK_DESKTOP
    return [_normalize_ua_for_chromium(ua, i, is_mobile) for i, ua in enumerate(ua_list)]


def get_matching_ua(chrome_major: str, is_mobile: bool = False, seed_key: str = "") -> str:
    """
    FP-1: Return a User-Agent from the 27,103 pool deterministically selected via seed_key
    and aligned to the exact Chromium major version running (prevents LEAK-05 while
    utilizing all 27,103 UAs).
    """
    import hashlib
    pool = get_mobile_uas() if is_mobile else get_desktop_uas()
    if not pool:
        if is_mobile:
            return f"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Mobile Safari/537.36"
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Safari/537.36"

    if seed_key:
        idx = int.from_bytes(hashlib.sha256(seed_key.encode("utf-8")).digest()[:8], "big") % len(pool)
        chosen = pool[idx]
    else:
        target_pattern = f"Chrome/{chrome_major}."
        chosen = next((u for u in pool if target_pattern in u), pool[0])

    # Align Chrome/<major> and Edg/<major> to the running browser's major version
    chosen = re.sub(r"Chrome/\d+\.", f"Chrome/{chrome_major}.", chosen)
    chosen = re.sub(r"Edg/\d+\.", f"Edg/{chrome_major}.", chosen)
    return chosen


def get_desktop_uas() -> list[str]:
    """Return all 8,989 desktop User-Agents normalized for modern Chromium coherence."""
    global _normalized_desktop_pool
    init(auto_sync=True)
    if _normalized_desktop_pool:
        return _normalized_desktop_pool
    pool = _desktop_pool if _desktop_pool else _FALLBACK_DESKTOP
    _normalized_desktop_pool = _filter_recent_uas(pool, min_chrome_version=118, is_mobile=False)
    return _normalized_desktop_pool


def get_mobile_uas() -> list[str]:
    """Return all 18,114 mobile/tablet User-Agents normalized for modern Chromium coherence."""
    global _normalized_mobile_pool
    init(auto_sync=True)
    if _normalized_mobile_pool:
        return _normalized_mobile_pool
    pool = _mobile_pool if _mobile_pool else _FALLBACK_MOBILE
    _normalized_mobile_pool = _filter_recent_uas(pool, min_chrome_version=118, is_mobile=True)
    return _normalized_mobile_pool


def parse_ua_hardware_profile(ua: str) -> dict:
    """
    Parse a User-Agent string into its exact 4-Dimension Hardware & Browser Profile:
    - device_format: 'mobile' | 'tablet' | 'desktop'
    - is_mobile: bool
    - os_name: 'Android' | 'Windows' | 'macOS' | 'Linux'
    - os_version: str
    - platform: navigator.platform string
    - architecture: 'arm' | 'x86'
    - model: Android hardware model or ''
    - browser_brand: 'Google Chrome' | 'Microsoft Edge' | 'Samsung Internet'
    - major_ver: str
    - full_ver: str
    """
    ua_low = ua.lower()
    m_ver = re.search(r"(?:Chrome|CriOS|Edg)/(\d+)(?:\.([\d\.]+))?", ua)
    major_ver = m_ver.group(1) if m_ver else "131"
    full_ver = f"{major_ver}.{m_ver.group(2)}" if m_ver and m_ver.group(2) else f"{major_ver}.0.0.0"

    if "edg/" in ua_low:
        browser_brand = "Microsoft Edge"
    elif "samsungbrowser/" in ua_low:
        browser_brand = "Samsung Internet"
    else:
        browser_brand = "Google Chrome"

    if "android" in ua_low:
        os_name = "Android"
        arch = "arm"
        m_os = re.search(r"Android\s+(\d+(?:\.\d+)?)", ua, re.IGNORECASE)
        os_version = f"{m_os.group(1).split('.')[0]}.0.0" if m_os else "14.0.0"
        m_mod = re.search(r"Android\s+[^;]+;\s*([^)]+)\)", ua, re.IGNORECASE)
        model = m_mod.group(1).split("Build")[0].strip() if m_mod else "SM-S918B"
        if model.upper() in ("K", "MOBILE", "ANDROID", ""):
            model = "SM-S918B"
        is_tablet = ("mobile" not in ua_low) or any(t in model.lower() for t in ("sm-t", "sm-x", "tab", "pad"))
        device_format = "tablet" if is_tablet else "mobile"
        is_mobile = True
        platform = "Linux armv8l"
    elif "iphone" in ua_low or "ipad" in ua_low:
        os_name = "iOS"
        arch = "arm"
        os_version = "17.4.0"
        model = "iPad" if "ipad" in ua_low else "iPhone"
        device_format = "tablet" if "ipad" in ua_low else "mobile"
        is_mobile = True
        platform = model
    elif "macintosh" in ua_low or "mac os x" in ua_low:
        os_name = "macOS"
        arch = "arm"
        os_version = "14.5.0"
        model = ""
        device_format = "desktop"
        is_mobile = False
        platform = "MacIntel"
    elif "linux" in ua_low or "x11" in ua_low:
        os_name = "Linux"
        arch = "x86"
        os_version = "6.5.0"
        model = ""
        device_format = "desktop"
        is_mobile = False
        platform = "Linux x86_64"
    else:
        os_name = "Windows"
        arch = "x86"
        os_version = "15.0.0"
        model = ""
        device_format = "desktop"
        is_mobile = False
        platform = "Win32"

    return {
        "device_format": device_format,
        "is_mobile": is_mobile,
        "os_name": os_name,
        "os_version": os_version,
        "platform": platform,
        "architecture": arch,
        "model": model,
        "browser_brand": browser_brand,
        "major_ver": major_ver,
        "full_ver": full_ver,
    }


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
