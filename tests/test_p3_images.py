from __future__ import annotations

import re
from pathlib import Path
from bs4 import BeautifulSoup
from content_quality_gate import is_redirect_stub

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


def _get_article_pages(base: Path) -> list[Path]:
    pages = []
    for p in base.glob("*/*/index.html"):
        rel = p.relative_to(base)
        if len(rel.parts) != 3:
            continue
        if any(x in rel.parts for x in ("layouts", "_default", "category")):
            continue
        slug = rel.parts[1]
        if slug in STATIC_SLUGS:
            continue
        try:
            head_snippet = p.read_text(encoding="utf-8", errors="ignore")[:600]
            if is_redirect_stub(head_snippet):
                continue
        except Exception:
            pass
        pages.append(p)
    return sorted(pages)


def _extract_content_images(soup: BeautifulSoup):
    for tag in soup.find_all(["aside", "nav", "header", "footer"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r"widget|sidebar|author-card")):
        tag.decompose()

    content = soup.find("div", class_="post-content") or soup.find("article") or soup.find("main")
    if not content:
        return []
    return content.find_all("img")


def test_zero_image_articles_is_zero():
    base = Path("sites")
    article_pages = _get_article_pages(base)
    assert len(article_pages) > 0, "No article pages found"

    zero_image_articles = []
    lt5_image_articles = []
    bad_alts = []

    TEMPLATE_PREFIXES = (
        "visual overview of",
        "practical implementation and",
        "comparative analysis and",
        "step-by-step documentation",
        "financial considerations,",
    )

    seen_corpus_alts: dict[str, str] = {}

    for p in article_pages:
        text = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")

        title_tag = soup.find("title") or soup.find("h1")
        title_text = title_tag.get_text().strip().lower() if title_tag else ""

        content_imgs = _extract_content_images(soup)
        if len(content_imgs) == 0:
            zero_image_articles.append(str(p))
        elif len(content_imgs) < 5:
            lt5_image_articles.append((str(p), len(content_imgs)))

        for img in content_imgs:
            alt = img.get("alt", "").strip()
            alt_clean = re.sub(r"\s+", " ", alt).strip()
            alt_lower = alt_clean.lower()

            if not alt_clean:
                bad_alts.append((str(p), "empty alt"))
            elif "exhibit" in alt_lower:
                bad_alts.append((str(p), f"Exhibit N alt: {alt}"))
            elif alt_lower == title_text:
                bad_alts.append((str(p), f"Alt equals title: {alt}"))
            elif any(alt_lower.startswith(pref) for pref in TEMPLATE_PREFIXES):
                bad_alts.append((str(p), f"Template prefix alt: {alt}"))
            elif alt_lower in seen_corpus_alts:
                bad_alts.append((str(p), f"Duplicate alt across corpus (already on {seen_corpus_alts[alt_lower]}): {alt}"))
            else:
                seen_corpus_alts[alt_lower] = str(p)

            # (c) Fail if alt contains verbatim 8+ word substring of title
            title_words = re.sub(r"[^\w\s]", " ", title_text).split()
            if len(title_words) >= 8:
                alt_words_str = re.sub(r"[^\w\s]", " ", alt_lower)
                for i in range(len(title_words) - 7):
                    sub = " ".join(title_words[i : i + 8])
                    if sub in alt_words_str:
                        bad_alts.append((str(p), f"Verbatim 8+ word title substring in alt: '{sub}' in '{alt}'"))
                        break

    assert len(zero_image_articles) == 0, f"Found {len(zero_image_articles)} zero-image articles: {zero_image_articles[:5]}"
    assert len(lt5_image_articles) == 0, f"Found {len(lt5_image_articles)} articles with <5 images: {lt5_image_articles[:5]}"
    assert len(bad_alts) == 0, f"Found {len(bad_alts)} bad image alts: {bad_alts[:5]}"


def test_no_external_hotlinked_images_in_sites():
    base = Path("sites")
    external_domains_pattern = re.compile(
        r'src=["\']https?://(?:images\.unsplash\.com|bazartak\.(?:net|in)|kamtak\.in)',
        re.IGNORECASE,
    )

    violating_files = []
    for p in base.glob("**/*.html"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if external_domains_pattern.search(text):
            violating_files.append(str(p))

    assert len(violating_files) == 0, f"Found files with external hotlinked images: {violating_files}"


def test_all_content_images_self_hosted_and_exist():
    base = Path("sites")
    missing_images = []
    article_pages = _get_article_pages(base)

    for p in article_pages:
        domain_dir = p.parent.parent
        text = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        content_imgs = _extract_content_images(soup)

        for img in content_imgs:
            src = img.get("src", "")
            if not src.startswith("/img/"):
                missing_images.append((str(p), f"Non-self-hosted content image src: {src}"))
                continue
            local_path = domain_dir / src.lstrip("/")
            if not local_path.exists():
                missing_images.append((str(p), f"Missing disk file: {src}"))

    assert len(missing_images) == 0, f"Missing local image files on disk: {missing_images[:5]}"
