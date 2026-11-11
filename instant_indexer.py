"""
instant_indexer.py — Production Instant Search Indexer (IndexNow + Bing + Yandex + Google)
=============================================================================================
Provides real-time submission to IndexNow API (Bing, Yandex, Yahoo, Seznam, Naver) and
maintains sitemaps, robots.txt, and llms.txt across all 10 publisher network domains.

IndexNow Protocol:
  Key: adstera8291a0c7e5bf4182bdc6019a
  Verification file: https://<domain>/adstera8291a0c7e5bf4182bdc6019a.txt
"""

from __future__ import annotations
import os
import glob
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
import httpx
from network_registry import NETWORK_REGISTRY

INDEXNOW_KEY = "adstera8291a0c7e5bf4182bdc6019a"
INDEXNOW_ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
]
DB_PATH = os.path.join("state", "autopublish.db")


def provision_verification_keys() -> None:
    """Ensure every website root directory contains the IndexNow verification key file and llms.txt."""
    sites_dir = "sites"
    if not os.path.exists(sites_dir):
        return

    for site_key, site_info in NETWORK_REGISTRY.items():
        domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
        name = site_info["name"]
        desc = site_info["desc"]

        # Canonical sites/<site_key>.com directory
        target_dirs = [
            os.path.join(sites_dir, f"{site_key}.com"),
        ]

        for d in target_dirs:
            if not os.path.exists(d):
                continue

            # 1. IndexNow Verification File
            key_file = os.path.join(d, f"{INDEXNOW_KEY}.txt")
            with open(key_file, "w", encoding="utf-8") as f:
                f.write(INDEXNOW_KEY)

            # 2. robots.txt
            robots_file = os.path.join(d, "robots.txt")
            robots_content = f"""User-agent: *
Allow: /

# Generative Engine Optimization (GEO) AI Crawlers
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

Sitemap: https://{domain}/sitemap.xml
"""
            with open(robots_file, "w", encoding="utf-8") as f:
                f.write(robots_content)

            # 3. llms.txt (GEO standard for AI search engines)
            llms_file = os.path.join(d, "llms.txt")
            llms_content = f"""# {name}
> {desc}

## Authoritative Coverage
- In-depth, analytical consumer guides, empirical comparison benchmarks, statutory regulatory updates, and financial calculators.
- Verified and fact-checked by {name} Research Desk.

## Sitemaps & Feeds
- Canonical Sitemap: https://{domain}/sitemap.xml
- IndexNow Key: https://{domain}/{INDEXNOW_KEY}.txt
"""
            with open(llms_file, "w", encoding="utf-8") as f:
                f.write(llms_content)

    print("[Instant Indexer] IndexNow verification keys, robots.txt, and llms.txt provisioned across all domains.")


def update_sitemap_xml(site_id: str, new_url: str) -> None:
    """Safely append new URL to sitemap.xml in canonical site directory."""
    sites_dir = "sites"
    target_dirs = [
        os.path.join(sites_dir, f"{site_id}.com"),
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    url_node_str = f"  <url>\n    <loc>{new_url}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.9</priority>\n  </url>\n"

    for d in target_dirs:
        sitemap_path = os.path.join(d, "sitemap.xml")
        if not os.path.exists(sitemap_path):
            continue

        with open(sitemap_path, "r", encoding="utf-8") as f:
            content = f.read()

        # If URL is already in sitemap, do nothing
        if new_url in content:
            continue

        if "</urlset>" in content:
            updated = content.replace("</urlset>", url_node_str + "</urlset>")
            with open(sitemap_path, "w", encoding="utf-8") as f:
                f.write(updated)


def submit_to_indexnow(clean_domain: str, url_list: list[str]) -> bool:
    """Submit a batch of URLs to the IndexNow API protocol."""
    if not url_list:
        return False

    payload = {
        "host": clean_domain,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{clean_domain}/{INDEXNOW_KEY}.txt",
        "urlList": url_list,
    }

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "Adstera-Instant-Indexer/1.0",
    }

    success = False
    for ep in INDEXNOW_ENDPOINTS:
        try:
            resp = httpx.post(ep, json=payload, headers=headers, timeout=10)
            if resp.status_code in (200, 202):
                print(f"[IndexNow SUCCESS] Submitted {len(url_list)} URLs for {clean_domain} to {ep} (HTTP {resp.status_code})")
                success = True
            else:
                print(f"[IndexNow Notice] {ep} returned HTTP {resp.status_code} for {clean_domain}: {resp.text[:120]}")
        except Exception as e:
            print(f"[IndexNow Error] Could not reach {ep}: {e}")

    return success


def ping_google_sitemap(clean_domain: str) -> bool:
    """Ping Google with updated sitemap."""
    sitemap_url = f"https://{clean_domain}/sitemap.xml"
    ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
    try:
        r = httpx.get(ping_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        print(f"[Google Ping] Pinged sitemap {sitemap_url} (HTTP {r.status_code})")
        return True
    except Exception as e:
        print(f"[Google Ping Notice] Ping for {clean_domain}: {e}")
        return False


def broadcast_new_post(site_id: str, new_post_url: str) -> bool:
    """Broadcast newly published article across IndexNow, sitemaps, and search engines."""
    site_info = NETWORK_REGISTRY.get(site_id)
    if not site_info:
        return False

    clean_domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
    
    # 1. Ensure keys and robots are in place
    provision_verification_keys()

    # 2. Update sitemap.xml
    update_sitemap_xml(site_id, new_post_url)

    # 3. Submit URL List (Post URL + Homepage + Sitemap)
    urls = [
        new_post_url,
        f"https://{clean_domain}/",
        f"https://{clean_domain}/sitemap.xml",
    ]

    indexnow_ok = submit_to_indexnow(clean_domain, urls)
    google_ok = ping_google_sitemap(clean_domain)
    try:
        from gsc_auth import GSCAuthManager
        if GSCAuthManager().is_configured():
            import asyncio
            from gsc_submitter import GoogleIndexingSubmitter

            async def _submit_real_gsc() -> bool:
                sub = GoogleIndexingSubmitter()
                r1 = await sub.submit_url(new_post_url, action="URL_UPDATED")
                r2 = await sub.submit_sitemap(f"https://{clean_domain}/sitemap.xml", mock_fallback=False)
                return bool(r1.get("status") == "ok" and r1.get("authenticated")) or bool(r2)

            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    if pool.submit(asyncio.run, _submit_real_gsc()).result(timeout=20):
                        google_ok = True
            except RuntimeError:
                if asyncio.run(_submit_real_gsc()):
                    google_ok = True
    except Exception as gsc_exc:
        print(f"[GSC API Notice] Authenticated Indexing API skipped for {clean_domain}: {gsc_exc}")

    # 4. Update database flag if DB exists
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.cursor().execute(
                "UPDATE published_posts SET google_pinged = ? WHERE domain = ? AND ? LIKE '%' || slug || '%'",
                (1 if (indexnow_ok or google_ok) else 0, site_id, new_post_url)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    return indexnow_ok or google_ok


def broadcast_all_network_sites() -> dict[str, int]:
    """Broadcast all existing pages from all 10 sites to IndexNow for immediate indexing."""
    provision_verification_keys()
    results = {}

    for site_key, site_info in NETWORK_REGISTRY.items():
        clean_domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
        site_dir = os.path.join("sites", f"{site_key}.com")
        
        urls_to_submit = [
            f"https://{clean_domain}/",
            f"https://{clean_domain}/calculator",
            f"https://{clean_domain}/sitemap.xml",
        ]

        # Scan HTML files
        if os.path.exists(site_dir):
            for f in glob.glob(os.path.join(site_dir, "*.html")):
                basename = os.path.basename(f)
                if basename in ("index.html", "calculator.html"):
                    continue
                slug = basename.replace(".html", "")
                urls_to_submit.append(f"https://{clean_domain}/{slug}")

        urls_to_submit = list(set(urls_to_submit))
        print(f"\n[Instant Indexer] Broadcasting {len(urls_to_submit)} URLs for {clean_domain}...")
        ok = submit_to_indexnow(clean_domain, urls_to_submit)
        ping_google_sitemap(clean_domain)
        results[clean_domain] = len(urls_to_submit) if ok else 0

    return results


if __name__ == "__main__":
    print("="*60)
    print("EXECUTING INSTANT INDEXER BROADCAST ACROSS ALL 10 SITES")
    print("="*60)
    res = broadcast_all_network_sites()
    print("\nSummary of indexed submissions:")
    for dom, count in res.items():
        print(f"  [OK] {dom}: {count} URLs submitted to IndexNow")
