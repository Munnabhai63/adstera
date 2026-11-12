"""A3 Quantile Revenue & eCPM Forecaster using pure-Python IRLS.

Fits P10 / P50 / P90 linear quantile regressions on 7..60 days of history via
Iteratively Reweighted Least Squares (IRLS), falling back gracefully to
median + IQR bands when fewer than `min_history_days` observations exist.
"""
from __future__ import annotations

import logging
import math
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from phase3.config_loader import A3ForecasterConfig, Phase3Config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.a3_forecaster.irls_quantile")


def _extract_a3_config(cfg: Any) -> A3ForecasterConfig:
    defaults = A3ForecasterConfig()
    if cfg is None:
        return defaults
    if isinstance(cfg, A3ForecasterConfig):
        return cfg
    if isinstance(cfg, Phase3Config):
        return cfg.a3_forecaster
    if hasattr(cfg, "a3_forecaster"):
        sub = getattr(cfg, "a3_forecaster")
        if isinstance(sub, A3ForecasterConfig):
            return sub
        if isinstance(sub, dict):
            return _dict_to_a3(sub, defaults)
    if isinstance(cfg, dict):
        sub = cfg.get("a3_forecaster", cfg)
        if isinstance(sub, dict):
            return _dict_to_a3(sub, defaults)
    return defaults


def _dict_to_a3(data: dict, defaults: A3ForecasterConfig) -> A3ForecasterConfig:
    return A3ForecasterConfig(
        quantiles=list(data.get("quantiles", defaults.quantiles)),
        min_history_days=int(data.get("min_history_days", defaults.min_history_days)),
        max_history_days=int(data.get("max_history_days", defaults.max_history_days)),
        irls_max_iter=int(data.get("irls_max_iter", defaults.irls_max_iter)),
        irls_tol=float(data.get("irls_tol", defaults.irls_tol)),
        irls_epsilon=float(data.get("irls_epsilon", defaults.irls_epsilon)),
        default_impressions_per_day=float(
            data.get("default_impressions_per_day", defaults.default_impressions_per_day)
        ),
        fallback_iqr_spread=float(data.get("fallback_iqr_spread", defaults.fallback_iqr_spread)),
    )


def _quantile_linear_interp(sorted_vals: Sequence[float], q: float) -> float:
    """Compute quantile q in [0, 1] via linear interpolation on sorted values."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _solve_weighted_linear_2x2(
    x_vals: Sequence[float],
    y_vals: Sequence[float],
    weights: Sequence[float],
    ridge: float = 1e-10,
) -> Tuple[float, float]:
    """Solve (X^T W X + ridge * I) [intercept, slope]^T = X^T W y in pure Python."""
    s00 = 0.0
    s01 = 0.0
    s11 = 0.0
    rhs0 = 0.0
    rhs1 = 0.0
    for x, y, w in zip(x_vals, y_vals, weights):
        s00 += w
        s01 += w * x
        s11 += w * x * x
        rhs0 += w * y
        rhs1 += w * x * y

    a = s00 + ridge
    b = s01
    c = s01
    d = s11 + ridge
    det = a * d - b * c
    if abs(det) < 1e-15:
        mean_y = rhs0 / s00 if s00 > 0.0 else 0.0
        return mean_y, 0.0

    intercept = (rhs0 * d - b * rhs1) / det
    slope = (a * rhs1 - rhs0 * c) / det
    return float(intercept), float(slope)


def fit_irls_quantile(
    y_vals: Sequence[float],
    tau: float,
    *,
    max_iter: int = 100,
    tol: float = 1e-6,
    epsilon: float = 1e-5,
) -> Tuple[float, float]:
    """Fit linear quantile regression y_t = intercept + slope * t using IRLS.

    Returns (intercept, slope).
    """
    n = len(y_vals)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return float(y_vals[0]), 0.0

    x_vals = [float(i) for i in range(n)]
    y_clean = [float(v) for v in y_vals]
    tau_c = min(0.999, max(0.001, float(tau)))
    eps = max(1e-9, float(epsilon))

    # Initialize from OLS
    ones = [1.0] * n
    intercept, slope = _solve_weighted_linear_2x2(x_vals, y_clean, ones)

    for _ in range(max(1, int(max_iter))):
        weights: List[float] = []
        for x, y in zip(x_vals, y_clean):
            r = y - (intercept + slope * x)
            denom = max(abs(r), eps)
            w = (tau_c / denom) if r >= 0.0 else ((1.0 - tau_c) / denom)
            weights.append(w)

        new_intercept, new_slope = _solve_weighted_linear_2x2(x_vals, y_clean, weights)
        if abs(new_intercept - intercept) < tol and abs(new_slope - slope) < tol:
            intercept, slope = new_intercept, new_slope
            break
        intercept, slope = new_intercept, new_slope

    return float(intercept), float(slope)


class IRLSQuantileForecaster:
    """Quantile revenue and eCPM forecaster using pure-Python IRLS."""

    def __init__(self, cfg: Any = None, store: Optional[Phase3Store] = None) -> None:
        self.cfg = _extract_a3_config(cfg)
        self.store = store
        self.min_history_days = max(1, int(self.cfg.min_history_days))
        self.max_history_days = max(self.min_history_days, int(self.cfg.max_history_days))
        self.irls_max_iter = max(1, int(self.cfg.irls_max_iter))
        self.irls_tol = max(1e-12, float(self.cfg.irls_tol))
        self.irls_epsilon = max(1e-9, float(self.cfg.irls_epsilon))
        self.default_impressions = max(1.0, float(self.cfg.default_impressions_per_day))
        self.fallback_iqr_spread = max(0.0, float(self.cfg.fallback_iqr_spread))

    def _parse_series(self, series: Iterable[Any]) -> Tuple[List[float], List[float]]:
        revenues: List[float] = []
        ecpms: List[float] = []
        if series is None:
            return revenues, ecpms

        for item in series:
            rev = 0.0
            ecpm = 0.0
            if isinstance(item, (int, float)):
                rev = float(item)
                ecpm = (rev / self.default_impressions) * 1000.0
            elif isinstance(item, dict):
                raw_rev = item.get("revenue", item.get("total_revenue", 0.0))
                rev = float(raw_rev) if raw_rev is not None else 0.0
                if "ecpm" in item and item["ecpm"] is not None:
                    ecpm = float(item["ecpm"])
                else:
                    impr = float(item.get("impressions") or self.default_impressions)
                    impr = impr if impr > 0.0 else self.default_impressions
                    ecpm = (rev / impr) * 1000.0
            else:
                continue

            if not (math.isfinite(rev) and math.isfinite(ecpm)):
                continue
            revenues.append(max(0.0, rev))
            ecpms.append(max(0.0, ecpm))

        if len(revenues) > self.max_history_days:
            revenues = revenues[-self.max_history_days :]
            ecpms = ecpms[-self.max_history_days :]
        return revenues, ecpms

    def _median_iqr_bands(self, values: Sequence[float]) -> Tuple[float, float, float]:
        if not values:
            return 0.0, 0.0, 0.0
        sorted_v = sorted(values)
        med = float(statistics.median(sorted_v))
        q25 = _quantile_linear_interp(sorted_v, 0.25)
        q75 = _quantile_linear_interp(sorted_v, 0.75)
        iqr = max(0.0, q75 - q25)
        half_band = iqr * 0.95 if iqr > 0.0 else med * self.fallback_iqr_spread
        p10 = max(0.0, med - half_band)
        p50 = max(p10, med)
        p90 = max(p50, med + half_band)
        return p10, p50, p90

    def forecast(self, series: Iterable[Any], horizon_days: int = 7) -> Dict[str, Any]:
        """Forecast P10/P50/P90 revenue (horizon total) and eCPM bands.

        Returns dict with keys:
            p10, p50, p90, ecpm_bands, method, sample_count,
            horizon_days, daily, slopes, intercepts.
        """
        horizon = max(1, int(horizon_days))
        try:
            revenues, ecpms = self._parse_series(series)
        except Exception as exc:
            log_event(logger, logging.ERROR, "a3_parse_series_failed", error=str(exc))
            revenues, ecpms = [], []

        n = len(revenues)

        if n < self.min_history_days:
            d_p10, d_p50, d_p90 = self._median_iqr_bands(revenues)
            e_p10, e_p50, e_p90 = self._median_iqr_bands(ecpms)
            result: Dict[str, Any] = {
                "p10": round(d_p10 * horizon, 6),
                "p50": round(d_p50 * horizon, 6),
                "p90": round(d_p90 * horizon, 6),
                "ecpm_bands": {
                    "p10": round(e_p10, 6),
                    "p50": round(e_p50, 6),
                    "p90": round(e_p90, 6),
                },
                "method": "median_fallback",
                "sample_count": n,
                "horizon_days": horizon,
                "daily": {
                    "p10": [round(d_p10, 6)] * horizon,
                    "p50": [round(d_p50, 6)] * horizon,
                    "p90": [round(d_p90, 6)] * horizon,
                },
                "slopes": {"p10": 0.0, "p50": 0.0, "p90": 0.0},
                "intercepts": {
                    "p10": round(d_p10, 6),
                    "p50": round(d_p50, 6),
                    "p90": round(d_p90, 6),
                },
            }
        else:
            q_list = list(self.cfg.quantiles) if len(self.cfg.quantiles) == 3 else [0.10, 0.50, 0.90]
            q_lo, q_mid, q_hi = sorted(float(q) for q in q_list)

            rev_models = {}
            ecpm_models = {}
            for label, tau in (("p10", q_lo), ("p50", q_mid), ("p90", q_hi)):
                rev_models[label] = fit_irls_quantile(
                    revenues,
                    tau,
                    max_iter=self.irls_max_iter,
                    tol=self.irls_tol,
                    epsilon=self.irls_epsilon,
                )
                ecpm_models[label] = fit_irls_quantile(
                    ecpms,
                    tau,
                    max_iter=self.irls_max_iter,
                    tol=self.irls_tol,
                    epsilon=self.irls_epsilon,
                )

            daily_p10: List[float] = []
            daily_p50: List[float] = []
            daily_p90: List[float] = []
            ecpm_p10_list: List[float] = []
            ecpm_p50_list: List[float] = []
            ecpm_p90_list: List[float] = []

            for step in range(horizon):
                t = float(n + step)
                r10 = max(0.0, rev_models["p10"][0] + rev_models["p10"][1] * t)
                r50 = max(0.0, rev_models["p50"][0] + rev_models["p50"][1] * t)
                r90 = max(0.0, rev_models["p90"][0] + rev_models["p90"][1] * t)
                r10, r50, r90 = sorted((r10, r50, r90))
                daily_p10.append(round(r10, 6))
                daily_p50.append(round(r50, 6))
                daily_p90.append(round(r90, 6))

                e10 = max(0.0, ecpm_models["p10"][0] + ecpm_models["p10"][1] * t)
                e50 = max(0.0, ecpm_models["p50"][0] + ecpm_models["p50"][1] * t)
                e90 = max(0.0, ecpm_models["p90"][0] + ecpm_models["p90"][1] * t)
                e10, e50, e90 = sorted((e10, e50, e90))
                ecpm_p10_list.append(e10)
                ecpm_p50_list.append(e50)
                ecpm_p90_list.append(e90)

            result = {
                "p10": round(sum(daily_p10), 6),
                "p50": round(sum(daily_p50), 6),
                "p90": round(sum(daily_p90), 6),
                "ecpm_bands": {
                    "p10": round(sum(ecpm_p10_list) / horizon, 6),
                    "p50": round(sum(ecpm_p50_list) / horizon, 6),
                    "p90": round(sum(ecpm_p90_list) / horizon, 6),
                },
                "method": "irls_quantile",
                "sample_count": n,
                "horizon_days": horizon,
                "daily": {
                    "p10": daily_p10,
                    "p50": daily_p50,
                    "p90": daily_p90,
                },
                "slopes": {
                    "p10": round(rev_models["p10"][1], 6),
                    "p50": round(rev_models["p50"][1], 6),
                    "p90": round(rev_models["p90"][1], 6),
                },
                "intercepts": {
                    "p10": round(rev_models["p10"][0], 6),
                    "p50": round(rev_models["p50"][0], 6),
                    "p90": round(rev_models["p90"][0], 6),
                },
            }

        if self.store is not None:
            try:
                self.store.log_forecast(
                    horizon_days=horizon,
                    sample_count=int(result["sample_count"]),
                    method=str(result["method"]),
                    p10_revenue=float(result["p10"]),
                    p50_revenue=float(result["p50"]),
                    p90_revenue=float(result["p90"]),
                    p10_ecpm=float(result["ecpm_bands"]["p10"]),
                    p50_ecpm=float(result["ecpm_bands"]["p50"]),
                    p90_ecpm=float(result["ecpm_bands"]["p90"]),
                )
            except Exception as exc:
                log_event(logger, logging.ERROR, "a3_store_persist_failed", error=str(exc))

        return result
