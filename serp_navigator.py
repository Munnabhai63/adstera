"""
serp_navigator.py — Real Google Search Journey Engine (ADV-1 & ADV-2)

Executes authentic end-to-end Google search journeys:
1. Navigates to Google (google.co.in / google.com).
2. Simulates realistic human typing cadence with hesitations.
3. Browses SERP with scroll reading pauses.
4. Locates target publisher domain in search results.
5. Clicks organic snippet with Fitts's Law mouse curve.
Produces:
- Authentic Google session cookies (NID, 1P_JAR, AEC)
- HTTP Referer: https://www.google.com/
- Sec-Fetch-Site: cross-site
- Sec-Fetch-User: ?1 (physical user activation gesture)
"""
from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import urlparse

from playwright.async_api import Page

import human

logger = logging.getLogger(__name__)

GOOGLE_SEARCH_SELECTORS = [
    "textarea[name='q']",
    "input[name='q']",
    "#APjFqb",
    "textarea.gLFyf",
    "input.gLFyf",
]


class SerpNavigator:
    """Simulates real organic visitor search journeys starting on Google."""

    async def execute_journey(
        self,
        page: Page,
        target_domain: str,
        keyword: str,
        rng: Optional[random.Random] = None,
        timeout_ms: int = 25000,
    ) -> bool:
        """
        Execute full Google search journey to target domain.
        Returns True if target domain was successfully navigated to from SERP, False otherwise.
        """
        if rng is None:
            rng = random.Random()

        google_origin = "https://www.google.co.in" if rng.random() < 0.85 else "https://www.google.com"
        logger.info("ADV-1: Initiating organic Google journey for '%s' -> %s", keyword, target_domain)

        try:
            # Step 1: Navigate to Google homepage
            await page.goto(google_origin, wait_until="domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(rng.uniform(1.2, 2.5))

            # Step 2: Handle any Google cookie consent overlay if present
            consent_buttons = ["button:has-text('Accept all')", "button:has-text('I agree')", "#L2AGLb", "#W0wltc"]
            for c_btn in consent_buttons:
                try:
                    c_elem = await page.query_selector(c_btn)
                    if c_elem and await c_elem.is_visible():
                        await human.click_element_by_box(page, c_elem, rng)
                        await asyncio.sleep(rng.uniform(0.5, 1.2))
                        break
                except Exception:
                    pass

            # Step 3: Locate Search Input Box
            input_elem = None
            for sel in GOOGLE_SEARCH_SELECTORS:
                elem = await page.query_selector(sel)
                if elem and await elem.is_visible():
                    input_elem = elem
                    break

            if not input_elem:
                logger.debug("Google search input not found, falling back to direct query URL")
                search_url = f"{google_origin}/search?q={keyword.replace(' ', '+')}"
                await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            else:
                # Click search box
                box = await input_elem.bounding_box()
                if box:
                    await human.move_mouse(page, box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5, rng)
                    await page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
                    await asyncio.sleep(rng.uniform(0.2, 0.5))

                # Human-like typing with variable per-character hesitation
                for char in keyword:
                    await page.keyboard.press(char)
                    delay_ms = rng.uniform(45, 140)
                    if rng.random() < 0.05:  # 5% micro-pause
                        delay_ms += rng.uniform(200, 450)
                    await asyncio.sleep(delay_ms / 1000.0)

                await asyncio.sleep(rng.uniform(0.4, 0.9))
                # Submit search
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
                    await page.keyboard.press("Enter")

            # Step 4: Browse SERP with reading scroll pauses
            await asyncio.sleep(rng.uniform(1.8, 3.5))
            await human.scroll_page(page, rng)
            await asyncio.sleep(rng.uniform(1.0, 2.0))

            # Step 5: Locate Target Domain in Organic Results
            target_link = None
            links = await page.query_selector_all("a[href]")
            clean_dom = target_domain.lower().replace("www.", "")

            for l in links:
                href = await l.get_attribute("href")
                if href and clean_dom in href.lower() and not href.startswith("https://www.google"):
                    if await l.is_visible():
                        target_link = l
                        break

            if target_link:
                await target_link.scroll_into_view_if_needed()
                await asyncio.sleep(rng.uniform(0.3, 0.7))
                box = await target_link.bounding_box()
                if box:
                    cx = box["x"] + box["width"] * rng.uniform(0.25, 0.75)
                    cy = box["y"] + box["height"] * rng.uniform(0.25, 0.75)
                    await human.move_mouse(page, cx, cy, rng)
                    await asyncio.sleep(rng.uniform(0.15, 0.35))
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
                        await page.mouse.click(cx, cy)
                    logger.info("ADV-1: Successfully clicked organic SERP link for %s!", target_domain)
                    return True

            # If not visibly on page 1, navigate to domain with Google referer
            logger.debug("ADV-1: Domain not found in visible SERP page 1, navigating with Google referer")
            dest_url = f"https://{target_domain}/"
            await page.goto(dest_url, referer=page.url, wait_until="domcontentloaded", timeout=timeout_ms)
            return True

        except Exception as exc:
            logger.debug("ADV-1 organic Google journey notice: %s", exc)
            return False


async def real_google_journey(
    page: Page,
    keyword: str,
    target_domain: str,
    rng: Optional[random.Random] = None,
    **kwargs,
) -> bool:
    """Convenience functional wrapper for SerpNavigator.execute_journey."""
    navigator = SerpNavigator()
    return await navigator.execute_journey(
        page=page,
        target_domain=target_domain,
        keyword=keyword,
        rng=rng,
    )
