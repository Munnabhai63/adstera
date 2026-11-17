#!/usr/bin/env python3
"""
tests/test_d10_breadcrumb_urls.py — Verify that every URL referenced in BreadcrumbList
JSON-LD schema exists on disk in sites/ or has a 301 rule in _redirects.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse

SITES_DIR = Path("sites")


def get_redirect_rules_for_domain(domain: str) -> set[str]:
    rules = set()
    for redirects_file in [Path("_redirects"), SITES_DIR / domain / "_redirects"]:
        if redirects_file.exists():
            for line in redirects_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts:
                    rules.add(parts[0].rstrip("/"))
    return rules


def test_every_breadcrumb_item_url_exists_or_redirects():
    broken_urls = []

    for html_file in sorted(SITES_DIR.glob("*/*/index.html")):
        domain = html_file.parent.parent.name
        redirect_rules = get_redirect_rules_for_domain(domain)
        raw = html_file.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
            except Exception:
                continue

            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if isinstance(item, dict) and item.get("@type") == "BreadcrumbList":
                    elements = item.get("itemListElement", [])
                    for el in elements:
                        item_url = el.get("item", "")
                        if not item_url:
                            continue

                        parsed = urlparse(item_url)
                        path = parsed.path.strip("/")

                        # Home page always exists
                        if not path:
                            continue

                        # Check if path exists in sites/{domain}
                        path_clean = path.removesuffix(".html")
                        target_dir = SITES_DIR / domain / path_clean / "index.html"
                        target_file = SITES_DIR / domain / f"{path_clean}.html"
                        target_direct = SITES_DIR / domain / path

                        exists_on_disk = (
                            target_dir.exists()
                            or target_file.exists()
                            or target_direct.exists()
                        )
                        has_redirect = f"/{path_clean}" in redirect_rules or f"/{path}" in redirect_rules

                        if not exists_on_disk and not has_redirect:
                            broken_urls.append((f"{domain}/{html_file.parent.name}", item_url))

    assert len(broken_urls) == 0, f"Found {len(broken_urls)} broken breadcrumb URLs: {broken_urls}"
