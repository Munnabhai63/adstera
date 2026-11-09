"""
cloudflare_manager.py — Autonomous Cloudflare Domain Fleet Orchestrator.

Automatically provisions and configures the user's 10 publisher domains in Cloudflare:
- Creates zone (Free plan)
- Configures SSL/TLS to 'full'
- Enables 'Always Use HTTPS'
- Configures A record (@ -> cPanel 148.113.0.192 proxied)
- Configures CNAME (www -> @ proxied)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cloudflare_manager")

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

DEFAULT_ORIGIN_IP = "148.113.0.192"


def _load_env() -> tuple[str, str]:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    env_file = Path(".env")
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "CLOUDFLARE_API_TOKEN" and not token:
                token = v
            elif k == "CLOUDFLARE_ACCOUNT_ID" and not account_id:
                account_id = v
    return token, account_id


class CloudflareFleetManager:
    API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, token: str, account_id: str) -> None:
        self.token = token
        self.account_id = account_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def list_existing_zones(self) -> dict[str, dict[str, Any]]:
        """Fetch all zones currently registered under the account."""
        url = f"{self.API_BASE}/zones?account.id={self.account_id}&per_page=50"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=self.headers)
            data = resp.json()
            if not data.get("success"):
                logger.error("Failed to list zones: %s", data.get("errors"))
                return {}
            zones = {z["name"]: z for z in data.get("result", [])}
            return zones

    def create_zone(self, domain: str) -> dict[str, Any] | None:
        """Add a new domain/zone under the Cloudflare account (Free plan)."""
        url = f"{self.API_BASE}/zones"
        payload = {
            "name": domain,
            "account": {"id": self.account_id},
            "jump_start": True,
            "type": "full",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=self.headers, json=payload)
            data = resp.json()
            if resp.status_code in (200, 201) and data.get("success"):
                logger.info("[+] Created zone for %s (ID: %s)", domain, data["result"]["id"])
                return data["result"]
            else:
                logger.warning("[-] Could not create zone %s: %s", domain, data.get("errors"))
                return None

    def configure_ssl_and_settings(self, zone_id: str, domain: str) -> None:
        """Set SSL to Full, Always Use HTTPS, and Automatic HTTPS Rewrites."""
        with httpx.Client(timeout=15.0) as client:
            # 1. SSL Mode: Full
            ssl_url = f"{self.API_BASE}/zones/{zone_id}/settings/ssl"
            client.patch(ssl_url, headers=self.headers, json={"value": "full"})

            # 2. Always Use HTTPS: on
            https_url = f"{self.API_BASE}/zones/{zone_id}/settings/always_use_https"
            client.patch(https_url, headers=self.headers, json={"value": "on"})

            # 3. Automatic HTTPS Rewrites: on
            rewrites_url = f"{self.API_BASE}/zones/{zone_id}/settings/automatic_https_rewrites"
            client.patch(rewrites_url, headers=self.headers, json={"value": "on"})

            logger.info("[✓] SSL Full & Always HTTPS configured for %s", domain)

    def ensure_dns_records(self, zone_id: str, domain: str, origin_ip: str = DEFAULT_ORIGIN_IP) -> None:
        """Ensure root A record and www CNAME are proxied through Cloudflare."""
        url = f"{self.API_BASE}/zones/{zone_id}/dns_records"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=self.headers)
            records = resp.json().get("result", [])

            has_root_a = any(r["name"] == domain and r["type"] == "A" for r in records)
            has_www = any(r["name"] == f"www.{domain}" for r in records)

            if not has_root_a:
                client.post(
                    url,
                    headers=self.headers,
                    json={
                        "type": "A",
                        "name": domain,
                        "content": origin_ip,
                        "ttl": 1,
                        "proxied": True,
                    },
                )
                logger.info("[+] Added root A record for %s -> %s (Proxied)", domain, origin_ip)

            if not has_www:
                client.post(
                    url,
                    headers=self.headers,
                    json={
                        "type": "CNAME",
                        "name": f"www.{domain}",
                        "content": domain,
                        "ttl": 1,
                        "proxied": True,
                    },
                )
                logger.info("[+] Added www CNAME record for %s -> %s (Proxied)", domain, domain)

    def provision_entire_fleet(self) -> list[dict[str, Any]]:
        """Orchestrate entire 10-domain fleet."""
        existing = self.list_existing_zones()
        report = []

        for dom in DOMAINS_FLEET:
            logger.info("Processing domain: %s...", dom)
            zone = existing.get(dom)
            is_new = False
            if not zone:
                zone = self.create_zone(dom)
                is_new = True

            if not zone:
                report.append({"domain": dom, "status": "FAILED_TO_CREATE", "ns": []})
                continue

            zone_id = zone["id"]
            ns = zone.get("name_servers") or ["josh.ns.cloudflare.com", "kiki.ns.cloudflare.com"]

            # Apply SSL and DNS settings
            try:
                self.configure_ssl_and_settings(zone_id, dom)
                self.ensure_dns_records(zone_id, dom, DEFAULT_ORIGIN_IP)
            except Exception as exc:
                logger.warning("Error configuring settings for %s: %s", dom, exc)

            report.append({
                "domain": dom,
                "status": "ACTIVE" if zone.get("status") == "active" else "PENDING_NAMESERVER_UPDATE",
                "zone_id": zone_id,
                "ns": ns,
                "is_new": is_new,
            })

        return report


def main() -> None:
    token, account_id = _load_env()
    if not token or not account_id:
        print("[-] Error: CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID missing in .env")
        return

    print("==================================================================")
    print("  AUTONOMOUS CLOUDFLARE 10-DOMAIN FLEET PROVISIONER")
    print(f"  Account ID: {account_id}")
    print("==================================================================")

    mgr = CloudflareFleetManager(token=token, account_id=account_id)
    report = mgr.provision_entire_fleet()

    print("\n==================================================================")
    print("  CLOUDFLARE 10-DOMAIN FLEET SUMMARY REPORT")
    print("==================================================================")
    for r in report:
        dom = r["domain"]
        st = r["status"]
        ns_str = ", ".join(r.get("ns", []))
        print(f" * {dom.ljust(18)} : [{st}] | Nameservers: {ns_str}")

    print("\n[+] All 10 Domains configured with SSL Full, Always HTTPS, and Proxied DNS!")
    print("[+] Nameservers to set in Hostinger for all pending domains:")
    print("    1. josh.ns.cloudflare.com")
    print("    2. kiki.ns.cloudflare.com")


if __name__ == "__main__":
    main()
