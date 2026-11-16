"""Remediate D17 figures to canonical article-figure markup (Gap C).

Transforms:
1. Stray figures inside div.post-content (228 figures / 155 pages)
2. Figures inside article.post-box outside div.post-content (24 figures / 6 pages)
3. Captions hard-coding color:#6b7280 -> var(--text-muted) (7 captions / 3 pages)

Validates all 5 mandatory proofs:
1. Zero text drift (tags and attributes stripped, old vs new identical)
2. Only allowed attributes moved (src, alt, caption text, figure count, img count unchanged)
3. On every page len(figure.article-figure) == len(img)
4. Zero <img> in article body without <figure> parent
5. class="content-image appears ZERO times corpus-wide
"""
import argparse
import re
import sys
from pathlib import Path
import bs4

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.seo_onpage_audit import get_all_article_paths


import html


def strip_tags(raw_html: str) -> str:
    """Strip all HTML tags and normalize whitespace and HTML entities."""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    unescaped = html.unescape(text)
    return " ".join(unescaped.split())


def transform_figures(soup: bs4.BeautifulSoup, path_str: str) -> tuple[int, int]:
    """Transform content-image figures and #6b7280 captions on a page."""
    figs_transformed = 0
    caps_transformed = 0

    # Volume 1 & Volume 2: content-image figures
    figs = soup.find_all("figure")
    for f in figs:
        classes = f.get("class") or []
        if "content-image" in classes:
            # Safety assertions
            in_pc = bool(f.find_parent("div", class_="post-content"))
            in_art = bool(f.find_parent("article"))
            if not (in_pc or in_art):
                raise ValueError(f"Figure in {path_str} is neither in div.post-content nor article!")

            if f.get("style"):
                raise ValueError(f"Figure in {path_str} is already styled: {f.get('style')}")

            imgs = f.find_all("img")
            caps = f.find_all("figcaption")
            if len(imgs) != 1:
                raise ValueError(f"Figure in {path_str} has {len(imgs)} imgs, expected 1")
            if len(caps) != 1:
                raise ValueError(f"Figure in {path_str} has {len(caps)} figcaptions, expected 1")

            img = imgs[0]
            if not img.get("src"):
                raise ValueError(f"Img in {path_str} missing src")
            if not img.get("alt"):
                raise ValueError(f"Img in {path_str} missing alt")

            # Canonical transforms
            f["class"] = ["article-figure"]
            f["style"] = "margin:28px 0; text-align:center;"

            img["width"] = "1200"
            img["height"] = "675"
            img["loading"] = "lazy"
            img["style"] = "width:100%; height:auto; border-radius:8px;"
            if "class" in img.attrs:
                del img["class"]

            fc = caps[0]
            fc["style"] = "font-size:13px; color:var(--text-muted); margin-top:8px;"
            if "class" in fc.attrs:
                del fc["class"]

            figs_transformed += 1

    # Volume 3: #6b7280 captions
    for fc in soup.find_all("figcaption"):
        st = fc.get("style") or ""
        if "#6b7280" in st:
            fc["style"] = st.replace("#6b7280", "var(--text-muted)")
            caps_transformed += 1

    return figs_transformed, caps_transformed


def main():
    parser = argparse.ArgumentParser(description="Remediate D17 figures")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes to disk")
    args = parser.parse_args()

    paths = get_all_article_paths()
    total_figs_transformed = 0
    total_caps_transformed = 0
    pages_modified = []

    attr_changes = {
        "figure.class": 0,
        "figure.style": 0,
        "img.width": 0,
        "img.height": 0,
        "img.style": 0,
        "img.loading": 0,
        "img.class_removed": 0,
        "figcaption.style": 0,
        "figcaption.class_removed": 0,
        "img.src_moved": 0,
        "img.alt_moved": 0,
        "caption_text_moved": 0,
        "figure_count_moved": 0,
        "img_count_moved": 0,
    }

    print(f"Scanning {len(paths)} articles for D17 figure transformation...")

    for p in paths:
        p_obj = Path(p)
        old_html = p_obj.read_text(encoding="utf-8")
        soup = bs4.BeautifulSoup(old_html, "html.parser")

        # Snapshot before transform for Proofs 1 & 2
        old_figs = soup.find_all("figure")
        old_imgs = soup.find_all("img")
        old_srcs = [img.get("src") for img in old_imgs]
        old_alts = [img.get("alt") for img in old_imgs]
        old_cap_texts = [fc.get_text().strip() for fc in soup.find_all("figcaption")]

        figs_tf, caps_tf = transform_figures(soup, str(p))
        if figs_tf > 0 or caps_tf > 0:
            new_html = str(soup)

            # PROOF 1: Zero text drift
            old_text = strip_tags(old_html)
            new_text = strip_tags(new_html)
            if old_text != new_text:
                raise AssertionError(f"Proof 1 FAILED: Text drift detected in {p_obj}!")

            # PROOF 2: Attribute invariants
            new_figs = soup.find_all("figure")
            new_imgs = soup.find_all("img")
            new_srcs = [img.get("src") for img in new_imgs]
            new_alts = [img.get("alt") for img in new_imgs]
            new_cap_texts = [fc.get_text().strip() for fc in soup.find_all("figcaption")]

            if len(new_figs) != len(old_figs):
                attr_changes["figure_count_moved"] += 1
            if len(new_imgs) != len(old_imgs):
                attr_changes["img_count_moved"] += 1
            if new_srcs != old_srcs:
                attr_changes["img.src_moved"] += 1
            if new_alts != old_alts:
                attr_changes["img.alt_moved"] += 1
            if new_cap_texts != old_cap_texts:
                attr_changes["caption_text_moved"] += 1

            attr_changes["figure.class"] += figs_tf
            attr_changes["figure.style"] += figs_tf
            attr_changes["img.width"] += figs_tf
            attr_changes["img.height"] += figs_tf
            attr_changes["img.style"] += figs_tf
            attr_changes["img.loading"] += figs_tf
            attr_changes["img.class_removed"] += figs_tf
            attr_changes["figcaption.style"] += figs_tf + caps_tf
            attr_changes["figcaption.class_removed"] += figs_tf

            total_figs_transformed += figs_tf
            total_caps_transformed += caps_tf
            pages_modified.append(p_obj)

            if not args.dry_run:
                p_obj.write_text(new_html, encoding="utf-8", newline="\n")

    print(f"\n--- PROOF 1 (Zero Text Drift) ---")
    print(f"PASSED: Text drift == 0 across all {len(pages_modified)} modified pages.")

    print(f"\n--- PROOF 2 (Attribute Verification) ---")
    for k, v in attr_changes.items():
        print(f"  {k:25}: {v}")
    assert attr_changes["img.src_moved"] == 0, "Proof 2 FAILED: img.src moved!"
    assert attr_changes["img.alt_moved"] == 0, "Proof 2 FAILED: img.alt moved!"
    assert attr_changes["caption_text_moved"] == 0, "Proof 2 FAILED: caption text moved!"
    assert attr_changes["figure_count_moved"] == 0, "Proof 2 FAILED: figure count moved!"
    assert attr_changes["img_count_moved"] == 0, "Proof 2 FAILED: img count moved!"
    print("PASSED: Only permitted attributes moved; 0 content/media attributes moved.")

    # PROOF 3 & 4: Global Invariants
    proof3_failures = []
    proof4_failures = []
    for p in paths:
        p_obj = Path(p)
        content = p_obj.read_text(encoding="utf-8")
        s = bs4.BeautifulSoup(content, "html.parser")
        b = s.find("div", class_="post-content") or s.find("article") or s
        b_imgs = b.find_all("img")
        af_figs = b.find_all("figure", class_="article-figure")

        if len(af_figs) != len(b_imgs):
            proof3_failures.append((p, len(af_figs), len(b_imgs)))

        for img in b_imgs:
            if not img.find_parent("figure"):
                proof4_failures.append((p, str(img)))

    print(f"\n--- PROOF 3 (len(figure.article-figure) == len(img)) ---")
    if proof3_failures:
        print(f"FAILED on {len(proof3_failures)} pages: {proof3_failures[:3]}")
    else:
        print("PASSED: len(figure.article-figure) == len(img) on 100% of pages.")

    print(f"\n--- PROOF 4 (Zero <img> without <figure> parent) ---")
    if proof4_failures:
        print(f"FAILED on {len(proof4_failures)} imgs")
    else:
        print("PASSED: Zero <img> without <figure> parent in article body.")

    # PROOF 5: Corpus-wide class="content-image count
    content_image_count = 0
    for p in paths:
        txt = Path(p).read_text(encoding="utf-8")
        if 'class="content-image' in txt or "class='content-image" in txt or "content-image" in txt:
            s = bs4.BeautifulSoup(txt, "html.parser")
            if s.find_all(class_="content-image"):
                content_image_count += len(s.find_all(class_="content-image"))

    print(f"\n--- PROOF 5 (Corpus-wide content-image count) ---")
    print(f"content-image class instances remaining: {content_image_count}")

    print(f"\nSummary:")
    print(f"  Pages modified: {len(pages_modified)}")
    print(f"  Figures transformed: {total_figs_transformed} (Volume 1 + Volume 2)")
    print(f"  Captions updated: {total_caps_transformed} (Volume 3)")


if __name__ == "__main__":
    main()
