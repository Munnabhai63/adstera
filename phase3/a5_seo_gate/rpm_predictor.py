"""A5 High-RPM Keyword Predictor using a Gamma-Poisson hierarchical model.

Combines Google Search Console (GSC) demand/CTR/position signals with
Adsterra historical eCPM/revenue/niche RPM signals under config-driven
Gamma priors (`phase3/config.yaml -> a5_seo_gate`).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from phase3.a5_seo_gate import resolve_a5_config
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.a5_seo_gate.rpm_predictor")

# Mathematical constants (not tunable hyperparameters)
PER_MILLE = 1000.0
MIN_SERP_POSITION = 1.0
DEFAULT_FALLBACK_POSITION = 10.0
CI_LOWER_QUANTILE = 0.025
CI_UPPER_QUANTILE = 0.975
GAMMA_EPS = 1e-12
SERIES_MAX_ITER = 300
BISECTION_ITER = 64


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Parse finite non-negative-safe float, returning ``default`` if malformed."""
    if val is None or isinstance(val, bool):
        return default
    try:
        parsed = float(val)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _pick_float(item: Dict[str, Any], nested: Dict[str, Any], keys: Tuple[str, ...], default: float = 0.0) -> float:
    """Return first valid finite float found across top-level or nested dict keys."""
    for source in (nested, item):
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source and source[key] is not None:
                val = _safe_float(source[key], float("nan"))
                if math.isfinite(val):
                    return val
    return default


def _regularized_gamma_p(alpha: float, x: float) -> float:
    """Compute regularized lower incomplete gamma P(alpha, x) in pure Python."""
    if x <= 0.0:
        return 0.0
    if alpha <= 0.0:
        return 1.0

    log_prefactor = -x + alpha * math.log(x) - math.lgamma(alpha)
    if x < alpha + 1.0:
        # Power series representation
        term = 1.0 / alpha
        total = term
        for k in range(1, SERIES_MAX_ITER + 1):
            term *= x / (alpha + k)
            total += term
            if abs(term) <= abs(total) * GAMMA_EPS:
                break
        return min(1.0, max(0.0, total * math.exp(log_prefactor)))

    # Continued fraction representation for Q(alpha, x) = 1 - P(alpha, x)
    b = x + 1.0 - alpha
    c = 1.0 / 1e-30
    d = 1.0 / max(b, 1e-30)
    h = d
    for i in range(1, SERIES_MAX_ITER + 1):
        an = -i * (i - alpha)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= GAMMA_EPS:
            break
    q = math.exp(log_prefactor) * h
    return min(1.0, max(0.0, 1.0 - q))


def _gamma_quantile(alpha: float, beta: float, prob: float) -> float:
    """Invert Gamma(alpha, beta) CDF at ``prob`` using bracketed bisection."""
    if alpha <= 0.0 or beta <= 0.0 or prob <= 0.0:
        return 0.0
    if prob >= 1.0:
        return float("inf")

    lo = 0.0
    hi = max(alpha + 10.0 * math.sqrt(alpha), 20.0)
    while _regularized_gamma_p(alpha, hi) < prob and hi < 1e12:
        hi *= 2.0

    for _ in range(BISECTION_ITER):
        mid = 0.5 * (lo + hi)
        if _regularized_gamma_p(alpha, mid) < prob:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi) / beta


class GammaPoissonRPMPredictor:
    """Hierarchical Gamma-Poisson RPM predictor and keyword ranker."""

    def __init__(self, cfg: Any = None) -> None:
        self.a5_cfg, self.adsterra_cfg = resolve_a5_config(cfg)

    def _extract_signals(self, item: Dict[str, Any]) -> Dict[str, float]:
        gsc_dict = item.get("gsc") if isinstance(item.get("gsc"), dict) else {}
        ads_dict = item.get("adsterra") if isinstance(item.get("adsterra"), dict) else {}

        gsc_impr = max(0.0, _pick_float(item, gsc_dict, ("gsc_impressions", "impressions"), 0.0))
        gsc_clicks = max(0.0, _pick_float(item, gsc_dict, ("gsc_clicks", "clicks"), 0.0))
        raw_ctr = _pick_float(item, gsc_dict, ("gsc_ctr", "ctr"), -1.0)
        if 0.0 <= raw_ctr <= 1.0:
            gsc_ctr = raw_ctr
        elif gsc_impr > 0.0:
            gsc_ctr = min(1.0, gsc_clicks / gsc_impr)
        else:
            gsc_ctr = max(0.0, self.adsterra_cfg.default_ctr)

        raw_pos = _pick_float(item, gsc_dict, ("gsc_position", "avg_position", "position"), 0.0)
        position = max(MIN_SERP_POSITION, raw_pos) if raw_pos > 0.0 else DEFAULT_FALLBACK_POSITION

        ad_impr = max(0.0, _pick_float(item, ads_dict, ("adsterra_impressions", "ad_impressions", "impressions" if ads_dict else ""), 0.0))
        revenue = max(0.0, _pick_float(item, ads_dict, ("adsterra_revenue", "revenue"), 0.0))
        hist_ecpm = max(0.0, _pick_float(item, ads_dict, ("historical_ecpm", "ecpm", "cpm"), 0.0))
        niche_rpm = max(0.0, _pick_float(item, ads_dict, ("niche_rpm", "category_rpm"), 0.0))

        return {
            "gsc_impressions": gsc_impr,
            "gsc_clicks": gsc_clicks,
            "gsc_ctr": gsc_ctr,
            "position": position,
            "ad_impressions": ad_impr,
            "revenue": revenue,
            "historical_ecpm": hist_ecpm,
            "niche_rpm": niche_rpm,
        }

    def predict_one(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Compute hierarchical Gamma-Poisson posterior RPM & confidence bounds for one keyword."""
        sig = self._extract_signals(item)

        alpha_0 = max(GAMMA_EPS, float(self.a5_cfg.gamma_prior_alpha))
        beta_0 = max(GAMMA_EPS, float(self.a5_cfg.gamma_prior_beta))
        w_gsc = max(0.0, float(self.a5_cfg.gsc_ctr_weight))
        w_ads = max(0.0, float(self.a5_cfg.adsterra_rpm_weight))
        pos_base = min(max(GAMMA_EPS, float(self.a5_cfg.position_decay_base)), 1.0)

        default_ecpm = max(GAMMA_EPS, float(self.adsterra_cfg.default_ecpm_usd))
        default_ctr = max(GAMMA_EPS, float(self.adsterra_cfg.default_ctr))

        # Hierarchical niche prior update: niche RPM informs the group-level prior rate.
        niche_rpm = sig["niche_rpm"]
        if niche_rpm > 0.0:
            alpha_prior = alpha_0 + niche_rpm * w_ads
            beta_prior = beta_0 + w_ads
        else:
            alpha_prior = alpha_0
            beta_prior = beta_0

        # Adsterra observed RPM & log-scaled exposure (keeps CI shrinking with volume
        # without allowing raw volume asymmetry to erase the GSC stream).
        ad_impr = sig["ad_impressions"]
        revenue = sig["revenue"]
        hist_ecpm = sig["historical_ecpm"]

        if ad_impr > 0.0 and revenue > 0.0:
            obs_ad_rpm = revenue / (ad_impr / PER_MILLE)
            e_ads = math.log1p(ad_impr / PER_MILLE)
        elif hist_ecpm > 0.0:
            obs_ad_rpm = hist_ecpm
            e_ads = math.log1p(ad_impr / PER_MILLE) if ad_impr > 0.0 else 1.0
        elif niche_rpm > 0.0:
            obs_ad_rpm = niche_rpm
            e_ads = 1.0
        else:
            obs_ad_rpm = 0.0
            e_ads = 0.0

        # GSC signal: CTR lift relative to baseline scaled by SERP position decay.
        position_factor = pos_base ** max(0.0, sig["position"] - MIN_SERP_POSITION)
        base_rpm_ref = niche_rpm if niche_rpm > 0.0 else (hist_ecpm if hist_ecpm > 0.0 else default_ecpm)
        ctr_ratio = sig["gsc_ctr"] / default_ctr
        gsc_implied_rpm = base_rpm_ref * ctr_ratio * position_factor

        gsc_impr = sig["gsc_impressions"]
        has_gsc_obs = gsc_impr > 0.0 or sig["gsc_clicks"] > 0.0 or any(
            k in item for k in ("ctr", "gsc_ctr", "position", "gsc_position", "avg_position")
        ) or (isinstance(item.get("gsc"), dict) and bool(item.get("gsc")))
        if gsc_impr > 0.0:
            e_gsc = math.log1p(gsc_impr / PER_MILLE)
        elif has_gsc_obs:
            e_gsc = 1.0
        else:
            e_gsc = 0.0

        post_alpha = alpha_prior + (w_ads * obs_ad_rpm * e_ads) + (w_gsc * gsc_implied_rpm * e_gsc)
        post_beta = beta_prior + (w_ads * e_ads) + (w_gsc * e_gsc)

        expected_rpm = post_alpha / post_beta
        ci_low = _gamma_quantile(post_alpha, post_beta, CI_LOWER_QUANTILE)
        ci_high = _gamma_quantile(post_alpha, post_beta, CI_UPPER_QUANTILE)

        # Conservative Empirical-Bayes score: midpoint between posterior mean and 2.5% lower bound.
        score = 0.5 * (expected_rpm + ci_low)

        result = dict(item)
        result.update(
            {
                "expected_rpm": round(expected_rpm, 6),
                "posterior_alpha": round(post_alpha, 6),
                "posterior_beta": round(post_beta, 6),
                "rpm_ci_low": round(ci_low, 6),
                "rpm_ci_high": round(ci_high, 6),
                "score": round(score, 6),
            }
        )
        return result

    def rank_keywords(self, keywords: Iterable[Any]) -> List[Dict[str, Any]]:
        """Rank a sequence of keyword dicts by descending Bayesian RPM score (fail-safe)."""
        if keywords is None or isinstance(keywords, (str, bytes, dict)):
            log_event(
                logger,
                logging.WARNING,
                "a5_rpm_invalid_keywords_container",
                received_type=type(keywords).__name__,
            )
            return []

        ranked: List[Dict[str, Any]] = []
        skipped = 0
        for raw in keywords:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            try:
                ranked.append(self.predict_one(raw))
            except Exception as exc:
                skipped += 1
                log_event(
                    logger,
                    logging.WARNING,
                    "a5_rpm_item_failed",
                    error=str(exc),
                )

        ranked.sort(key=lambda r: (r["score"], r["expected_rpm"]), reverse=True)
        log_event(
            logger,
            logging.INFO,
            "a5_rpm_ranked",
            total_ranked=len(ranked),
            skipped=skipped,
            top_score=ranked[0]["score"] if ranked else 0.0,
        )
        return ranked


def rank_keywords(keywords: List[Dict[str, Any]], cfg: Any = None) -> List[Dict[str, Any]]:
    """Module-level convenience wrapper for ``GammaPoissonRPMPredictor(cfg).rank_keywords``."""
    try:
        predictor = GammaPoissonRPMPredictor(cfg)
        return predictor.rank_keywords(keywords)
    except Exception as exc:
        log_event(logger, logging.ERROR, "a5_rpm_rank_failed", error=str(exc))
        return []
