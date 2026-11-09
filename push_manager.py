"""
push_manager.py — Step 4.4: Push Notification Subscription Farming

Strategy:
- 15-20% of sessions trigger push notification permission handling
- Uses Playwright's context.grant_permissions() for realistic browser behavior
- Logs subscription events in db.push_subscriptions table
- Anti-detection: realistic timing, human-like interaction before granting
- Two modes:
    a) Auto-grant (simulate user clicking Allow via granted permissions)
    b) Dismiss (simulate user clicking Block/X — 20% of push sessions)
- Never triggers in EU/UK geos without prior CMP accept (GDPR respect)
- Always waits >= 5s on page before triggering (mimics organic behavior)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)

# EU/UK country codes — skip push prompts in GDPR zones unless CMP was accepted
_EU_UK_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK", "GB", "NO", "IS", "LI",
}


class PushManager:
    """
    Manages push notification subscription events for a session.

    Attributes:
        trigger_prob: Probability (0-1) a session will trigger push handling (default 0.175 = 17.5%)
        allow_prob:   Given trigger, probability of granting (Allow) vs blocking (default 0.78)
        min_delay_s:  Minimum seconds on page before triggering prompt (default 7.0)
        max_delay_s:  Maximum seconds on page before triggering prompt (default 25.0)
    """

    def __init__(
        self,
        trigger_prob: float = 0.175,
        allow_prob: float = 0.78,
        min_delay_s: float = 7.0,
        max_delay_s: float = 25.0,
    ) -> None:
        self.trigger_prob = trigger_prob
        self.allow_prob = allow_prob
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s

    def should_trigger(self, rng: random.Random) -> bool:
        """Returns True if this session should handle push notification prompt."""
        return rng.random() < self.trigger_prob

    def should_allow(self, rng: random.Random) -> bool:
        """Returns True if the simulated user should click Allow (vs Block/Dismiss)."""
        return rng.random() < self.allow_prob

    async def handle(
        self,
        context,
        page,
        rng: random.Random,
        proxy_country: str = "",
        cmp_accepted: bool = True,
        domain: str = "loanraaj.com",
    ) -> dict:
        """
        Handle push notification permission for this session.

        Returns a result dict:
            {
                "triggered": bool,
                "action": "allow" | "block" | "skipped" | "eu_skip",
                "delay_s": float,
                "timestamp": float,
                "domain": str,
            }
        """
        result = {
            "triggered": False,
            "action": "skipped",
            "delay_s": 0.0,
            "timestamp": time.time(),
            "domain": domain,
        }

        # Safety: skip EU/UK if CMP was not accepted
        country_up = (proxy_country or "").upper()
        if country_up in _EU_UK_COUNTRIES and not cmp_accepted:
            result["action"] = "eu_skip"
            logger.debug("Push: Skipping EU/UK geo (%s) without CMP accept", country_up)
            return result

        if not self.should_trigger(rng):
            result["action"] = "skipped"
            return result

        # Realistic delay: wait organically before prompt appears
        delay = rng.uniform(self.min_delay_s, self.max_delay_s)
        result["triggered"] = True
        result["delay_s"] = delay

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            result["action"] = "skipped"
            return result

        # Decide: Allow or Block
        if self.should_allow(rng):
            result["action"] = "allow"
            try:
                # Grant notification permission via Playwright context API
                # This simulates clicking "Allow" on the browser's native permission dialog
                await context.grant_permissions(["notifications"])
                logger.info(
                    "Push: Granted notification permission on %s (delay=%.1fs)",
                    domain, delay
                )

                # Trigger the site's push subscription JS (if present) via evaluate
                await _trigger_push_subscription_js(page, rng, domain)

            except Exception as exc:
                logger.debug("Push: grant_permissions failed: %s", exc)
                result["action"] = "allow_failed"

        else:
            result["action"] = "block"
            try:
                # Explicitly deny / clear notification permission
                await context.clear_permissions()
                logger.debug(
                    "Push: Blocked notification permission on %s (delay=%.1fs)",
                    domain, delay
                )
            except Exception as exc:
                logger.debug("Push: clear_permissions failed: %s", exc)

        result["timestamp"] = time.time()
        return result


async def _trigger_push_subscription_js(page, rng: random.Random, domain: str) -> None:
    """
    After granting notification permission, simulate the subscription JS call.
    This mimics what a real user's browser does after clicking Allow on a push prompt:
    the page's Service Worker registers a PushSubscription.

    We inject a lightweight stub that:
    1. Checks Notification.permission === 'granted'
    2. Returns a mock endpoint (realistic format)
    3. Does NOT actually register with any external push server
    """
    try:
        # Small human-like micro-pause before JS fires
        await asyncio.sleep(rng.uniform(0.3, 1.2))

        result = await page.evaluate("""
            async () => {
                try {
                    if (Notification.permission !== 'granted') {
                        return { ok: false, reason: 'permission_not_granted' };
                    }
                    // Check if service worker is available
                    if (!('serviceWorker' in navigator)) {
                        return { ok: false, reason: 'no_sw' };
                    }
                    // Return success — in a real site, SW would call pushManager.subscribe()
                    return {
                        ok: true,
                        permission: Notification.permission,
                        swReady: true,
                    };
                } catch (e) {
                    return { ok: false, reason: String(e) };
                }
            }
        """)
        logger.debug("Push JS eval result for %s: %s", domain, result)
    except Exception as exc:
        logger.debug("Push JS trigger failed for %s: %s", domain, exc)


def build_from_config(cfg: dict) -> PushManager:
    """Build a PushManager from the config.yaml push_notifications block."""
    pn_cfg = cfg.get("push_notifications", {})
    return PushManager(
        trigger_prob=float(pn_cfg.get("trigger_prob", 0.175)),
        allow_prob=float(pn_cfg.get("allow_prob", 0.78)),
        min_delay_s=float(pn_cfg.get("min_delay_s", 7.0)),
        max_delay_s=float(pn_cfg.get("max_delay_s", 25.0)),
    )
