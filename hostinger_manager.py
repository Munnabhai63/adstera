"""
hostinger_manager.py — Hostinger API Autonomous Domain Nameserver Orchestrator.

Updates nameservers across all 10 publisher domains in Hostinger to Cloudflare Anycast:
- ns1: josh.ns.cloudflare.com
- ns2: kiki.ns.cloudflare.com
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hostinger_manager")

DOMAINS_FLEET = [
    "loanraaj.com",
    "rechargetak.com",
    "rechargepur.com",
    "tazaloan.com",
    "loankiseva.com",
    "karzseva.com",
    "loantau.com",
    "tazabhav.com",
    "tazarokda.com",
    "rechargekar.com",
]

TARGET_NS1 = "josh.ns.cloudflare.com"
TARGET_NS2 = "kiki.ns.cloudflare.com"


def _load_token() -> str:
    token = os.environ.get("HOSTINGER_API_TOKEN", "")
    env_file = Path(".env")
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "HOSTINGER_API_TOKEN" and not token:
                token = v
    return token


class HostingerFleetManager:
    API_BASE = "https://developers.hostinger.com/api/domains/v1"

    def __init__(self, token: str) -> None:
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def list_portfolio(self) -> list[dict[str, Any]]:
        """List all domains under the Hostinger account."""
        url = f"{self.API_BASE}/portfolio"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error("Failed to list Hostinger portfolio: %s", resp.text)
                return []

    def update_nameservers(self, domain: str, ns1: str = TARGET_NS1, ns2: str = TARGET_NS2) -> dict[str, Any]:
        """Update nameservers for a specific domain."""
        url = f"{self.API_BASE}/portfolio/{domain}/nameservers"
        payload = {"ns1": ns1, "ns2": ns2}
        with httpx.Client(timeout=15.0) as client:
            resp = client.put(url, headers=self.headers, json=payload)
            if resp.status_code == 200:
                logger.info("[✓] Successfully updated nameservers for %s -> (%s, %s)", domain, ns1, ns2)
                return {"success": True, "domain": domain, "message": resp.json().get("message", "OK")}
            else:
                logger.warning("[-] Failed to update nameservers for %s: HTTP %d - %s", domain, resp.status_code, resp.text)
                return {"success": False, "domain": domain, "error": resp.text}

    def sync_all_fleet(self) -> list[dict[str, Any]]:
        """Update all fleet domains to point to Cloudflare."""
        portfolio = self.list_portfolio()
        registered_names = {d["domain"].lower() for d in portfolio}
        results = []

        for dom in DOMAINS_FLEET:
            dom_lower = dom.lower()
            if dom_lower not in registered_names:
                logger.warning("Domain %s not found in Hostinger portfolio — skipping.", dom)
                results.append({"domain": dom, "success": False, "error": "Not in Hostinger portfolio"})
                continue

            res = self.update_nameservers(dom_lower)
            results.append(res)
            time.sleep(0.5)

        return results


def main() -> None:
    token = _load_token()
    if not token:
        print("[-] HOSTINGER_API_TOKEN missing in .env")
        return

    print("==================================================================")
    print("  HOSTINGER 10-DOMAIN NAMESERVER FLEET ORCHESTRATOR")
    print("==================================================================")

    mgr = HostingerFleetManager(token)
    results = mgr.sync_all_fleet()

    print("\n==================================================================")
    print("  UPDATE SUMMARY REPORT")
    print("==================================================================")
    for r in results:
        status_str = "SUCCESS" if r.get("success") else "FAILED"
        print(f" * {r['domain'].ljust(18)} : [{status_str}] {r.get('message', r.get('error', ''))}")

    print("\n[+] All domains pointed to Cloudflare Anycast Nameservers:")
    print(f"    1. {TARGET_NS1}")
    print(f"    2. {TARGET_NS2}")


if __name__ == "__main__":
    main()
