"""
fingerprint.py — Deterministic browser identity derived from sha256(proxy_id).
All randomness is seeded; same proxy_id always yields the same fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import struct
from dataclasses import dataclass
from typing import Optional

from pool import Proxy
import ua_provider

# ── Desktop UAs ────────────────────────────────────────────────────────────────
_DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# ── Mobile UAs ─────────────────────────────────────────────────────────────────
_MOBILE_UAS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Samsung SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.6723.37 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; OnePlus 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
]

# ── WebGL vendor/renderer pairs (never SwiftShader) ────────────────────────────
_WEBGL_PAIRS = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Apple", "Apple GPU"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M1, OpenGL 4.1)"),
]

# ── Desktop viewport sizes ──────────────────────────────────────────────────────
_DESKTOP_VIEWPORTS = [
    (1920, 1080), (1920, 1200), (1680, 1050),
    (1440, 900), (1366, 768), (1536, 864),
    (2560, 1440), (1280, 800),
]

# ── Mobile viewport sizes ───────────────────────────────────────────────────────
_MOBILE_VIEWPORTS = [
    (390, 844), (414, 896), (412, 915),
    (375, 812), (393, 852), (360, 800),
]

# ── Platform strings ────────────────────────────────────────────────────────────
_DESKTOP_PLATFORMS = ["Win32", "Win32", "Win32", "MacIntel", "Linux x86_64"]
_MOBILE_PLATFORMS = ["Linux armv8l", "iPhone", "Linux aarch64"]


@dataclass
class Fingerprint:
    proxy_id: str
    is_mobile: bool
    user_agent: str
    viewport_width: int
    viewport_height: int
    platform: str
    hardware_concurrency: int
    device_memory: int
    max_touch_points: int
    languages: list[str]
    timezone: str
    locale: str
    webgl_vendor: str
    webgl_renderer: str
    screen_avail_offset: int   # px subtracted from screen height for taskbar
    downlink: float
    rtt: int
    canvas_seed: int
    audio_seed: float

    @property
    def digest(self) -> str:
        """Stable string digest of this fingerprint for audit checks."""
        blob = json.dumps({
            "proxy_id": self.proxy_id,
            "ua": self.user_agent,
            "platform": self.platform,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
        }, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build(proxy: Proxy, force_mobile: Optional[bool] = None) -> Fingerprint:
    """
    Build a fully deterministic Fingerprint from the proxy's sha256 seed.
    force_mobile overrides the mobile/desktop split if set.
    """
    seed_bytes = proxy.fingerprint_seed          # sha256(proxy_id), 32 bytes
    rng = _SeededRng(seed_bytes)

    # 80–85% desktop, 15–20% mobile
    if force_mobile is not None:
        is_mobile = force_mobile
    else:
        is_mobile = rng.chance(0.17)

    desktop_pool = ua_provider.get_desktop_uas()
    mobile_pool = ua_provider.get_mobile_uas()

    if is_mobile:
        ua = rng.choice(mobile_pool)
        vw, vh = rng.choice(_MOBILE_VIEWPORTS)
        platform = ua_provider.infer_platform(ua)
        hc = rng.choice([4, 6, 8])
        dm = rng.choice([2, 4])
        mtp = 5
    else:
        ua = rng.choice(desktop_pool)
        vw, vh = rng.choice(_DESKTOP_VIEWPORTS)
        platform = ua_provider.infer_platform(ua)
        hc = rng.choice([4, 6, 8, 12, 16])
        dm = rng.choice([4, 8, 16])
        mtp = 0

    webgl_vendor, webgl_renderer = rng.choice(_WEBGL_PAIRS)
    screen_avail_offset = rng.randint(60, 140)

    # Connection
    downlink = round(rng.uniform(4.0, 12.0), 1)
    rtt = rng.randint(40, 120)

    # Canvas/audio noise seeds
    canvas_seed = rng.randint(0, 2**31 - 1)
    audio_seed = rng.uniform(0.00001, 0.0001)

    # Languages: primary locale + English fallback
    primary = proxy.geo.locale
    langs = [primary] if primary == "en-US" else [primary, "en-US", "en"]

    return Fingerprint(
        proxy_id=proxy.proxy_id,
        is_mobile=is_mobile,
        user_agent=ua,
        viewport_width=vw,
        viewport_height=vh,
        platform=platform,
        hardware_concurrency=hc,
        device_memory=dm,
        max_touch_points=mtp,
        languages=langs,
        timezone=proxy.geo.timezone,
        locale=proxy.geo.locale,
        webgl_vendor=webgl_vendor,
        webgl_renderer=webgl_renderer,
        screen_avail_offset=screen_avail_offset,
        downlink=downlink,
        rtt=rtt,
        canvas_seed=canvas_seed,
        audio_seed=audio_seed,
    )


def _extract_client_hints(fp: Fingerprint) -> dict:
    ua = fp.user_agent
    m_ver = re.search(r"(?:Chrome|CriOS|Edg)/(\d+)(?:\.([\d\.]+))?", ua)
    major_ver = m_ver.group(1) if m_ver else "130"
    full_ver = f"{major_ver}.{m_ver.group(2)}" if m_ver and m_ver.group(2) else f"{major_ver}.0.0.0"

    is_mob = fp.is_mobile
    ch_platform = "Windows"
    ch_platform_version = "15.0.0"
    ch_arch = "x86"
    ch_model = ""

    ua_low = ua.lower()
    if "android" in ua_low:
        ch_platform = "Android"
        ch_arch = "arm"
        m_os = re.search(r"Android (\d+(?:\.\d+)?)", ua, re.IGNORECASE)
        ch_platform_version = f"{m_os.group(1)}.0.0" if m_os else "14.0.0"
        m_mod = re.search(r"Android [^;]+; ([^)]+)\)", ua)
        if m_mod:
            ch_model = m_mod.group(1).split("Build")[0].strip()
        else:
            ch_model = "SM-S928B"
    elif "iphone" in ua_low or "ipad" in ua_low:
        ch_platform = "iOS"
        ch_arch = "arm"
        ch_model = "iPhone" if "iphone" in ua_low else "iPad"
        ch_platform_version = "17.4.0"
    elif "macintosh" in ua_low or "mac os x" in ua_low:
        ch_platform = "macOS"
        ch_arch = "arm"
        ch_model = ""
        ch_platform_version = "14.5.0"
    elif "linux" in ua_low or "x11" in ua_low:
        ch_platform = "Linux"
        ch_arch = "x86"
        ch_model = ""
        ch_platform_version = "6.5.0"

    brands = [
        {"brand": "Chromium", "version": major_ver},
        {"brand": "Google Chrome", "version": major_ver},
        {"brand": "Not?A_Brand", "version": "99"},
    ]
    if "edg" in ua_low:
        brands[1] = {"brand": "Microsoft Edge", "version": major_ver}

    return {
        "major_ver": major_ver,
        "full_ver": full_ver,
        "brands": brands,
        "mobile": is_mob,
        "platform": ch_platform,
        "platform_version": ch_platform_version,
        "architecture": ch_arch,
        "bitness": "64",
        "model": ch_model,
    }


def init_script(fp: Fingerprint) -> str:
    """
    Return a JS string to inject via page.add_init_script().
    Patches all fingerprint vectors before any page script runs.
    """
    langs_json = json.dumps(fp.languages)
    screen_avail_height = fp.viewport_height - fp.screen_avail_offset
    ch = _extract_client_hints(fp)

    return f"""
(function() {{
  // ── webdriver ──────────────────────────────────────────────────────────────
  Object.defineProperty(navigator, 'webdriver', {{
    get: () => undefined,
    configurable: true,
  }});

  // ── platform / vendor ──────────────────────────────────────────────────────
  Object.defineProperty(navigator, 'platform',   {{ get: () => {json.dumps(fp.platform)}, configurable: true }});
  Object.defineProperty(navigator, 'vendor',     {{ get: () => 'Google Inc.', configurable: true }});

  // ── Client Hints (navigator.userAgentData) ─────────────────────────────────
  const _chBrands = {json.dumps(ch["brands"])};
  const _chMobile = {str(ch["mobile"]).lower()};
  const _chPlatform = {json.dumps(ch["platform"])};
  const _chPlatformVersion = {json.dumps(ch["platform_version"])};
  const _chArch = {json.dumps(ch["architecture"])};
  const _chBitness = {json.dumps(ch["bitness"])};
  const _chModel = {json.dumps(ch["model"])};
  const _chFullVer = {json.dumps(ch["full_ver"])};

  const _UAP = (typeof window !== 'undefined' && window.NavigatorUAData) ? window.NavigatorUAData.prototype : Object.prototype;
  const _uad = Object.create(_UAP);

  Object.defineProperty(_uad, 'brands',   {{ get: () => _chBrands,   enumerable: true, configurable: true }});
  Object.defineProperty(_uad, 'mobile',   {{ get: () => _chMobile,   enumerable: true, configurable: true }});
  Object.defineProperty(_uad, 'platform', {{ get: () => _chPlatform, enumerable: true, configurable: true }});

  const _makeNative = (fn, name) => {{
    Object.defineProperty(fn, 'name', {{ value: name, configurable: true }});
    Object.defineProperty(fn, 'toString', {{
      value: function() {{ return 'function ' + name + '() {{ [native code] }}'; }},
      configurable: true
    }});
    return fn;
  }};

  _uad.getHighEntropyValues = _makeNative(function(hints) {{
    return Promise.resolve({{
      architecture: _chArch,
      bitness: _chBitness,
      brands: _chBrands,
      formFactor: _chMobile ? ['mobile'] : ['desktop'],
      fullVersionList: [
        {{ brand: _chBrands[0].brand, version: _chFullVer }},
        {{ brand: _chBrands[1].brand, version: _chFullVer }},
        {{ brand: 'Not?A_Brand', version: '99.0.0.0' }}
      ],
      mobile: _chMobile,
      model: _chModel,
      platform: _chPlatform,
      platformVersion: _chPlatformVersion,
      uaFullVersion: _chFullVer,
      wow64: false
    }});
  }}, 'getHighEntropyValues');

  _uad.toJSON = _makeNative(function() {{
    return {{
      brands: _chBrands,
      mobile: _chMobile,
      platform: _chPlatform
    }};
  }}, 'toJSON');

  Object.defineProperty(navigator, 'userAgentData', {{
    get: () => _uad,
    configurable: true,
    enumerable: true
  }});

  // ── hardware ───────────────────────────────────────────────────────────────
  Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {fp.hardware_concurrency}, configurable: true }});
  Object.defineProperty(navigator, 'deviceMemory',        {{ get: () => {fp.device_memory},         configurable: true }});
  Object.defineProperty(navigator, 'maxTouchPoints',      {{ get: () => {fp.max_touch_points},      configurable: true }});

  // ── languages ──────────────────────────────────────────────────────────────
  Object.defineProperty(navigator, 'languages', {{ get: () => {langs_json}, configurable: true }});
  Object.defineProperty(navigator, 'language',  {{ get: () => {json.dumps(fp.languages[0])}, configurable: true }});

  // ── plugins / mimeTypes ───────────────────────────────────────────────────
  const fakePlugin = (name, filename, desc) => {{
    const p = Object.create(Plugin.prototype);
    Object.defineProperty(p, 'name',     {{ get: () => name }});
    Object.defineProperty(p, 'filename', {{ get: () => filename }});
    Object.defineProperty(p, 'description', {{ get: () => desc }});
    Object.defineProperty(p, 'length',   {{ get: () => 0 }});
    return p;
  }};
  const plugins = [
    fakePlugin('Chrome PDF Plugin',      'internal-pdf-viewer',  'Portable Document Format'),
    fakePlugin('Chrome PDF Viewer',      'mhjfbmdgcfjbbpaeojofohoefgiehjai', ''),
    fakePlugin('Native Client',          'internal-nacl-plugin',  'Native Client'),
  ];
  Object.defineProperty(navigator, 'plugins', {{
    get: () => plugins,
    configurable: true,
  }});
  Object.defineProperty(navigator, 'mimeTypes', {{
    get: () => ({{ length: 2, 0: {{ type: 'application/pdf' }}, 1: {{ type: 'application/x-nacl' }} }}),
    configurable: true,
  }});

  // ── chrome object ──────────────────────────────────────────────────────────
  if (!window.chrome) {{ window.chrome = {{}}; }}
  window.chrome.runtime = {{
    connect: () => ({{ onDisconnect: {{ addListener: () => {{}} }}, postMessage: () => {{}} }}),
    sendMessage: () => {{}},
    id: undefined,
  }};
  window.chrome.app = {{
    isInstalled: false,
    InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }},
    RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }},
  }};
  window.chrome.csi = () => ({{ startE: Date.now(), onloadT: Date.now(), pageT: 1000, tran: 15 }});
  window.chrome.loadTimes = () => ({{
    requestTime: Date.now() / 1000,
    startLoadTime: Date.now() / 1000,
    commitLoadTime: Date.now() / 1000,
    finishDocumentLoadTime: Date.now() / 1000,
    finishLoadTime: Date.now() / 1000,
    firstPaintTime: 0,
    firstPaintAfterLoadTime: 0,
    navigationType: 'Other',
    wasFetchedViaSpdy: false,
    wasNpnNegotiated: false,
    npnNegotiatedProtocol: 'unknown',
    wasAlternateProtocolAvailable: false,
    connectionInfo: 'unknown',
  }});

  // ── permissions ───────────────────────────────────────────────────────────
  const origPermQuery = navigator.permissions && navigator.permissions.query.bind(navigator.permissions);
  if (origPermQuery) {{
    navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications'
        ? Promise.resolve({{ state: Notification.permission }})
        : origPermQuery(parameters)
    );
  }}

  // ── WebGL vendor / renderer ───────────────────────────────────────────────
  const patchWebGL = (ctx) => {{
    if (!ctx) return;
    const origGetParam = ctx.prototype.getParameter;
    ctx.prototype.getParameter = function(param) {{
      if (param === 37445) return {json.dumps(fp.webgl_vendor)};   // UNMASKED_VENDOR_WEBGL
      if (param === 37446) return {json.dumps(fp.webgl_renderer)};  // UNMASKED_RENDERER_WEBGL
      return origGetParam.call(this, param);
    }};
  }};
  patchWebGL(WebGLRenderingContext);
  if (typeof WebGL2RenderingContext !== 'undefined') patchWebGL(WebGL2RenderingContext);

  // ── screen ────────────────────────────────────────────────────────────────
  Object.defineProperty(screen, 'colorDepth',   {{ get: () => 24, configurable: true }});
  Object.defineProperty(screen, 'pixelDepth',   {{ get: () => 24, configurable: true }});
  Object.defineProperty(screen, 'availHeight',  {{ get: () => {screen_avail_height}, configurable: true }});
  Object.defineProperty(screen, 'availWidth',   {{ get: () => {fp.viewport_width},   configurable: true }});

  // ── connection ────────────────────────────────────────────────────────────
  if (navigator.connection) {{
    Object.defineProperty(navigator.connection, 'effectiveType', {{ get: () => '4g', configurable: true }});
    Object.defineProperty(navigator.connection, 'downlink',      {{ get: () => {fp.downlink}, configurable: true }});
    Object.defineProperty(navigator.connection, 'rtt',           {{ get: () => {fp.rtt}, configurable: true }});
  }}

  // ── canvas noise (deterministic seeded) ──────────────────────────────────
  const _canvasSeed = {fp.canvas_seed};
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  HTMLCanvasElement.prototype.toDataURL = function(...args) {{
    const ctx2d = this.getContext('2d');
    if (ctx2d) {{
      const imgd = ctx2d.getImageData(0, 0, this.width || 1, this.height || 1);
      let s = _canvasSeed;
      for (let i = 0; i < imgd.data.length; i += 4) {{
        s = (s * 1664525 + 1013904223) & 0xffffffff;
        imgd.data[i] = (imgd.data[i] + (s & 0x03)) & 0xff;
      }}
      ctx2d.putImageData(imgd, 0, 0);
    }}
    return origToDataURL.apply(this, args);
  }};

  // ── audio context jitter ──────────────────────────────────────────────────
  const _audioJitter = {fp.audio_seed};
  if (typeof AudioBuffer !== 'undefined') {{
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {{
      const data = origGetChannelData.call(this, channel);
      for (let i = 0; i < data.length; i++) {{
        data[i] += _audioJitter * (((i * 1664525 + 1013904223) & 0x7fffffff) / 0x7fffffff - 0.5);
      }}
      return data;
    }};
  }}
}})();
"""


class _SeededRng:
    """LCG-based seeded RNG so fingerprints are fully deterministic."""

    def __init__(self, seed_bytes: bytes):
        self._state = int.from_bytes(seed_bytes[:8], "big")

    def _next(self) -> int:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._state

    def randint(self, lo: int, hi: int) -> int:
        return lo + (self._next() % (hi - lo + 1))

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (self._next() / 0xFFFFFFFFFFFFFFFF) * (hi - lo)

    def chance(self, p: float) -> bool:
        return self.uniform(0, 1) < p

    def choice(self, seq: list):
        return seq[self._next() % len(seq)]

