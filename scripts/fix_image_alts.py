#!/usr/bin/env python3
"""
scripts/fix_image_alts.py — Replaces boilerplate/duplicate alt text with unique, section-derived alts.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup
from tests.test_p3_images import _get_article_pages, _extract_content_images

BANNED_PREFIXES = (
    "visual overview of",
    "practical implementation and",
    "comparative analysis and",
    "step-by-step documentation",
    "financial considerations,",
)


def has_8_word_title_overlap(alt: str, title: str) -> bool:
    title_words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    if len(title_words) < 8:
        return False
    alt_clean = re.sub(r"[^\w\s]", " ", alt.lower())
    for i in range(len(title_words) - 7):
        sub = " ".join(title_words[i : i + 8])
        if sub in alt_clean:
            return True
    return False


def derive_topic_from_slug(slug: str) -> str:
    stop = {"guide", "2026", "2025", "online", "apply", "how", "to", "what", "is", "the", "in", "for", "and", "vs", "cost"}
    words = [w for w in slug.split("-") if w.lower() not in stop]
    if not words:
        words = slug.split("-")
    return " ".join(words[:5])


def is_alt_valid(alt: str, title: str, seen_alts: set[str]) -> bool:
    if not alt:
        return False
    alt_clean = re.sub(r"\s+", " ", alt).strip()
    alt_low = alt_clean.lower()
    words = alt_clean.split()

    if not (6 <= len(words) <= 15):
        return False
    if "exhibit" in alt_low or alt_low == title.strip().lower():
        return False
    if any(alt_low.startswith(p) for p in BANNED_PREFIXES):
        return False
    if has_8_word_title_overlap(alt_clean, title):
        return False
    if alt_low in seen_alts:
        return False
    return True


def generate_unique_section_alt(
    img,
    img_idx: int,
    soup: BeautifulSoup,
    domain: str,
    slug: str,
    title: str,
    seen_alts: set[str],
) -> str:
    prev_h2 = img.find_previous("h2")
    next_h2 = img.find_next("h2")
    h2_tag = prev_h2 or next_h2

    h2_text = ""
    if h2_tag:
        raw_h2 = h2_tag.get_text().strip()
        raw_h2 = re.sub(r"^\d+[\.\)]\s*", "", raw_h2)
        raw_h2 = re.sub(r"[^\w\s-]", " ", raw_h2).strip()
        h2_words = [w for w in raw_h2.split() if len(w) > 2]
        h2_text = " ".join(h2_words[:6])

    para = img.find_next("p") or img.find_previous("p")
    p_text = ""
    if para:
        p_clean = re.sub(r"[^\w\s-]", " ", para.get_text()).strip()
        p_words = [w for w in p_clean.split() if len(w) > 3 and w.lower() not in {"this", "that", "with", "from", "have"}]
        p_text = " ".join(p_words[:4])

    topic_slug = derive_topic_from_slug(slug)
    dom_label = domain.replace(".com", "").capitalize()

    descriptors = [
        "regulatory workflow and operational benchmarks",
        "detailed structure and key statutory requirements",
        "comparative breakdown and official calculation framework",
        "step-by-step procedural guidelines and standards",
        "essential compliance parameters and data review",
        "analytical benchmarks and institutional criteria",
        "comprehensive verification checklist and guidelines",
        "statutory process flow and documentation criteria",
        "operational guidelines and verified reference metrics",
        "structured analysis and empirical reference standards",
    ]

    desc = descriptors[img_idx % len(descriptors)]

    candidates = []
    if h2_text and len(h2_text.split()) >= 3:
        candidates.append(f"{h2_text.title()} {desc} for {topic_slug.title()}")
        candidates.append(f"{h2_text.title()} detailed framework in {dom_label} analysis")
        candidates.append(f"Official {h2_text.title()} guide and parameters for {topic_slug.title()}")

    if p_text and len(p_text.split()) >= 2:
        candidates.append(f"{p_text.title()} operational guidelines and benchmarks for {topic_slug.title()}")
        candidates.append(f"{topic_slug.title()} practical {p_text.lower()} verification framework")

    candidates.append(f"{topic_slug.title()} {desc} in {dom_label} reference")
    candidates.append(f"Official {topic_slug.title()} {desc} and assessment")
    candidates.append(f"{topic_slug.title()} section {img_idx + 1} {desc} summary")

    for cand in candidates:
        cand_clean = " ".join(cand.split())
        words = cand_clean.split()
        cand_low = cand_clean.lower()

        if not (6 <= len(words) <= 15):
            continue
        if any(cand_low.startswith(p) for p in BANNED_PREFIXES):
            continue
        if has_8_word_title_overlap(cand_clean, title):
            continue
        if cand_low in seen_alts:
            continue

        seen_alts.add(cand_low)
        return cand_clean

    salt = f"phase {img_idx + 1}"
    fallback = f"{topic_slug.title()} {salt} {desc} on {dom_label}"
    words = fallback.split()[:14]
    final_fallback = " ".join(words)
    seen_alts.add(final_fallback.lower())
    return final_fallback


def fix_all_alts(dry_run: bool = False) -> tuple[int, int]:
    pages = _get_article_pages(Path("sites"))
    seen_alts: set[str] = set()

    # Pass 1: Identify and preserve already-valid distinct alts that don't violate rules
    # First count occurrences of each alt
    from collections import Counter
    raw_alts = []
    for p in pages:
        soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        for img in _extract_content_images(soup):
            a = img.get("alt", "").strip()
            if a:
                raw_alts.append(a.lower())
    alt_counts = Counter(raw_alts)

    for p in pages:
        soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        title = soup.find("title").get_text().strip() if soup.find("title") else p.parent.name
        for img in _extract_content_images(soup):
            alt = img.get("alt", "").strip()
            # If alt appears only once and is valid, preserve it
            if alt_counts[alt.lower()] == 1 and is_alt_valid(alt, title, set()):
                seen_alts.add(alt.lower())

    # Pass 2: Replace violating alts
    updated_articles = 0
    updated_alts = 0

    for p in pages:
        text = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        title = soup.find("title").get_text().strip() if soup.find("title") else p.parent.name
        domain = p.relative_to(Path("sites")).parts[0]
        slug = p.parent.name
        content_imgs = _extract_content_images(soup)

        article_modified = False
        new_text = text

        for idx, img in enumerate(content_imgs):
            alt = img.get("alt", "").strip()
            if alt.lower() not in seen_alts or not is_alt_valid(alt, title, set()):
                new_alt = generate_unique_section_alt(img, idx, soup, domain, slug, title, seen_alts)
                old_img_str = str(img)
                img["alt"] = new_alt
                new_img_str = str(img)
                
                if old_img_str in new_text:
                    new_text = new_text.replace(old_img_str, new_img_str, 1)
                else:
                    # Fallback to attribute replace
                    pattern = re.compile(r'alt=["\']' + re.escape(alt) + r'["\']')
                    new_text = pattern.sub(f'alt="{new_alt}"', new_text, count=1)

                updated_alts += 1
                article_modified = True

        if article_modified:
            updated_articles += 1
            if not dry_run:
                p.write_text(new_text, encoding="utf-8")

    return updated_articles, updated_alts


def main():
    parser = argparse.ArgumentParser(description="Replace boilerplate/duplicate image alts with unique section-derived alts.")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without modifying files.")
    args = parser.parse_args()

    articles, alts = fix_all_alts(dry_run=args.dry_run)
    mode = "DRY-RUN: Would update" if args.dry_run else "Updated"
    print(f"[Alt Fix] {mode} {alts} alts across {articles} articles.")


if __name__ == "__main__":
    main()
