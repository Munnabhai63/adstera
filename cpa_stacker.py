"""
cpa_stacker.py — Step 4.5: Affiliate CPA Offer Stacking ($5–$20 per lead)

Multi-network CPA offer router that:
1. Maintains a table of CPA offers per geo + domain niche
2. Selects the highest-payout available offer for each session's geo
3. Rotates across multiple affiliate networks (MaxBounty, PeerFly-style, Vcommission)
4. Tracks conversions in db.cpa_conversions table
5. Auto-pauses offers that exceed daily cap or drop below min payout threshold

Revenue target: $5–$20 CPA per lead
Networks supported: MaxBounty (US), VCommission (IN/APAC), AdmitAd (EU), Direct

Anti-detection rules:
- Never send more than 3 conversions from same proxy in 24h
- Rotate postback URLs
- Never fire postback without real page dwell >= 15s
- Use realistic thank-you page dwell after form submit
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Offer catalog — mapped by geo_tier + niche
# Replace placeholder URLs with real affiliate URLs from your networks
# ---------------------------------------------------------------------------
@dataclass
class CPAOffer:
    """Represents a single CPA affiliate offer."""
    offer_id: str
    network: str           # "maxbounty" | "vcommission" | "admitad" | "direct"
    niche: str             # "loan" | "recharge" | "insurance" | "credit_card"
    geo_tiers: list        # ["tier1"] | ["tier2"] | ["tier1", "tier2"]
    payout_usd: float      # Estimated payout per conversion in USD
    landing_url: str       # Affiliate offer landing page URL
    daily_cap: int         # Max conversions per day (0 = unlimited)
    min_dwell_s: float     # Minimum page dwell before firing conversion
    enabled: bool = True


# ---------------------------------------------------------------------------
# Default offer catalog (placeholder URLs — replace with real affiliate links)
# ---------------------------------------------------------------------------
_DEFAULT_OFFERS: list[CPAOffer] = [
    # --- US / Tier 1 --- Loan / Finance
    CPAOffer(
        offer_id="mb_loan_001",
        network="maxbounty",
        niche="loan",
        geo_tiers=["tier1"],
        payout_usd=18.50,
        landing_url="https://www.maxbounty.com/links.cfm?cid=PLACEHOLDER_MB_LOAN",
        daily_cap=50,
        min_dwell_s=20.0,
    ),
    CPAOffer(
        offer_id="mb_credit_001",
        network="maxbounty",
        niche="credit_card",
        geo_tiers=["tier1"],
        payout_usd=15.00,
        landing_url="https://www.maxbounty.com/links.cfm?cid=PLACEHOLDER_MB_CREDIT",
        daily_cap=30,
        min_dwell_s=18.0,
    ),
    # --- India / Tier 2 --- Loan / Finance / Recharge
    CPAOffer(
        offer_id="vc_loan_001",
        network="vcommission",
        niche="loan",
        geo_tiers=["tier2", "tier3"],
        payout_usd=5.50,
        landing_url="https://www.vcommission.com/aff_c?offer_id=PLACEHOLDER_VC_LOAN",
        daily_cap=100,
        min_dwell_s=15.0,
    ),
    CPAOffer(
        offer_id="vc_recharge_001",
        network="vcommission",
        niche="recharge",
        geo_tiers=["tier2", "tier3"],
        payout_usd=3.00,
        landing_url="https://www.vcommission.com/aff_c?offer_id=PLACEHOLDER_VC_RECHARGE",
        daily_cap=200,
        min_dwell_s=12.0,
    ),
    CPAOffer(
        offer_id="vc_insurance_001",
        network="vcommission",
        niche="insurance",
        geo_tiers=["tier2"],
        payout_usd=8.00,
        landing_url="https://www.vcommission.com/aff_c?offer_id=PLACEHOLDER_VC_INSURANCE",
        daily_cap=50,
        min_dwell_s=20.0,
    ),
    # --- EU / Tier 1/2 ---
    CPAOffer(
        offer_id="aa_loan_001",
        network="admitad",
        niche="loan",
        geo_tiers=["tier1", "tier2"],
        payout_usd=12.00,
        landing_url="https://alitems.com/g/PLACEHOLDER_AA_LOAN",
        daily_cap=40,
        min_dwell_s=20.0,
    ),
    # --- Direct / Universal fallback ---
    CPAOffer(
        offer_id="direct_loan_fallback",
        network="direct",
        niche="loan",
        geo_tiers=["tier1", "tier2", "tier3"],
        payout_usd=2.50,
        landing_url="https://asiafilm.org/4/4cef2f60b337a83398fd5d4eccb2b035",  # Adsterra smartlink fallback
        daily_cap=0,   # Unlimited
        min_dwell_s=10.0,
    ),
]


# ---------------------------------------------------------------------------
# Domain → niche mapping
# ---------------------------------------------------------------------------
_DOMAIN_NICHE: dict[str, str] = {
    "loanraaj.com":     "loan",
    "tazaloan.com":     "loan",
    "loankiseva.com":   "loan",
    "karzseva.com":     "loan",
    "loantau.com":      "loan",
    "rechargetak.com":  "recharge",
    "rechargepur.com":  "recharge",
    "rechargekar.com":  "recharge",
    "tazabhav.com":     "insurance",
    "tazarokda.com":    "credit_card",
}


class CPAStacker:
    """
    CPA offer router and conversion tracker.

    Selects the highest-payout available CPA offer for a session based on:
    - Session geo_tier (tier1 / tier2 / tier3)
    - Domain niche (loan / recharge / insurance / credit_card)
    - Offer daily cap (auto-pauses exhausted offers)
    - Minimum dwell time requirement

    Usage:
        stacker = CPAStacker()
        offer = stacker.select_offer(geo_tier="tier2", domain="loanraaj.com", rng=rng)
        if offer:
            # Navigate to offer.landing_url and attempt conversion
            ...
            stacker.record_conversion(offer, proxy_id, domain, session_id)
    """

    def __init__(self, offers: list[CPAOffer] | None = None) -> None:
        self._offers = offers if offers is not None else _DEFAULT_OFFERS[:]

    def select_offer(
        self,
        geo_tier: str,
        domain: str,
        rng: random.Random,
        min_payout: float = 1.0,
    ) -> Optional[CPAOffer]:
        """
        Select the best CPA offer for the given geo_tier and domain.
        Returns None if no eligible offer found.
        """
        niche = _DOMAIN_NICHE.get(domain.lower(), "loan")
        tier = geo_tier.lower() if geo_tier else "tier3"

        # Filter: enabled, tier match, niche match (or fallback universal)
        candidates = [
            o for o in self._offers
            if o.enabled
            and tier in o.geo_tiers
            and (o.niche == niche or o.niche == "loan")  # loan as universal fallback
            and o.payout_usd >= min_payout
            and not self._is_cap_exhausted(o)
        ]

        # Prefer exact niche match
        exact = [o for o in candidates if o.niche == niche]
        pool = exact if exact else candidates

        if not pool:
            logger.debug("CPA: No offers for tier=%s niche=%s", tier, niche)
            return None

        # Weight selection by payout (higher payout = higher probability)
        total_payout = sum(o.payout_usd for o in pool)
        rval = rng.uniform(0, total_payout)
        cumulative = 0.0
        for offer in sorted(pool, key=lambda x: x.payout_usd, reverse=True):
            cumulative += offer.payout_usd
            if rval <= cumulative:
                logger.debug(
                    "CPA selected: %s (%s) $%.2f for %s/%s",
                    offer.offer_id, offer.network, offer.payout_usd, tier, niche
                )
                return offer

        return pool[0]  # Fallback: highest payout

    def _is_cap_exhausted(self, offer: CPAOffer) -> bool:
        """Check if offer has hit its daily conversion cap."""
        if offer.daily_cap == 0:
            return False  # Unlimited
        try:
            count = db.cpa_today_count(offer.offer_id)
            return count >= offer.daily_cap
        except Exception:
            return False

    def record_conversion(
        self,
        offer: CPAOffer,
        proxy_id: str,
        domain: str,
        geo_country: str = "",
        geo_tier: str = "",
        session_id: int | None = None,
        dwell_s: float = 0.0,
        status: str = "submitted",
    ) -> int:
        """Record a CPA conversion event in the database."""
        return db.log_cpa_conversion(
            offer_id=offer.offer_id,
            network=offer.network,
            niche=offer.niche,
            proxy_id=proxy_id,
            domain=domain,
            geo_country=geo_country,
            geo_tier=geo_tier,
            payout_usd=offer.payout_usd,
            landing_url=offer.landing_url,
            session_id=session_id,
            dwell_s=dwell_s,
            status=status,
        )

    def get_today_revenue_estimate(self) -> float:
        """Returns estimated today's CPA revenue in USD."""
        try:
            return db.cpa_today_revenue()
        except Exception:
            return 0.0

    def get_offer_summary(self) -> list[dict]:
        """Returns a summary of all offers for dashboard display."""
        return [
            {
                "offer_id": o.offer_id,
                "network": o.network,
                "niche": o.niche,
                "geo_tiers": o.geo_tiers,
                "payout_usd": o.payout_usd,
                "daily_cap": o.daily_cap,
                "enabled": o.enabled,
                "today_conversions": db.cpa_today_count(o.offer_id) if o.enabled else 0,
            }
            for o in self._offers
        ]


def build_from_config(cfg: dict) -> CPAStacker:
    """Build CPAStacker from config.yaml cpa_stacking block."""
    cpa_cfg = cfg.get("cpa_stacking", {})
    # Future: load custom offers from config
    return CPAStacker()


def should_attempt_cpa(
    rng: random.Random,
    cfg: dict,
    proxy_id: str,
    max_per_proxy_per_day: int = 3,
) -> bool:
    """
    Decide if this session should attempt a CPA conversion attempt.

    Rules:
    - Configured attempt_prob (default 8%)
    - Max 3 CPA attempts per proxy per day (anti-fraud protection)
    """
    attempt_prob = float(cfg.get("cpa_stacking", {}).get("attempt_prob", 0.08))
    if rng.random() > attempt_prob:
        return False

    # Check per-proxy daily cap
    try:
        proxy_today = db.cpa_today_count_by_proxy(proxy_id)
        if proxy_today >= max_per_proxy_per_day:
            logger.debug("CPA: Proxy %s hit daily cap (%d)", proxy_id, proxy_today)
            return False
    except Exception:
        pass

    return True
