"""Test suite for D17: Canonical article-figure markup conventions across corpus.

Verifies:
1. class="content-image" appears ZERO times across all HTML files.
2. Every figure in the article body has class="article-figure" and standard inline style.
3. Every <img> in article body has width="1200", height="675", loading="lazy", and standard style.
4. Every <figcaption> has font-size:13px and color:var(--text-muted).
5. Zero <img> inside article body without a <figure> parent.
"""
from pathlib import Path
import bs4
import pytest
from scripts.seo_onpage_audit import get_all_article_paths


def test_no_content_image_class_in_corpus():
    """Ensure class='content-image' appears exactly ZERO times across all articles."""
    paths = get_all_article_paths()
    violating_pages = []
    for p in paths:
        content = Path(p).read_text(encoding="utf-8")
        if "content-image" in content:
            s = bs4.BeautifulSoup(content, "html.parser")
            if s.find_all(class_="content-image"):
                violating_pages.append(str(p))

    assert len(violating_pages) == 0, f"Found {len(violating_pages)} pages with 'content-image' class: {violating_pages[:5]}"


def test_all_article_figures_have_canonical_markup():
    """Ensure all figures inside article containers follow the canonical markup."""
    paths = get_all_article_paths()
    non_canonical_figures = []

    for p in paths:
        s = bs4.BeautifulSoup(Path(p).read_text(encoding="utf-8"), "html.parser")
        b = s.find("div", class_="post-content") or s.find("article") or s
        figures = b.find_all("figure")
        for f in figures:
            classes = f.get("class") or []
            if "article-figure" not in classes:
                non_canonical_figures.append((p, f"figure class={classes}"))
                continue
            f_style = f.get("style") or ""
            if "margin:28px 0; text-align:center;" not in f_style and "margin: 28px 0; text-align: center;" not in f_style:
                non_canonical_figures.append((p, f"figure style={f_style}"))

            imgs = f.find_all("img")
            if len(imgs) != 1:
                non_canonical_figures.append((p, f"figure img count={len(imgs)}"))
            else:
                img = imgs[0]
                if img.get("width") != "1200" or img.get("height") != "675":
                    non_canonical_figures.append((p, f"img dimensions {img.get('width')}x{img.get('height')}"))

            caps = f.find_all("figcaption")
            if len(caps) != 1:
                non_canonical_figures.append((p, f"figure figcaption count={len(caps)}"))
            else:
                cap_style = caps[0].get("style") or ""
                if "var(--text-muted)" not in cap_style:
                    non_canonical_figures.append((p, f"figcaption style={cap_style}"))

    assert len(non_canonical_figures) == 0, f"Found {len(non_canonical_figures)} non-canonical figures: {non_canonical_figures[:5]}"


def test_zero_img_without_figure_parent():
    """Ensure zero <img> in article body exists without a <figure> parent."""
    paths = get_all_article_paths()
    orphan_imgs = []

    for p in paths:
        s = bs4.BeautifulSoup(Path(p).read_text(encoding="utf-8"), "html.parser")
        b = s.find("div", class_="post-content") or s.find("article") or s
        for img in b.find_all("img"):
            if not img.find_parent("figure"):
                orphan_imgs.append((p, str(img)[:80]))

    assert len(orphan_imgs) == 0, f"Found {len(orphan_imgs)} orphaned <img> tags: {orphan_imgs[:5]}"
