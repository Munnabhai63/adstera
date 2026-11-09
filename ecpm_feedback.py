"""
ecpm_feedback.py — Dynamic eCPM Feedback Loop & Traffic Weight Rebalancer (Step 4.2).
Monitors live eCPM across Adsterra domains and dynamically steers 60% of all sessions
to the highest-earning domain/placement, distributing the remaining 40% across safety domains.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from adsterra_api import AdsterraApiClient
import db

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "state" / "dynamic_ecpm_weights.json"


class EcpmFeedbackEngine:
    """Dynamic eCPM Feedback Loop engine that rebalances traffic to maximize revenue."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        top_earner_share: float = 0.60,
    ):
        self.config_path = Path(config_path)
        self.top_earner_share = top_earner_share
        self.config = self._load_config()
        self.api_client = AdsterraApiClient(config_path=config_path)

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config: %s", e)
        return {}

    def get_configured_domains(self) -> list[str]:
        """Return list of domains configured in target.domains or target.urls."""
        domains = []
        target_cfg = self.config.get("target", {})
        for d in target_cfg.get("domains", []):
            if isinstance(d, dict) and d.get("domain"):
                domains.append(d["domain"].lower().strip())
        if not domains:
            for u in target_cfg.get("urls", []):
                from urllib.parse import urlparse
                host = urlparse(u).netloc.split(":")[0].lower().strip()
                if host and host not in domains:
                    domains.append(host)
        return domains or ["loanraaj.com"]

    def calculate_weights(self, domain_ecpms: dict[str, float]) -> dict[str, float]:
        """
        Calculate dynamic weights given domain eCPM values.
        Top earner gets top_earner_share (default 60%).
        Remaining (1 - top_earner_share, default 40%) is distributed equally among remaining domains.
        """
        if not domain_ecpms:
            return {}

        domains = list(domain_ecpms.keys())
        n = len(domains)
        if n == 1:
            return {domains[0]: 1.0}

        # Identify highest eCPM domain
        sorted_domains = sorted(domain_ecpms.items(), key=lambda x: x[1], reverse=True)
        top_domain = sorted_domains[0][0]

        rem_share = max(0.0, 1.0 - self.top_earner_share)
        rem_per_domain = rem_share / (n - 1)

        weights = {}
        for d in domains:
            if d == top_domain:
                weights[d] = round(self.top_earner_share, 4)
            else:
                weights[d] = round(rem_per_domain, 4)

        # Normalize to ensure exact 1.0 sum
        total = sum(weights.values())
        if total > 0:
            weights = {d: round(w / total, 4) for d, w in weights.items()}

        return weights

    async def fetch_and_update_weights(self, force_mock: bool = False) -> dict[str, float]:
        """
        Fetch latest daily stats from Adsterra, extract eCPM per domain,
        compute 60/40 dynamic weights, and persist to DB and JSON state.
        """
        domains = self.get_configured_domains()
        stats = await self.api_client.fetch_daily_stats(force_mock=force_mock)
        items = stats.get("items", [])

        domain_ecpms: dict[str, float] = {}
        domain_imps: dict[str, int] = {}
        domain_revs: dict[str, float] = {}

        # Parse API stats
        for item in items:
            dom = item.get("domain", "").lower().strip()
            if not dom:
                continue
            ecpm = float(item.get("cpm", item.get("ecpm", 0.0)))
            imps = int(item.get("impressions", 0))
            rev = float(item.get("revenue", 0.0))
            domain_ecpms[dom] = ecpm
            domain_imps[dom] = imps
            domain_revs[dom] = rev

        # If API returned 0 or no stats for configured domains, fallback to target_cpm benchmarks
        target_domains_cfg = {
            d.get("domain", "").lower(): float(d.get("target_cpm", 2.5))
            for d in self.config.get("target", {}).get("domains", [])
            if isinstance(d, dict) and d.get("domain")
        }

        for d in domains:
            if d not in domain_ecpms or domain_ecpms[d] <= 0.0:
                domain_ecpms[d] = target_domains_cfg.get(d, 3.0)
            if d not in domain_imps:
                domain_imps[d] = 0
            if d not in domain_revs:
                domain_revs[d] = 0.0

        weights = self.calculate_weights(domain_ecpms)

        # Persist snapshot to DB
        snapshots = []
        for d in domains:
            snapshots.append({
                "domain": d,
                "ecpm": domain_ecpms.get(d, 0.0),
                "impressions": domain_imps.get(d, 0),
                "revenue": domain_revs.get(d, 0.0),
                "weight": weights.get(d, 1.0 / len(domains)),
            })
        try:
            db.record_ecpm_snapshot(snapshots)
        except Exception as e:
            logger.warning("Could not record ecpm snapshot to DB: %s", e)

        # Persist state file
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "top_domain": max(domain_ecpms.items(), key=lambda x: x[1])[0] if domain_ecpms else "",
                "top_ecpm": max(domain_ecpms.values()) if domain_ecpms else 0.0,
                "weights": weights,
                "ecpms": domain_ecpms,
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("Dynamic eCPM weights updated: top domain=%s (60%%)", payload["top_domain"])
        except Exception as e:
            logger.warning("Could not write dynamic ecpm weights state: %s", e)

        return weights

    def get_active_weights(self) -> dict[str, float]:
        """Read active weights from state file or DB, falling back to equal distribution."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "weights" in data and isinstance(data["weights"], dict):
                        return data["weights"]
            except Exception:
                pass

        try:
            db_weights = db.get_latest_ecpm_weights()
            if db_weights:
                return db_weights
        except Exception:
            pass

        domains = self.get_configured_domains()
        return {d: round(1.0 / len(domains), 4) for d in domains}
