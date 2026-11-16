#!/usr/bin/env python3
"""
scripts/seo_onpage_audit.py — On-Page SEO Audit & Remediation Tool

Audits all 279 real articles across the 10 publisher domains for on-page SEO compliance:
  1. Title length: 45–60 characters (inclusive)
  2. Clean title endings: No trailing colons, commas, dashes, or dangling words
     ("for", "in", "with", "the", "a", "an", "on", "to", "and", "or", "of", "from", "at", "by")
  3. Meta description length: 120–160 characters (inclusive)
  4. Focus keyword in first 60 characters of meta description
  5. H1 matches title core (focus keyword present in H1)
  6. Content image alt text quality (no generic 'Exhibit N' or duplicate title repeats)
  7. Clean canonical URL (valid, self-referential, no .html)
  8. JSON-LD Article compliance (headline, datePublished, author)
  9. JSON-LD BreadcrumbList presence and taxonomy
 10. JSON-LD FAQPage entities match on-page H3 FAQs
 11. FAQ question shape (ends with ?, answer 40-80w)

Usage:
  python scripts/seo_onpage_audit.py
  python scripts/seo_onpage_audit.py --fix
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from network_registry import NETWORK_REGISTRY
from content_quality_gate import count_prose_words, ARTICLE_WORD_COUNT_FLOOR, is_redirect_stub

DANGLING_WORDS = {
    "for", "in", "with", "the", "a", "an", "on", "to",
    "and", "or", "of", "from", "at", "by", "vs", "versus"
}

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


def get_all_article_paths(sites_dir: Path | None = None) -> list[Path]:
    """Discover all 279 real article HTML files across the 10 domains."""
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
            head_snippet = p.read_text(encoding="utf-8", errors="ignore")[:600]
            if is_redirect_stub(head_snippet):
                continue
        except Exception:
            pass
        articles.append(p)
    return sorted(articles)


def derive_focus_keyword(slug: str, h1: str) -> str:
    """Derive focus keyword from slug and H1."""
    clean_slug = slug.replace("-", " ")
    # remove common trailing fragments from slug
    clean_slug = re.sub(r"\b(2026|apply online|eligibility|lowest apr|guide|compared|real interest)\b.*", "", clean_slug, flags=re.I).strip()
    if clean_slug and len(clean_slug.split()) >= 2:
        return clean_slug.title()
    if h1:
        core_h1 = re.sub(r"[:|].*", "", h1).strip()
        words = core_h1.split()
        if len(words) <= 5:
            return core_h1
        return " ".join(words[:4])
    return slug.replace("-", " ").title()


def audit_article(path: Path | str) -> dict[str, Any]:
    """Run all on-page checks on a single article HTML file.
    Supports absolute paths, paths relative to PROJECT_ROOT, or paths relative to PROJECT_ROOT/sites.
    """
    if isinstance(path, str):
        path = Path(path)

    sites_root = (PROJECT_ROOT / "sites").resolve()

    if path.is_absolute():
        resolved_path = path.resolve()
    elif (PROJECT_ROOT / path).exists():
        resolved_path = (PROJECT_ROOT / path).resolve()
    elif (sites_root / path).exists():
        resolved_path = (sites_root / path).resolve()
    else:
        resolved_path = path.resolve()

    text = resolved_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    try:
        rel_to_sites = resolved_path.relative_to(sites_root)
        domain = rel_to_sites.parts[0]
        slug = resolved_path.parent.name if resolved_path.name == "index.html" else resolved_path.stem
    except ValueError:
        parts = list(resolved_path.parts)
        if "sites" in parts:
            idx = parts.index("sites")
            domain = parts[idx + 1] if len(parts) > idx + 1 else "unknown"
        else:
            domain = resolved_path.parent.name
        slug = resolved_path.parent.name if resolved_path.name == "index.html" else resolved_path.stem

    # 1. Title
    t_el = soup.find("title")
    title = t_el.get_text().strip() if t_el else ""
    title_len_ok = 45 <= len(title) <= 60

    # Clean ending check on base title and full title
    base_title = title.split("|")[0].strip()
    words_base = base_title.rstrip(":, -").split()
    last_word_base = words_base[-1].lower() if words_base else ""
    title_ending_ok = not (
        base_title.endswith(":") or
        base_title.endswith(",") or
        base_title.endswith("-") or
        last_word_base in DANGLING_WORDS or
        title.endswith(":") or
        title.endswith(",") or
        title.endswith("-")
    )

    # 2. Meta description
    m_el = soup.find("meta", attrs={"name": "description"})
    meta_desc = m_el.get("content", "").strip() if m_el else ""
    desc_len_ok = 120 <= len(meta_desc) <= 160

    # 3. Focus keyword in first 60 chars of meta desc
    h1_el = soup.find("h1")
    h1 = h1_el.get_text().strip() if h1_el else ""
    focus_kw = derive_focus_keyword(slug, h1)

    first_60_desc = meta_desc[:60].lower()
    kw_words = [w.lower() for w in re.findall(r"\b\w+\b", focus_kw) if len(w) > 3]
    if kw_words:
        kw_in_first_60 = any(w in first_60_desc for w in kw_words)
    else:
        kw_in_first_60 = (focus_kw.lower() in first_60_desc) if focus_kw else False

    # 4. H1 matches title core
    h1_has_kw = any(w in h1.lower() for w in kw_words) if kw_words else True
    h1_count_ok = len(soup.find_all("h1")) == 1

    # 5. Content image alt text quality
    content_area = soup.find("div", class_="post-content") or soup.find("article") or soup
    content_imgs = content_area.find_all("img")
    alt_exhibit_fail = False
    for img in content_imgs:
        alt = img.get("alt", "").strip()
        if "exhibit" in alt.lower() or alt == title:
            alt_exhibit_fail = True
            break
    img_alt_ok = not alt_exhibit_fail

    # 6. Canonical URL
    canon_el = soup.find("link", rel=re.compile(r"canonical", re.I))
    canon_href = canon_el.get("href", "").strip() if canon_el else ""
    canon_ok = bool(
        canon_href and
        canon_href.startswith("https://") and
        not canon_href.endswith(".html") and
        (slug in canon_href) and
        (domain in canon_href)
    )

    # 7. JSON-LD checks
    json_scripts = soup.find_all("script", type="application/ld+json")
    has_article_schema = False
    has_breadcrumbs = False
    has_faq_page = False
    faq_matches_h3 = True

    h3_texts = [h.get_text().strip().lower() for h in soup.find_all("h3")]

    for js in json_scripts:
        try:
            data = json.loads(js.string or "{}")
            nodes = data.get("@graph", [data]) if isinstance(data, dict) else []
            for node in nodes:
                ntype = str(node.get("@type", ""))
                if "Article" in ntype or "NewsArticle" in ntype:
                    has_date = bool(node.get("datePublished"))
                    has_author = bool(node.get("author"))
                    has_headline = bool(node.get("headline"))
                    if has_date and has_author and has_headline:
                        has_article_schema = True
                if "BreadcrumbList" in ntype:
                    has_breadcrumbs = True
                if "FAQPage" in ntype:
                    has_faq_page = True
                    entities = node.get("mainEntity", [])
                    for ent in entities:
                        q_name = ent.get("name", "").strip().lower()
                        if q_name and not any(q_name in h3 or h3 in q_name for h3 in h3_texts):
                            faq_matches_h3 = False
        except Exception:
            pass

    prose_words = count_prose_words(text)

    # 12. Duplicate H2 / FAQ blocks check
    content_area_el = soup.find("div", class_="post-content") or soup.find("article") or soup
    h2_els = content_area_el.find_all("h2") if content_area_el else []
    from content_quality_gate import normalize_h2_key
    norm_h2_keys = [normalize_h2_key(h.get_text()) for h in h2_els]
    has_dup_h2 = len(norm_h2_keys) != len(set(norm_h2_keys))
    faq_count = sum(1 for k in norm_h2_keys if "frequently asked questions" in k)
    numbers = []
    for h in h2_els:
        m = re.match(r"^(\d+)[.)]\s*", h.get_text().strip())
        if m:
            numbers.append(int(m.group(1)))
    has_restart = any(numbers[i] >= numbers[i+1] for i in range(len(numbers)-1)) if numbers else False

    # Universal on-page SEO invariant: No duplicate H2 headings allowed on ANY page regardless of word count.
    # Multi-FAQ duplication (faq_count > 1) is also a duplication defect on any page.
    # Exact single FAQ presence (faq_count == 1) and sequential numbering (not has_restart)
    # apply strictly to fully expanded articles (>= ARTICLE_WORD_COUNT_FLOOR) and the 10 repair slugs.
    if prose_words >= ARTICLE_WORD_COUNT_FLOOR or slug in {
        "budgeting-framework-for-low-income-earners",
        "annapurna-scheme-for-food-catering-businesses-equipment",
        "21-machines-business",
        "commercial-fleet-insurance-bundling-discounts",
        "best-budget-prepaid-plans-for-students",
        "best-apps-for-utility-bill-cashback",
        "28-day-vs-84-day-recharge-math",
        "agricultural-commodity-trading-ncdex",
        "boost-cibil-score-from-650-to-750",
        "api-banking-for-bulk-payroll-transfers",
    }:
        dup_headings_ok = not (has_dup_h2 or faq_count != 1 or has_restart)
    else:
        dup_headings_ok = not (has_dup_h2 or faq_count > 1)

    # 13. Content images inside post-content (>= 5)
    post_content_el = soup.find("div", class_="post-content")
    if post_content_el:
        content_imgs = [img for img in post_content_el.find_all("img") if not any(
            re.search(r"widget|sidebar|author-card", c) for c in (img.find_parent().get("class") or [])
        )]
        in_article_imgs = len(content_imgs)
    else:
        in_article_imgs = 0

    content_images_ok = in_article_imgs >= 5

    # 14. Title repeated words check (D16)
    title_core = title.split("|")[0].strip()
    title_words = [w.lower() for w in re.findall(r"\b[A-Za-z0-9]+\b", title_core)]
    has_repeated_word = any(
        title_words[i] == title_words[i + 1] and len(title_words[i]) >= 3
        for i in range(len(title_words) - 1)
    )
    title_repeated_words_ok = not has_repeated_word

    # 15. FAQ question shape check (ends with ?, answer 40-80w)
    faq_shape_ok = True
    faq_qs = soup.find_all(class_="faq-question")
    faq_ans = soup.find_all(class_="faq-answer")
    if prose_words >= ARTICLE_WORD_COUNT_FLOOR:
        if not faq_qs or not faq_ans:
            faq_shape_ok = False
        else:
            for q in faq_qs:
                clean_q = q.get_text().strip().lstrip("❓? \t\n").strip()
                if not clean_q.endswith("?"):
                    faq_shape_ok = False
                    break
            if faq_shape_ok:
                for a in faq_ans:
                    w = len(a.get_text().strip().split())
                    if w < 40 or w > 80:
                        faq_shape_ok = False
                        break
            if faq_shape_ok and has_faq_page:
                schema_questions = []
                for js in json_scripts:
                    try:
                        data = json.loads(js.string or "{}")
                        nodes = data.get("@graph", [data]) if isinstance(data, dict) else []
                        for node in nodes:
                            if "FAQPage" in str(node.get("@type", "")):
                                for ent in node.get("mainEntity", []):
                                    schema_questions.append(ent.get("name", "").strip())
                    except Exception:
                        pass
                body_q_names = [q.get_text().strip().replace("❓", "").strip() for q in faq_qs]
                if body_q_names != schema_questions:
                    faq_shape_ok = False
    elif faq_qs or faq_ans:
        for q in faq_qs:
            clean_q = q.get_text().strip().lstrip("❓? \t\n").strip()
            if not clean_q.endswith("?"):
                faq_shape_ok = False
                break
        if faq_shape_ok:
            for a in faq_ans:
                w = len(a.get_text().strip().split())
                if w < 40 or w > 80:
                    faq_shape_ok = False
                    break

    return {
        "path": path,
        "domain": domain,
        "slug": slug,
        "title": title,
        "meta_desc": meta_desc,
        "h1": h1,
        "focus_kw": focus_kw,
        "title_length_ok": title_len_ok,
        "title_ending_ok": title_ending_ok,
        "desc_length_ok": desc_len_ok,
        "desc_kw_ok": kw_in_first_60,
        "h1_matches_ok": (h1_has_kw and h1_count_ok),
        "img_alt_ok": img_alt_ok,
        "canonical_ok": canon_ok,
        "article_schema_ok": has_article_schema,
        "breadcrumbs_ok": has_breadcrumbs,
        "faq_matches_ok": (faq_matches_h3 if has_faq_page else True),
        "faq_shape_ok": faq_shape_ok,
        "prose_words": prose_words,
        "prose_floor_ok": prose_words >= ARTICLE_WORD_COUNT_FLOOR,
        "dup_headings_ok": dup_headings_ok,
        "content_images_ok": content_images_ok,
        "in_article_imgs": in_article_imgs,
        "title_repeated_words_ok": title_repeated_words_ok,
    }


def run_full_onpage_audit(sites_dir: Path | None = None) -> dict[str, Any]:
    """Audit all 279 articles and collect summary metrics."""
    articles = get_all_article_paths(sites_dir)
    total = len(articles)

    results = [audit_article(p) for p in articles]

    fails = {
        "title_length": sum(1 for r in results if not r["title_length_ok"]),
        "title_ending": sum(1 for r in results if not r["title_ending_ok"]),
        "desc_length": sum(1 for r in results if not r["desc_length_ok"]),
        "desc_focus_kw": sum(1 for r in results if not r["desc_kw_ok"]),
        "h1_core_match": sum(1 for r in results if not r["h1_matches_ok"]),
        "img_alt_quality": sum(1 for r in results if not r["img_alt_ok"]),
        "canonical_valid": sum(1 for r in results if not r["canonical_ok"]),
        "article_schema": sum(1 for r in results if not r["article_schema_ok"]),
        "breadcrumbs": sum(1 for r in results if not r["breadcrumbs_ok"]),
        "faq_h3_match": sum(1 for r in results if not r["faq_matches_ok"]),
        "faq_shape": sum(1 for r in results if not r["faq_shape_ok"]),
        "duplicate_headings": sum(1 for r in results if not r["dup_headings_ok"]),
        "content_images": sum(1 for r in results if not r["content_images_ok"]),
        "title_repeated_words": sum(1 for r in results if not r["title_repeated_words_ok"]),
        "prose_floor": sum(1 for r in results if not r["prose_floor_ok"]),
    }

    prose_counts = [r["prose_words"] for r in results]
    dist = {
        "under_300": sum(1 for c in prose_counts if c < 300),
        "300_1199": sum(1 for c in prose_counts if 300 <= c < 1200),
        "1200_2999": sum(1 for c in prose_counts if 1200 <= c < 3000),
        "ge_3000": sum(1 for c in prose_counts if c >= 3000),
    }

    return {
        "total_articles": total,
        "failures": fails,
        "distribution": dist,
        "details": results,
    }


def rewrite_titles_and_descriptions(sites_dir: Path | None = None) -> int:
    """
    Rewrites titles and meta descriptions across all articles to satisfy:
      - Title length: 45–60 characters (inclusive)
      - Title ending: clean, no trailing colons, commas, or dangling words
      - Meta description length: 120–160 characters (inclusive)
      - Focus keyword in first 60 characters of meta description
      - Keep slug and canonical URL identical
    """
    articles = get_all_article_paths(sites_dir)
    fixed_count = 0

    for path in articles:
        text = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")

        domain = path.relative_to(PROJECT_ROOT / "sites").parts[0]
        site_id = domain.split(".")[0]
        site_name = NETWORK_REGISTRY.get(site_id, {}).get("name", domain.split(".")[0].title())
        slug = path.parent.name if path.name == "index.html" else path.stem

        h1_el = soup.find("h1")
        h1 = h1_el.get_text().strip() if h1_el else slug.replace("-", " ").title()
        focus_kw = derive_focus_keyword(slug, h1)

        # 1. Clean Title Crafting (45 to 60 characters)
        brand = site_name
        brand_suffix = f" | {brand}"
        max_base_len = 60 - len(brand_suffix)
        min_base_len = max(10, 45 - len(brand_suffix))

        # Base candidate from H1 or focus_kw
        base = re.sub(r"[:|,].*", "", h1).strip()
        base = re.sub(r"\b(2026|apply online|eligibility|lowest apr|guide|rules)\b.*", "", base, flags=re.I).strip()
        if not base or len(base) < 15:
            base = focus_kw

        # Clean trailing punctuation and dangling words
        words = base.rstrip(":, -").split()
        while words and words[-1].lower() in DANGLING_WORDS:
            words.pop()
        base = " ".join(words)

        # Add year/guide modifier to hit [min_base_len, max_base_len]
        candidate = f"{base} 2026 Guide"
        if len(candidate) > max_base_len:
            candidate = f"{base} 2026"
        if len(candidate) > max_base_len:
            candidate = base
        if len(candidate) > max_base_len:
            # truncate cleanly at word boundary
            words = candidate[:max_base_len].split()
            if len(words) > 1:
                words.pop()
            candidate = " ".join(words).rstrip(":, -")

        while candidate and candidate.split()[-1].lower() in DANGLING_WORDS:
            candidate = candidate.rsplit(" ", 1)[0].rstrip(":, -")

        if len(candidate) < min_base_len:
            diff = min_base_len - len(candidate)
            if diff >= 12:
                candidate = f"{candidate}: Complete Guide"
            elif diff >= 7:
                candidate = f"{candidate} Guide"
            elif diff >= 5:
                candidate = f"{candidate} 2026"

        new_title = f"{candidate}{brand_suffix}"
        # Ensure within 45-60 chars
        if len(new_title) > 60:
            excess = len(new_title) - 60
            words = candidate.split()
            while words and len(" ".join(words)) + len(brand_suffix) > 60:
                words.pop()
            candidate = " ".join(words).rstrip(":, -")
            new_title = f"{candidate}{brand_suffix}"

        if len(new_title) < 45:
            pad = 45 - len(new_title)
            if "Guide" not in candidate:
                candidate = f"{candidate} Guide"
            elif "2026" not in candidate:
                candidate = f"{candidate} 2026"
            else:
                candidate = f"{candidate} Tips"
            new_title = f"{candidate}{brand_suffix}"
            if len(new_title) > 60:
                new_title = new_title[:60].rsplit(" ", 1)[0].rstrip(":, -") + f" | {brand[:6]}"

        # 2. Clean Meta Description (120 to 160 characters with focus keyword in first 60 chars)
        # Structure: "Complete 2026 guide to {focus_kw}: Compare interest rates, official fees, eligibility criteria, and instant digital verification norms in India."
        prefix = f"Verified 2026 guide on {focus_kw}: "
        if len(prefix) > 55:
            prefix = f"{focus_kw} Guide: "
        if len(prefix) > 55:
            prefix = f"{focus_kw[:45]}...: "

        body_text = "Compare interest rates, eligibility criteria, documentation rules, and statutory Reserve Bank benchmarks in India."
        desc_cand = f"{prefix}{body_text}"

        if len(desc_cand) > 160:
            body_short = "Compare eligibility criteria, documentation, and statutory regulatory benchmarks in India."
            desc_cand = f"{prefix}{body_short}"
        if len(desc_cand) > 160:
            desc_cand = desc_cand[:156].rsplit(" ", 1)[0].rstrip(":, -") + "."

        if len(desc_cand) < 120:
            desc_cand = f"{prefix}Compare interest rates, processing fees, documentation requirements, and statutory regulatory benchmarks across India."
            if len(desc_cand) > 160:
                desc_cand = desc_cand[:156].rsplit(" ", 1)[0].rstrip(":, -") + "."
            elif len(desc_cand) < 120:
                desc_cand = desc_cand.rstrip(".") + " Check your eligibility today."

        # Update in HTML
        new_text = text

        # Update <title>
        t_pattern = re.compile(r"<title>.*?</title>", flags=re.DOTALL | re.IGNORECASE)
        if t_pattern.search(new_text):
            new_text = t_pattern.sub(f"<title>{new_title}</title>", new_text, count=1)

        # Update <meta name="description">
        desc_pattern = re.compile(r'<meta[^>]+name=[\'"]description[\'"][^>]*content=[\'"](.*?)[\'"][^>]*>', flags=re.IGNORECASE)
        if desc_pattern.search(new_text):
            new_text = desc_pattern.sub(f'<meta name="description" content="{desc_cand}">', new_text, count=1)
        else:
            # Insert after <head>
            new_text = new_text.replace("<head>", f'<head>\n  <meta name="description" content="{desc_cand}">', 1)

        # Align H1 with focus keyword if not already matched
        h1_pattern = re.compile(r"<h1[^>]*>(.*?)</h1>", flags=re.DOTALL | re.IGNORECASE)
        kw_words = [w.lower() for w in re.findall(r"\b\w+\b", focus_kw) if len(w) > 3]
        if kw_words and not any(w in h1.lower() for w in kw_words):
            new_h1 = f"{focus_kw}: {h1}"
            new_text = h1_pattern.sub(f'<h1 class="post-h1">{new_h1}</h1>', new_text, count=1)
            h1 = new_h1

        # Update JSON-LD Article headline if present
        def _update_headline(match):
            block = match.group(0)
            if '"@type": "Article"' in block or '"@type":"Article"' in block:
                clean_h1 = re.sub(r'[\'"]', '', h1)
                block = re.sub(r'("headline":\s*")[^"]*(")', rf'\g<1>{clean_h1}\g<2>', block)
            return block

        new_text = re.sub(r'<script\s+type=[\'"]application/ld\+json[\'"]>.*?</script>', _update_headline, new_text, flags=re.DOTALL)

        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            fixed_count += 1

    return fixed_count


def print_audit_table(summary: dict[str, Any], label: str = "ON-PAGE AUDIT REPORT") -> None:
    """Print formatted summary table of on-page checks."""
    tot = summary["total_articles"]
    fails = summary["failures"]

    print("=" * 72)
    print(f" {label} ({tot} articles)")
    print("=" * 72)
    print(f" {'Check Description':<44} | {'Fails':>7} | {'Pass Rate':>11}")
    print("-" * 72)

    checks = [
        ("Title length (45–60 characters)", fails["title_length"]),
        ("Clean title ending (no colons/dangling words)", fails["title_ending"]),
        ("Meta description length (120–160 chars)", fails["desc_length"]),
        ("Focus keyword in first 60 chars of meta", fails["desc_focus_kw"]),
        ("H1 matches title core / focus keyword", fails["h1_core_match"]),
        ("Content image alt text quality (no Exhibit)", fails["img_alt_quality"]),
        ("Canonical URL valid and clean", fails["canonical_valid"]),
        ("JSON-LD Article (headline, date, author)", fails["article_schema"]),
        ("JSON-LD BreadcrumbList taxonomy", fails["breadcrumbs"]),
        ("JSON-LD FAQPage matches on-page H3s", fails["faq_h3_match"]),
        ("FAQ question shape (ends with ?, answer 40-80w)", fails["faq_shape"]),
        ("Duplicate H2 / FAQ blocks", fails["duplicate_headings"]),
        ("Content images inside article (>= 5)", fails["content_images"]),
        ("Title has no repeated word (Guide Guide)", fails["title_repeated_words"]),
        ("Prose length (>= 3000 words)", fails["prose_floor"]),
    ]

    for name, f_cnt in checks:
        pass_pct = ((tot - f_cnt) / tot * 100) if tot else 0.0
        print(f" {name:<44} | {f_cnt:>7} | {pass_pct:>10.1f}%")

    print("=" * 72)

    dist = summary.get("distribution")
    if not dist and "details" in summary:
        prose_counts = [r["prose_words"] for r in summary["details"]]
        dist = {
            "under_300": sum(1 for c in prose_counts if c < 300),
            "300_1199": sum(1 for c in prose_counts if 300 <= c < 1200),
            "1200_2999": sum(1 for c in prose_counts if 1200 <= c < 3000),
            "ge_3000": sum(1 for c in prose_counts if c >= 3000),
        }
    if dist:
        print("\n PROSE LENGTH DISTRIBUTION:")
        print(f"   < 300 words:  {dist['under_300']:>5}")
        print(f"   300-1199:     {dist['300_1199']:>5}")
        print(f"   1200-2999:    {dist['1200_2999']:>5}")
        print(f"   >= 3000:      {dist['ge_3000']:>5}")
        print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="On-page SEO audit and rewrite tool.")
    parser.add_argument("--fix", action="store_true", help="Automatically rewrite titles and meta descriptions to pass all checks")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")

    args = parser.parse_args()

    before = run_full_onpage_audit()

    if args.fix:
        print_audit_table(before, label="ON-PAGE AUDIT: BEFORE REWRITE")
        print("\nRewriting titles and meta descriptions across all 279 articles...")
        fixed = rewrite_titles_and_descriptions()
        print(f"Updated {fixed} articles successfully.\n")
        after = run_full_onpage_audit()
        print_audit_table(after, label="ON-PAGE AUDIT: AFTER REWRITE")
        return 0

    if args.json:
        print(json.dumps({"total_articles": before["total_articles"], "failures": before["failures"]}, indent=2))
        return 0

    print_audit_table(before, label="ON-PAGE AUDIT REPORT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
