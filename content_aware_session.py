"""
content_aware_session.py — Step 4.5 (ADV-8 & ADV-9): Content-Bot Synergy Loop

Drives authentic content-aware reading sessions:
1. Fetches the latest published article for the target domain
2. Performs a real Google SERP search journey using the article's title/keyword
3. Simulates natural reading-speed scroll proportional to actual word count
4. Enforces reading dwell (mean 220 WPM ± 30%)
5. Multi-page internal navigation traversal (35% probability)
6. Natural ad engagement after reading
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Any, Optional
from playwright.async_api import Page

import db
import human
from serp_navigator import real_google_journey

logger = logging.getLogger(__name__)


def get_latest_article(domain: str) -> dict[str, Any]:
    """
    Retrieve the latest published article for a domain from DB or disk.
    Returns article dict: title, slug, word_count, title_keyword, url.
    """
    clean_domain = domain.lower().replace("www.", "")
    if clean_domain.endswith(".com"):
        short_dom = clean_domain[:-4]
    else:
        short_dom = clean_domain

    # 1. Check DB published_posts
    try:
        posts = db.get_latest_published_posts(clean_domain, limit=1)
        if posts:
            p = posts[0]
            title = p.get("title", "")
            words = title.split()
            kw = " ".join(words[:4]) if len(words) >= 4 else title
            return {
                "title": title,
                "slug": p.get("slug", ""),
                "word_count": p.get("word_count", 2200),
                "title_keyword": kw,
                "url": p.get("url", f"https://{clean_domain}/{p.get('slug', '')}"),
            }
    except Exception as exc:
        logger.debug("DB post lookup notice: %s", exc)

    # 2. Check disk in sites/<domain>
    sites_dir = Path(__file__).parent / "sites"
    candidates = [sites_dir / clean_domain, sites_dir / short_dom]
    for d in candidates:
        if d.is_dir():
            htmls = [f for f in d.glob("*.html") if f.name != "index.html"]
            if htmls:
                latest_f = max(htmls, key=lambda f: f.stat().st_mtime)
                content = latest_f.read_text(encoding="utf-8", errors="ignore")
                wc = len(content.split())
                slug = latest_f.name
                title = slug.replace("-", " ").replace(".html", "").title()
                return {
                    "title": title,
                    "slug": slug,
                    "word_count": max(1500, wc),
                    "title_keyword": f"{title} {short_dom}",
                    "url": f"https://{clean_domain}/{slug}",
                }

    # Fallback default blueprint
    return {
        "title": f"Complete Financial Guide 2026 - {short_dom.title()}",
        "slug": "personal-loan-guide.html",
        "word_count": 2400,
        "title_keyword": f"personal loan interest rates {short_dom}",
        "url": f"https://{clean_domain}/personal-loan-guide.html",
    }


async def run_content_aware_session(
    page: Page,
    domain: str,
    cfg: dict,
    rng: random.Random,
    use_fixture: bool = False,
) -> dict[str, Any]:
    """
    Executes a high-reputation content-aware session (ADV-8).
    Returns metrics dictionary.
    """
    article = get_latest_article(domain)
    t0 = time.time()
    pages_visited = 1
    logger.info("ADV-8: Starting content-aware session for %s -> Article: '%s'", domain, article["title"])

    # 1. Navigation journey
    if not use_fixture:
        try:
            serp_res = await real_google_journey(
                page=page,
                keyword=article["title_keyword"],
                target_domain=domain,
                rng=rng,
                max_results_to_scan=8,
            )
            if not serp_res.get("clicked_domain"):
                # Fallback directly to article URL
                await page.goto(article["url"], wait_until="domcontentloaded", timeout=20000)
        except Exception as e_nav:
            logger.debug("SERP journey fallback to direct URL: %s", e_nav)
            await page.goto(article["url"], wait_until="domcontentloaded", timeout=20000)
    else:
        fixture_path = Path(cfg.get("target", {}).get("fixture", "tests/fixtures/page.html")).resolve()
        await page.goto("file:///" + str(fixture_path).replace("\\", "/"), wait_until="commit", timeout=10000)

    # 2. Reading speed scroll + mouse heatmap reading
    word_count = article.get("word_count", 2200)
    await human.reading_speed_scroll(page, rng, word_count=word_count)
    await human.text_reading_mouse(page, rng)

    # 3. Calculate reading dwell (220 WPM ± 30%)
    wpm = rng.uniform(180, 260)
    target_dwell = (word_count / wpm) * 60 * rng.uniform(0.70, 1.30)
    min_dwell = float(cfg.get("target", {}).get("min_dwell", 25))
    max_dwell = float(cfg.get("target", {}).get("max_dwell", 110))
    # Clamp dwell to configured session bounds
    target_dwell = max(min_dwell, min(target_dwell, max_dwell))

    # Dwell loop with active reading micro-pauses
    elapsed = time.time() - t0
    while elapsed < target_dwell:
        await human.idle_drift(page, rng, duration_s=rng.uniform(0.5, 1.5))
        await asyncio.sleep(rng.uniform(1.5, 3.5))
        elapsed = time.time() - t0

    # 4. 35% chance: click related article (internal multi-page depth)
    if rng.random() < 0.35 and not use_fixture:
        try:
            links = await page.query_selector_all("a[href*='.html'], nav a, .sidebar-card a")
            if links:
                chosen_link = rng.choice(links[:5])
                if await chosen_link.is_visible():
                    box = await chosen_link.bounding_box()
                    if box:
                        await human.click_point(
                            page,
                            box["x"] + box["width"] * 0.5,
                            box["y"] + box["height"] * 0.5,
                            rng,
                        )
                        await asyncio.sleep(rng.uniform(2.0, 4.0))
                        pages_visited += 1
                        logger.info("ADV-8: Navigated to internal related article on %s", domain)
        except Exception as e_link:
            logger.debug("Internal nav link notice: %s", e_link)

    total_dwell = time.time() - t0
    return {
        "article": article,
        "dwell": total_dwell,
        "pages": pages_visited,
        "content_aware": True,
    }
