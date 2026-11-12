"""
cmp.py — Consent Management Platform banner detection and acceptance.
"""
from __future__ import annotations

import asyncio
import logging
import random

from playwright.async_api import Page

import human

logger = logging.getLogger(__name__)

# Common CMP accept-button selectors (Didomi, OneTrust, Cookiebot, TrustArc, custom)
_ACCEPT_SELECTORS = [
    # Didomi
    "#didomi-notice-agree-button",
    "[data-didomi-action='agree']",
    # OneTrust
    "#onetrust-accept-btn-handler",
    ".onetrust-accept-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyButtonAccept",
    # TrustArc
    ".call",
    "a.trust-button.pdynamicbutton",
    # Generic
    "button[id*='accept']",
    "button[class*='accept']",
    "button[id*='agree']",
    "button[class*='agree']",
    "button[id*='consent']",
    "button[class*='consent']",
    "a[id*='accept']",
    "a[class*='accept']",
    # Fixture-specific (our test HTML)
    "#cmp-accept",
]

_REJECT_SELECTORS = [
    "#didomi-notice-disagree-button",
    "#onetrust-reject-all-handler",
    "button[id*='reject']",
    "button[class*='reject']",
    "#cmp-reject",
]


async def handle(
    page: Page,
    accept_prob: float = 0.88,
    rng: random.Random | None = None,
    timeout_ms: float = 3000,
    cdp_session: Any = None,
    is_mobile: bool = False,
) -> bool:
    """
    Detect and interact with a CMP banner on the current page.

    Returns True if a banner was found and acted upon, False if no banner found.
    88% chance of accepting, 12% chance of rejecting (or just closing).
    """
    if rng is None:
        rng = random.Random()

    # Short wait for banner to appear
    await asyncio.sleep(rng.uniform(0.8, 2.0))

    for sel in _ACCEPT_SELECTORS:
        try:
            elem = await page.query_selector(sel)
            if elem is None:
                continue
            visible = await elem.is_visible()
            if not visible:
                continue

            logger.debug("CMP banner found via selector: %s", sel)

            should_accept = rng.random() < accept_prob

            if should_accept:
                ok = await human.click_element(page, sel, rng, cdp_session=cdp_session, is_mobile=is_mobile)
                if ok:
                    logger.debug("CMP: accepted banner")
                    await asyncio.sleep(rng.uniform(0.5, 1.2))
                    return True
            else:
                # Try to find a reject button
                for rsel in _REJECT_SELECTORS:
                    relem = await page.query_selector(rsel)
                    if relem and await relem.is_visible():
                        await human.click_element(page, rsel, rng, cdp_session=cdp_session, is_mobile=is_mobile)
                        logger.debug("CMP: rejected banner")
                        await asyncio.sleep(rng.uniform(0.5, 1.2))
                        return True

                # BHV-6: Reject path — try close button (X), or scroll past banner without accepting
                close_selectors = ["[aria-label*='close']", "[aria-label*='Close']", ".close", "button.dismiss", "a.dismiss"]
                dismissed = False
                for csel in close_selectors:
                    celem = await page.query_selector(csel)
                    if celem and await celem.is_visible():
                        await human.click_element(page, csel, rng, cdp_session=cdp_session, is_mobile=is_mobile)
                        logger.debug("CMP: dismissed banner via close button %s", csel)
                        await asyncio.sleep(rng.uniform(0.5, 1.2))
                        dismissed = True
                        return True
                if not dismissed:
                    # User scrolled past banner without giving consent
                    logger.debug("CMP: BHV-6 reject active, ignoring banner without accepting")
                    await asyncio.sleep(rng.uniform(0.5, 1.0))
                    return True

        except Exception as exc:
            logger.debug("CMP selector %s error: %s", sel, exc)
            continue

    logger.debug("No CMP banner detected on this page")
    return False

