"""
setup_tunnel.py — Sets up and points rechargekar.com to the Cloudflare Tunnel.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import httpx

from cloudflare_manager import _load_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_tunnel")

TUNNEL_ID = "3fd601c7-288f-496c-9f93-db0d37822076"
TUNNEL_TARGET = f"{TUNNEL_ID}.cfargotunnel.com"
DOMAIN = "rechargekar.com"
ZONE_ID = "090d02accb95b73cc9ccd539b9915576"


def route_dns_to_tunnel() -> None:
    token, account_id = _load_env()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Fetch existing records for rechargekar.com
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records"
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        records = resp.json().get("result", [])

        for r in records:
            name = r.get("name", "")
            rtype = r.get("type", "")
            rid = r.get("id", "")
            if name in (DOMAIN, f"www.{DOMAIN}") and rtype in ("A", "CNAME"):
                logger.info("Removing old %s record: %s -> %s", rtype, name, r.get("content"))
                client.delete(f"{url}/{rid}", headers=headers)

        # 2. Add CNAME records pointing to Tunnel Target
        for host in (DOMAIN, f"www.{DOMAIN}"):
            payload = {
                "type": "CNAME",
                "name": host,
                "content": TUNNEL_TARGET,
                "ttl": 1,
                "proxied": True,
            }
            create_resp = client.post(url, headers=headers, json=payload)
            data = create_resp.json()
            if create_resp.status_code in (200, 201) and data.get("success"):
                logger.info("[✓] Pointed %s to tunnel (%s)", host, TUNNEL_TARGET)
            else:
                logger.warning("[-] Failed to create record for %s: %s", host, data.get("errors"))


if __name__ == "__main__":
    route_dns_to_tunnel()
