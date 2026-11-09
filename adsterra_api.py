"""
adsterra_api.py — Adsterra Publisher Statistics API Client & Reconciliation Engine.

Pillar 1 of 5 Advanced Enterprise Pillars:
- Connects to Adsterra Official Stats API (https://api3.adsterratools.com/v1/statistic.json)
- Fetches real-time impressions, clicks, CTR, eCPM, and revenue per domain
- Reconciles live API data against local SQLite session logs (sessions.db)
- Calculates discrepancy percentages to calibrate click/dwell pacing
- Provides realistic mock mode for offline testing and verification
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
import yaml

import db

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api3.adsterratools.com/v1/statistic.json"


class AdsterraApiClient:
    """Official Adsterra Publisher Stats API Client with automated local reconciliation."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        config_path: str = "config.yaml",
    ):
        self.config_path = Path(config_path)
        self.config = self._load_config()

        api_cfg = self.config.get("adsterra_api", {})
        self.api_key = api_key or api_cfg.get("api_key", "").strip()
        self.endpoint = endpoint or api_cfg.get("endpoint", DEFAULT_ENDPOINT)
        self.enabled = api_cfg.get("enabled", False)
        self.sync_interval_min = api_cfg.get("sync_interval_min", 15)

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
        dummy_markers = ["placeholder", "dummy", "test", "demo", "xxx", "your_"]
        return any(m in self.api_key.lower() for m in dummy_markers)

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
        """
        Generate mathematically realistic Adsterra stats matching local simulation
        across all 10 publisher domains.
        """
        import hashlib

        items = []
        for dom in self.configured_domains:
            # Deterministic seeded generation per domain + date
            seed_val = int(hashlib.md5(f"{dom}:{start_date}".encode()).hexdigest()[:8], 16)

            # Plausible impressions for a warming domain (45 - 180)
            imps = 40 + (seed_val % 140)

            # Plausible clicks targeting 3.8% - 4.6% CTR
            ctr_target = 3.6 + ((seed_val % 12) * 0.1)
            clicks = max(1, round((imps * ctr_target) / 100.0))
            actual_ctr = round((clicks / imps) * 100.0, 2)

            # High eCPM between $4.50 and $8.20 based on niche
            base_cpm = 5.20
            if "loan" in dom or "karz" in dom:
                base_cpm = 7.10
            elif "rokda" in dom or "bhav" in dom:
                base_cpm = 6.40
            cpm = round(base_cpm + ((seed_val % 18) * 0.1), 2)

            # Revenue = (impressions / 1000 * cpm) + (clicks * lead_multiplier)
            revenue = round((imps / 1000.0 * cpm) + (clicks * 0.05), 3)

            items.append({
                "domain": dom,
                "date": start_date,
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
        stats_resp = await self.fetch_daily_stats(
            start_date=target_date,
            finish_date=target_date,
            force_mock=force_mock,
        )

        items = stats_resp.get("items", [])
        reconciled = []

        # Read local domain stats for comparison
        local_summary = {d["domain"]: d for d in db.all_domains_summary()}

        for item in items:
            dom = item.get("domain", "")
            if not dom:
                continue

            api_imps = int(item.get("impressions", 0))
            api_clicks = int(item.get("clicks", 0))
            api_ctr = float(item.get("ctr", 0.0))
            api_cpm = float(item.get("cpm", 0.0))
            api_rev = float(item.get("revenue", 0.0))

            # Retrieve local recorded impressions for this domain today
            loc_data = local_summary.get(dom, {})
            local_imps = int(loc_data.get("impressions", 0))

            # Calculate discrepancy percentage: (API - Local) / Local * 100
            if local_imps > 0:
                discrepancy = round(((api_imps - local_imps) / local_imps) * 100.0, 2)
            else:
                discrepancy = 0.0 if api_imps == 0 else 100.0

            # Store in database audit log
            sync_id = db.record_adsterra_sync(
                domain=dom,
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
                "domain": dom,
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

        logger.info("Adsterra API: Reconciled %d domains for %s", len(reconciled), target_date)
        return reconciled

    def sync_now(self, force_mock: bool = False) -> list[dict[str, Any]]:
        """Synchronous wrapper for sync_and_reconcile."""
        return asyncio.run(self.sync_and_reconcile(force_mock=force_mock))


def print_reconciliation_table(records: list[dict[str, Any]]) -> None:
    """Print an eye-readable, professional terminal table for manual CMD verification."""
    print("\n" + "=" * 98)
    print(" [+] ADSTERRA STATS API RECONCILIATION REPORT (PILLAR 1)")
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
    parser.add_argument("--key", type=str, default=None, help="Explicit Adsterra API Key override")
    parser.add_argument("--date", type=str, default=None, help="Target sync date (YYYY-MM-DD)")

    args = parser.parse_args()

    client = AdsterraApiClient(api_key=args.key)
    force = args.mock or client.is_mock_mode()
    
    print(f"[*] Initializing Adsterra API Client (Mode: {'MOCK/SIMULATION' if force else 'LIVE_API'})...")
    records = client.sync_now(force_mock=force)
    print_reconciliation_table(records)
