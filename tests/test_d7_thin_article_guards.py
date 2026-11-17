from __future__ import annotations

import re
from pathlib import Path
from bs4 import BeautifulSoup

STATIC_SLUGS = {
    "about-us",
    "contact-us",
    "privacy-policy",
    "terms-and-conditions",
    "disclaimer",
    "calculator",
    "emi-calculator",
    "gold-calculator",
    "fd-calculator",
    "sip-calculator",
}


def test_no_ads_or_article_schema_on_thin_pages():
    """
    D7 Invariant: Any article page with prose content < 300 words MUST NOT
    render ad slots ('adsterra' or 'container-') or Article/FAQPage JSON-LD schema.
    """
    sites_dir = Path("sites")
    violating_pages = []

    for html_file in sorted(sites_dir.glob("*/*/index.html")):
        slug = html_file.parent.name
        if slug in STATIC_SLUGS:
            continue

        raw = html_file.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")

        # Decompose non-content semantic elements
        for tag in soup.find_all(["aside", "nav", "header", "footer"]):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile(r"widget|sidebar|author-card|eeat")):
            tag.decompose()

        content = (
            soup.find("div", class_="post-body")
            or soup.find("div", class_="post-content")
            or soup.find("article")
        )
        text = content.get_text().strip() if content else ""
        words = len(text.split())

        if words < 300:
            has_adsterra = bool(re.search(r"adsterra|container-[a-f0-9]", raw, re.I))
            has_article_schema = bool(re.search(r'"@type"\s*:\s*"Article"', raw))
            has_faq_schema = bool(re.search(r'"@type"\s*:\s*"FAQPage"', raw))

            if has_adsterra or has_article_schema or has_faq_schema:
                violating_pages.append(
                    f"{html_file.parent.parent.name}/{slug} (words={words}, ads={has_adsterra}, article={has_article_schema}, faq={has_faq_schema})"
                )

    assert len(violating_pages) == 0, (
        f"Found {len(violating_pages)} thin articles (<300 words) with ads or Article/FAQPage schema:\n"
        + "\n".join(violating_pages)
    )
