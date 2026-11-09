"""
serp_synthesizer.py — Dynamic SERP Organic Search Referrer Synthesizer.

Pillar 3 of 5 Advanced Enterprise Pillars:
- Synthesizes authentic Google & Bing organic search queries per publisher domain
- Interpolates residential/mobile proxy geo location (City, State) into commercial intent queries
- Builds 100% legitimate Google Search Referrer URLs with genuine tracking parameters
- Simulates real user search engine journeys: search -> scroll SERP -> click organic result
- Eliminates direct-traffic clusters and invalid traffic (IVT) flags
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Optional

import yaml

import human

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger(__name__)

# Dynamic Query Templates by Domain Category & Niche
DOMAIN_QUERY_MATRIX: dict[str, list[str]] = {
    "loanraaj.com": [
        "best emergency personal loans low interest {city} {state}",
        "instant business loans same day approval {state}",
        "apply personal loan online fast pre approval {city}",
        "top rated personal loan EMI calculator 2026",
        "low interest unsecured loans {city} near me",
    ],
    "rechargetak.com": [
        "top prepaid mobile recharge cashback offers today",
        "best recharge coupon codes 100 percent cashback {city}",
        "airtel jio vi prepaid recharge discount deals 2026",
        "free mobile recharge promo code today",
        "latest telecom recharge plans and reward points",
    ],
    "rechargepur.com": [
        "best utility electricity bill payment cashback app",
        "online bill payment discount offers {city}",
        "water bill upi cashback rewards today",
        "pay electricity bill online get flat cashback",
        "broadband and gas cylinder bill payment coupon",
    ],
    "tazaloan.com": [
        "instant cash loan salary advance {city} {state}",
        "urgent cash loans 1 hour approval no collateral",
        "short term payday cash loans online {city}",
        "emergency instant cash advance without bank visit",
        "fast credit loan approval today in {city}",
    ],
    "loankiseva.com": [
        "government msme business loan schemes startup subsidy",
        "low interest small business loans mudra scheme",
        "commercial loan for women entrepreneurs {state}",
        "prime minister employment loan scheme eligibility 2026",
        "collateral free business financing options {city}",
    ],
    "karzseva.com": [
        "how to repair bad cibil credit score quickly",
        "bank loan debt settlement legal advice {city}",
        "best credit repair company reviews 2026",
        "remove negative loan defaults from cibil report",
        "one time loan settlement lawyer consultation {city}",
    ],
    "loantau.com": [
        "gold loan lowest interest rate per gram {city} {state}",
        "kisan credit card agriculture loan subsidy 2026",
        "tractor financing low down payment schemes {state}",
        "instant gold jewelry loan appraisal near me {city}",
        "rural housing loan eligibility and subsidy",
    ],
    "tazabhav.com": [
        "24k 22k gold rate today live market price {city}",
        "silver price per 10 gram today live chart",
        "todays commodity market bullion prices {city}",
        "gold rate forecast 2026 investment outlook",
        "live gold hallmarked jewelry rate per tola",
    ],
    "tazarokda.com": [
        "best zero brokerage demat trading account 2026",
        "top stock trading apps for beginners low fees",
        "mutual fund SIP return calculator highest yield",
        "best options trading platforms with advanced charting",
        "how to build long term wealth in stock market 2026",
    ],
    "rechargekar.com": [
        "dth recharge discount coupon code airtel tataplay",
        "fastag recharge 10 percent cashback upi offer",
        "metro smart card recharge discount coupons {city}",
        "best dth annual recharge packs cashback deals",
        "instant cable and dth wallet recharge promo code",
    ],
}

DEFAULT_US_GEOS = [
    {"city": "New York", "state": "NY"},
    {"city": "Dallas", "state": "TX"},
    {"city": "Chicago", "state": "IL"},
    {"city": "Atlanta", "state": "GA"},
    {"city": "Houston", "state": "TX"},
    {"city": "Miami", "state": "FL"},
    {"city": "Los Angeles", "state": "CA"},
    {"city": "Phoenix", "state": "AZ"},
]


class SerpSynthesizer:
    """Dynamic SERP organic search query generator and natural referrer builder."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

        serp_cfg = self.config.get("serp", {})
        self.enabled = serp_cfg.get("enabled", True)
        self.organic_prob = float(serp_cfg.get("organic_prob", 0.40))
        self.default_engine = serp_cfg.get("search_engine", "google")
        self.max_scroll_depth = int(serp_cfg.get("max_serp_scroll_depth", 3))

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", self.config_path, e)
        return {}

    def should_use_organic_serp(self, rng: Optional[random.Random] = None) -> bool:
        """Decide whether the session should arrive via a dynamic organic search referrer."""
        if not self.enabled:
            return False
        r = rng or random.Random()
        return r.random() < self.organic_prob

    def generate_query(
        self,
        domain: str,
        city: str = "Dallas",
        state: str = "TX",
        rng: Optional[random.Random] = None,
    ) -> str:
        """
        Generate a high-commercial-intent search query for the given domain,
        interpolating proxy geo city and state.
        """
        r = rng or random.Random()
        clean_dom = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]

        templates = DOMAIN_QUERY_MATRIX.get(clean_dom)
        if not templates:
            # Fallback based on keywords in domain
            if "loan" in clean_dom or "credit" in clean_dom:
                templates = DOMAIN_QUERY_MATRIX["loanraaj.com"]
            elif "recharge" in clean_dom:
                templates = DOMAIN_QUERY_MATRIX["rechargetak.com"]
            elif "bhav" in clean_dom or "rokda" in clean_dom:
                templates = DOMAIN_QUERY_MATRIX["tazarokda.com"]
            else:
                templates = [
                    "best online financial services and deals {city}",
                    "top personal utility portals in {city} {state}",
                ]

        raw_template = r.choice(templates)
        query = raw_template.replace("{city}", city).replace("{state}", state)
        return query.strip()

    def build_organic_referrer_url(
        self,
        domain: str,
        query: Optional[str] = None,
        city: str = "Dallas",
        state: str = "TX",
        engine: str = "google",
        rng: Optional[random.Random] = None,
    ) -> str:
        """
        Build an authentic Google or Bing search results referrer URL with genuine tracking parameters:
        Example: https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=&ved=2ahUKEwj...&url=...
        """
        r = rng or random.Random()
        q = query or self.generate_query(domain, city=city, state=state, rng=r)
        encoded_q = urllib.parse.quote_plus(q)

        target_url = f"https://{domain.lower().replace('https://', '').replace('http://', '').strip('/')}"

        if engine.lower() == "bing":
            # Microsoft Bing organic search referrer format
            return f"https://www.bing.com/search?q={encoded_q}&form=QBLH&sp=-1&lq=0&pq={encoded_q}&sc=10-14&qs=n&sk=&cvid={r.randint(1000000, 9999999)}"

        # Google Search referrer with realistic tracking parameters (ved, usg, sa)
        ved_seeds = [
            "2ahUKEwj7iK3c8uSIAxXQzDgGHX3mB_QQFnoECAkQAQ",
            "2ahUKEwiX3Mvd8-SIAxV84DgGHWp-A-cQFnoECBIQAQ",
            "2ahUKEwjN5-Pe8uSIAxW2xjgGHb7_CfcQFnoECBMQAQ",
            "2ahUKEwjZteff8uSIAxXJzzgGHQdLA7gQFnoECBEQAQ",
        ]
        ved = r.choice(ved_seeds)
        usg = f"AOvVaw{r.randint(10000000, 99999999)}xK"

        # 50% search query SERP referrer, 50% Google URL redirector click referrer
        if r.random() < 0.50:
            return f"https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=&ved={ved}&url={urllib.parse.quote_plus(target_url)}&usg={usg}"
        else:
            return f"https://www.google.com/search?q={encoded_q}&oq={encoded_q}&sourceid=chrome&ie=UTF-8"

    async def navigate_via_serp(
        self,
        page: Any,
        target_url: str,
        domain: str,
        city: str = "Dallas",
        state: str = "TX",
        fixture_path: Optional[str] = None,
        rng: Optional[random.Random] = None,
    ) -> dict[str, Any]:
        """
        Execute full natural search engine journey in real Playwright browser:
        1. Navigates to SERP.
        2. Types dynamic query into search input using human typing cadence.
        3. Scrolls through search results with reading pauses.
        4. Finds and clicks the target organic entry.
        5. Arrives on publisher page with valid Google Referrer context.
        """
        r = rng or random.Random()
        query = self.generate_query(domain, city=city, state=state, rng=r)
        start_time = asyncio.get_event_loop().time()

        # Step 1: Navigate to Search Engine or SERP Fixture
        if fixture_path and Path(fixture_path).exists():
            serp_url = Path(fixture_path).resolve().as_uri()
            await page.goto(serp_url, wait_until="domcontentloaded")
        else:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

        # Step 2: Human interaction on SERP (simulate query typing if search input exists)
        try:
            search_input = await page.query_selector('input[name="q"], textarea[name="q"], input[type="text"]')
            if search_input and await search_input.is_visible():
                await human.type_text_human(page, 'input[name="q"], textarea[name="q"]', query, rng=r)
                await asyncio.sleep(r.uniform(0.5, 1.2))
        except Exception:
            pass

        # Step 3: Browse search results (eased scroll)
        try:
            await human.scroll_page(page, rng=r)
            await asyncio.sleep(r.uniform(1.2, 2.5))
        except Exception:
            pass

        # Step 4: Find and click organic link for target domain
        clean_dom = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
        clicked = False

        candidate_selectors = [
            f'a[href*="{clean_dom}"]',
            '.g a.title',
            '.g a',
            'div[data-sokoban-container] a',
        ]

        for sel in candidate_selectors:
            try:
                link_el = await page.query_selector(sel)
                if link_el and await link_el.is_visible():
                    clicked = await human.click_element(page, sel, rng=r)
                    if clicked:
                        logger.info("SERP Synthesizer: Clicked organic link (%s) for %s", sel, clean_dom)
                        break
            except Exception:
                continue

        # If click didn't navigate (e.g. mock fixture), navigate directly with headers
        if not clicked:
            ref_url = self.build_organic_referrer_url(domain, query=query, city=city, state=state, rng=r)
            try:
                await page.goto(target_url, referer=ref_url, wait_until="domcontentloaded")
            except Exception:
                pass

        total_dwell = round(asyncio.get_event_loop().time() - start_time, 2)
        ref_header = self.build_organic_referrer_url(domain, query=query, city=city, state=state, rng=r)

        return {
            "success": True,
            "domain": domain,
            "target_url": target_url,
            "query": query,
            "engine": "google",
            "serp_dwell_sec": total_dwell,
            "organic_clicked": clicked,
            "referrer_header": ref_header,
        }

    def simulate_offline_serp(
        self,
        domain: str = "loanraaj.com",
        city: str = "Dallas",
        state: str = "TX",
    ) -> dict[str, Any]:
        """Generate simulated organic SERP referral data for offline verification."""
        q = self.generate_query(domain, city=city, state=state)
        ref = self.build_organic_referrer_url(domain, query=q, city=city, state=state)
        return {
            "domain": domain,
            "query": q,
            "engine": "google",
            "city": city,
            "state": state,
            "referrer_url": ref,
            "serp_dwell_sec": round(random.uniform(4.2, 8.5), 1),
            "organic_clicked": True,
        }


def print_serp_report(records: list[dict[str, Any]]) -> None:
    """Print an eye-readable summary of SERP organic queries for manual CMD audit."""
    print("\n" + "=" * 102)
    print(" [+] DYNAMIC SERP ORGANIC SEARCH REFERRER REPORT (PILLAR 3)")
    print("=" * 102)
    print(f"{'Domain':<16} | {'Geo':<14} | {'Synthesized Organic Google Query':<42} | {'SERP Dwell':>10}")
    print("-" * 102)

    for r in records:
        geo_str = f"{r['city']}, {r['state']}"
        print(
            f"{r['domain']:<16} | "
            f"{geo_str:<14} | "
            f"{r['query'][:42]:<42} | "
            f"{r['serp_dwell_sec']:>9.1f}s"
        )

    print("=" * 102)
    print(" Referrer Format: https://www.google.com/url?sa=t&rct=j&esrc=s&source=web&ved=2ahUKEwj...")
    print("=" * 102 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamic SERP Organic Search Referrer Synthesizer")
    parser.add_argument("--preview", action="store_true", help="Preview organic queries across all 10 publisher domains")
    parser.add_argument("--domain", type=str, default=None, help="Target specific domain")
    parser.add_argument("--city", type=str, default="Dallas", help="Simulate proxy geo city")
    parser.add_argument("--state", type=str, default="TX", help="Simulate proxy geo state")

    args = parser.parse_args()
    engine = SerpSynthesizer()

    domains_to_test = [args.domain] if args.domain else list(DOMAIN_QUERY_MATRIX.keys())
    results = []

    for idx, dom in enumerate(domains_to_test):
        geo = DEFAULT_US_GEOS[idx % len(DEFAULT_US_GEOS)]
        c_city = args.city if args.domain else geo["city"]
        c_state = args.state if args.domain else geo["state"]
        res = engine.simulate_offline_serp(domain=dom, city=c_city, state=c_state)
        results.append(res)

    print_serp_report(results)
