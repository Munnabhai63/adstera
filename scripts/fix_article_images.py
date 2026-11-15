#!/usr/bin/env python3
"""
scripts/fix_article_images.py — Distribute self-hosted images & fix alt text across articles

Ensures every article has >= 5 content images inside div.post-content,
and every content image has descriptive alt text (no 'Exhibit N', no article title repeats).
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent

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


def get_all_articles(sites_dir: Path | None = None) -> list[Path]:
    root = sites_dir or (PROJECT_ROOT / "sites")
    articles: list[Path] = []
    for p in root.rglob("*.html"):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if any(x in rel.parts for x in ("layouts", "_default", "category")):
            continue
        if p.name.startswith("google") and p.name.endswith(".html"):
            continue
        if len(rel.parts) <= 2 and p.name == "index.html":
            continue
        slug = p.parent.name if p.name == "index.html" else p.stem
        if slug in STATIC_SLUGS:
            continue
        try:
            head_snippet = p.read_text(encoding="utf-8", errors="ignore")[:600].lower()
            if 'http-equiv="refresh"' in head_snippet or "<title>moved</title>" in head_snippet:
                continue
        except Exception:
            pass
        articles.append(p)
    return sorted(articles)


def fix_images_in_article(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    domain = path.resolve().relative_to(PROJECT_ROOT / "sites").parts[0]
    local_img_dir = PROJECT_ROOT / "sites" / domain / "img"
    available_imgs = sorted([f.name for f in local_img_dir.glob("*.webp")])
    if not available_imgs:
        return False

    slug = path.parent.name if path.name == "index.html" else path.stem
    h1_el = soup.find("h1")
    article_title = h1_el.get_text().strip() if h1_el else slug.replace("-", " ").title()

    post_content = soup.find("div", class_="post-content")
    if not post_content:
        # Check if there's an article tag
        post_content = soup.find("article")
    if not post_content:
        return False

    modified = False

    # 1. Clean existing content image alt texts (remove Exhibit N and title copies)
    for img in post_content.find_all("img"):
        src = img.get("src", "")
        if "logo" in src.lower() or "badge" in src.lower():
            continue
        alt = img.get("alt", "").strip()
        if "exhibit" in alt.lower() or alt == article_title or not alt or "\n" in alt or len(alt) > 90 or "within sections" in alt.lower():
            # find preceding h2
            prev_h2 = img.find_previous("h2")
            h2_text = prev_h2.get_text().strip() if prev_h2 else ""
            h2_text = re.sub(r"^\d+\.\s*", "", h2_text).strip()
            if h2_text and 8 <= len(h2_text) <= 50 and "\n" not in h2_text:
                new_alt = f"{h2_text} - Structural Evaluation and Details"
            else:
                new_alt = f"{article_title} - Analytical Overview and Benchmarks"
            img["alt"] = new_alt
            modified = True

    # 2. Check content image count
    # Move or remove any figure mistakenly inside nav or toc
    for fig in post_content.find_all("figure"):
        if fig.find_parent(["nav", "aside", "header", "footer"]) or fig.find_parent(class_=re.compile(r"toc|widget|sidebar")):
            fig.decompose()
            modified = True

    content_imgs = [
        img for img in post_content.find_all("img")
        if "logo" not in img.get("src", "").lower() and "badge" not in img.get("src", "").lower()
        and not img.find_parent(["nav", "aside", "header", "footer"])
        and not img.find_parent(class_=re.compile(r"toc|widget|sidebar|author-card"))
    ]

    needed = 5 - len(content_imgs)
    if needed > 0:
        h = int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16)
        candidates = post_content.find_all(["p", "div", "table", "h2", "ul"])
        inserted = 0

        for i, el in enumerate(candidates):
            if inserted >= needed:
                break
            if el.name == "figure" or el.find_parent("figure"):
                continue
            if el.find_parent(["nav", "aside", "header", "footer"]) or el.find_parent(class_=re.compile(r"toc|widget|sidebar|author-card")):
                continue
            next_sib = el.find_next_sibling()
            if next_sib and next_sib.name == "figure":
                continue
            prev_sib = el.find_previous_sibling()
            if prev_sib and prev_sib.name == "figure":
                continue

            fig_fn = available_imgs[(h + (i + 1) * 7) % len(available_imgs)]
            fig_alt = f"{article_title} - Section Analysis & Documentation"

            fig_soup = BeautifulSoup(
                f'\n<figure class="article-figure" style="margin:28px 0; text-align:center;">\n'
                f'    <img src="/img/{fig_fn}" alt="{html.escape(fig_alt)}" loading="lazy" width="1200" height="675" style="width:100%; height:auto; border-radius:8px;">\n'
                f'    <figcaption style="font-size:13px; color:var(--text-muted); margin-top:8px;">Detailed analysis and documentation breakdown for {html.escape(article_title)}.</figcaption>\n'
                f'</figure>\n',
                "html.parser",
            )
            el.insert_after(fig_soup)
            inserted += 1
            modified = True

    if modified:
        path.write_text(str(soup), encoding="utf-8")
        return True
    return False


def main():
    articles = get_all_articles()
    print(f"Auditing and updating images across {len(articles)} articles...")
    updated = 0
    for p in articles:
        if fix_images_in_article(p):
            updated += 1
    print(f"Updated {updated} articles with self-hosted content images and clean alt text.")


if __name__ == "__main__":
    main()
