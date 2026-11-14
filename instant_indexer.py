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
import asyncio
import glob
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
import httpx
from network_registry import NETWORK_REGISTRY

logger = logging.getLogger("instant_indexer")

INDEXNOW_KEY = "adstera8291a0c7e5bf4182bdc6019a"
INDEXNOW_ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
]
DB_PATH = os.path.join("state", "autopublish.db")
_PROVISION_LOCK = threading.Lock()
_DB_WRITE_LOCK = threading.Lock()


def provision_verification_keys() -> None:
    """Ensure every website root directory contains the IndexNow verification key file and llms.txt."""
    sites_dir = "sites"
    if not os.path.exists(sites_dir):
        return

    with _PROVISION_LOCK:
        _provision_verification_keys_unlocked(sites_dir)


def _provision_verification_keys_unlocked(sites_dir: str) -> None:
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

            # 2. robots.txt (Claude-SEO v2.5.0 `seo-geo` + `seo-agentic`: separate AI Search, User-Agent & Training groups + Content-Signal)
            robots_file = os.path.join(d, "robots.txt")
            robots_content = f"""User-agent: *
Allow: /
Content-Signal: search=yes, ai-input=yes

# 1. AI Search & Answer-Engine Citability Crawlers (seo-geo)
User-agent: OAI-SearchBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Googlebot
Allow: /

User-agent: Applebot
Allow: /

# 2. User-Triggered AI Browsing Agents (seo-agentic)
User-agent: ChatGPT-User
Allow: /

User-agent: Claude-User
Allow: /

# 3. AI Model & Extended Knowledge Crawlers
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /

Sitemap: https://{domain}/sitemap.xml
"""
            with open(robots_file, "w", encoding="utf-8") as f:
                f.write(robots_content)

            # 3. llms.txt (Claude-SEO `seo-geo` & `seo-agentic` standard for AI answer engines)
            llms_file = os.path.join(d, "llms.txt")
            cats = site_info.get("categories", {})
            cat_links = "\n".join(
                f"- [{c_name}](https://{domain}/category/{c_data.get('slug', 'finance')}): Verified 2026 benchmarks, statutory rules, and comparison guides."
                for c_name, c_data in cats.items()
            )
            llms_content = f"""# {name}
> {desc}

## Authoritative Coverage & E-E-A-T Methodology
- In-depth, analytical consumer guides, empirical comparison tables, Indian statutory regulatory updates (RBI, TRAI, NPCI, SEBI, NABARD), and interactive financial calculators.
- Verified and fact-checked by the {name} Senior Research Desk: https://{domain}/about-us

## Core Topic Hubs
{cat_links}
- [Interactive Financial Calculator](https://{domain}/calculator): Live EMI, subsidy, and tariff estimator.

## Sitemaps & Discovery Feeds
- [Canonical XML Sitemap](https://{domain}/sitemap.xml): Full index of all published guides.
- [IndexNow Verification Key](https://{domain}/{INDEXNOW_KEY}.txt): Instant indexing verification endpoint.
"""
            with open(llms_file, "w", encoding="utf-8") as f:
                f.write(llms_content)

            # 4. Cloudflare Pages _redirects (enforce non-www canonical 301 redirect and .html to clean URL)
            redirects_file = os.path.join(d, "_redirects")
            redirects_content = (
                f"https://www.{domain}/* https://{domain}/:splat 301\n"
                f"http://www.{domain}/* https://{domain}/:splat 301\n"
                f"http://{domain}/* https://{domain}/:splat 301\n"
                f"/:slug.html /:slug 301\n"
            )
            with open(redirects_file, "w", encoding="utf-8") as f:
                f.write(redirects_content)

            # 5. Cloudflare 24x7 Serverless Edge Gateway on loanraaj.com (/v1/models & /v1/chat/completions)
            if site_key == "loanraaj":
                worker_file = os.path.join(d, "_worker.js")
                worker_js = """// Cloudflare Pages 24x7 Serverless FreeLLMAPI Edge Gateway + Static Asset Router
const GATEWAY_TOKEN = env.GATEWAY_TOKEN || "__GATEWAY_TOKEN__";

const UPSTREAM_ROUTES = [
  { provider: "ovh", model: "Qwen2.5-VL-72B-Instruct", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "ovh", model: "Mistral-Small-3.2-24B-Instruct-2506", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "ovh", model: "gpt-oss-120b", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "kilo", model: "cohere/north-mini-code:free", url: "https://api.kilo.ai/api/gateway/v1/chat/completions" },
  { provider: "kilo", model: "nvidia/nemotron-3.5-lightning:free", url: "https://api.kilo.ai/api/gateway/v1/chat/completions" }
];

function checkAuth(request, gatewayToken) {
  if (!gatewayToken || gatewayToken === "__GATEWAY_TOKEN__") return false;
  const auth = (request.headers.get("Authorization") || "").trim();
  return auth === `Bearer ${gatewayToken}` || auth === gatewayToken;
}` || auth === GATEWAY_TOKEN;
}

export default {
  async fetch(request, env) {
    const GATEWAY_TOKEN = env.GATEWAY_TOKEN;
    const url = new URL(request.url);
    if (url.pathname.startsWith("/v1/") && !GATEWAY_TOKEN) {
      return new Response(JSON.stringify({ error: "GATEWAY_TOKEN not configured" }), { status: 503, headers: { "Content-Type": "application/json" } });
    }
    if (url.hostname === "www.loanraaj.com") {
      url.hostname = "loanraaj.com";
      return Response.redirect(url.toString(), 301);
    }

    if (url.pathname === "/v1/models" && request.method === "GET") {
      if (!checkAuth(request, GATEWAY_TOKEN)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      const data = UPSTREAM_ROUTES.map((r) => ({
        id: r.model,
        object: "model",
        owned_by: r.provider,
        edge_gateway: "cloudflare-24x7"
      }));
      data.unshift({ id: "auto", object: "model", owned_by: "freellmapi-edge", edge_gateway: "cloudflare-24x7" });
      return new Response(JSON.stringify({ object: "list", data }), {
        status: 200,
        headers: { "Content-Type": "application/json", "X-Edge-Gateway": "cloudflare-loanraaj-24x7" }
      });
    }

    if (url.pathname === "/v1/chat/completions" && request.method === "POST") {
      if (!checkAuth(request, GATEWAY_TOKEN)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return new Response(JSON.stringify({ error: "Invalid JSON body" }), { status: 400, headers: { "Content-Type": "application/json" } });
      }

      const requestedModel = (body.model || "auto").trim();
      const ordered = [];
      for (const r of UPSTREAM_ROUTES) {
        if (r.model === requestedModel) ordered.push(r);
      }
      for (const r of UPSTREAM_ROUTES) {
        if (!ordered.includes(r)) ordered.push(r);
      }

      const errors = [];
      for (const route of ordered) {
        try {
          const upstreamPayload = {
            model: route.model,
            messages: body.messages || [],
            max_tokens: body.max_tokens || 2500,
            temperature: typeof body.temperature === "number" ? body.temperature : 0.7
          };
          const resp = await fetch(route.url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "User-Agent": "Mozilla/5.0 FreeLLMAPI-Cloudflare-Edge/2.0"
            },
            body: JSON.stringify(upstreamPayload)
          });
          if (resp.ok) {
            const data = await resp.json();
            const choice = (data.choices && data.choices[0]) || {};
            const msg = choice.message || {};
            const text = (msg.content || msg.reasoning_content || msg.reasoning || "").trim();
            if (text.length > 0) {
              if (!msg.content) {
                data.choices[0].message.content = text;
              }
              return new Response(JSON.stringify(data), {
                status: 200,
                headers: {
                  "Content-Type": "application/json",
                  "X-Edge-Gateway": "cloudflare-loanraaj-24x7",
                  "X-Served-Provider": route.provider,
                  "X-Served-Model": route.model
                }
              });
            }
          } else {
            errors.push(`${route.provider}/${route.model}:HTTP_${resp.status}`);
          }
        } catch (err) {
          errors.push(`${route.provider}/${route.model}:${err.message}`);
        }
      }

      return new Response(JSON.stringify({ error: "All upstream providers failed", details: errors }), {
        status: 502,
        headers: { "Content-Type": "application/json", "X-Edge-Gateway": "cloudflare-loanraaj-24x7" }
      });
    }

    return env.ASSETS.fetch(request);
  }
};
"""
                with open(worker_file, "w", encoding="utf-8") as f:
                    f.write(worker_js)

    print("[Instant Indexer] IndexNow verification keys, robots.txt, llms.txt, _redirects, and Edge Gateway provisioned across all domains.")


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


def ping_google_sitemap(clean_domain: str, fallback_deprecated: bool = False) -> dict[str, Any]:
    """
    Submit updated sitemap via Google Search Console Sitemaps API when configured.
    Never returns True/success without a verified outcome.

    Returns a structured outcome dict:
      - {"status": "submitted", "verified": True}
      - {"status": "submitted", "verified": False, "reason": "deprecated endpoint"}
      - {"status": "skipped", "reason": "no credentials"}
      - {"status": "failed", "reason": "<actual error>"}
    """
    sitemap_url = f"https://{clean_domain}/sitemap.xml"
    is_configured = False
    try:
        from gsc_auth import GSCAuthManager
        is_configured = GSCAuthManager().is_configured()
    except Exception as exc:
        logger.debug("GSCAuthManager check exception for %s: %s", clean_domain, exc)

    if is_configured:
        try:
            from gsc_submitter import GoogleIndexingSubmitter
            sub = GoogleIndexingSubmitter()

            async def _submit() -> bool:
                return await sub.submit_sitemap(sitemap_url, mock_fallback=False)

            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    ok = pool.submit(asyncio.run, _submit()).result(timeout=15)
            except RuntimeError:
                ok = asyncio.run(_submit())

            if ok:
                return {"status": "submitted", "verified": True}
            else:
                return {"status": "failed", "reason": "GSC Sitemaps API rejected or returned unverified status"}
        except Exception as exc:
            logger.warning("GSC Sitemaps API exception for %s: %s", clean_domain, exc)
            return {"status": "failed", "reason": str(exc)}

    # Unconfigured fallback path:
    if fallback_deprecated:
        ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
        try:
            r = httpx.get(ping_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if r.status_code in (200, 202):
                return {"status": "submitted", "verified": False, "reason": "deprecated endpoint"}
            return {"status": "failed", "reason": f"Deprecated ping returned HTTP {r.status_code}"}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    return {"status": "skipped", "reason": "no credentials"}


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
    google_res = ping_google_sitemap(clean_domain)
    if isinstance(google_res, dict):
        google_ok = bool(google_res.get("status") == "submitted" and google_res.get("verified"))
        st = google_res.get("status")
        if st == "skipped":
            print(f"[GSC Sitemap Notice] Google sitemap submission skipped for {clean_domain}: {google_res.get('reason')}")
        elif st == "submitted" and not google_res.get("verified"):
            print(f"[GSC Sitemap Notice] Google sitemap attempted via deprecated endpoint for {clean_domain} (unverified)")
        elif st == "submitted" and google_res.get("verified"):
            print(f"[GSC Sitemap SUCCESS] Google sitemap verified and accepted via GSC API for {clean_domain}")
        elif st == "failed":
            print(f"[GSC Sitemap Warning] Google sitemap submission failed for {clean_domain}: {google_res.get('reason')}")
    else:
        google_ok = bool(google_res)

    try:
        from gsc_auth import GSCAuthManager
        if GSCAuthManager().is_configured():
            import asyncio
            from gsc_submitter import GoogleIndexingSubmitter

            async def _submit_real_gsc() -> bool:
                sub = GoogleIndexingSubmitter()
                r1 = await sub.submit_url(new_post_url, action="URL_UPDATED")
                r2 = await sub.submit_sitemap(f"https://{clean_domain}/sitemap.xml", mock_fallback=False)
                ok1 = bool(r1.get("status") == "ok" and r1.get("authenticated"))
                if ok1 or r2:
                    print(f"[GSC Indexing API SUCCESS] {new_post_url} (URL_UPDATED={ok1}, Sitemap_PUT={bool(r2)})")
                return ok1 or bool(r2)

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
            with _DB_WRITE_LOCK:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                conn.execute("PRAGMA busy_timeout=30000;")
                conn.cursor().execute(
                    "UPDATE published_posts SET google_pinged = ? WHERE domain = ? AND ? LIKE '%' || slug || '%'",
                    (1 if (indexnow_ok or google_ok) else 0, site_id, new_post_url)
                )
                conn.commit()
                conn.close()
        except Exception:
            pass

    return indexnow_ok or google_ok


STATIC_SLUGS = {
    "about-us",
    "contact-us",
    "disclaimer",
    "privacy-policy",
    "terms-and-conditions",
    "calculator",
    "emi-calculator",
    "personal-loan-guide",
    "credit-card-apply",
}


def broadcast_all_network_sites(limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    """Broadcast all existing pages from all 10 sites to IndexNow for immediate indexing.
    
    Walks the directory tree to discover both:
      - sites/<domain>/<slug>/index.html -> https://<domain>/<slug>/
      - sites/<domain>/<slug>.html       -> https://<domain>/<slug>
    Excludes domain root index.html, calculator.html, google*.html, and STATIC_SLUGS.
    Deduplicates URLs and respects optional limit.
    """
    if not dry_run:
        provision_verification_keys()
    results = {}

    for site_key, site_info in NETWORK_REGISTRY.items():
        clean_domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
        site_dir = os.path.join("sites", f"{site_key}.com")
        
        urls_to_submit = [
            f"https://{clean_domain}/",
            f"https://{clean_domain}/sitemap.xml",
        ]

        # Scan HTML files across directory tree
        if os.path.exists(site_dir):
            site_path = Path(site_dir)
            for root, dirs, files in os.walk(site_dir):
                root_path = Path(root)
                if any(part in ("layouts", "_default") for part in root_path.parts):
                    continue
                for filename in files:
                    if not filename.endswith(".html"):
                        continue
                    if filename.startswith("google"):
                        continue
                    if filename == "calculator.html":
                        continue
                    
                    file_path = root_path / filename
                    rel = file_path.relative_to(site_path)
                    rel_parts = rel.parts
                    
                    if filename == "index.html":
                        if len(rel_parts) == 1:
                            # Skip domain root index.html (already included as https://clean_domain/)
                            continue
                        slug = "/".join(rel_parts[:-1])
                        if slug in STATIC_SLUGS or any(part in STATIC_SLUGS for part in rel_parts[:-1]):
                            continue
                        urls_to_submit.append(f"https://{clean_domain}/{slug}/")
                    else:
                        # Skip flat <slug>.html file if sibling directory <slug>/index.html exists
                        sibling_dir = file_path.with_suffix("")
                        if (sibling_dir / "index.html").exists():
                            continue
                        slug = rel.with_suffix("").as_posix()
                        if slug in STATIC_SLUGS or any(part in STATIC_SLUGS for part in rel_parts):
                            continue
                        urls_to_submit.append(f"https://{clean_domain}/{slug}")

        # Deduplicate URLs per domain preserving order
        urls_to_submit = list(dict.fromkeys(urls_to_submit))

        if limit is not None and limit > 0:
            urls_to_submit = urls_to_submit[:limit]

        if dry_run:
            print(f"[Instant Indexer (Dry-Run)] Discovered {len(urls_to_submit)} URLs for {clean_domain}")
            results[clean_domain] = len(urls_to_submit)
            continue

        print(f"\n[Instant Indexer] Broadcasting {len(urls_to_submit)} URLs for {clean_domain}...")
        ok = submit_to_indexnow(clean_domain, urls_to_submit)
        google_res = ping_google_sitemap(clean_domain)
        if isinstance(google_res, dict):
            st = google_res.get("status")
            if st == "skipped":
                print(f"  [GSC Sitemap Notice] Google sitemap submission skipped for {clean_domain}: {google_res.get('reason')}")
            elif st == "submitted" and not google_res.get("verified"):
                print(f"  [GSC Sitemap Notice] Google sitemap attempted via deprecated endpoint for {clean_domain} (unverified)")
            elif st == "submitted" and google_res.get("verified"):
                print(f"  [GSC Sitemap SUCCESS] Google sitemap verified and accepted via GSC API for {clean_domain}")
            elif st == "failed":
                print(f"  [GSC Sitemap Warning] Google sitemap submission failed for {clean_domain}: {google_res.get('reason')}")
        results[clean_domain] = len(urls_to_submit) if ok else 0

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Instant Indexer Broadcast across publisher network")
    parser.add_argument("--dry-run", action="store_true", help="Scan and print discovered URLs per domain without submitting")
    parser.add_argument("--limit", type=int, default=None, help="Cap URLs discovered per domain")
    args = parser.parse_args()

    mode_str = "DRY-RUN SCAN" if args.dry_run else "BROADCAST ACROSS ALL 10 SITES"
    print("=" * 60)
    print(f"EXECUTING INSTANT INDEXER ({mode_str})")
    print("=" * 60)
    res = broadcast_all_network_sites(limit=args.limit, dry_run=args.dry_run)
    print("\nSummary of indexed submissions:")
    for dom, count in res.items():
        status_label = "URLs Discovered (Dry-Run)" if args.dry_run else "URLs submitted to IndexNow"
        print(f"  [OK] {dom}: {count} {status_label}")
