#!/usr/bin/env python3
"""
scripts/repair_content_images.py — E1 Defect Repair Tool.

Repairs at-floor articles that had their content images placed outside div.post-content:
1. Identifies existing clean figure blocks on the page.
2. Places 5 figures INSIDE div.post-content after the 2nd, 4th, 6th, 8th, 10th <h2> tags.
3. Removes redundant/stray figures from outside div.post-content.
4. Preserves LF line endings and verifies >= 5 content images inside div.post-content.

Usage:
    python scripts/repair_content_images.py --dry-run
    python scripts/repair_content_images.py --apply
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

from content_quality_gate import ARTICLE_WORD_COUNT_FLOOR, count_prose_words
from scripts.seo_onpage_audit import get_all_article_paths


def get_target_h2_indices(n_h2: int, n_figs: int = 5) -> list[int]:
    """
    Returns 0-based indices of H2s to insert figures after.
    Target: 2nd, 4th, 6th, 8th, 10th H2 (indices 1, 3, 5, 7, 9).
    If fewer than 10 H2s, distribute evenly across available H2s.
    """
    if n_h2 >= 10:
        return [1, 3, 5, 7, 9][:n_figs]
    
    # When n_h2 < 10, spread across available H2s
    indices = [1, 3, 5, 7, n_h2 - 1]
    valid = sorted(list(set(min(i, n_h2 - 1) for i in indices)))
    curr = 1
    while len(valid) < n_figs and curr < n_h2:
        if curr not in valid:
            valid.append(curr)
        curr += 1
    valid.sort()
    return valid[:n_figs]


def repair_article_images(path: Path, apply: bool = False) -> tuple[bool, str]:
    """
    Inspects and optionally repairs content image placement for an article.
    Returns (modified, log_message).
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    prose = count_prose_words(text)
    if prose < ARTICLE_WORD_COUNT_FLOOR:
        return False, "sub-floor"

    soup = BeautifulSoup(text, "html.parser")
    pc = soup.find("div", class_="post-content")
    if not pc:
        return False, "no post-content div"

    pc_imgs = pc.find_all("img")
    if len(pc_imgs) >= 5:
        return False, f"already has {len(pc_imgs)} images inside post-content"

    # Find all figures on the page
    all_figs = soup.find_all("figure")
    if not all_figs:
        return False, "ERROR: no figures found on page"

    # Filter clean figures (avoid old Exhibit alts)
    clean_figs = []
    for f in all_figs:
        img = f.find("img")
        if img:
            alt = img.get("alt", "")
            if "exhibit" not in alt.lower():
                clean_figs.append(f)

    # Fallback to all_figs if clean_figs < 5
    selected_figs = clean_figs[:5] if len(clean_figs) >= 5 else all_figs[:5]
    if len(selected_figs) < 5:
        return False, f"ERROR: only {len(selected_figs)} figures available"

    # Deep copy / extract figures so they can be moved
    extracted_fig_htmls = [str(f) for f in selected_figs]

    # Decompose all old figures on the page
    for f in all_figs:
        f.decompose()

    # Find H2s inside post-content
    h2s = pc.find_all("h2")
    if not h2s:
        return False, "ERROR: no H2s inside post-content"

    target_indices = get_target_h2_indices(len(h2s), len(extracted_fig_htmls))

    # Insert each figure after its target H2
    # To maintain correct order, insert in reverse or sequentially
    for fig_html, h2_idx in zip(extracted_fig_htmls, target_indices):
        target_h2 = h2s[h2_idx]
        new_fig_soup = BeautifulSoup(fig_html, "html.parser").find("figure")
        target_h2.insert_after(new_fig_soup)

    # Verify repair
    new_pc_imgs = pc.find_all("img")
    if len(new_pc_imgs) < 5:
        return False, f"ERROR: after repair, post-content has only {len(new_pc_imgs)} images"

    slug = path.parent.name if path.name == "index.html" else path.stem
    plan_msg = (
        f"{path.parent.parent.name}/{slug}: "
        f"moved 5 figures inside div.post-content after H2s at indices {target_indices} (total H2s: {len(h2s)})"
    )

    if apply:
        # Write out with strictly LF line endings
        updated_html = str(soup)
        # Ensure clean LF line endings
        updated_html = updated_html.replace("\r\n", "\n").replace("\r", "\n")
        path.write_text(updated_html, encoding="utf-8", newline="\n")

    return True, plan_msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair content image placement inside div.post-content.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Inspect and print plan without writing to disk")
    group.add_argument("--apply", action="store_true", help="Apply image repair to affected articles")

    args = parser.parse_args()

    articles = get_all_article_paths()
    repaired = 0
    skipped = 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== REPAIR CONTENT IMAGES [{mode}] ===")

    for p in articles:
        modified, msg = repair_article_images(p, apply=args.apply)
        if modified:
            repaired += 1
            print(f"  [{mode}] {msg}")
        elif msg not in ("sub-floor",):
            skipped += 1

    print("=" * 60)
    print(f"Total articles checked: {len(articles)}")
    print(f"Articles targeted/repaired: {repaired}")
    print(f"Articles already compliant/skipped: {len(articles) - repaired}")
    print("=" * 60)

    if args.dry_run:
        print("Dry run completed. Run with --apply to write changes.")
    else:
        print(f"Successfully applied repair to {repaired} articles.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
