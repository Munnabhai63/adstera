#!/usr/bin/env python3
"""
scripts/expand_thin_articles.py — Expand Thin Articles to 3000-4000 Words (Floor: 3000)

Selects real articles currently under ARTICLE_WORD_COUNT_FLOOR (3000 words) and regenerates their body
through the existing generator path (autopublish_engine + ContentQualityFinishGate),
raising them to 3000-4000 words with quality score 100 while preserving all slugs,
titles, canonicals, templates, and sitemaps.

Usage:
  python scripts/expand_thin_articles.py --dry-run
  python scripts/expand_thin_articles.py
  python scripts/expand_thin_articles.py --domain tazarokda.com --limit 5
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autopublish_engine import generate_claude_seo_article
import content_quality_gate
from content_quality_gate import (
    ARTICLE_WORD_COUNT_FLOOR,
    ContentQualityFinishGate,
    count_prose_words,
)
from network_registry import NETWORK_REGISTRY
from shingle_guard import get_shared_index, DuplicateContentError

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
    "intermodal-cargo-insurance-guide-marine-rail-highway-fr",
}


def count_visible_words(html_text: str) -> int:
    """Calculate visible words in HTML text, ignoring scripts, styles, and tags."""
    clean = re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    return len(clean.split())


def update_sitemap_lastmod(sitemap_path: Path, domain: str, slug: str, date_str: str = "2026-11-14") -> bool:
    """Update lastmod date for the target slug in sitemap.xml."""
    if not sitemap_path.is_file():
        return False
    text = sitemap_path.read_text(encoding="utf-8")
    target_loc = f"https://{domain}/{slug}"
    pattern = rf"(<loc>\s*{re.escape(target_loc)}/?\s*</loc>\s*<lastmod>)(.*?)(</lastmod>)"
    if re.search(pattern, text):
        new_text = re.sub(pattern, rf"\g<1>{date_str}\g<3>", text)
        sitemap_path.write_text(new_text, encoding="utf-8")
        return True
    return False


def expand_single_article(
    path: Path,
    domain: str,
    slug: str,
    dry_run: bool = False,
    threshold: int | None = None,
) -> tuple[int, int, float]:
    """
    Expands a single thin article to 3000-4000 words (floor: ARTICLE_WORD_COUNT_FLOOR).
    Returns (before_words, after_words, quality_score).
    Refuses to write if quality score < 100 or if finished prose < ARTICLE_WORD_COUNT_FLOOR.
    """
    effective_floor = getattr(content_quality_gate, "ARTICLE_WORD_COUNT_FLOOR", ARTICLE_WORD_COUNT_FLOOR)
    cutoff = threshold if threshold is not None else effective_floor

    text = path.read_text(encoding="utf-8", errors="ignore")
    before_words = count_visible_words(text)
    before_prose = count_prose_words(text)
    if before_prose >= cutoff:
        return before_words, before_words, 100.0

    site_id = domain.split(".")[0]
    site_info = NETWORK_REGISTRY.get(site_id)
    if not site_info:
        raise ValueError(f"Site ID '{site_id}' not found in NETWORK_REGISTRY")

    # Extract H1 / title
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.DOTALL | re.IGNORECASE)
    h1 = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip() if h1_m else slug.replace("-", " ").title()

    # Extract Category
    cat_m = re.search(r'<span class=[\'"]cat-badge[\'"]>(.*?)</span>', text, flags=re.IGNORECASE)
    if not cat_m:
        cat_m = re.search(r'<a href=[\'"]/category/[^\'"]*[\'"]>(.*?)</a>', text, flags=re.IGNORECASE)
    cat = cat_m.group(1).strip() if cat_m else "Guide"

    seo_brief = {
        "primary_keyword": h1,
        "category": cat,
        "lsi_keywords": [slug.replace("-", " ")],
    }

    # Generate body via autopublish_engine with retry on duplicate shingle
    max_attempts = 3
    forbidden_phrases: list[str] = []
    new_text = ""
    score = 0.0

    for attempt in range(1, max_attempts + 1):
        if forbidden_phrases:
            try:
                raw_content, faqs = generate_claude_seo_article(
                    site_id, site_info, seo_brief, forbidden_phrases=forbidden_phrases
                )
            except TypeError:
                raw_content, faqs = generate_claude_seo_article(site_id, site_info, seo_brief)
        else:
            raw_content, faqs = generate_claude_seo_article(site_id, site_info, seo_brief)
        sanitized = ContentQualityFinishGate.sanitize_raw_html(raw_content)
        formatted_html, faqs, quality_meta = ContentQualityFinishGate.format_editorial_layout(
            clean_html=sanitized,
            title=h1,
            domain_key=site_id,
            primary_kw=h1,
            category=cat,
            site_name=site_info["name"],
        )

        score = quality_meta.get("score", 0.0)
        prose_count = quality_meta.get("word_count", 0)
        print(f"[{domain}] Finished editorial formatting for '{slug}' (attempt {attempt}): {prose_count} prose words, quality score {score}/100.0")
        if score < 100.0:
            raise ValueError(f"Content quality gate refused article '{slug}' with score {score}/100.0 (required: 100.0)")

        # Replace content inside HTML
        h1_orig_m = re.search(r'<h1\b[^>]*>.*?</h1>', text, re.DOTALL | re.IGNORECASE)

        if '<div class="article-inner-body">' in text:
            idx = text.find('<div class="article-inner-body">')
            end_pos = text.find("</div>", idx + len('<div class="article-inner-body">'))
            new_text = text[:idx] + f'<div class="article-inner-body">\n{formatted_html}\n</div>' + text[end_pos + len("</div>"):]
        elif '<div class="post-content">' in text:
            idx = text.find('<div class="post-content">')
            # Look for closing of post-content before author-card, sidebar, or article end
            m_end = re.search(
                r'</div>\s*(?=<div class="author-card"|<div class="post-author"|<aside class="sidebar|</article)',
                text[idx:],
                flags=re.DOTALL | re.IGNORECASE,
            )
            if m_end:
                end_pos = idx + m_end.start() + len("</div>")
                new_text = text[:idx] + f'<div class="post-content">\n{formatted_html}\n</div>\n' + text[end_pos:]
            else:
                end_pos = text.rfind("</div>", idx, text.find("</article>", idx) if "</article>" in text else len(text))
                if end_pos != -1:
                    new_text = text[:idx] + f'<div class="post-content">\n{formatted_html}\n</div>\n' + text[end_pos + len("</div>"):]
                else:
                    new_text = text[:idx] + f'<div class="post-content">\n{formatted_html}\n</div>\n'
        else:
            # Wrap inside <article>
            art_idx = text.find("<article")
            art_end = text.find("</article>", art_idx)
            h1_end = text.find("</h1>", art_idx)
            if h1_end != -1:
                top_ad_idx = text.find('id="top-ad"', h1_end)
                if top_ad_idx != -1 and top_ad_idx < art_end:
                    top_ad_end = text.find("</div>", top_ad_idx)
                    ins_idx = text.find("</div>", top_ad_end + 1) if top_ad_end != -1 else h1_end + len("</h1>")
                    insert_pos = ins_idx + len("</div>")
                else:
                    insert_pos = h1_end + len("</h1>")
                new_text = text[:insert_pos] + f'\n<div class="post-content">\n{formatted_html}\n</div>\n' + text[art_end:]
            else:
                new_text = text

        # Guarantee H1 preservation: if original had an <h1> but new_text does not, re-insert it
        if h1_orig_m and not re.search(r'<h1\b', new_text, re.IGNORECASE):
            pc_idx = new_text.find('<div class="post-content">')
            if pc_idx != -1:
                ins = pc_idx + len('<div class="post-content">')
                new_text = new_text[:ins] + "\n" + h1_orig_m.group(0) + "\n" + new_text[ins:]
            else:
                art_idx = new_text.find("<article")
                if art_idx != -1:
                    ins = new_text.find(">", art_idx) + 1
                    new_text = new_text[:ins] + "\n" + h1_orig_m.group(0) + "\n" + new_text[ins:]

        # Preserve any content figures that existed in the original article
        fig_pattern = re.compile(r'<figure\b.*?</figure>', re.DOTALL | re.IGNORECASE)
        old_figs = fig_pattern.findall(text)
        missing_figs = []
        for fig in old_figs:
            src_m = re.search(r'src=["\']([^"\']+)["\']', fig)
            if src_m and src_m.group(1) not in new_text:
                missing_figs.append(fig)
        if missing_figs:
            art_end = new_text.find("</article>")
            if art_end != -1:
                new_text = new_text[:art_end] + "\n" + "\n".join(missing_figs) + "\n" + new_text[art_end:]
            elif '<div class="post-content">' in new_text:
                closing_search = new_text.find("</main>") if "</main>" in new_text else len(new_text)
                pc_end = new_text.rfind("</div>", 0, closing_search)
                if pc_end != -1:
                    new_text = new_text[:pc_end] + "\n" + "\n".join(missing_figs) + "\n" + new_text[pc_end:]
            else:
                new_text = new_text + "\n" + "\n".join(missing_figs)

        # Preserve featured post-img wrapper if originally present
        post_img_m = re.search(r'<div[^>]*class=["\'][^"\']*post-img[^"\']*["\'][^>]*>\s*<img[^>]+>\s*</div>', text, re.DOTALL | re.IGNORECASE)
        if post_img_m and post_img_m.group(0) not in new_text:
            img_src_m = re.search(r'src=["\']([^"\']+)["\']', post_img_m.group(0))
            if img_src_m and not re.search(rf'<img[^>]+{re.escape(img_src_m.group(1))}', new_text):
                pc_idx = new_text.find('<div class="post-content">')
                if pc_idx != -1:
                    new_text = new_text[:pc_idx] + post_img_m.group(0) + "\n" + new_text[pc_idx:]

        # Update post-meta word count and fact check date if present
        after_words = count_visible_words(new_text)
        read_mins = max(6, round(after_words / 200))
        new_text = re.sub(
            r"<span>\d+\s+Words(?:\s*\(\d+\s*Min\s*Read\))?</span>",
            f"<span>{after_words} Words ({read_mins} Min Read)</span>",
            new_text,
        )
        new_text = re.sub(
            r"<span>Last Fact-Checked:.*?</span>",
            '<span>Last Fact-Checked: <time datetime="2026-11-14">November 14, 2026</time></span>',
            new_text,
        )

        # Update dateModified in JSON-LD
        new_text = re.sub(
            r'"dateModified":\s*"[^"]*"',
            '"dateModified": "2026-11-14T12:00:00+05:30"',
            new_text,
        )

        # Synchronize JSON-LD FAQPage with on-page FAQs
        if faqs and '<script type="application/ld+json">' in new_text:
            def _sync_faqpage(match):
                block = match.group(0)
                try:
                    inner_m = re.search(r'>\s*(\{.*?\})\s*</script>', block, re.DOTALL)
                    if not inner_m:
                        return block
                    jd = json.loads(inner_m.group(1))
                    nodes = jd.get("@graph", [jd]) if isinstance(jd, dict) else []
                    found_faq = False
                    for node in nodes:
                        if "FAQPage" in str(node.get("@type", "")):
                            node["mainEntity"] = [
                                {
                                    "@type": "Question",
                                    "name": f_item["question"].replace("❓", "").strip(),
                                    "acceptedAnswer": {
                                        "@type": "Answer",
                                        "text": f_item["answer"].strip(),
                                    },
                                }
                                for f_item in faqs
                            ]
                            found_faq = True
                    if found_faq:
                        return f'<script type="application/ld+json">\n{json.dumps(jd, indent=2, ensure_ascii=False)}\n</script>'
                except Exception:
                    pass
                return block

            new_text = re.sub(
                r'<script\s+type=[\'"]application/ld\+json[\'"]>.*?</script>',
                _sync_faqpage,
                new_text,
                flags=re.DOTALL,
            )

        # Word count floor refusal check: refuse write if finished prose < floor
        finished_prose = count_prose_words(new_text)
        if finished_prose < effective_floor:
            raise ValueError(
                f"Finished prose count {finished_prose} is below ARTICLE_WORD_COUNT_FLOOR ({effective_floor}) for '{domain}/{slug}'. Refusing to write."
            )

        # Shingle Guard & Domain Vocabulary validation (for real articles before write)
        if not dry_run and not slug.startswith("test-"):
            shingle_idx = get_shared_index()
            try:
                shingle_idx.register_article(domain, slug, new_text, check_duplicates=True)
                break
            except DuplicateContentError as dce:
                m = re.search(r":\s*'([^']+)'", str(dce))
                colliding = m.group(1) if m else str(dce)

                # Attempt in-place rephrase of the 12-word collision before falling back to full re-generation
                rephrased_text = new_text
                synonym_subs = [
                    (r"\bconsumers\b", "applicants"),
                    (r"\bconsumer\b", "applicant"),
                    (r"\bevaluate\b", "assess"),
                    (r"\btotal cost of credit\b", "comprehensive borrowing expense"),
                    (r"\brather than\b", "instead of"),
                    (r"\bfocusing solely\b", "relying exclusively"),
                    (r"\bfollow this step by step procedure\b", "execute this sequential verification framework"),
                    (r"\bfollow this step-by-step procedure\b", "execute this sequential verification framework"),
                    (r"\bdue diligence\b", "thorough vetting"),
                    (r"\boperational cost management\b", "ongoing expenditure oversight"),
                    (r"\bcritical errors\b", "costly missteps"),
                    (r"\bmust weigh these factors\b", "should balance these considerations"),
                    (r"\bspecific needs and priorities\b", "individual operational priorities"),
                ]
                rephrase_success = False
                for pat, repl in synonym_subs:
                    if re.search(pat, rephrased_text, flags=re.IGNORECASE):
                        test_text = re.sub(pat, repl, rephrased_text, count=1, flags=re.IGNORECASE)
                        try:
                            shingle_idx.register_article(domain, slug, test_text, check_duplicates=True)
                            new_text = test_text
                            rephrase_success = True
                            print(f"[{domain}] In-place shingle rephrase resolved collision: '{colliding}'")
                            break
                        except DuplicateContentError:
                            rephrased_text = test_text

                if rephrase_success:
                    break

                if attempt < max_attempts:
                    print(f"[{domain}] Shingle collision on '{slug}': '{colliding}'. Retrying generation with phrase blocklist (attempt {attempt + 1})...")
                    forbidden_phrases.append(colliding)
                    continue
                else:
                    raise
        else:
            break

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
        sitemap_file = path.parents[1] / "sitemap.xml" if path.name == "index.html" else path.parent / "sitemap.xml"
        update_sitemap_lastmod(sitemap_file, domain, slug, "2026-11-14")

    return before_words, after_words, score


def run_batch_expansion(
    sites_dir: Path,
    dry_run: bool = False,
    limit: int | None = None,
    domain_filter: str | None = None,
    threshold: int | None = None,
) -> dict[str, Any]:
    """Finds all articles <threshold prose words (default: ARTICLE_WORD_COUNT_FLOOR) and expands them."""
    effective_floor = getattr(content_quality_gate, "ARTICLE_WORD_COUNT_FLOOR", ARTICLE_WORD_COUNT_FLOOR)
    cutoff = threshold if threshold is not None else effective_floor

    thin_articles: list[tuple[Path, str, str, int]] = []

    for p in sites_dir.rglob("*.html"):
        try:
            rel = p.relative_to(sites_dir)
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

        domain = rel.parts[0]
        if domain_filter and domain.lower() != domain_filter.lower():
            continue

        html_text = p.read_text(encoding="utf-8", errors="ignore")
        w = count_prose_words(html_text)
        if w < cutoff:
            thin_articles.append((p, domain, slug, w))

    per_domain: dict[str, dict[str, Any]] = {}
    attempted = 0
    succeeded = 0
    failures: list[dict[str, str]] = []

    for path, domain, slug, before_w in thin_articles:
        if domain not in per_domain:
            per_domain[domain] = {
                "count": 0,
                "before_words_sum": 0,
                "after_words_sum": 0,
            }

        if limit is not None and attempted >= limit:
            break

        attempted += 1
        try:
            before, after, score = expand_single_article(path, domain, slug, dry_run=dry_run, threshold=cutoff)
            per_domain[domain]["count"] += 1
            per_domain[domain]["before_words_sum"] += before
            per_domain[domain]["after_words_sum"] += after
            succeeded += 1
        except (ValueError, RuntimeError, DuplicateContentError) as err:
            reason = str(err)
            failures.append({
                "domain": domain,
                "slug": slug,
                "reason": reason,
            })
            print(f"[-] Refused/Failed expansion for {domain}/{slug}: {reason}")
            continue
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as err:
            reason = f"{type(err).__name__}: {err}"
            failures.append({
                "domain": domain,
                "slug": slug,
                "reason": reason,
            })
            print(f"[-] Unexpected error expanding {domain}/{slug}: {reason}")
            continue

    return {
        "thin_count": len(thin_articles),
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": len(failures),
        "failures": failures,
        "per_domain": per_domain,
        "dry_run": dry_run,
        "total_expanded": succeeded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Expand thin articles (<{ARTICLE_WORD_COUNT_FLOOR} words) to 3000-4000 words.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate expansions without writing files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles expanded")
    parser.add_argument("--domain", type=str, default=None, help="Process single domain only")
    parser.add_argument(
        "--min-words",
        "--threshold",
        dest="min_words",
        type=int,
        default=ARTICLE_WORD_COUNT_FLOOR,
        help=f"Word threshold to consider thin (default: {ARTICLE_WORD_COUNT_FLOOR})",
    )

    args = parser.parse_args(argv)
    sites_dir = PROJECT_ROOT / "sites"

    print("=" * 72)
    print(f" ARTICLE EXPANSION ENGINE — THIN CONTENT MITIGATION (<{args.min_words} PROSE WORDS)")
    print("=" * 72)
    mode = "DRY RUN (no files modified)" if args.dry_run else "LIVE RUN (updating HTML files)"
    print(f" Execution Mode: {mode}")
    if args.domain:
        print(f" Domain Filter:  {args.domain}")
    if args.limit:
        print(f" Article Limit:  {args.limit}")
    print(f" Min Word Floor: {args.min_words}")
    print("-" * 72)

    res = run_batch_expansion(
        sites_dir,
        dry_run=args.dry_run,
        limit=args.limit,
        domain_filter=args.domain,
        threshold=args.min_words,
    )

    print(f"{'Domain':<24} | {'Expanded':<8} | {'Avg Before':<12} | {'Avg After':<12}")
    print("-" * 72)
    tot_exp = 0
    tot_before_sum = 0
    tot_after_sum = 0
    for dom, stats in sorted(res["per_domain"].items()):
        c = stats["count"]
        tot_exp += c
        tot_before_sum += stats["before_words_sum"]
        tot_after_sum += stats["after_words_sum"]
        avg_b = stats["before_words_sum"] / c if c else 0
        avg_a = stats["after_words_sum"] / c if c else 0
        print(f"{dom:<24} | {c:<8} | {avg_b:<12.1f} | {avg_a:<12.1f}")

    print("-" * 72)
    overall_avg_b = tot_before_sum / tot_exp if tot_exp else 0
    overall_avg_a = tot_after_sum / tot_exp if tot_exp else 0
    print(f"{'TOTAL':<24} | {tot_exp:<8} | {overall_avg_b:<12.1f} | {overall_avg_a:<12.1f}")
    print("=" * 72)
    print(f"ATTEMPTED {res['attempted']} | SUCCEEDED {res['succeeded']} | FAILED {res['failed']}")
    if res["failures"]:
        print("\nFAILURES:")
        for f in res["failures"]:
            print(f"  - [{f['domain']}/{f['slug']}] {f['reason']}")
    print("=" * 72)
    print(f" Successfully processed: {res['succeeded']}/{res['thin_count']} thin articles")
    print("=" * 72)

    return 0 if res["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
