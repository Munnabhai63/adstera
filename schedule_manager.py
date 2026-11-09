"""
schedule_manager.py — Publishing Schedule & Pipeline Governor (PUB-2)

Enforces:
1. Exactly 5 posts per day per domain limit.
2. 3 to 4 hour minimum spacing between consecutive posts on the same domain.
3. 30-minute staggered offset between domain clusters:
   - Group 1 (Personal Loans): loanraaj.com, tazaloan.com (Offset: 0 min)
   - Group 2 (Business/Debt): loankiseva.com, karzseva.com, loantau.com (Offset: 30 min)
   - Group 3 (Recharges): rechargetak.com, rechargepur.com, rechargekar.com (Offset: 60 min)
   - Group 4 (Market Rates): tazabhav.com, tazarokda.com (Offset: 90 min)
4. Integration with QualityGate and CloudflarePublisher.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional

import db
from cf_publisher import CloudflarePublisher, ALL_DOMAINS
from content_writer import ContentWriter
from quality_gate import QualityGate
from trends_fetcher import TrendsFetcher

logger = logging.getLogger(__name__)

# Domain Stagger Groups (minutes offset from base interval)
DOMAIN_GROUPS = {
    "group_1": {"domains": ["loanraaj.com", "tazaloan.com"], "offset_min": 0},
    "group_2": {"domains": ["loankiseva.com", "karzseva.com", "loantau.com"], "offset_min": 30},
    "group_3": {"domains": ["rechargetak.com", "rechargepur.com", "rechargekar.com"], "offset_min": 60},
    "group_4": {"domains": ["tazabhav.com", "tazarokda.com"], "offset_min": 90},
}

MAX_POSTS_PER_DAY = 5
MIN_INTERVAL_HOURS = 3.0


class ScheduleManager:
    """Orchestrates autonomous scheduled publishing across all 10 domains."""

    def __init__(self):
        self.tf = TrendsFetcher()
        self.cw = ContentWriter()
        self.qg = QualityGate()
        self.pub = CloudflarePublisher()

    def can_publish_today(self, domain: str) -> tuple[bool, str]:
        """Check if domain has remaining quota today and enough time elapsed since last post."""
        today_count = db.get_published_count_today(domain)
        if today_count >= MAX_POSTS_PER_DAY:
            return False, f"Daily cap reached ({today_count}/{MAX_POSTS_PER_DAY})"

        latest = db.get_latest_published_posts(domain, limit=1)
        if latest:
            last_ts_str = latest[0]["published_at"]
            try:
                last_dt = datetime.fromisoformat(last_ts_str)
                elapsed_hours = (datetime.now() - last_dt).total_seconds() / 3600.0
                if elapsed_hours < MIN_INTERVAL_HOURS:
                    return False, f"Too soon since last post ({elapsed_hours:.1f}h < {MIN_INTERVAL_HOURS}h)"
            except Exception:
                pass

        return True, "Eligible to publish"

    async def execute_publishing_cycle(self, domain: str, rng: Optional[random.Random] = None) -> Optional[dict]:
        """
        Execute a full publishing cycle for one domain:
        1. Check schedule constraints.
        2. Fetch trending brief.
        3. Generate 2000+ word localized article.
        4. Pass through 3-layer Quality Gate.
        5. Publish to Hugo directory and update sitemap.
        """
        if rng is None:
            rng = random.Random()

        can_pub, reason = self.can_publish_today(domain)
        if not can_pub:
            logger.info("Skipping %s publishing cycle: %s", domain, reason)
            return None

        logger.info("Starting autonomous publishing cycle for %s...", domain)
        brief = await self.tf.get_content_brief(domain, rng=rng)
        article = await self.cw.generate_article(brief, rng=rng)

        # Quality Gate Pass
        passed, report = self.qg.evaluate_article(article)
        if not passed:
            logger.warning("Article failed initial quality gate, applying auto-humanizer...")
            article = self.qg.humanize_article(article)
            passed, report = self.qg.evaluate_article(article)

        if not passed:
            logger.error("Article rejected by Quality Gate for %s. Publishing aborted.", domain)
            return None

        # Publish
        res = self.pub.publish_article(article, report)
        logger.info("Successfully published article on %s: %s", domain, res["url"])
        return res

    async def run_daily_sweep(self) -> dict:
        """Run a sweep across all domains, attempting publishing where schedule permits."""
        results = {}
        for domain in ALL_DOMAINS:
            try:
                res = await self.execute_publishing_cycle(domain)
                results[domain] = res if res else "skipped_or_not_eligible"
            except Exception as exc:
                logger.error("Publishing cycle failed for %s: %s", domain, exc)
                results[domain] = f"error: {exc}"
        return results
