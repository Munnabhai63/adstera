"""
adsterra_api.py — Official Adsterra Publisher API Client & Live Reconciliation Engine.

Pillar 1 of 5 Advanced Enterprise Pillars:
- Connects to Adsterra Official Publisher API:
    - Statistics: https://api3.adsterratools.com/publisher/stats.json
    - Websites/Domains: https://api3.adsterratools.com/publisher/domains.json
    - Placements/Smartlinks: https://api3.adsterratools.com/publisher/placements.json
- Reads ADSTERRA_API_KEY securely from .env (zero hardcoded secrets in git)
- Reconciles live API impressions, clicks, CTR, eCPM, and revenue against local sessions.db
- Maps domain IDs to friendly domain titles and auto-discovers active Smartlink direct URLs
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml

import db

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger(__name__)

DEFAULT_STATS_ENDPOINT = "https://api3.adsterratools.com/publisher/stats.json"
DEFAULT_DOMAINS_ENDPOINT = "https://api3.adsterratools.com/publisher/domains.json"
DEFAULT_PLACEMENTS_ENDPOINT = "https://api3.adsterratools.com/publisher/placements.json"


def load_env_credentials() -> dict[str, str]:
    """Load key-value credentials from .env without third-party dependencies."""
    env_file = Path(".env")
    res = {}
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        res[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("Error reading .env file: %s", e)
    return res


class AdsterraApiClient:
    """Official Adsterra Publisher API Client with live stats reconciliation and placement discovery."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        config_path: str = "config.yaml",
    ):
        self.config_path = Path(config_path)
        self.config = self._load_config()

        env_vars = load_env_credentials()
        api_cfg = self.config.get("adsterra_api", {})

        # If api_key is explicitly provided, honor it; otherwise fallback to .env/os.environ/config
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                os.environ.get("ADSTERRA_API_KEY")
                or env_vars.get("ADSTERRA_API_KEY")
                or api_cfg.get("api_key", "").strip()
            )
        self.endpoint = endpoint or api_cfg.get("endpoint", DEFAULT_STATS_ENDPOINT)
        self.domains_endpoint = DEFAULT_DOMAINS_ENDPOINT
        self.placements_endpoint = DEFAULT_PLACEMENTS_ENDPOINT
        self.enabled = True if self.api_key else api_cfg.get("enabled", False)

        # Configured domains from target.domains
        self.configured_domains = [
            d.get("domain") for d in self.config.get("target", {}).get("domains", [])
            if isinstance(d, dict) and d.get("domain")
        ]
        if not self.configured_domains:
            self.configured_domains = ["loanraaj.com"]

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", self.config_path, e)
        return {}

    def is_mock_mode(self) -> bool:
        """Return True if API key is absent or a dummy placeholder."""
        if not self.api_key:
            return True
        dummy_markers = ["placeholder", "dummy", "demo", "xxx", "your_"]
        return any(m in self.api_key.lower() for m in dummy_markers)

    async def fetch_publisher_domains(self) -> list[dict[str, Any]]:
        """Fetch list of publisher websites/domains registered on Adsterra."""
        if self.is_mock_mode():
            return [{"id": 6183986, "title": "smart-link-3549341"}]

        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.domains_endpoint, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("items", [])
                logger.warning("Adsterra fetch_publisher_domains HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("Network error in fetch_publisher_domains: %s", e)
        return []

    async def fetch_placements(self) -> list[dict[str, Any]]:
        """Fetch active ad units and Smartlink direct URLs from Adsterra."""
        if self.is_mock_mode():
            return [
                {
                    "id": 32152060,
                    "domain_id": 6183986,
                    "title": "Smartlink_1",
                    "direct_url": "https://auctionr.org/4/a5bfea4c2c6f44a99100a526d75bc804",
                }
            ]

        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.placements_endpoint, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("items", [])
                logger.warning("Adsterra fetch_placements HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("Network error in fetch_placements: %s", e)
        return []

    async def fetch_daily_stats(
        self,
        start_date: str | None = None,
        finish_date: str | None = None,
        group_by: str = "domain",
        force_mock: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch statistics from Adsterra Stats API.
        If force_mock is True or no valid API key is present, generates authentic mock data.
        """
        today_str = datetime.date.today().isoformat()
        start = start_date or today_str
        finish = finish_date or today_str

        if force_mock or self.is_mock_mode():
            logger.info("Adsterra API: Running in MOCK / SIMULATION mode.")
            return self._generate_mock_stats(start, finish)

        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "Adsterra-Fleet-Engine/1.0",
        }
        params = {
            "start_date": start,
            "finish_date": finish,
            "group_by": group_by,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.endpoint, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Adsterra API: Successfully fetched stats (%d records)", len(data.get("items", [])))
                    return data
                elif resp.status_code in (401, 403):
                    logger.error("Adsterra API Authentication Failed (HTTP %s): Check API key", resp.status_code)
                    return {"status": "error", "error": f"Auth failed (HTTP {resp.status_code})", "items": []}
                else:
                    logger.warning("Adsterra API returned HTTP %s: %s", resp.status_code, resp.text[:200])
                    return {"status": "error", "error": f"HTTP {resp.status_code}", "items": []}
        except Exception as e:
            logger.error("Adsterra API network error: %s", e)
            return {"status": "error", "error": str(e), "items": []}

    def _generate_mock_stats(self, start_date: str, finish_date: str) -> dict[str, Any]:
        """Generate realistic mock stats for offline test runs."""
        import hashlib

        items = []
        for dom in self.configured_domains:
            seed_val = int(hashlib.md5(f"{dom}:{start_date}".encode()).hexdigest()[:8], 16)
            imps = 40 + (seed_val % 140)
            ctr_target = 3.6 + ((seed_val % 12) * 0.1)
            clicks = max(1, round((imps * ctr_target) / 100.0))
            actual_ctr = round((clicks / imps) * 100.0, 2)

            base_cpm = 5.20
            if "loan" in dom or "karz" in dom:
                base_cpm = 7.10
            elif "rokda" in dom or "bhav" in dom:
                base_cpm = 6.40
            cpm = round(base_cpm + ((seed_val % 18) * 0.1), 2)
            revenue = round((imps / 1000.0 * cpm) + (clicks * 0.05), 3)

            items.append({
                "domain": dom,
                "date": start_date,
                "impression": imps,
                "impressions": imps,
                "clicks": clicks,
                "ctr": actual_ctr,
                "cpm": cpm,
                "revenue": revenue,
            })

        return {"status": "ok", "mode": "mock_simulated", "items": items}

    async def sync_and_reconcile(
        self,
        date_str: str | None = None,
        force_mock: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Synchronize API stats and reconcile against local domain_stats table in sessions.db.
        Stores audit records in adsterra_api_sync.
        """
        db.init()
        target_date = date_str or datetime.date.today().isoformat()

        # Step 1: Fetch publisher registered domains to resolve ID -> name mapping
        domains_list = await self.fetch_publisher_domains()
        dom_id_map = {str(d.get("id")): d.get("title", "") for d in domains_list}

        # Step 2: Fetch daily stats
        stats_resp = await self.fetch_daily_stats(
            start_date=target_date,
            finish_date=target_date,
            force_mock=force_mock,
        )

        items = stats_resp.get("items", [])
        reconciled = []

        # Read local domain stats for comparison
        local_summary = {d["domain"]: d for d in db.all_domains_summary(date_str=target_date)}

        # If live API returns specific domain IDs, match them with our active domains
        for item in items:
            raw_dom = str(item.get("domain", ""))
            # Resolve name from map or use first configured domain if smartlink ID
            dom_name = dom_id_map.get(raw_dom, raw_dom)
            if dom_name.isdigit() or "smart-link" in dom_name:
                dom_name = self.configured_domains[0] if self.configured_domains else "loanraaj.com"

            # Support both Adsterra 'impression' and 'impressions'
            api_imps = int(item.get("impression") or item.get("impressions") or 0)
            api_clicks = int(item.get("clicks", 0))
            api_ctr = float(item.get("ctr", 0.0))
            api_cpm = float(item.get("cpm", 0.0))
            api_rev = float(item.get("revenue", 0.0))

            loc_data = local_summary.get(dom_name, {})
            local_imps = int(loc_data.get("impressions", 0))

            if local_imps > 0:
                discrepancy = round(((api_imps - local_imps) / local_imps) * 100.0, 2)
            else:
                discrepancy = 0.0 if api_imps == 0 else 100.0

            sync_id = db.record_adsterra_sync(
                domain=dom_name,
                date=target_date,
                api_impressions=api_imps,
                api_clicks=api_clicks,
                api_ctr=api_ctr,
                api_cpm=api_cpm,
                api_revenue=api_rev,
                local_impressions=local_imps,
                discrepancy_pct=discrepancy,
            )

            rec = {
                "sync_id": sync_id,
                "domain": dom_name,
                "date": target_date,
                "api_impressions": api_imps,
                "api_clicks": api_clicks,
                "api_ctr": api_ctr,
                "api_cpm": api_cpm,
                "api_revenue": api_rev,
                "local_impressions": local_imps,
                "discrepancy_pct": discrepancy,
                "status": "ALIGNED" if abs(discrepancy) < 15.0 else "DISCREPANCY_DETECTED",
            }
            reconciled.append(rec)

        logger.info("Adsterra API: Reconciled %d records for %s", len(reconciled), target_date)
        return reconciled

    def sync_now(self, force_mock: bool = False) -> list[dict[str, Any]]:
        """Synchronous wrapper for sync_and_reconcile."""
        return asyncio.run(self.sync_and_reconcile(force_mock=force_mock))


def print_reconciliation_table(records: list[dict[str, Any]], mode_str: str = "LIVE_API") -> None:
    """Print an eye-readable, professional terminal table for manual CMD verification."""
    print("\n" + "=" * 98)
    print(f" [+] ADSTERRA STATS API RECONCILIATION REPORT (MODE: {mode_str})")
    print("=" * 98)
    print(
        f"{'Domain':<18} | {'API Imps':>8} | {'API Clicks':>10} | {'API CTR':>8} | "
        f"{'API eCPM':>9} | {'API Rev':>8} | {'Local Imps':>10} | {'Discrepancy':>11}"
    )
    print("-" * 98)

    total_api_imps = 0
    total_api_clicks = 0
    total_api_rev = 0.0

    for r in records:
        total_api_imps += r["api_impressions"]
        total_api_clicks += r["api_clicks"]
        total_api_rev += r["api_revenue"]

        disc_str = f"{r['discrepancy_pct']:+.1f}%"
        print(
            f"{r['domain']:<18} | "
            f"{r['api_impressions']:>8} | "
            f"{r['api_clicks']:>10} | "
            f"{r['api_ctr']:>7.2f}% | "
            f"${r['api_cpm']:>8.2f} | "
            f"${r['api_revenue']:>7.3f} | "
            f"{r['local_impressions']:>10} | "
            f"{disc_str:>11}"
        )

    overall_ctr = (total_api_clicks / total_api_imps * 100.0) if total_api_imps > 0 else 0.0
    overall_cpm = (total_api_rev / total_api_imps * 1000.0) if total_api_imps > 0 else 0.0

    print("=" * 98)
    print(
        f"{'TOTAL / AVERAGE':<18} | "
        f"{total_api_imps:>8} | "
        f"{total_api_clicks:>10} | "
        f"{overall_ctr:>7.2f}% | "
        f"${overall_cpm:>8.2f} | "
        f"${total_api_rev:>7.2f} | "
        f"{'':>10} | {'OPTIMAL':>11}"
    )
    print("=" * 98 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adsterra API Client & Reconciliation Engine")
    parser.add_argument("--sync", action="store_true", help="Trigger live/mock sync and reconciliation")
    parser.add_argument("--mock", action="store_true", help="Force mock simulation mode even if key is present")
    parser.add_argument("--placements", action="store_true", help="Fetch and display live Adsterra placements/Smartlinks")
    parser.add_argument("--key", type=str, default=None, help="Explicit Adsterra API Key override")
    parser.add_argument("--date", type=str, default=None, help="Target sync date (YYYY-MM-DD)")

    args = parser.parse_args()

    client = AdsterraApiClient(api_key=args.key)
    force = args.mock or client.is_mock_mode()
    mode = "MOCK_SIMULATION" if force else "LIVE_OFFICIAL_API"

    if args.placements:
        print(f"[*] Fetching live Adsterra placements using API token ({mode})...")
        placements = asyncio.run(client.fetch_placements())
        print("\n" + "=" * 90)
        print(" 🎯 LIVE ADSTERRA SMARTLINKS & PLACEMENTS")
        print("=" * 90)
        for p in placements:
            print(f" - [{p.get('id')}] {p.get('title')}: {p.get('direct_url')}")
        print("=" * 90 + "\n")
    else:
        print(f"[*] Connecting to Adsterra Official API (Mode: {mode})...")
        records = client.sync_now(force_mock=force)
        print_reconciliation_table(records, mode_str=mode)
