"""
cookie_warmer.py — Autonomous Profile Pre-Warming Engine.
Visits authoritative commercial domains (Google, Wikipedia, Amazon, Forbes, TechCrunch)
to accumulate authentic commercial cookies before monetization visits.
Directly aligns with MAHI Browser's cookie-warmer-service.ts architecture.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.resolve()
WARMED_COOKIES_DIR = PROJECT_ROOT / "state" / "mahi_bridge" / "cookies"
WARMED_COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# Authoritative warming sites roster (Mirrored from MAHI Browser's cookie-warmer-service.ts)
WARMING_ROSTER = [
    # Search & Navigation
    {"url": "https://www.google.com", "name": "Google Search", "category": "Search", "weight": 10},
    {"url": "https://www.bing.com", "name": "Microsoft Bing", "category": "Search", "weight": 8},
    {"url": "https://duckduckgo.com", "name": "DuckDuckGo", "category": "Search", "weight": 7},

    # High-Intent Finance & Commercial (Highest CPM impact for Adsterra)
    {"url": "https://www.forbes.com", "name": "Forbes Media", "category": "Finance", "weight": 10},
    {"url": "https://www.cnn.com", "name": "CNN Business", "category": "News", "weight": 8},
    {"url": "https://www.bbc.com/news", "name": "BBC World News", "category": "News", "weight": 9},

    # E-Commerce & Retail Tracking Pixels
    {"url": "https://www.amazon.com", "name": "Amazon Storefront", "category": "Commerce", "weight": 10},
    {"url": "https://www.ebay.com", "name": "eBay Marketplace", "category": "Commerce", "weight": 8},

    # Tech, Software & Cloud Intent
    {"url": "https://techcrunch.com", "name": "TechCrunch", "category": "Tech", "weight": 9},
    {"url": "https://en.wikipedia.org/wiki/Artificial_intelligence", "name": "Wikipedia AI", "category": "Reference", "weight": 9},
    {"url": "https://en.wikipedia.org/wiki/Cloud_computing", "name": "Wikipedia Cloud", "category": "Reference", "weight": 8},
    {"url": "https://stackoverflow.com", "name": "Stack Overflow", "category": "Tech", "weight": 8},
]


class CookieWarmer:
    """Automates natural pre-session browsing across authoritative portals."""

    def __init__(self, cookies_dir: Optional[Path] = None):
        self.cookies_dir = cookies_dir or WARMED_COOKIES_DIR
        self.cookies_dir.mkdir(parents=True, exist_ok=True)

    def select_warming_targets(self, count: int = 2, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
        """Selects balanced authoritative warming sites across search, commerce, and news."""
        r = rng if rng is not None else random
        weights = [s["weight"] for s in WARMING_ROSTER]
        # Weighted sample without duplicates
        selected: List[Dict[str, Any]] = []
        available = list(WARMING_ROSTER)
        for _ in range(min(count, len(available))):
            w = [s["weight"] for s in available]
            chosen = r.choices(available, weights=w, k=1)[0]
            selected.append(chosen)
            available.remove(chosen)
        return selected

    async def warm_profile_session(
        self,
        context: BrowserContext,
        profile_id: str,
        site_count: int = 2,
        dwell_per_site: float = 8.0,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """
        Executes a lightweight, natural warming cycle:
        1. Opens page in the context.
        2. Performs small organic scroll to trigger pixel beacons.
        3. Dwells for configured interval.
        4. Saves persistent cookies state.
        """
        r = rng if rng is not None else random
        targets = self.select_warming_targets(count=site_count, rng=r)
        visited: List[str] = []
        t0 = time.time()

        page: Optional[Page] = None
        try:
            page = await context.new_page()

            for target in targets:
                url = target["url"]
                logger.info("Warming profile %s on %s (%s)...", profile_id, target["name"], url)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    visited.append(target["name"])

                    # Natural human micro-scroll to activate ad/tracking scripts
                    scroll_px = r.randint(250, 650)
                    await page.mouse.wheel(0, scroll_px)
                    await asyncio.sleep(r.uniform(2.5, min(dwell_per_site, 6.0)))

                    # Optional second micro-scroll
                    if r.random() < 0.6:
                        await page.mouse.wheel(0, r.randint(150, 350))
                        await asyncio.sleep(r.uniform(1.5, 3.5))

                except Exception as site_err:
                    logger.debug("Warming site %s skipped/timed out: %s", url, site_err)
                    continue

            # Extract accumulated cookies
            cookies = await context.cookies()
            cookies_count = len(cookies)

            # Save state
            state_file = self.cookies_dir / f"{profile_id}_state.json"
            await context.storage_state(path=str(state_file))
            logger.info(
                "Profile %s warmed successfully! %d cookies gathered across %d sites in %.1fs",
                profile_id, cookies_count, len(visited), time.time() - t0
            )

            return {
                "profile_id": profile_id,
                "success": True,
                "sites_visited": visited,
                "cookies_count": cookies_count,
                "state_file": str(state_file),
                "duration_s": round(time.time() - t0, 2),
            }

        except Exception as exc:
            logger.warning("Error during profile warming for %s: %s", profile_id, exc)
            return {
                "profile_id": profile_id,
                "success": False,
                "error": str(exc),
                "sites_visited": visited,
                "cookies_count": 0,
            }
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    def has_warmed_state(self, profile_id: str) -> bool:
        """Check if profile has already been warmed on disk."""
        f = self.cookies_dir / f"{profile_id}_state.json"
        return f.exists() and f.stat().st_size > 50

    def get_warmed_cookies_count(self, profile_id: str) -> int:
        """Read count of stored cookies from saved state JSON."""
        f = self.cookies_dir / f"{profile_id}_state.json"
        if not f.exists():
            return 0
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return len(data.get("cookies", []))
        except Exception:
            return 0

