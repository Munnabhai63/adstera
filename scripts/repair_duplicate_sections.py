#!/usr/bin/env python3
"""
scripts/repair_duplicate_sections.py — Deterministic repair of duplicate sections (D6).
Merges repeated H2 headings, consolidates multiple FAQ headers into a single block,
and renumbers H2s sequentially on in-scope expanded pages.
Zero LLM calls. Fully lossless and idempotent.

Usage:
  python scripts/repair_duplicate_sections.py --dry-run
  python scripts/repair_duplicate_sections.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from content_quality_gate import (
    count_prose_words,
    has_duplicate_sections,
    merge_duplicate_sections,
    normalize_h2_key,
)

IN_SCOPE_SLUGS = [
    "karzseva.com/budgeting-framework-for-low-income-earners",
    "loankiseva.com/annapurna-scheme-for-food-catering-businesses-equipment",
    "loanraaj.com/21-machines-business",
    "loantau.com/commercial-fleet-insurance-bundling-discounts",
    "rechargekar.com/best-budget-prepaid-plans-for-students",
    "rechargepur.com/best-apps-for-utility-bill-cashback",
    "rechargetak.com/28-day-vs-84-day-recharge-math",
    "tazabhav.com/agricultural-commodity-trading-ncdex",
    "tazaloan.com/boost-cibil-score-from-650-to-750",
    "tazarokda.com/api-banking-for-bulk-payroll-transfers",
]


def inspect_page_headings(html: str) -> tuple[list[str], int, int]:
    soup = BeautifulSoup(html, "html.parser")
    pc = soup.find("div", class_="post-content") or soup.find("article") or soup
    h2s = [re.sub(r"\s+", " ", h.get_text()).strip() for h in pc.find_all("h2")]
    faqs = sum(1 for h in h2s if "frequently asked questions" in normalize_h2_key(h))
    norm_keys = [normalize_h2_key(h) for h in h2s]
    dups = len(norm_keys) - len(set(norm_keys))
    return h2s, faqs, dups


def repair_pages(apply_changes: bool = False) -> int:
    mode = "APPLY" if apply_changes else "DRY RUN"
    print(f"=== REPAIR DUPLICATE SECTIONS ({mode}) ===")
    
    repaired_count = 0
    for slug in IN_SCOPE_SLUGS:
        p = PROJECT_ROOT / "sites" / slug / "index.html"
        if not p.exists():
            print(f"[-] File not found: {p}")
            continue

        raw_html = p.read_text(encoding="utf-8")
        h2s_before, faqs_before, dups_before = inspect_page_headings(raw_html)
        words_before = count_prose_words(raw_html)

        if not has_duplicate_sections(BeautifulSoup(raw_html, "html.parser")) and dups_before == 0 and faqs_before <= 1:
            print(f"[OK] Already clean: {slug} ({words_before} words, {len(h2s_before)} H2s)")
            continue

        merged_html = merge_duplicate_sections(raw_html)
        h2s_after, faqs_after, dups_after = inspect_page_headings(merged_html)
        words_after = count_prose_words(merged_html)

        print(f"\n[{'REPAIRED' if apply_changes else 'FOUND'}] {slug}:")
        print(f"  Prose words: {words_before} -> {words_after} (drop: {words_before - words_after})")
        print(f"  FAQ H2s:     {faqs_before} -> {faqs_after}")
        print(f"  Duplicate H2s: {dups_before} -> {dups_after}")
        print("  Headings before:")
        for h in h2s_before:
            print(f"    - {h}")
        print("  Headings after:")
        for h in h2s_after:
            print(f"    + {h}")

        if apply_changes:
            p.write_text(merged_html, encoding="utf-8")
            repaired_count += 1
        else:
            repaired_count += 1

    print(f"\nTotal pages {'repaired' if apply_changes else 'to repair'}: {repaired_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair duplicate sections in expanded articles.")
    parser.add_argument("--dry-run", action="store_true", help="List pages and headings without modifying files")
    parser.add_argument("--apply", action="store_true", help="Apply changes in-place to files")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        return 1

    return repair_pages(apply_changes=args.apply)


if __name__ == "__main__":
    sys.exit(main())
