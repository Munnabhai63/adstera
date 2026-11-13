from __future__ import annotations

import re
from pathlib import Path


def test_zero_image_articles_is_zero():
    base = Path("sites")
    img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

    article_pages = list(base.glob("*/*/index.html"))
    assert len(article_pages) > 0, "No article pages found"

    zero_image_articles = []
    lt5_image_articles = []

    for p in article_pages:
        text = p.read_text(encoding="utf-8", errors="ignore")
        content_imgs = [
            i for i in img_pattern.findall(text)
            if "logo" not in i.lower() and "badge" not in i.lower()
        ]
        if len(content_imgs) == 0:
            zero_image_articles.append(str(p))
        elif len(content_imgs) < 5:
            lt5_image_articles.append((str(p), len(content_imgs)))

    assert len(zero_image_articles) == 0, f"Found {len(zero_image_articles)} zero-image articles"
    assert len(lt5_image_articles) == 0, f"Found {len(lt5_image_articles)} articles with <5 images: {lt5_image_articles[:5]}"


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
    img_pattern = re.compile(r'<img[^>]+src=["\'](/img/[^"\']+)["\']', re.IGNORECASE)

    missing_images = []
    for p in base.glob("*/*/index.html"):
        domain_dir = p.parent.parent
        text = p.read_text(encoding="utf-8", errors="ignore")
        for img_rel in img_pattern.findall(text):
            local_path = domain_dir / img_rel.lstrip("/")
            if not local_path.exists():
                missing_images.append((str(p), img_rel))

    assert len(missing_images) == 0, f"Missing local image files on disk: {missing_images[:5]}"
