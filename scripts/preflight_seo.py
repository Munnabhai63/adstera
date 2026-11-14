#!/usr/bin/env python3
"""
scripts/preflight_seo.py — SEO & Transport Preflight Audit Gate

Evaluates readiness of all required inputs, transport credentials, API tokens,
and article content quality metrics before live traffic generation or publishing.

Reports OK, MISSING, FAIL, or UNVERIFIABLE for:
  1. Network Transport (proxies.txt valid count + ADB devices connected)
  2. Google Search Console (Service Account JSON or OAuth2 credentials)
  3. IndexNow Verification Keys (provisioned across all 10 network domains)
  4. FreeLLMAPI Gateway Token (presence only; never echoes secrets)
  5. Cloudflare Tunnel Token (presence only; never echoes secrets)
  6. Article Readiness Snapshot (total articles, <600w count, missing metadata)

Exit code:
  0: All required inputs are present and verified.
  1: One or more required inputs are MISSING or FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from network_registry import NETWORK_REGISTRY
from content_quality_gate import (
    ARTICLE_WORD_COUNT_FLOOR,
    count_body_words,
    count_page_words,
    count_prose_words,
)


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


def _read_env_keys(env_path: Path) -> dict[str, bool]:
    """Check existence of keys in .env without storing or exposing their values."""
    present_keys: dict[str, bool] = {}
    if not env_path.is_file():
        return present_keys
    try:
        content = env_path.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and v:
                    present_keys[k] = True
    except Exception:
        pass
    return present_keys


def check_transport(cfg_path: Path) -> dict[str, Any]:
    """Check proxy list validity and USB ADB Android devices."""
    import yaml
    from pool import validate_proxy_lines

    cfg: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    proxy_rel = cfg.get("proxy", {}).get("file", "proxies.txt")
    proxy_file = PROJECT_ROOT / proxy_rel

    valid_proxies = []
    malformed = []
    if proxy_file.is_file():
        lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        valid_proxies, malformed = validate_proxy_lines(lines)

    adb_devices = []
    try:
        import mobile_adb
        adb_devices = [d for d in mobile_adb.list_devices() if d.get("status") == "device"]
    except Exception:
        pass

    has_transport = len(valid_proxies) > 0 or len(adb_devices) > 0
    status = "OK" if has_transport else "MISSING"

    details = f"{len(valid_proxies)} valid proxy(ies) in {proxy_rel}, {len(adb_devices)} ADB device(s) connected"
    remedy = ""
    if not has_transport:
        remedy = f"Populate {proxy_rel} with residential proxies (see proxies.example.txt) or connect an Android device via USB ADB."

    return {
        "category": "Transport",
        "status": status,
        "details": details,
        "valid_proxies_count": len(valid_proxies),
        "malformed_proxies_count": len(malformed),
        "malformed_lines": malformed,
        "adb_devices_count": len(adb_devices),
        "remedy": remedy,
    }


def check_gsc() -> dict[str, Any]:
    """Check Google Search Console credentials via GSCAuthManager (never prints secrets)."""
    try:
        from gsc_auth import GSCAuthManager
        auth_mgr = GSCAuthManager()
        st = auth_mgr.get_status()
        is_conf = st.get("configured", False)
        auth_type = st.get("auth_type", "unconfigured")
        client_email = st.get("client_email", "")

        status = "OK" if is_conf else "MISSING"
        if is_conf:
            details = f"Configured via {auth_type}" + (f" ({client_email})" if client_email else "")
            remedy = ""
        else:
            details = "Unconfigured (no service account JSON or OAuth token found)"
            remedy = "Set up Google Search Console Service Account in state/gsc_service_account.json (see docs/STEP1_OWNER_ACTIONS.md)."

        return {
            "category": "Google Search Console",
            "status": status,
            "details": details,
            "auth_type": auth_type,
            "client_email": client_email,
            "remedy": remedy,
        }
    except Exception as exc:
        return {
            "category": "Google Search Console",
            "status": "FAIL",
            "details": f"Error inspecting GSC credentials: {exc}",
            "auth_type": "error",
            "client_email": "",
            "remedy": "Verify gsc_auth.py configuration and permissions.",
        }


def check_indexnow_keys() -> dict[str, Any]:
    """Verify IndexNow key verification files across all 10 registered domains."""
    from instant_indexer import INDEXNOW_KEY

    sites_dir = PROJECT_ROOT / "sites"
    missing = []
    verified = []

    for site_key, site_info in NETWORK_REGISTRY.items():
        domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
        expected_dir = sites_dir / f"{site_key}.com"
        key_file = expected_dir / f"{INDEXNOW_KEY}.txt"

        if key_file.is_file():
            try:
                content = key_file.read_text(encoding="utf-8").strip()
                if content == INDEXNOW_KEY:
                    verified.append(domain)
                else:
                    missing.append((domain, "key mismatch"))
            except Exception as e:
                missing.append((domain, str(e)))
        else:
            missing.append((domain, "file missing"))

    total = len(NETWORK_REGISTRY)
    if len(verified) == total:
        status = "OK"
        details = f"{len(verified)}/{total} network sites verified with key '{INDEXNOW_KEY[:10]}...'"
        remedy = ""
    else:
        status = "FAIL"
        details = f"{len(verified)}/{total} network sites verified ({len(missing)} missing or invalid)"
        remedy = 'Run python -c "import instant_indexer; instant_indexer.provision_verification_keys()"'

    return {
        "category": "IndexNow Verification",
        "status": status,
        "details": details,
        "verified_count": len(verified),
        "total_count": total,
        "missing": missing,
        "remedy": remedy,
    }


def check_token_presence(
    category_name: str,
    env_vars: list[str],
    doc_anchor: str,
    env_keys: dict[str, bool],
) -> dict[str, Any]:
    """Check if a required token is present in os.environ or .env without exposing its value."""
    found_var = None
    source = None

    for var in env_vars:
        if os.environ.get(var):
            found_var = var
            source = "environment"
            break
        elif env_keys.get(var):
            found_var = var
            source = ".env file"
            break

    if found_var:
        return {
            "category": category_name,
            "status": "OK",
            "details": f"Present (found {found_var} in {source})",
            "remedy": "",
        }
    else:
        vars_str = " or ".join(env_vars)
        return {
            "category": category_name,
            "status": "MISSING",
            "details": f"Absent ({vars_str} not set in environment or .env)",
            "remedy": f"Set {env_vars[0]} in .env or environment (see docs/STEP1_OWNER_ACTIONS.md#{doc_anchor}).",
        }


def collect_article_snapshot(sites_root: Path | None = None) -> dict[str, Any]:
    """Scan and compute real-world article content metrics across sites/."""
    sites_dir = sites_root if sites_root is not None else (PROJECT_ROOT / "sites")
    if not sites_dir.is_dir():
        return {
            "category": "Article Snapshot",
            "status": "UNVERIFIABLE",
            "details": f"{sites_dir} directory not found",
            "total_articles": 0,
            "under_600_words": 0,
            "pct_under_600": 0.0,
            "missing_metadata": 0,
            "pct_missing_metadata": 0.0,
            "average_words": 0,
            "median_words": 0,
        }

    articles: list[Path] = []
    for p in sites_dir.rglob("*.html"):
        try:
            rel = p.relative_to(sites_dir)
        except ValueError:
            continue

        # Exclude layouts, category listings, or _default
        if any(x in rel.parts for x in ("layouts", "_default", "category")):
            continue
        # Exclude google verification files
        if p.name.startswith("google") and p.name.endswith(".html"):
            continue
        # Exclude domain root homepages: rel.parts is (<domain>, 'index.html'), len is 2
        if len(rel.parts) <= 2 and p.name == "index.html":
            continue
        slug = p.parent.name if p.name == "index.html" else p.stem
        if slug in STATIC_SLUGS:
            continue
        articles.append(p)

    total = len(articles)
    if total == 0:
        return {
            "category": "Article Snapshot",
            "status": "UNVERIFIABLE",
            "details": f"0 articles found in {sites_dir}",
            "total_articles": 0,
            "under_600_words": 0,
            "pct_under_600": 0.0,
            "missing_metadata": 0,
            "pct_missing_metadata": 0.0,
            "average_words": 0,
            "median_words": 0,
        }

    under_600 = 0
    missing_meta = 0
    page_counts: list[int] = []
    body_counts: list[int] = []
    prose_counts: list[int] = []
    articles_data: list[dict[str, Any]] = []

    for art in articles:
        try:
            rel = art.relative_to(sites_dir)
            domain = rel.parts[0]
            slug = art.parent.name if art.name == "index.html" else art.stem
            text = art.read_text(encoding="utf-8", errors="ignore")

            page_w = count_page_words(text)
            body_w = count_body_words(text)
            prose_w = count_prose_words(text)

            page_counts.append(page_w)
            body_counts.append(body_w)
            prose_counts.append(prose_w)

            articles_data.append({
                "domain": domain,
                "slug": slug,
                "page_words": page_w,
                "body_words": body_w,
                "prose_words": prose_w,
            })

            # Base threshold and under_600 solely on prose_words
            if prose_w < 600:
                under_600 += 1

            # Check for author and datePublished in Schema.org or meta
            has_date = "datePublished" in text
            has_author = "author" in text
            if not (has_date and has_author):
                missing_meta += 1
        except Exception:
            pass

    prose_counts.sort()
    page_counts.sort()
    body_counts.sort()

    avg_prose = sum(prose_counts) / len(prose_counts) if prose_counts else 0
    median_prose = prose_counts[len(prose_counts) // 2] if prose_counts else 0

    avg_page = sum(page_counts) / len(page_counts) if page_counts else 0
    median_page = page_counts[len(page_counts) // 2] if page_counts else 0

    avg_body = sum(body_counts) / len(body_counts) if body_counts else 0
    median_body = body_counts[len(body_counts) // 2] if body_counts else 0

    pct_under_600 = (under_600 / total * 100) if total else 0
    pct_missing_meta = (missing_meta / total * 100) if total else 0

    ge_1200 = sum(1 for w in prose_counts if w >= 1200)
    ge_2000 = sum(1 for w in prose_counts if w >= 2000)
    ge_3000 = sum(1 for w in prose_counts if w >= 3000)

    return {
        "category": "Article Snapshot",
        "status": "INFO",
        "total_articles": total,
        "canonical_standard": "prose_words",
        "floor_threshold": ARTICLE_WORD_COUNT_FLOOR,
        "under_600_words": under_600,
        "pct_under_600": round(pct_under_600, 1),
        "missing_metadata": missing_meta,
        "pct_missing_metadata": round(pct_missing_meta, 1),
        "average_words": round(avg_prose, 1),
        "median_words": median_prose,
        "average_prose_words": round(avg_prose, 1),
        "median_prose_words": median_prose,
        "average_page_words": round(avg_page, 1),
        "median_page_words": median_page,
        "average_body_words": round(avg_body, 1),
        "median_body_words": median_body,
        "prose_ge_1200": ge_1200,
        "prose_ge_2000": ge_2000,
        "prose_ge_3000": ge_3000,
        "articles": articles_data,
    }


def run_preflight(cfg_path: Path, env_path: Path) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    """Execute all preflight checks and determine overall pass/fail status."""
    env_keys = _read_env_keys(env_path)

    checks: list[dict[str, Any]] = [
        check_transport(cfg_path),
        check_gsc(),
        check_indexnow_keys(),
        check_token_presence("FreeLLMAPI Token", ["FREELLMAPI_TOKEN", "FREELLMAPI_KEY"], "2-freellmapi-token-setup", env_keys),
        check_token_presence("Cloudflare Tunnel Token", ["CLOUDFLARE_TUNNEL_TOKEN", "TUNNEL_TOKEN"], "1-cloudflare-zero-trust-tunnel-setup", env_keys),
    ]

    snapshot = collect_article_snapshot()

    has_missing_or_fail = any(c["status"] in ("MISSING", "FAIL") for c in checks)
    exit_code = 1 if has_missing_or_fail else 0

    return exit_code, checks, snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight SEO and Transport input validation.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--env", default=".env", help="Path to .env")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    parser.add_argument("--allow-missing", action="store_true", help="Exit with 0 even if inputs are missing (advisory run)")
    parser.add_argument("--table", action="store_true", help="Print table of all articles with page, body, prose words")

    args = parser.parse_args()
    cfg_path = PROJECT_ROOT / args.config
    env_path = PROJECT_ROOT / args.env

    exit_code, checks, snapshot = run_preflight(cfg_path, env_path)
    effective_exit_code = 0 if args.allow_missing else exit_code
    effective_status = "PASS" if effective_exit_code == 0 else "FAIL"

    if args.json:
        payload = {
            "exit_code": effective_exit_code,
            "overall_status": effective_status,
            "checks": checks,
            "article_snapshot": snapshot,
        }
        print(json.dumps(payload, indent=2))
        return effective_exit_code

    print("=" * 72)
    print(" PRE-FLIGHT SEO & TRANSPORT READINESS REPORT")
    print("=" * 72)

    for c in checks:
        st = c["status"]
        cat = c["category"]
        details = c["details"]
        tag = f"[{st:7s}]"
        print(f" {tag} {cat}: {details}")
        if c.get("remedy") and st in ("MISSING", "FAIL"):
            print(f"           -> Remedy: {c['remedy']}")

        # List any malformed proxy lines if present
        if c.get("malformed_lines"):
            print(f"           [!] {len(c['malformed_lines'])} malformed line(s) detected in proxies.txt:")
            for item in c["malformed_lines"][:5]:
                print(f"               Line {item['line']}: {item['text']!r} ({item['error']})")
            if len(c["malformed_lines"]) > 5:
                print(f"               ... and {len(c['malformed_lines']) - 5} more")

    print("-" * 72)
    st = snapshot.get("status", "INFO")
    tot = snapshot.get("total_articles", 0)
    u600 = snapshot.get("under_600_words", 0)
    u600_pct = snapshot.get("pct_under_600", 0.0)
    mmeta = snapshot.get("missing_metadata", 0)
    mmeta_pct = snapshot.get("pct_missing_metadata", 0.0)
    avg_w = snapshot.get("average_words", 0)
    med_w = snapshot.get("median_words", 0)
    avg_prose = snapshot.get("average_prose_words", avg_w)
    med_prose = snapshot.get("median_prose_words", med_w)
    avg_page = snapshot.get("average_page_words", 0)
    avg_body = snapshot.get("average_body_words", 0)
    ge_1200 = snapshot.get("prose_ge_1200", 0)
    ge_2000 = snapshot.get("prose_ge_2000", 0)
    ge_3000 = snapshot.get("prose_ge_3000", 0)

    print(f" [INFO   ] Article Readiness Snapshot: {tot} real articles across 10 domains")
    print(f"           - Standard: prose_words (Floor: {ARTICLE_WORD_COUNT_FLOOR})")
    print(f"           - Under 600 prose words: {u600}/{tot} ({u600_pct:.1f}%) [High Priority for Step 2 Expansion]")
    print(f"           - Missing author / datePublished: {mmeta}/{tot} ({mmeta_pct:.1f}%)")
    print(f"           - Average: prose={avg_prose}w | body={avg_body}w | page={avg_page}w")
    print(f"           - Median:  prose={med_prose}w | body={snapshot.get('median_body_words', 0)}w | page={snapshot.get('median_page_words', 0)}w")
    print(f"           - Prose word tiers: >=1200: {ge_1200}/{tot} | >=2000: {ge_2000}/{tot} | >=3000: {ge_3000}/{tot}")

    arts = snapshot.get("articles", [])
    if arts:
        display_arts = arts if args.table else arts[:20]
        print("\n" + "-" * 78)
        print(f" {'Domain':<18} | {'Slug':<34} | {'Page':>6} | {'Body':>6} | {'Prose':>6}")
        print("-" * 78)
        for row in display_arts:
            slug_disp = (row['slug'][:31] + '...') if len(row['slug']) > 34 else row['slug']
            print(f" {row['domain']:<18} | {slug_disp:<34} | {row['page_words']:>6} | {row['body_words']:>6} | {row['prose_words']:>6}")
        if not args.table and len(arts) > 20:
            print(f" ... ({len(arts) - 20} more articles omitted; pass --table to display all {len(arts)})")
        print("-" * 78)
        print(f" {'SUMMARY (AVG)':<18} | {f'{tot} articles':<34} | {round(avg_page):>6} | {round(avg_body):>6} | {round(avg_prose):>6}")
        print("-" * 78)
    print("=" * 72)

    if exit_code == 0:
        print(" RESULT: ALL REQUIRED INPUTS PRESENT & VERIFIED [READY]")
    else:
        print(" RESULT: ACTION REQUIRED — Missing inputs detected above [NOT READY]")
        print(" Refer to docs/STEP1_OWNER_ACTIONS.md for step-by-step resolution instructions.")

    print("=" * 72)

    if args.allow_missing:
        return 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
