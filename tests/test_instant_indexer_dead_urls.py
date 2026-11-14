#!/usr/bin/env python3
"""
tests/test_instant_indexer_dead_urls.py — Verify dead flat .html URLs are skipped in instant indexer
"""

from __future__ import annotations

import os
from pathlib import Path
from instant_indexer import broadcast_all_network_sites, NETWORK_REGISTRY, STATIC_SLUGS

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_instant_indexer_skips_dead_flat_urls():
    # 1. Measure unfiltered total
    unfiltered_total = 0
    for site_key, site_info in NETWORK_REGISTRY.items():
        clean_domain = site_info["domain"].replace("https://", "").replace("http://", "").rstrip("/")
        site_dir = PROJECT_ROOT / "sites" / f"{site_key}.com"
        urls = [f"https://{clean_domain}/", f"https://{clean_domain}/sitemap.xml"]
        if site_dir.exists():
            for root, dirs, files in os.walk(site_dir):
                root_path = Path(root)
                if any(part in ("layouts", "_default") for part in root_path.parts):
                    continue
                for filename in files:
                    if not filename.endswith(".html") or filename.startswith("google") or filename == "calculator.html":
                        continue
                    file_path = root_path / filename
                    rel = file_path.relative_to(site_dir)
                    rel_parts = rel.parts
                    if filename == "index.html":
                        if len(rel_parts) == 1:
                            continue
                        slug = "/".join(rel_parts[:-1])
                        if slug in STATIC_SLUGS or any(part in STATIC_SLUGS for part in rel_parts[:-1]):
                            continue
                        urls.append(f"https://{clean_domain}/{slug}/")
                    else:
                        slug = rel.with_suffix("").as_posix()
                        if slug in STATIC_SLUGS or any(part in STATIC_SLUGS for part in rel_parts):
                            continue
                        urls.append(f"https://{clean_domain}/{slug}")
        unfiltered_total += len(dict.fromkeys(urls))

    assert unfiltered_total == 379, f"Expected 379 unfiltered URLs, got {unfiltered_total}"

    # 2. Run instant indexer in dry-run mode
    results = broadcast_all_network_sites(dry_run=True)
    filtered_total = sum(results.values())

    assert filtered_total == 339, f"Expected 339 filtered URLs, got {filtered_total}"
    assert unfiltered_total - filtered_total == 40, f"Expected drop of 40 URLs, got {unfiltered_total - filtered_total}"

    print(f"\n[Q7 PROVE SUCCESS] Unfiltered: {unfiltered_total} | Filtered: {filtered_total} | Exactly dropped 40 dead flat URLs.")
