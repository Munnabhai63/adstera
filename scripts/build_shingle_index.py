#!/usr/bin/env python3
"""
scripts/build_shingle_index.py — Deterministic rebuild of the 12-word prose shingle index.
Builds state/prose_shingles.json from sites/ with sorted keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shingle_guard import (
    SHINGLE_INDEX_PATH,
    extract_prose_paragraphs,
    get_12_word_shingles,
)
from scripts.seo_onpage_audit import get_all_article_paths


def build_shingle_index(output_path: Path = SHINGLE_INDEX_PATH, dry_run: bool = False) -> int:
    """Build deterministic 12-word shingle index from all sites/ HTML files."""
    sites_dir = PROJECT_ROOT / "sites"
    articles = sorted(get_all_article_paths(sites_dir), key=lambda p: str(p.as_posix()))

    index: dict[str, dict[str, str]] = {}
    total_shingles_scanned = 0

    print(f"Scanning {len(articles)} articles from {sites_dir}...")

    for path in articles:
        domain = path.relative_to(sites_dir).parts[0]
        slug = path.parent.name if path.name == "index.html" else path.stem
        page_id = f"{domain}/{slug}"

        html_text = path.read_text(encoding="utf-8", errors="ignore")
        paras = extract_prose_paragraphs(html_text)
        full_prose = " ".join(paras)

        shingles = get_12_word_shingles(full_prose)
        total_shingles_scanned += len(shingles)

        for shingle in shingles:
            if shingle not in index:
                index[shingle] = {
                    "domain": domain,
                    "slug": slug,
                    "page_id": page_id,
                }

    sorted_index = {k: index[k] for k in sorted(index.keys())}
    print(f"Total shingles scanned: {total_shingles_scanned}")
    print(f"Unique shingles indexed: {len(sorted_index)}")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(sorted_index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Index successfully written to {output_path}")

    return len(sorted_index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild deterministic 12-word prose shingle index.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate index without writing file.")
    args = parser.parse_args()
    build_shingle_index(dry_run=args.dry_run)
