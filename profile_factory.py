"""
profile_factory.py — Unlimited Hardware Profile Generator.
Generates mathematically consistent, authentic MAHI Browser hardware profiles on-the-fly
without bloating the desktop app database. Supports thousands of concurrent profiles.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from typing import Any, Dict, List, Optional
from accounts_manager import Account
from pool import Proxy

logger = logging.getLogger(__name__)

# Real-world desktop screen distribution
_DESKTOP_VIEWPORTS = [
    {"width": 1920, "height": 1080, "weight": 62},
    {"width": 1536, "height": 864,  "weight": 14},
    {"width": 1440, "height": 900,  "weight": 9},
    {"width": 1366, "height": 768,  "weight": 8},
    {"width": 2560, "height": 1440, "weight": 7},
]

# Real GPU Renderers for WebGL
_WEBGL_RENDERERS = [
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "weight": 45,
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "weight": 35,
    },
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "weight": 20,
    },
]


class ProfileFactory:
    """Generates synthetic, fully coherent MAHI Browser hardware profiles on demand."""

    @classmethod
    def generate_profile(
        cls,
        account: Optional[Account] = None,
        proxy: Optional[Proxy] = None,
        seed: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a single complete profile definition with display, hardware,
        audio, canvas, and locale configurations.
        """
        raw_seed = seed or (account.email if account else (proxy.proxy_id if proxy else str(uuid.uuid4())))
        seed_hash = hashlib.sha256(raw_seed.encode()).hexdigest()
        rng = random.Random(int(seed_hash[:8], 16))

        # Viewport selection
        vp_weights = [v["weight"] for v in _DESKTOP_VIEWPORTS]
        vp = rng.choices(_DESKTOP_VIEWPORTS, weights=vp_weights, k=1)[0]

        # WebGL renderer
        gpu_weights = [g["weight"] for g in _WEBGL_RENDERERS]
        gpu = rng.choices(_WEBGL_RENDERERS, weights=gpu_weights, k=1)[0]

        # Hardware metrics
        cores = rng.choice([4, 8, 12, 16])
        memory = rng.choice([8, 16, 32])
        taskbar_offset = rng.randint(60, 110)

        # Geo mapping
        lang = proxy.geo.locale if proxy and proxy.geo else "en-US"
        tz = proxy.geo.timezone if proxy and proxy.geo else "America/New_York"
        country = proxy.geo.country if proxy and proxy.geo else "US"

        profile_id = f"gen_{seed_hash[:12]}"
        name = f"Persona {account.name}" if account else f"Profile {profile_id}"

        profile_payload = {
            "id": profile_id,
            "name": name,
            "account_id": account.account_id if account else None,
            "email": account.email if account else None,
            "status": "active",
            "seed": seed_hash,
            "settings": {
                "browser": {
                    "engine": "chrome",
                    "version": "138.0.7204.183",
                    "userAgent": (
                        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        f"(KHTML, like Gecko) Chrome/138.0.7204.183 Safari/537.36"
                    ),
                    "enableExtensions": True,
                },
                "display": {
                    "screenWidth": vp["width"],
                    "screenHeight": vp["height"],
                    "availWidth": vp["width"],
                    "availHeight": vp["height"] - taskbar_offset,
                    "colorDepth": 24,
                    "deviceScaleFactor": 1,
                },
                "hardware": {
                    "concurrency": cores,
                    "memory": memory,
                    "webgl_vendor": gpu["vendor"],
                    "webgl_renderer": gpu["renderer"],
                    "canvas_noise_seed": int(seed_hash[8:16], 16) % 1000000000,
                    "audio_jitter_seed": (int(seed_hash[16:24], 16) % 10000) / 1000000.0,
                },
                "locale": {
                    "language": lang,
                    "timezone": tz,
                    "country": country,
                    "languagesList": [lang, "en"],
                },
                "network": {
                    "directConnection": False if proxy else True,
                    "webrtc": "disable_non_proxied_udp",
                },
                "permissions": {
                    "notifications": "prompt",
                    "geolocation": "prompt",
                    "camera": "prompt",
                    "microphone": "prompt",
                },
            },
        }

        return profile_payload

    @classmethod
    def generate_batch(cls, count: int, prefix: str = "batch_user") -> List[Dict[str, Any]]:
        """Generate a batch of N unique profiles instantly."""
        profiles = []
        for i in range(count):
            s = f"{prefix}_{i}_{uuid.uuid4().hex[:6]}"
            p = cls.generate_profile(seed=s)
            profiles.append(p)
        return profiles
