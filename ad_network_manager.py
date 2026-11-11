"""
ad_network_manager.py — Multi-Ad-Network Rotation Engine (Step 4.3).
Eliminates single-network dependency and mitigates account ban risk by probabilistically
rotating sessions across 3 top direct-link & popunder monetization platforms:
  1. Adsterra (default 50% share)
  2. PropellerAds / Monetag (default 30% share)
  3. HilltopAds (default 20% share)
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_NETWORKS = {
    "adsterra": {
        "enabled": True,
        "weight": 0.50,
        "smartlinks": [
            "https://araplhn.org/4/17dc693c036f3b211f48887d232add4b",
            "https://araplhn.org/4/36def2a0119696fb23e3fe034ccfcbc6",
            "https://araplhn.org/4/efed43a0653e93bd1dc62b74d42e4c6a",
            "https://araplhn.org/4/b85c5d24beb88d58bfb4e161e1f74dd9",
            "https://araplhn.org/4/2caa4b8918499ce7fd21fc1b92ec94aa",
            "https://araplhn.org/4/8b6f18f361f42dc7c2c708b4ce5f6f28",
            "https://araplhn.org/4/5758e39593ed52767a2328758c2683da",
            "https://araplhn.org/4/ca5b06c43def4844f857da9379d3229d",
            "https://araplhn.org/4/683357397a7ae6ec26a028b4100a876c",
            "https://araplhn.org/4/7a123d148c127cf4f54df5374d59a985",
        ],
    },
    "propellerads": {
        "enabled": True,
        "weight": 0.30,
        "smartlinks": [
            "https://propeller-direct.com/smartlink/3549341",
            "https://monetag-direct.net/smartlink/489102",
        ],
    },
    "hilltopads": {
        "enabled": True,
        "weight": 0.20,
        "smartlinks": [
            "https://hilltop-direct.com/smartlink/778899",
            "https://hilltop-direct.com/smartlink/889900",
        ],
    },
}


class AdNetworkManager:
    """Manages multi-network rotation, smartlink selection, and traffic share enforcement."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config: %s", e)
        return {}

    def get_networks(self) -> dict[str, dict[str, Any]]:
        """Return configured ad networks with fallback to DEFAULT_NETWORKS."""
        net_cfg = self.config.get("ad_networks", {})
        if not net_cfg or not isinstance(net_cfg, dict):
            return dict(DEFAULT_NETWORKS)

        merged = {}
        for name, defaults in DEFAULT_NETWORKS.items():
            override = net_cfg.get(name, {})
            merged[name] = {
                "enabled": override.get("enabled", defaults["enabled"]),
                "weight": float(override.get("weight", defaults["weight"])),
                "smartlinks": override.get("smartlinks") or defaults["smartlinks"],
            }
        for name, data in net_cfg.items():
            if name not in merged and isinstance(data, dict):
                merged[name] = {
                    "enabled": data.get("enabled", True),
                    "weight": float(data.get("weight", 0.10)),
                    "smartlinks": data.get("smartlinks", []),
                }
        return merged

    def select_network(self, rng: random.Random) -> str:
        """Probabilistically select an active ad network according to configured weights."""
        nets = self.get_networks()
        active = [name for name, data in nets.items() if data.get("enabled", True)]
        if not active:
            return "adsterra"

        weights = [nets[name].get("weight", 1.0) for name in active]
        total = sum(weights)
        if total <= 0:
            return rng.choice(active)

        return rng.choices(active, weights=weights, k=1)[0]

    def select_smartlink(self, network_name: str, rng: random.Random) -> Optional[str]:
        """Return a random active smartlink URL for the given network."""
        nets = self.get_networks()
        net = nets.get(network_name)
        if not net or not net.get("enabled", True):
            net = nets.get("adsterra", DEFAULT_NETWORKS["adsterra"])

        links = net.get("smartlinks", [])
        clean = [l.strip() for l in links if isinstance(l, str) and l.strip()]
        if clean:
            return rng.choice(clean)
        return None

    def get_rotation_plan(self) -> dict[str, float]:
        """Return active percentage distribution across enabled networks."""
        nets = self.get_networks()
        active = {name: data.get("weight", 0.0) for name, data in nets.items() if data.get("enabled", True)}
        total = sum(active.values())
        if total > 0:
            return {name: round(w / total, 3) for name, w in active.items()}
        return {name: round(1.0 / len(active), 3) for name in active}

    def get_domain_smartlink(self, domain_or_key: str) -> str:
        """Return the dedicated, high-eCPM Adsterra direct link for the given domain."""
        try:
            from adsterra_links import get_adsterra_config
            return get_adsterra_config(domain_or_key)["url"]
        except Exception:
            return "https://asiafilm.org/4/5a10ac2f61030bfc4a933d19243bd9d5"
