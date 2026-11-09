"""
geo_router.py — Geo-Targeted Premium Traffic Routing Engine (Step 4.1).
Routes sessions based on proxy country tier to maximize eCPM and revenue:
  - Tier 1 (US, UK, CA, AU, DE, FR, etc.) -> High-CPC Direct Smartlinks & Finance sites ($8–$25 eCPM)
  - Tier 2 (IT, ES, BR, MX, AE, etc.) -> Mid-tier investment & trading portals ($3–$7 eCPM)
  - Tier 3 (IN, PK, BD, etc.) -> High-volume utility & recharge portals ($0.80–$2.20 eCPM)
"""
from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIER1_COUNTRIES = {
    "US", "GB", "UK", "CA", "AU", "DE", "FR", "NL", "CH", "SE", "NO", "DK", "NZ", "SG"
}

DEFAULT_TIER2_COUNTRIES = {
    "IT", "ES", "PL", "BR", "MX", "ZA", "AE", "SA", "KR", "JP", "TW", "IL", "PT", "GR"
}


def classify_geo_tier(country: Optional[str], custom_tier1: Optional[list[str]] = None) -> str:
    """
    Classify a 2-letter country code into 'tier1', 'tier2', or 'tier3'.
    Defaults to 'tier1' if country is unknown/empty to prioritize premium rates.
    """
    if not country or not isinstance(country, str):
        return "tier1"

    c = country.strip().upper()
    tier1_set = set(custom_tier1) if custom_tier1 else DEFAULT_TIER1_COUNTRIES

    if c in tier1_set:
        return "tier1"
    elif c in DEFAULT_TIER2_COUNTRIES:
        return "tier2"
    else:
        return "tier3"


def _get_dynamic_weights_for_urls(urls: list[str]) -> list[float]:
    from urllib.parse import urlparse
    try:
        from ecpm_feedback import EcpmFeedbackEngine
        engine = EcpmFeedbackEngine()
        weights_map = engine.get_active_weights()
    except Exception:
        weights_map = {}

    weights = []
    for u in urls:
        host = urlparse(u).netloc.split(":")[0].lower().strip()
        weights.append(weights_map.get(host, 1.0))
    return weights


def select_geo_target(
    cfg: dict,
    proxy_country: Optional[str],
    rng: random.Random,
) -> tuple[str, str]:
    """
    Select target URL and return (url, tier).
    If geo_routing is enabled, selects from tier-specific targets using dynamic eCPM weights.
    Otherwise falls back to standard target pool.
    """
    geo_cfg = cfg.get("geo_routing", {})
    if not geo_cfg.get("enabled", True):
        # Fall back to standard target selection
        tier = classify_geo_tier(proxy_country)
        return (_select_standard_target(cfg, rng), tier)

    custom_t1 = geo_cfg.get("tier1_countries")
    tier = classify_geo_tier(proxy_country, custom_t1)

    tier_key = f"{tier}_targets"
    pool = geo_cfg.get(tier_key)

    if pool and isinstance(pool, list):
        clean_pool = [u.strip() for u in pool if isinstance(u, str) and u.strip()]
        if clean_pool:
            weights = _get_dynamic_weights_for_urls(clean_pool)
            selected_url = rng.choices(clean_pool, weights=weights, k=1)[0]
            logger.info(
                "GeoRouter: Routed [%s (%s)] -> %s",
                proxy_country or "UNKNOWN",
                tier.upper(),
                selected_url,
            )
            return (selected_url, tier)

    # Fallback to standard URL pool if tier pool is empty
    return (_select_standard_target(cfg, rng), tier)


def _select_standard_target(cfg: dict, rng: random.Random) -> str:
    target_cfg = cfg.get("target", {})
    pool = target_cfg.get("urls") or target_cfg.get("url_pool")
    if pool and isinstance(pool, list):
        clean_pool = [u.strip() for u in pool if isinstance(u, str) and u.strip()]
        if clean_pool:
            weights = target_cfg.get("url_weights")
            if weights and isinstance(weights, list) and len(weights) == len(clean_pool):
                return rng.choices(clean_pool, weights=weights, k=1)[0]
            # Use dynamic eCPM weights if no static weights provided
            dyn_weights = _get_dynamic_weights_for_urls(clean_pool)
            return rng.choices(clean_pool, weights=dyn_weights, k=1)[0]
    return target_cfg.get("url", "https://loanraaj.com")


def get_estimated_ecpm(tier: str) -> float:
    """Return benchmark eCPM rate for reporting and revenue forecasting."""
    rates = {
        "tier1": 12.50,
        "tier2": 4.80,
        "tier3": 1.25,
    }
    return rates.get(tier, 2.50)
