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
from dataclasses import dataclass, field
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
    fonts: list[str] = field(default_factory=list)
    extensions: list[dict] = field(default_factory=list)

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


# ── Platform Fonts Catalogs (Step 3.1: Font Enumeration Spoofing) ─────────────
_WINDOWS_FONTS = [
    "Arial", "Arial Black", "Bahnschrift", "Calibri", "Cambria", "Candara",
    "Comic Sans MS", "Consolas", "Constantia", "Corbel", "Courier New", "Ebrima",
    "Franklin Gothic Medium", "Gabriola", "Gadugi", "Georgia", "Impact", "Ink Free",
    "Javanese Text", "Leelawadee UI", "Lucida Console", "Lucida Sans Unicode",
    "Malgun Gothic", "Marlett", "Microsoft Himalaya", "Microsoft JhengHei",
    "Microsoft New Tai Lue", "Microsoft PhagsPa", "Microsoft Sans Serif",
    "Microsoft Tai Le", "Microsoft YaHei", "Microsoft Yi Baiti", "MS Gothic",
    "MS PGothic", "MS UI Gothic", "MV Boli", "Myanmar Text", "Nirmala UI",
    "Palatino Linotype", "Segoe Print", "Segoe Script", "Segoe UI",
    "Segoe UI Historic", "Segoe UI Emoji", "Segoe UI Symbol", "SimSun",
    "Sitka Small", "Sylfaen", "Symbol", "Tahoma", "Times New Roman",
    "Trebuchet MS", "Verdana", "Webdings", "Wingdings", "Yu Gothic"
]

_MACOS_FONTS = [
    "San Francisco", "Helvetica", "Helvetica Neue", "Arial", "Arial Black",
    "Avenir", "Avenir Next", "Courier", "Courier New", "Georgia", "Gill Sans",
    "Lucida Grande", "Menlo", "Monaco", "Optima", "Palatino", "Times",
    "Times New Roman", "Trebuchet MS", "Verdana", "Apple Color Emoji", "Geneva",
    "Futura", "Baskerville", "Copperplate", "Didot"
]

_ANDROID_FONTS = [
    "Roboto", "Noto Sans", "Droid Sans", "Droid Serif", "Droid Sans Mono",
    "Noto Color Emoji", "Noto Serif", "Roboto Medium", "Roboto Light",
    "Roboto Condensed", "Cutive Mono"
]

_LINUX_FONTS = [
    "Liberation Sans", "Liberation Serif", "Liberation Mono", "DejaVu Sans",
    "DejaVu Serif", "DejaVu Sans Mono", "Ubuntu", "Ubuntu Mono", "FreeSans",
    "FreeSerif", "FreeMono", "Noto Color Emoji"
]


def _generate_fonts(platform: str, is_mobile: bool, rng: _SeededRng) -> list[str]:
    """Return a deterministic, platform-coherent subset of realistic system fonts."""
    plat_low = platform.lower()
    if is_mobile or "android" in plat_low:
        catalog = list(_ANDROID_FONTS)
    elif "mac" in plat_low or "iphone" in plat_low or "ios" in plat_low:
        catalog = list(_MACOS_FONTS)
    elif "linux" in plat_low:
        catalog = list(_LINUX_FONTS)
    else:
        catalog = list(_WINDOWS_FONTS)

    core = catalog[:12]
    rest = catalog[12:]
    if rest:
        sample_size = min(len(rest), rng.randint(len(rest) // 2, len(rest)))
        shuffled = list(rest)
        for i in range(len(shuffled) - 1, 0, -1):
            j = rng.randint(0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        selected = sorted(set(core + shuffled[:sample_size]))
    else:
        selected = sorted(set(core))
    return selected


# ── Step 3.3: Browser Extension Signatures ────────────────────────────────────
_DESKTOP_EXTENSIONS = [
    {
        "id": "ghbmnnjldmmeejimcflloakocagkodme",
        "name": "Google Docs Offline",
        "version": "1.61.4",
    },
    {
        "id": "nmmhkkegccagdldgiimedpiccmgmieda",
        "name": "Google Pay / Web Store Payments",
        "version": "1.0.0.6",
    },
    {
        "id": "cjpalhdlnbpafiamejdnhcphjbkeiagm",
        "name": "uBlock Origin",
        "version": "1.58.0",
    },
    {
        "id": "kbfnbcaeplbcioakkpcpgfkobkghlhen",
        "name": "Grammarly",
        "version": "14.1165.0",
    },
    {
        "id": "hdokiejnpimakedhajhdlcegeplioahd",
        "name": "LastPass",
        "version": "4.120.0",
    },
]


def _generate_extensions(is_mobile: bool, rng: _SeededRng) -> list[dict]:
    """Return deterministic set of realistic installed extensions for desktop Chrome."""
    if is_mobile:
        return []
    base = [_DESKTOP_EXTENSIONS[0]]  # Google Docs Offline default in Chrome
    pool = _DESKTOP_EXTENSIONS[1:]
    k = rng.randint(1, len(pool))
    shuffled = list(pool)
    for i in range(len(shuffled) - 1, 0, -1):
        j = rng.randint(0, i)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return base + shuffled[:k]


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

    # Step 3.1: Seeded platform fonts
    fonts = _generate_fonts(platform, is_mobile, rng)

    # Step 3.3: Seeded browser extensions
    extensions = _generate_extensions(is_mobile, rng)

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
        fonts=fonts,
        extensions=extensions,
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


def _generate_media_devices(fp: Fingerprint) -> list[dict]:
    seed = fp.canvas_seed
    devs = []
    if fp.is_mobile:
        configs = [
            ("audioinput", "mic_in"),
            ("audiooutput", "speaker_out"),
            ("videoinput", "cam_back"),
            ("videoinput", "cam_front"),
        ]
    else:
        configs = [
            ("audioinput", "mic_default"),
            ("audiooutput", "speaker_default"),
            ("videoinput", "webcam_default"),
        ]

    for kind, tag in configs:
        d_id = hashlib.sha256(f"{seed}_{kind}_{tag}".encode()).hexdigest()
        g_id = hashlib.sha256(f"{seed}_{kind}_group".encode()).hexdigest()
        devs.append({"kind": kind, "deviceId": d_id, "groupId": g_id, "label": ""})
    return devs


def _generate_battery(fp: Fingerprint) -> dict:
    seed = fp.canvas_seed
    if fp.is_mobile:
        level = round(0.45 + (seed % 48) / 100.0, 2)
        charging = (seed % 5) == 0
    else:
        is_laptop = (seed % 2) == 0
        if is_laptop:
            level = round(0.55 + (seed % 42) / 100.0, 2)
            charging = (seed % 3) == 0
        else:
            level = 1.0
            charging = True

    ch_time = 0 if level == 1.0 else ((seed % 3600) + 1800 if charging else None)
    dis_time = None if charging else ((seed % 14400) + 7200)

    return {
        "level": level,
        "charging": charging,
        "chargingTime": ch_time,
        "dischargingTime": dis_time,
    }


def _calibrate_gpu_noise(webgl_renderer: str, is_mobile: bool) -> tuple[int, int]:
    """
    Step 3.5: Calibrate canvas noise range to match real devices with that GPU architecture.
    Returns (max_lsb, stride_mod).
    """
    r = webgl_renderer.lower()
    if is_mobile or "adreno" in r or "mali" in r or "apple gpu" in r:
        return (2, 3)
    elif "nvidia" in r or "geforce" in r:
        return (2, 4)
    elif "radeon" in r or "amd" in r:
        return (2, 4)
    elif "intel" in r or "iris" in r:
        return (1, 6)
    else:
        return (1, 5)


def init_script(fp: Fingerprint) -> str:
    """
    Return a JS string to inject via page.add_init_script().
    Patches all fingerprint vectors before any page script runs.
    """
    langs_json = json.dumps(fp.languages)
    screen_avail_height = fp.viewport_height - fp.screen_avail_offset
    ch = _extract_client_hints(fp)
    media_devs = _generate_media_devices(fp)
    bat_info = _generate_battery(fp)
    gpu_max_lsb, gpu_stride_mod = _calibrate_gpu_noise(fp.webgl_renderer, fp.is_mobile)

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

  // ── chrome object & Step 3.3: Extension Emulation ──────────────────────────
  if (!window.chrome) {{ window.chrome = {{}}; }}
  const _installedExtensions = {json.dumps(fp.extensions)};
  const _installedExtIds = new Set(_installedExtensions.map(e => e.id));

  if (!{json.dumps(fp.is_mobile)}) {{
    window.chrome.runtime = {{
      id: undefined,
      OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }},
      OnRestartRequiredReason: {{ APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }},
      PlatformArch: {{ ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
      PlatformNaclArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
      PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }},
      RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }},
      getURL: _makeNative(function(path) {{
        return 'chrome-extension://' + (_installedExtensions[0] ? _installedExtensions[0].id : 'ghbmnnjldmmeejimcflloakocagkodme') + '/' + (path || '').replace(/^\\//, '');
      }}, 'getURL'),
      getManifest: _makeNative(function() {{
        return {{
          manifest_version: 3,
          name: _installedExtensions[0] ? _installedExtensions[0].name : 'Google Docs Offline',
          version: _installedExtensions[0] ? _installedExtensions[0].version : '1.61.4'
        }};
      }}, 'getManifest'),
      sendMessage: _makeNative(function(targetId, message, options, responseCallback) {{
        let cb = typeof options === 'function' ? options : responseCallback;
        const extId = typeof targetId === 'string' ? targetId : '';
        const isInstalled = _installedExtIds.has(extId);

        if (isInstalled) {{
          if (typeof cb === 'function') {{
            setTimeout(() => {{
              window.chrome.runtime.lastError = undefined;
              cb({{ status: 'ok', version: '3.0.0' }});
            }}, 5);
          }}
          return Promise.resolve({{ status: 'ok', version: '3.0.0' }});
        }} else {{
          if (typeof cb === 'function') {{
            setTimeout(() => {{
              window.chrome.runtime.lastError = {{ message: 'Could not establish connection. Receiving end does not exist.' }};
              cb(undefined);
            }}, 5);
          }}
          return Promise.reject(new Error('Could not establish connection. Receiving end does not exist.'));
        }}
      }}, 'sendMessage'),
      connect: _makeNative(function(targetId, connectInfo) {{
        const extId = typeof targetId === 'string' ? targetId : '';
        const isInstalled = _installedExtIds.has(extId);
        return {{
          name: connectInfo ? connectInfo.name || '' : '',
          sender: {{ id: extId }},
          onDisconnect: {{
            addListener: _makeNative(function(fn) {{
              if (!isInstalled && typeof fn === 'function') {{
                setTimeout(() => fn({{ error: {{ message: 'Could not establish connection.' }} }}), 5);
              }}
            }}, 'addListener'),
            removeListener: _makeNative(function() {{}}, 'removeListener'),
            hasListener: _makeNative(function() {{ return false; }}, 'hasListener'),
          }},
          onMessage: {{
            addListener: _makeNative(function() {{}}, 'addListener'),
            removeListener: _makeNative(function() {{}}, 'removeListener'),
            hasListener: _makeNative(function() {{ return false; }}, 'hasListener'),
          }},
          postMessage: _makeNative(function() {{}}, 'postMessage'),
          disconnect: _makeNative(function() {{}}, 'disconnect'),
        }};
      }}, 'connect'),
    }};
  }} else {{
    window.chrome.runtime = {{
      id: undefined,
      connect: () => ({{ onDisconnect: {{ addListener: () => {{}} }}, postMessage: () => {{}} }}),
      sendMessage: () => {{}},
    }};
  }}
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
    ctx.prototype.getParameter = _makeNative(function(param) {{
      if (param === 37445) return {json.dumps(fp.webgl_vendor)};   // UNMASKED_VENDOR_WEBGL
      if (param === 37446) return {json.dumps(fp.webgl_renderer)};  // UNMASKED_RENDERER_WEBGL
      return origGetParam.call(this, param);
    }}, 'getParameter');
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

  // ── mediaDevices (enumerateDevices) ───────────────────────────────────────
  const _mockDevData = {json.dumps(media_devs)};
  const _devProto = (typeof window !== 'undefined' && window.MediaDeviceInfo)
    ? window.MediaDeviceInfo.prototype
    : Object.prototype;

  const _mockDevices = _mockDevData.map((d) => {{
    const item = Object.create(_devProto);
    Object.defineProperties(item, {{
      deviceId: {{ value: d.deviceId, enumerable: true }},
      kind:     {{ value: d.kind,     enumerable: true }},
      label:    {{ value: d.label,    enumerable: true }},
      groupId:  {{ value: d.groupId,  enumerable: true }},
      toJSON:   {{
        value: _makeNative(function() {{
          return {{ deviceId: this.deviceId, kind: this.kind, label: this.label, groupId: this.groupId }};
        }}, 'toJSON'),
        enumerable: true
      }}
    }});
    return item;
  }});

  if (!navigator.mediaDevices) {{
    const _mdProto = (typeof window !== 'undefined' && window.MediaDevices)
      ? window.MediaDevices.prototype
      : (typeof EventTarget !== 'undefined' ? EventTarget.prototype : Object.prototype);
    navigator.mediaDevices = Object.create(_mdProto);
  }}

  navigator.mediaDevices.enumerateDevices = _makeNative(function() {{
    return Promise.resolve(_mockDevices);
  }}, 'enumerateDevices');

  // ── Battery Status API (navigator.getBattery) ─────────────────────────────
  const _batData = {json.dumps(bat_info)};
  const _bmProto = (typeof window !== 'undefined' && window.BatteryManager)
    ? window.BatteryManager.prototype
    : (typeof EventTarget !== 'undefined' ? EventTarget.prototype : Object.prototype);

  const _batteryManager = Object.create(_bmProto);
  Object.defineProperties(_batteryManager, {{
    charging:        {{ value: _batData.charging, enumerable: true }},
    chargingTime:    {{ value: _batData.chargingTime === null ? Infinity : _batData.chargingTime, enumerable: true }},
    dischargingTime: {{ value: _batData.dischargingTime === null ? Infinity : _batData.dischargingTime, enumerable: true }},
    level:           {{ value: _batData.level, enumerable: true }},
    onchargingchange:        {{ value: null, writable: true, enumerable: true }},
    onchargingtimechange:    {{ value: null, writable: true, enumerable: true }},
    ondischargingtimechange: {{ value: null, writable: true, enumerable: true }},
    onlevelchange:           {{ value: null, writable: true, enumerable: true }}
  }});

  navigator.getBattery = _makeNative(function() {{
    return Promise.resolve(_batteryManager);
  }}, 'getBattery');

  // ── canvas & WebGL buffer integrity (Step 3.5: GPU Calibrated LSB Jitter) ──
  const _canvasSeed = {fp.canvas_seed};
  const _gpuMaxLsb = {gpu_max_lsb};
  const _gpuStrideMod = {gpu_stride_mod};
  const _applyDeterministicJitter = (data, w, h, sx, sy) => {{
    let seed = _canvasSeed;
    const len = data.length;
    for (let i = 0; i < len; i += 4) {{
      const pIdx = i >> 2;
      if ((pIdx % _gpuStrideMod) !== 0) continue;
      const px = (pIdx % w) + sx;
      const py = Math.floor(pIdx / w) + sy;
      const hVal = (Math.imul(px ^ seed, 1664525) + Math.imul(py ^ 0x5bd1e995, 1013904223)) ^ seed;
      const rawR = (hVal & 3);
      const jR = rawR === 1 ? _gpuMaxLsb : (rawR === 2 ? -_gpuMaxLsb : 0);
      const rawB = ((hVal >> 2) & 3);
      const jB = rawB === 1 ? _gpuMaxLsb : (rawB === 2 ? -_gpuMaxLsb : 0);
      if (jR !== 0) data[i] = Math.max(0, Math.min(255, data[i] + jR));
      if (jB !== 0) data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + jB));
    }}
  }};

  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = _makeNative(function(sx, sy, sw, sh, ...args) {{
    const imgData = origGetImageData.call(this, sx, sy, sw, sh, ...args);
    if (imgData && imgData.data && imgData.data.length > 0) {{
      _applyDeterministicJitter(imgData.data, imgData.width, imgData.height, sx, sy);
    }}
    return imgData;
  }}, 'getImageData');

  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = _makeNative(function(...args) {{
    const w = this.width;
    const h = this.height;
    if (w > 0 && h > 0) {{
      try {{
        const offscreen = document.createElement('canvas');
        offscreen.width = w;
        offscreen.height = h;
        const offCtx = offscreen.getContext('2d');
        if (offCtx) {{
          offCtx.drawImage(this, 0, 0);
          const imgd = origGetImageData.call(offCtx, 0, 0, w, h);
          if (imgd && imgd.data) {{
            _applyDeterministicJitter(imgd.data, w, h, 0, 0);
            offCtx.putImageData(imgd, 0, 0);
            return origToDataURL.apply(offscreen, args);
          }}
        }}
      }} catch(e) {{}}
    }}
    return origToDataURL.apply(this, args);
  }}, 'toDataURL');

  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  if (origToBlob) {{
    HTMLCanvasElement.prototype.toBlob = _makeNative(function(callback, ...args) {{
      const w = this.width;
      const h = this.height;
      if (w > 0 && h > 0 && typeof callback === 'function') {{
        try {{
          const offscreen = document.createElement('canvas');
          offscreen.width = w;
          offscreen.height = h;
          const offCtx = offscreen.getContext('2d');
          if (offCtx) {{
            offCtx.drawImage(this, 0, 0);
            const imgd = origGetImageData.call(offCtx, 0, 0, w, h);
            if (imgd && imgd.data) {{
              _applyDeterministicJitter(imgd.data, w, h, 0, 0);
              offCtx.putImageData(imgd, 0, 0);
              return origToBlob.call(offscreen, callback, ...args);
            }}
          }}
        }} catch(e) {{}}
      }}
      return origToBlob.apply(this, [callback, ...args]);
    }}, 'toBlob');
  }}

  const patchReadPixels = (glProto) => {{
    if (!glProto || !glProto.prototype || !glProto.prototype.readPixels) return;
    const origReadPixels = glProto.prototype.readPixels;
    glProto.prototype.readPixels = _makeNative(function(x, y, w, h, format, type, pixels, ...args) {{
      const res = origReadPixels.call(this, x, y, w, h, format, type, pixels, ...args);
      if (pixels && pixels.length > 0) {{
        _applyDeterministicJitter(pixels, w, h, x, y);
      }}
      return res;
    }}, 'readPixels');
  }};
  patchReadPixels(WebGLRenderingContext);
  if (typeof WebGL2RenderingContext !== 'undefined') patchReadPixels(WebGL2RenderingContext);

  // ── audio context jitter (Step 7: WebAudio / AudioContext stealth) ──────
  const _audioJitter = {fp.audio_seed};
  const _jitteredBuffers = new WeakSet();

  if (typeof AudioBuffer !== 'undefined' && AudioBuffer.prototype) {{
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    if (origGetChannelData) {{
      AudioBuffer.prototype.getChannelData = _makeNative(function(channel) {{
        const data = origGetChannelData.call(this, channel);
        if (!_jitteredBuffers.has(this)) {{
          for (let i = 0; i < data.length; i++) {{
            data[i] += _audioJitter * (((i * 1664525 + 1013904223) & 0x7fffffff) / 0x7fffffff - 0.5);
          }}
          _jitteredBuffers.add(this);
        }}
        return data;
      }}, 'getChannelData');
    }}
  }}

  const _patchAudioContext = (ctxProto) => {{
    if (!ctxProto || !ctxProto.prototype || !ctxProto.prototype.getOutputTimestamp) return;
    const origGot = ctxProto.prototype.getOutputTimestamp;
    ctxProto.prototype.getOutputTimestamp = _makeNative(function() {{
      const ts = origGot.call(this);
      const jitterFactor = (_audioJitter * 1000) % 0.005;
      return {{
        contextTime: (ts.contextTime || this.currentTime || 0) + jitterFactor,
        performanceTime: (ts.performanceTime || performance.now()) + (jitterFactor * 1000),
      }};
    }}, 'getOutputTimestamp');
  }};
  if (typeof AudioContext !== 'undefined') _patchAudioContext(AudioContext);
  if (typeof webkitAudioContext !== 'undefined') _patchAudioContext(webkitAudioContext);

  if (typeof AnalyserNode !== 'undefined' && AnalyserNode.prototype) {{
    const origGbfd = AnalyserNode.prototype.getByteFrequencyData;
    if (origGbfd) {{
      AnalyserNode.prototype.getByteFrequencyData = _makeNative(function(array) {{
        origGbfd.call(this, array);
        if (array && array.length > 0) {{
          for (let i = 0; i < array.length; i += 7) {{
            const noise = Math.floor(((_audioJitter * (i + 13)) % 1) * 3) - 1;
            array[i] = Math.max(0, Math.min(255, array[i] + noise));
          }}
        }}
      }}, 'getByteFrequencyData');
    }}
    const origGffd = AnalyserNode.prototype.getFloatFrequencyData;
    if (origGffd) {{
      AnalyserNode.prototype.getFloatFrequencyData = _makeNative(function(array) {{
        origGffd.call(this, array);
        if (array && array.length > 0) {{
          for (let i = 0; i < array.length; i += 7) {{
            array[i] += (_audioJitter * 0.01) * (((i * 214013 + 2531011) & 0x7fffffff) / 0x7fffffff - 0.5);
          }}
        }}
      }}, 'getFloatFrequencyData');
    }}
  }}

  // ── Step 3.1: Font Enumeration Spoofing (document.fonts.check & queryLocalFonts) ──
  const _spoofedFonts = {json.dumps(fp.fonts)};
  const _fontSet = new Set(_spoofedFonts.map(f => f.toLowerCase()));

  if (typeof document !== 'undefined' && document.fonts && document.fonts.check) {{
    const origCheck = document.fonts.check.bind(document.fonts);
    document.fonts.check = _makeNative(function(font, text) {{
      if (typeof font === 'string') {{
        const parts = font.split(/[,]+/);
        for (let p of parts) {{
          const clean = p.replace(/['"]/g, '').trim().toLowerCase();
          const family = clean.replace(/^(?:\\d+(?:\\.\\d+)?(?:px|pt|em|rem|%)\\s+|italic\\s+|bold\\s+|small-caps\\s+)+/i, '').trim();
          if (family && _fontSet.has(family)) {{
            return true;
          }}
        }}
      }}
      return origCheck(font, text);
    }}, 'check');
  }}

  if (typeof window !== 'undefined') {{
    window.queryLocalFonts = _makeNative(function() {{
      const records = _spoofedFonts.map(f => ({{
        family: f,
        fullName: f,
        postscriptName: f.replace(/\\s+/g, ''),
        style: 'Regular'
      }}));
      return Promise.resolve(records);
    }}, 'queryLocalFonts');
  }}

  // ── Step 3.2: WebRTC IP Leak Prevention (Enhanced) ──────────────────────────
  if (typeof window !== 'undefined' && window.RTCPeerConnection) {{
    const _origRTC = window.RTCPeerConnection;
    const _isPrivateIP = (str) => {{
      if (!str || typeof str !== 'string') return false;
      return /(?:192\\.168\\.|10\\.|172\\.(?:1[6-9]|2\\d|3[01])\\.|\\.local|fc00:|fe80:)/i.test(str);
    }};

    const _sanitizeSDP = (sdp) => {{
      if (!sdp || typeof sdp !== 'string') return sdp;
      const lines = sdp.split(/\\r?\\n/);
      const filtered = lines.map(line => {{
        if (/^a=candidate:.*\\btyp\\s+host\\b/i.test(line)) return null;
        if (/^a=candidate:/i.test(line) && (_isPrivateIP(line) || /127\\.0\\.0\\.1/.test(line))) return null;
        if (/^o=.*\\bIN\\s+IP4\\s+/i.test(line)) {{
          return line.replace(/\\bIN\\s+IP4\\s+\\S+/, 'IN IP4 0.0.0.0');
        }}
        if (/^c=IN\\s+IP4\\s+/i.test(line)) {{
          return 'c=IN IP4 0.0.0.0';
        }}
        return line;
      }}).filter(l => l !== null && l !== undefined);
      let out = filtered.join('\\r\\n');
      if (!out.endsWith('\\r\\n')) {{
        out += '\\r\\n';
      }}
      return out;
    }};

    function PatchedRTCPeerConnection(...args) {{
      const pc = new _origRTC(...args);

      let customHandler = null;
      Object.defineProperty(pc, 'onicecandidate', {{
        get: () => customHandler,
        set: (fn) => {{
          if (typeof fn === 'function') {{
            customHandler = _makeNative(function(event) {{
              if (event && event.candidate) {{
                const candStr = event.candidate.candidate || '';
                if (/\\btyp\\s+host\\b/i.test(candStr) || _isPrivateIP(candStr)) {{
                  return;
                }}
              }}
              return fn.apply(this, arguments);
            }}, 'onicecandidate');
          }} else {{
            customHandler = fn;
          }}
        }},
        configurable: true,
        enumerable: true
      }});

      const origAddEventListener = pc.addEventListener.bind(pc);
      pc.addEventListener = _makeNative(function(type, listener, options) {{
        if (type === 'icecandidate' && typeof listener === 'function') {{
          const wrapped = function(event) {{
            if (event && event.candidate) {{
              const candStr = event.candidate.candidate || '';
              if (/\\btyp\\s+host\\b/i.test(candStr) || _isPrivateIP(candStr)) {{
                return;
              }}
            }}
            return listener.apply(this, arguments);
          }};
          return origAddEventListener(type, wrapped, options);
        }}
        return origAddEventListener(type, listener, options);
      }}, 'addEventListener');

      const origCreateOffer = pc.createOffer.bind(pc);
      pc.createOffer = _makeNative(function(arg1, arg2, arg3) {{
        if (typeof arg1 === 'function') {{
          const successCb = arg1;
          const errorCb = typeof arg2 === 'function' ? arg2 : () => {{}};
          return origCreateOffer(function(desc) {{
            if (desc && desc.sdp) {{
              try {{
                Object.defineProperty(desc, 'sdp', {{
                  value: _sanitizeSDP(desc.sdp),
                  writable: true,
                  configurable: true,
                  enumerable: true
                }});
              }} catch(e) {{}}
            }}
            return successCb(desc);
          }}, errorCb, arg3);
        }}
        return origCreateOffer(arg1).then(desc => {{
          if (desc && desc.sdp) {{
            try {{
              Object.defineProperty(desc, 'sdp', {{
                value: _sanitizeSDP(desc.sdp),
                writable: true,
                configurable: true,
                enumerable: true
              }});
            }} catch(e) {{}}
          }}
          return desc;
        }});
      }}, 'createOffer');

      const origCreateAnswer = pc.createAnswer.bind(pc);
      pc.createAnswer = _makeNative(function(arg1, arg2, arg3) {{
        if (typeof arg1 === 'function') {{
          const successCb = arg1;
          const errorCb = typeof arg2 === 'function' ? arg2 : () => {{}};
          return origCreateAnswer(function(desc) {{
            if (desc && desc.sdp) {{
              try {{
                Object.defineProperty(desc, 'sdp', {{
                  value: _sanitizeSDP(desc.sdp),
                  writable: true,
                  configurable: true,
                  enumerable: true
                }});
              }} catch(e) {{}}
            }}
            return successCb(desc);
          }}, errorCb, arg3);
        }}
        return origCreateAnswer(arg1).then(desc => {{
          if (desc && desc.sdp) {{
            try {{
              Object.defineProperty(desc, 'sdp', {{
                value: _sanitizeSDP(desc.sdp),
                writable: true,
                configurable: true,
                enumerable: true
              }});
            }} catch(e) {{}}
          }}
          return desc;
        }});
      }}, 'createAnswer');

      const origSetLocalDescription = pc.setLocalDescription.bind(pc);
      pc.setLocalDescription = _makeNative(async function(desc) {{
        if (desc && desc.sdp) {{
          try {{
            Object.defineProperty(desc, 'sdp', {{
              value: _sanitizeSDP(desc.sdp),
              writable: true,
              configurable: true,
              enumerable: true
            }});
          }} catch(e) {{}}
        }}
        return origSetLocalDescription(desc);
      }}, 'setLocalDescription');

      return pc;
    }}

    PatchedRTCPeerConnection.prototype = _origRTC.prototype;
    PatchedRTCPeerConnection.prototype.constructor = PatchedRTCPeerConnection;
    Object.setPrototypeOf(PatchedRTCPeerConnection, _origRTC);

    window.RTCPeerConnection = _makeNative(PatchedRTCPeerConnection, 'RTCPeerConnection');
    if (typeof window.webkitRTCPeerConnection !== 'undefined') {{
      window.webkitRTCPeerConnection = window.RTCPeerConnection;
    }}
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

