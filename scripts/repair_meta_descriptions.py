"""
Phase 3 P3-5: Repair broken meta descriptions across all 10 sites.
Scans all HTML files in sites/, detects descriptions with '...', '{', 'page-link',
or length < 60 or > 160, and regenerates them from the first <p> of the article clamped to 155 characters.
"""
from __future__ import annotations

import html
import re
from pathlib import Path


def valid_description(d: str | None) -> bool:
    """Validate meta description according to SEO standards (60-160 chars, no placeholders, no ellipsis)."""
    if not d or not isinstance(d, str):
        return False
    clean = d.strip()
    if (
        "..." in clean
        or "{" in clean
        or "}" in clean
        or "page-link" in clean
        or "Need to include" in clean
        or clean.startswith(", ,")
    ):
        return False
    if len(clean) < 60 or len(clean) > 160:
        return False
    return True


def clean_text_from_html(html_fragment: str) -> str:
    """Strip HTML tags and unescape entities to get clean prose."""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_fallback_description(content: str) -> str:
    """Extract clean description from first substantial paragraph or title."""
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, flags=re.DOTALL | re.IGNORECASE)
    h1_title = clean_text_from_html(h1_match.group(1)) if h1_match else "Complete Guide"

    # Look for paragraph inside article or main that does not contain prompt garbage
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", content, flags=re.DOTALL | re.IGNORECASE)
    candidate = ""
    for p in paragraphs:
        cleaned = clean_text_from_html(p)
        # Skip garbage, prompt leaks, copyrights, disclaimers
        if (
            len(cleaned) >= 50
            and not cleaned.startswith("©")
            and "disclaimer" not in cleaned.lower()
            and "..." not in cleaned
            and "{" not in cleaned
            and "}" not in cleaned
            and "page-link" not in cleaned
            and "table (" not in cleaned
            and "unordered bullet" not in cleaned
            and "Need to include" not in cleaned
            and not cleaned.startswith(")")
            and not cleaned.startswith(".")
            and not cleaned.startswith(",")
        ):
            candidate = cleaned
            break

    if not candidate:
        # Fallback to h1 + context
        candidate = f"Complete guide on {h1_title}: compare updated rates, eligibility criteria, and step-by-step procedures."

    # Clamp to 155 chars at word boundary without ellipsis
    if len(candidate) > 155:
        candidate = candidate[:155].rsplit(" ", 1)[0]
    if len(candidate) < 60:
        candidate = f"{candidate} Updated benchmarks, eligibility criteria, and step-by-step guide."
        if len(candidate) > 155:
            candidate = candidate[:155].rsplit(" ", 1)[0]

    # Final guarantee
    if "..." in candidate or "{" in candidate or len(candidate) < 60 or len(candidate) > 160:
        candidate = f"Comprehensive analysis of {h1_title[:50]}: verified statutory rates, benchmarks, and step-by-step processes."
        if len(candidate) > 155:
            candidate = candidate[:155].rsplit(" ", 1)[0]

    return candidate


def repair_meta_descriptions(sites_dir: str = "sites") -> dict[str, int]:
    base = Path(sites_dir)
    stats = {
        "scanned": 0,
        "repaired": 0,
        "already_valid": 0,
        "missing_tag": 0,
    }

    # Match meta description tags in both attribute orders:
    # <meta name="description" content="..."> or <meta content="..." name="description">
    desc_pattern1 = re.compile(
        r'(<meta\s+name=["\']description["\']\s+content=["\'])(.*?)(["\'])',
        re.IGNORECASE | re.DOTALL,
    )
    desc_pattern2 = re.compile(
        r'(<meta\s+content=["\'])(.*?)(["\']\s+name=["\']description["\'])',
        re.IGNORECASE | re.DOTALL,
    )

    for html_file in base.glob("**/*.html"):
        stats["scanned"] += 1
        text = html_file.read_text(encoding="utf-8", errors="ignore")

        m1 = desc_pattern1.search(text)
        m2 = desc_pattern2.search(text)

        if not m1 and not m2:
            stats["missing_tag"] += 1
            continue

        raw_desc = m1.group(2) if m1 else m2.group(2)
        unescaped_desc = html.unescape(raw_desc).strip()

        # Check both raw and unescaped to ensure both are valid
        raw_valid = valid_description(raw_desc)
        unesc_valid = valid_description(unescaped_desc)
        if raw_valid and unesc_valid:
            stats["already_valid"] += 1
            continue

        # If unesc_valid is True but raw was too long due to HTML entities, shorten unescaped
        if unesc_valid:
            new_desc = unescaped_desc
        else:
            new_desc = extract_fallback_description(text)

        # Make sure escaped version is <= 160 chars
        escaped_new_desc = html.escape(new_desc, quote=True)
        while len(escaped_new_desc) > 160 and len(new_desc) > 60:
            new_desc = new_desc.rsplit(" ", 1)[0]
            escaped_new_desc = html.escape(new_desc, quote=True)

        if m1:
            new_text = desc_pattern1.sub(r"\g<1>" + escaped_new_desc + r"\g<3>", text, count=1)
        else:
            new_text = desc_pattern2.sub(r"\g<1>" + escaped_new_desc + r"\g<3>", text, count=1)

        html_file.write_text(new_text, encoding="utf-8")
        stats["repaired"] += 1

    return stats


if __name__ == "__main__":
    res = repair_meta_descriptions()
    print("Meta description repair results:")
    for k, v in res.items():
        print(f"  {k}: {v}")
