"""
trends_fetcher.py — Google Trends & Live Search Query Engine (CONT-1)

Extracts high-intent, trending search queries and topics for 10 publisher domains:
1. Google Trends RSS (geo=IN) for breaking Indian financial/market developments.
2. Google Autocomplete/Suggest API for long-tail high-CPC keywords.
3. Domain-niche taxonomies for targeted content generation.
"""
from __future__ import annotations

import logging
import random
import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Domain Niche Taxonomy Mapping
DOMAIN_NICHES = {
    "loanraaj.com": {
        "niche": "Personal & Business Loans",
        "keywords": ["instant personal loan", "low interest home loan", "cibil score check", "aadhar card loan 50000", "salary advance loan app"],
        "category": "finance_loans"
    },
    "tazaloan.com": {
        "niche": "Instant Cash Loans & Salary Advance",
        "keywords": ["urgent cash loan today", "instant loan without pan card", "student loan app 2026", "emergency medical loan online"],
        "category": "finance_loans"
    },
    "loankiseva.com": {
        "niche": "MSME & Business Loan Schemes",
        "keywords": ["pm mudra loan apply online", "msme business loan subsidy", "mahila loan yojana", "startup business funding india"],
        "category": "finance_loans"
    },
    "karzseva.com": {
        "niche": "Debt Relief & Credit Repair",
        "keywords": ["how to clear credit card debt", "improve cibil score from 600 to 750", "loan settlement process in hindi", "debt consolidation loan"],
        "category": "finance_loans"
    },
    "loantau.com": {
        "niche": "Rural Credit & Gold Loans",
        "keywords": ["sbi gold loan per gram rate today", "kisan credit card apply online", "tractor loan interest rate", "gramin bank loan scheme"],
        "category": "finance_loans"
    },
    "rechargetak.com": {
        "niche": "Mobile Recharge & Cashback Offers",
        "keywords": ["jio best 84 days plan 2026", "airtel free data coupon code", "vi unlimited night data plan", "paytm recharge promo code"],
        "category": "recharge_utility"
    },
    "rechargepur.com": {
        "niche": "Bill Pay, UPI Deals & Rewards",
        "keywords": ["electricity bill payment cashback google pay", "fastag recharge offer today", "cred cashback trick 2026", "phonepe upi reward points"],
        "category": "recharge_utility"
    },
    "rechargekar.com": {
        "niche": "DTH & Utility Wallet Cashbacks",
        "keywords": ["tata play recharge plan 1 month", "airtel dth 6 month pack", "dish tv new connection price", "free gas cylinder subsidy check"],
        "category": "recharge_utility"
    },
    "tazabhav.com": {
        "niche": "Live Gold/Silver Rates & Financial Markets",
        "keywords": ["gold rate today 22k 24k", "silver price per kg live", "petrol diesel price today delhi mumbai", "lpg cylinder price today"],
        "category": "market_rates"
    },
    "tazarokda.com": {
        "niche": "Stock Trading & Wealth Building",
        "keywords": ["best dividend stocks for long term", "top mutual funds sip 2026", "ipo allotment status check", "penny stocks to buy today"],
        "category": "market_rates"
    },
}


class TrendsFetcher:
    """Async engine to extract live Google trends and autocomplete queries for publisher domains."""

    def __init__(self, timeout: float = 8.0):
        self._timeout = httpx.Timeout(timeout)

    def fetch_live_indian_trends_sync(self) -> list[str]:
        """Synchronously fetch breaking trending search queries from Google Trends India RSS."""
        url = "https://trends.google.com/trending/rss?geo=IN"
        trends: list[str] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        if title is not None and title.text:
                            trends.append(title.text.strip())
        except Exception as exc:
            logger.debug("Google Trends RSS sync fetch notice: %s", exc)
        return trends

    def fetch_suggest_queries_sync(self, seed: str) -> list[str]:
        """Synchronously fetch long-tail search queries from Google Autocomplete suggest API."""
        url = "https://suggestqueries.google.com/complete/search"
        params = {"client": "chrome", "q": seed, "hl": "hi"}
        queries: list[str] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                        queries = [str(q).strip() for q in data[1] if str(q).strip()]
        except Exception as exc:
            logger.debug("Google Suggest sync fetch notice for '%s': %s", seed, exc)
        return queries

    async def fetch_live_indian_trends(self) -> list[str]:
        """Fetch breaking trending search queries from Google Trends India RSS."""
        url = "https://trends.google.com/trending/rss?geo=IN"
        trends: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        if title is not None and title.text:
                            trends.append(title.text.strip())
        except Exception as exc:
            logger.debug("Google Trends RSS fetch notice: %s", exc)
        return trends

    async def fetch_suggest_queries(self, seed: str) -> list[str]:
        """Fetch long-tail search queries from Google Autocomplete suggest API."""
        url = "https://suggestqueries.google.com/complete/search"
        params = {"client": "chrome", "q": seed, "hl": "hi"}
        queries: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                        queries = [str(q).strip() for q in data[1] if str(q).strip()]
        except Exception as exc:
            logger.debug("Google Suggest fetch notice for '%s': %s", seed, exc)
        return queries

    async def get_content_brief(self, domain: str, rng: Optional[random.Random] = None) -> dict:
        """
        Generate a comprehensive, SEO-optimized topic brief for a specific publisher domain.
        Returns topic title, target keywords, long-tail variations, and content angles.
        """
        if rng is None:
            rng = random.Random()

        domain_info = DOMAIN_NICHES.get(domain, DOMAIN_NICHES["loanraaj.com"])
        keywords_pool = domain_info["keywords"]
        primary_seed = rng.choice(keywords_pool)

        # Retrieve Google Suggest autocomplete variations
        suggested = await self.fetch_suggest_queries(primary_seed)
        long_tails = suggested[:5] if suggested else [f"{primary_seed} online", f"{primary_seed} details", f"{primary_seed} eligibility"]

        # Title generation with current year and high CTR hook
        year = "2026"
        hooks = [
            f"{primary_seed.title()} {year}: Online Apply, Eligibility & Complete Process",
            f"{primary_seed.title()} — Benefits, Charges & Rules You Must Know ({year})",
            f"How to Get {primary_seed.title()} Instantly: Step-by-Step Guide for {year}",
            f"{primary_seed.title()}: Latest Updates, Comparison & Smart Tips ({year})",
        ]
        title = rng.choice(hooks)

        return {
            "domain": domain,
            "niche": domain_info["niche"],
            "category": domain_info["category"],
            "title": title,
            "primary_keyword": primary_seed,
            "long_tail_keywords": long_tails,
            "year": year,
        }
