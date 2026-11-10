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
            "https://asiafilm.org/4/5a10ac2f61030bfc4a933d19243bd9d5",
            "https://asiafilm.org/4/c8ee7e929c7c0f77f48b9eb7f198735b",
            "https://asiafilm.org/4/e534aa2882340b6d23a31b264a473449",
            "https://asiafilm.org/4/4cef2f60b337a83398fd5d4eccb2b035",
            "https://asiafilm.org/4/17ddb2ab1cf803847dffc03339639ae2",
            "https://asiafilm.org/4/36bc7f04daecf4b91801beda6ea285a5",
            "https://asiafilm.org/4/e5d95a7029b0b931e6310b08c33befa3",
            "https://asiafilm.org/4/dd81186b26c491b694a530a285873443",
            "https://asiafilm.org/4/080aacbe5bb90ca178d15ff864c503f7",
            "https://asiafilm.org/4/c32806b04cb876619cbcff1c8f210313",
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
