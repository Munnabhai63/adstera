"""
nav.py — Multi-page session graph: internal link following, page-depth navigation.
"""
from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page

import human

logger = logging.getLogger(__name__)


async def collect_internal_links(page: Page, base_url: str) -> list[str]:
    """Return a list of href values that are internal to base_url's hostname."""
    base_host = urlparse(base_url).netloc
    try:
        hrefs: list[str] = await page.evaluate(
            """(baseHost) => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .map(a => a.href)
                    .filter(h => {
                        try {
                            const u = new URL(h);
                            return u.hostname === baseHost || u.hostname === '';
                        } catch { return false; }
                    });
            }""",
            base_host,
        )
        return list(set(hrefs))
    except Exception as exc:
        logger.debug("collect_internal_links failed: %s", exc)
        return []


async def navigate_internal(
    page: Page,
    current_url: str,
    base_url: str,
    rng: random.Random,
    timeout_ms: int = 15000,
) -> str | None:
    """
    Click a randomly selected internal link on the page.
    Returns the new URL on success, None on failure.
    """
    links = await collect_internal_links(page, base_url)
    # Exclude current page and empty hrefs
    links = [l for l in links if l and l != current_url]
    if not links:
        logger.debug("No internal links found on %s", current_url)
        return None

    target = rng.choice(links)
    logger.debug("Navigating internally to %s", target)

    # Move mouse to a believable position, then navigate (URL bar is realistic)
    viewport = page.viewport_size or {"width": 1280, "height": 800}
    await human.move_mouse(
        page,
        rng.uniform(100, viewport["width"] - 100),
        rng.uniform(100, viewport["height"] - 100),
        rng,
    )
    await asyncio.sleep(rng.uniform(0.3, 0.8))

    try:
        async with page.expect_navigation(timeout=timeout_ms, wait_until="domcontentloaded"):
            await page.goto(target, timeout=timeout_ms, wait_until="domcontentloaded")
        return page.url
    except Exception as exc:
        logger.debug("Internal navigation to %s failed: %s", target, exc)
        return None


async def run_session_pages(
    page: Page,
    start_url: str,
    cfg: dict,
    rng: random.Random,
    on_page_loaded: "AsyncCallable" = None,  # type: ignore[assignment]
) -> tuple[int, str]:
    """
    Navigate through 1–N pages in a session.
    Returns (pages_visited, final_url).
    on_page_loaded(page, url, page_num) is called after each page loads.
    """
    depth_min = cfg["session"]["page_depth_min"]
    depth_max = cfg["session"]["page_depth_max"]
    nav_prob = cfg["session"]["internal_nav_prob"]

    target_depth = rng.randint(depth_min, depth_max)
    pages_visited = 1
    current_url = start_url

    if on_page_loaded:
        await on_page_loaded(page, current_url, 1)

    while pages_visited < target_depth and rng.random() < nav_prob:
        new_url = await navigate_internal(page, current_url, start_url, rng)
        if new_url is None:
            break
        current_url = new_url
        pages_visited += 1
        if on_page_loaded:
            await on_page_loaded(page, current_url, pages_visited)

    return pages_visited, current_url

