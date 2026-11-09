"""
IVT LEAK FIXES SUITE (Network & Fingerprint Layers)
Complete integration of NET-1 to NET-4 and FP-1 to FP-6.
Ready to use with undetected-chromedriver, Playwright, or Selenium.
"""
from __future__ import annotations

import os
import re
import random
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger("ivt_patches")


# ==============================================================================
# 🌐 2.1 — NETWORK LAYER (NET-1 to NET-4)
# ==============================================================================

# ------------------------------------------------------------------------------
# NET-3: WebRTC Browser Launch Arguments
# ------------------------------------------------------------------------------
WEBRTC_CHROMIUM_ARGS: List[str] = [
    "--disable-features=WebRtcHideLocalIpsWithMdns",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--enforce-webrtc-ip-permission-check",
]


# ------------------------------------------------------------------------------
# NET-1: IP Reputation Pre-Filter (IPQualityScore API)
# ------------------------------------------------------------------------------
class IPQualityChecker:
    def __init__(self, api_key: Optional[str] = None, fraud_threshold: int = 75):
        self.api_key = api_key or os.getenv("IPQS_API_KEY", "")
        self.fraud_threshold = fraud_threshold
        self.base_url = "https://ipqualityscore.com/api/json/ip"

    async def check_ip(self, ip: str, client: Optional[httpx.AsyncClient] = None) -> bool:
        """
        Returns True if IP is clean.
        Rejects if fraud_score > threshold, or if VPN/Tor/Proxy is detected.
        Fails open if api_key is missing or for local loopback IPs.
        """
        if ip in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return True

        if not self.api_key or self.api_key.startswith("your_") or self.api_key == "YOUR_KEY":
            logger.debug("IPQualityChecker: No valid API key provided — failing open for %s", ip)
            return True

        url = f"{self.base_url}/{self.api_key}/{ip}"
        params = {"strictness": 1, "allow_public_access_points": "true"}

        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            own_client = True

        try:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"IPQualityScore returned HTTP {response.status_code} for IP: {ip}")
                return True  # Fail-open on upstream service failure

            data = response.json()
            if not data.get("success", False):
                logger.error(f"IPQualityScore API error: {data.get('message')}")
                return True

            fraud_score = int(data.get("fraud_score", 0))
            is_vpn = bool(data.get("vpn", False))
            is_tor = bool(data.get("tor", False))
            is_proxy = bool(data.get("proxy", False))

            if fraud_score > self.fraud_threshold or is_vpn or is_tor or is_proxy:
                logger.info(f"Rejected IP {ip} -> FraudScore: {fraud_score}, VPN: {is_vpn}, Tor: {is_tor}, Proxy: {is_proxy}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking IP reputation for {ip}: {e}")
            return True
        finally:
            if own_client:
                await client.aclose()


# ------------------------------------------------------------------------------
# NET-2: DNS / Geo Fallback Chain (Rate-Limit Safe)
# ------------------------------------------------------------------------------
class GeoResolver:
    @staticmethod
    async def resolve_host(host: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, Any]]:
        """
        Queries multiple geo APIs sequentially.
        If a rate limit (HTTP 429) is hit, falls back to the next provider.
        Rejects proxy if all APIs fail (never defaults to wrong geo).
        """
        if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return {
                "country": "United States",
                "countryCode": "US",
                "city": "New York",
                "timezone": "America/New_York",
                "query": host,
            }

        endpoints = [
            {
                "url": f"http://ip-api.com/json/{host}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query",
                "parser": lambda d: d if d.get("status") == "success" else None,
            },
            {
                "url": f"https://ipinfo.io/{host}/json",
                "parser": lambda d: {
                    "country": d.get("country", "US"),
                    "countryCode": d.get("country", "US"),
                    "city": d.get("city", "Dallas"),
                    "timezone": d.get("timezone", "America/Chicago"),
                    "query": d.get("ip", host),
                } if "country" in d else None,
            },
            {
                "url": f"https://freeipapi.com/api/json/{host}",
                "parser": lambda d: {
                    "country": d.get("countryName", "United States"),
                    "countryCode": d.get("countryCode", "US"),
                    "city": d.get("cityName", "Dallas"),
                    "timezone": d.get("timeZone", "America/Chicago"),
                    "query": d.get("ipAddress", host),
                } if "countryCode" in d else None,
            },
        ]

        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=6.0)
            own_client = True

        try:
            for ep in endpoints:
                try:
                    resp = await client.get(ep["url"], timeout=6.0)
                    if resp.status_code == 429:
                        logger.warning(f"Rate limit (429) hit on {ep['url']}, trying next fallback...")
                        continue
                    if resp.status_code == 200:
                        parsed = ep["parser"](resp.json())
                        if parsed:
                            return parsed
                except (httpx.RequestError, Exception) as exc:
                    logger.debug(f"Geo query failed for {ep['url']}: {exc}")
                    continue

            logger.error(f"All Geo resolvers failed for {host}. Rejecting proxy.")
            return None
        finally:
            if own_client:
                await client.aclose()


# ------------------------------------------------------------------------------
# NET-4: Proxy Anonymity & Header Leak Verification
# ------------------------------------------------------------------------------
class ProxyHeaderValidator:
    FORBIDDEN_HEADERS = {
        "x-forwarded-for",
        "via",
        "x-real-ip",
        "proxy-connection",
        "x-proxy-id",
        "forwarded",
        "client-ip",
    }

    @classmethod
    async def verify_proxy_anonymity(cls, proxy_url: str) -> bool:
        """
        Verifies via httpbin that the proxy does not leak proxy or real IP headers.
        """
        if not proxy_url or "127.0.0.1" in proxy_url or "localhost" in proxy_url:
            return True

        proxies = {"http://": proxy_url, "https://": proxy_url}
        test_url = "https://httpbin.org/headers"

        try:
            async with httpx.AsyncClient(proxies=proxies, timeout=10.0) as client:
                resp = await client.get(test_url)
                if resp.status_code != 200:
                    return True

                headers = {k.lower(): v for k, v in resp.json().get("headers", {}).items()}
                leaks = [h for h in cls.FORBIDDEN_HEADERS if h in headers]
                if leaks:
                    logger.warning(f"Proxy header leak detected {leaks} on {proxy_url}. Rejected.")
                    return False

                return True
        except Exception as e:
            logger.debug(f"Header verification error for {proxy_url}: {e} (fail-open)")
            return True


# ==============================================================================
# 🪪 2.2 — FINGERPRINT LAYER (FP-1 to FP-6)
# ==============================================================================

# ------------------------------------------------------------------------------
# FP-1 & FP-2: User-Agent Manager (Sync & Stale Filter)
# ------------------------------------------------------------------------------
class UserAgentManager:
    def __init__(self, min_chrome_version: int = 118):
        self.min_chrome_version = min_chrome_version

    @staticmethod
    def extract_chrome_major(browser_version_str: str) -> str:
        """Extracts major version: '130.0.6723.58' -> '130'"""
        match = re.search(r"^(\d+)", browser_version_str)
        return match.group(1) if match else "130"

    def filter_recent_uas(self, ua_list: List[str]) -> List[str]:
        """Rejects any UA where Chrome version < min_chrome_version (FP-2)."""
        valid_uas: List[str] = []
        for ua in ua_list:
            match = re.search(r"Chrome/(\d+)\.", ua)
            if match and int(match.group(1)) >= self.min_chrome_version:
                valid_uas.append(ua)
        return valid_uas

    @staticmethod
    def get_matching_ua(chrome_major: str, is_mobile: bool = False, os_type: str = "windows") -> str:
        """Generates synchronized UA matching the current browser major version (FP-1)."""
        if is_mobile:
            return (
                f"Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_major}.0.0.0 Mobile Safari/537.36"
            )
        if os_type == "windows":
            return (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_major}.0.0.0 Safari/537.36"
            )
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_major}.0.0.0 Safari/537.36"
        )


# ------------------------------------------------------------------------------
# FP-3, FP-4, FP-5, FP-6: Browser Client-Side JS Stealth Injection
# ------------------------------------------------------------------------------
def generate_stealth_js(session_salt: Optional[float] = None) -> str:
    """
    Generates pure JavaScript payload to be injected at document_start.
    Includes FP-3 (Window size), FP-4 (Plugins), FP-5 (Webdriver cleanup),
    and FP-6 (AudioContext salt).
    """
    if session_salt is None:
        session_salt = random.uniform(0.0000001, 0.0000099)
    salt_str = f"{session_salt:.9f}".rstrip("0") if isinstance(session_salt, float) else str(session_salt)

    return f"""
    (function () {{
        const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
        const SESSION_SALT = {salt_str};

        // -------------------------------------------------------------
        // FP-3: window.outerWidth/Height/screenX/Y spoof
        // -------------------------------------------------------------
        const vw = window.innerWidth || 1280;
        const vh = window.innerHeight || 720;
        const outerW = vw + rand(0, 16);
        const outerH = vh + rand(72, 92); // Titlebar + borders
        const sX = rand(0, 150);
        const sY = rand(0, 40);

        Object.defineProperty(window, 'outerWidth', {{ get: () => outerW, configurable: true }});
        Object.defineProperty(window, 'outerHeight', {{ get: () => outerH, configurable: true }});
        Object.defineProperty(window, 'screenX', {{ get: () => sX, configurable: true }});
        Object.defineProperty(window, 'screenY', {{ get: () => sY, configurable: true }});

        // -------------------------------------------------------------
        // FP-4: Realistic Chrome 130+ Plugins Array
        // -------------------------------------------------------------
        const pluginData = [
            {{ name: "PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" }},
            {{ name: "Chrome PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" }},
            {{ name: "Chromium PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" }},
            {{ name: "Microsoft Edge PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" }},
            {{ name: "WebKit built-in PDF", filename: "internal-pdf-viewer", description: "Portable Document Format" }}
        ];

        const pluginArray = Object.create(PluginArray.prototype);
        pluginData.forEach((p, idx) => {{
            const plugin = Object.create(Plugin.prototype);
            Object.defineProperties(plugin, {{
                name: {{ value: p.name, enumerable: true }},
                filename: {{ value: p.filename, enumerable: true }},
                description: {{ value: p.description, enumerable: true }},
                length: {{ value: 0, enumerable: true }}
            }});
            pluginArray[idx] = plugin;
        }});

        Object.defineProperty(pluginArray, 'length', {{ value: pluginData.length }});
        Object.defineProperty(navigator, 'plugins', {{ get: () => pluginArray, configurable: true }});

        // -------------------------------------------------------------
        // FP-5: navigator.webdriver full property descriptor cleanup
        // -------------------------------------------------------------
        const proto = Object.getPrototypeOf(navigator);
        if (proto && Object.prototype.hasOwnProperty.call(proto, 'webdriver')) {{
            try {{
                delete proto.webdriver;
            }} catch (e) {{}}
        }}
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined,
            configurable: true,
            enumerable: false
        }});

        // -------------------------------------------------------------
        // FP-6: AudioContext session-level salt
        // -------------------------------------------------------------
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {{
            const origGetTimestamp = AudioCtx.prototype.getOutputTimestamp;
            if (origGetTimestamp) {{
                AudioCtx.prototype.getOutputTimestamp = function () {{
                    const ts = origGetTimestamp.apply(this, arguments);
                    if (ts && typeof ts.contextTime === 'number') {{
                        ts.contextTime += SESSION_SALT;
                    }}
                    return ts;
                }};
            }}

            const origCreateAnalyser = AudioCtx.prototype.createAnalyser;
            if (origCreateAnalyser) {{
                AudioCtx.prototype.createAnalyser = function () {{
                    const node = origCreateAnalyser.apply(this, arguments);
                    const origGetFloat = node.getFloatFrequencyData;
                    node.getFloatFrequencyData = function (arr) {{
                        origGetFloat.apply(this, arguments);
                        for (let i = 0; i < arr.length; i += 8) {{
                            arr[i] += SESSION_SALT;
                        }}
                    }};
                    return node;
                }};
            }}
        }}
    }})();
    """


# ==============================================================================
# 🚀 UNIFIED RUNTIME MANAGER (Example Implementation Hook)
# ==============================================================================
class IVTPatchManager:
    """Convenience class to bundle both layers for workers."""
    def __init__(self, ipqs_api_key: str = ""):
        self.ip_checker = IPQualityChecker(api_key=ipqs_api_key)
        self.geo_resolver = GeoResolver()
        self.proxy_validator = ProxyHeaderValidator()
        self.ua_manager = UserAgentManager(min_chrome_version=118)

    def get_browser_launch_args(self) -> List[str]:
        """Returns NET-3 WebRTC protection flags."""
        return list(WEBRTC_CHROMIUM_ARGS)

    def get_stealth_script(self, session_salt: Optional[float] = None) -> str:
        """Returns FP-3 through FP-6 JavaScript payload for Page.addScriptToEvaluateOnNewDocument."""
        return generate_stealth_js(session_salt)
