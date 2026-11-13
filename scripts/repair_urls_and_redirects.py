"""
Phase 3 P3-4: Clean URL Migration & Redirects
1. Copy flat <slug>.html files to <slug>/index.html if missing.
2. Rewrite all internal href="/<slug>.html" links to href="/<slug>".
3. Delete flat <slug>.html files in sites/*/*.html (preserving root index.html).
4. Update _redirects files across all 10 sites with "/:slug.html /:slug 301".
"""
from __future__ import annotations

import glob
import os
import re
import shutil
from pathlib import Path


def repair_urls_and_redirects(sites_dir: str = "sites") -> dict[str, int]:
    base = Path(sites_dir)
    stats = {
        "twins_created": 0,
        "links_rewritten": 0,
        "files_with_rewrites": 0,
        "flat_deleted": 0,
        "redirects_updated": 0,
    }

    # Step 1: Ensure every flat article has a directory twin <slug>/index.html
    flat_articles = [
        f for f in base.glob("*/*.html")
        if f.name != "index.html" and f.is_file()
    ]

    for flat_file in flat_articles:
        slug = flat_file.stem
        site_dir = flat_file.parent
        dir_twin = site_dir / slug / "index.html"
        if not dir_twin.exists():
            dir_twin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(flat_file, dir_twin)
            stats["twins_created"] += 1

    # Step 2: Rewrite internal links in all html files across all sites
    link_pattern = re.compile(r'href=(["\'])/([a-z0-9-]+)\.html(["\'])', re.IGNORECASE)

    all_html_files = list(base.glob("**/*.html"))
    for html_file in all_html_files:
        try:
            content = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = html_file.read_text(encoding="utf-8", errors="ignore")

        new_content, count = link_pattern.subn(r'href=\1/\2\3', content)
        if count > 0:
            html_file.write_text(new_content, encoding="utf-8")
            stats["links_rewritten"] += count
            stats["files_with_rewrites"] += 1

    # Step 3: Delete all flat article files in sites/*/*.html (keep root index.html)
    for flat_file in flat_articles:
        try:
            flat_file.unlink()
            stats["flat_deleted"] += 1
        except Exception as e:
            print(f"Error deleting {flat_file}: {e}")

    # Step 4: Ensure _redirects in every site directory has "/:slug.html /:slug 301"
    for site_folder in base.iterdir():
        if site_folder.is_dir() and (site_folder / "index.html").exists():
            redirects_path = site_folder / "_redirects"
            current_text = ""
            if redirects_path.exists():
                current_text = redirects_path.read_text(encoding="utf-8")

            if "/:slug.html /:slug 301" not in current_text:
                if current_text and not current_text.endswith("\n"):
                    current_text += "\n"
                current_text += "/:slug.html /:slug 301\n"
                redirects_path.write_text(current_text, encoding="utf-8")
                stats["redirects_updated"] += 1

    return stats


if __name__ == "__main__":
    results = repair_urls_and_redirects()
    print("Repair URLs and Redirects finished:")
    for k, v in results.items():
        print(f"  {k}: {v}")
