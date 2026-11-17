#!/usr/bin/env python3
"""
scripts/audit_claude_seo.py — Claude-SEO Audit Runner

Runs run_full_claude_seo_audit across sample articles and whole corpus,
demonstrating real score enforcement via vendor/claude_seo.
"""

from __future__ import annotations

from pathlib import Path
import statistics
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import seo_pipeline

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
        articles.append(p)
    return sorted(articles)


def main():
    sites_dir = PROJECT_ROOT / "sites"
    articles = get_all_articles(sites_dir)
    print(f"Total articles discovered: {len(articles)}")

    # 1. 10 Sampled articles
    step = len(articles) // 10
    samples = articles[::step][:10]

    print("\n" + "=" * 80)
    print(" CLAUDE-SEO AUDIT: 10 SAMPLED ARTICLES (SCORE VARIATION PROOF)")
    print("=" * 80)
    print(f" {'Domain':<16} | {'Slug':<32} | {'Score':>6} | {'QRG':>5} | {'H2':>3} | {'Links':>5}")
    print("-" * 80)

    for p in samples:
        domain = p.relative_to(sites_dir).parts[0]
        slug = p.parent.name if p.name == "index.html" else p.stem
        canon = f"https://{domain}/{slug}"
        html = p.read_text(encoding="utf-8", errors="ignore")
        res = seo_pipeline.run_full_claude_seo_audit(html, canon)
        score = res["claude_seo_score"]
        qrg = res["qrg_overall_quality"]
        h2 = res["h2_count"]
        links = res["internal_links"]
        disp_slug = (slug[:29] + "...") if len(slug) > 32 else slug
        print(f" {domain:<16} | {disp_slug:<32} | {score:>5.1f}% | {qrg:>5} | {h2:>3} | {links:>5}")

    print("=" * 80)

    # 2. Entire corpus distribution
    scores = []
    qrg_scores = []
    for p in articles:
        domain = p.relative_to(sites_dir).parts[0]
        slug = p.parent.name if p.name == "index.html" else p.stem
        canon = f"https://{domain}/{slug}"
        html = p.read_text(encoding="utf-8", errors="ignore")
        res = seo_pipeline.run_full_claude_seo_audit(html, canon)
        scores.append(res["claude_seo_score"])
        qrg_scores.append(res["qrg_overall_quality"])

    mean_s = statistics.mean(scores)
    med_s = statistics.median(scores)
    min_s = min(scores)
    max_s = max(scores)
    count_100 = sum(1 for s in scores if s == 100.0)

    print("\n" + "=" * 80)
    print(" CLAUDE-SEO AUDIT: FULL CORPUS SCORE DISTRIBUTION")
    print("=" * 80)
    print(f" Total articles audited:    {len(scores)}")
    print(f" Mean Claude-SEO Score:     {mean_s:.2f} / 100")
    print(f" Median Claude-SEO Score:   {med_s:.2f} / 100")
    print(f" Min Claude-SEO Score:      {min_s:.2f} / 100")
    print(f" Max Claude-SEO Score:      {max_s:.2f} / 100")
    print(f" Articles scoring 100.0:    {count_100} / {len(scores)} ({count_100/len(scores)*100:.1f}%)")
    print(f" Mean QRG Overall Quality:  {statistics.mean(qrg_scores):.2f} / 100")
    print(f" Median QRG Quality:        {statistics.median(qrg_scores):.2f} / 100")
    print("=" * 80)


if __name__ == "__main__":
    main()
