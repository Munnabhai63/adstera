"""Legacy revenue forecaster adapter wrapping root ``revenue_forecast.py``."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import log_event

# ASSUMPTION: Root `revenue_forecast` exposes `RevenueForecaster` with `fit`,
# `predict_day`, `forecast_next_7_days`, `forecast_monthly_estimate`, and `detect_anomaly`.
try:
    import revenue_forecast  # type: ignore
except Exception:  # pragma: no cover
    revenue_forecast = None  # type: ignore[assignment]

logger = logging.getLogger("phase3.adapters.revenue_legacy")


class RevenueLegacyAdapter:
    """Adapter around ``revenue_forecast.RevenueForecaster``."""

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        legacy_cfg: Optional[Dict[str, Any]] = None,
        forecaster: Optional[Any] = None,
    ) -> None:
        self.cfg = cfg or load_phase3_config()
        self.legacy_cfg = legacy_cfg or {
            "target": {"cpm_rate": float(self.cfg.adsterra.default_ecpm_usd)},
            "scheduler": {
                "daily_cap": int(self.cfg.b2_farm.target_daily_sessions),
                "weekday_scale": list(self.cfg.a6_scheduler.weekday_scale),
            },
        }
        self._forecaster = forecaster

    @property
    def forecaster(self) -> Any:
        if self._forecaster is None and revenue_forecast is not None:
            self._forecaster = revenue_forecast.RevenueForecaster(cfg=self.legacy_cfg)
        return self._forecaster

    def fit(self, history: Optional[List[Dict[str, Any]]] = None) -> "RevenueLegacyAdapter":
        """Fit legacy OLS + moving average forecaster on daily revenue records."""
        if self.forecaster is None:
            return self
        try:
            self.forecaster.fit(history=history)
        except Exception as exc:
            log_event(logger, logging.WARNING, "revenue_legacy_fit_failed", error=str(exc))
        return self

    def predict_day(self, day_offset: int = 1) -> float:
        if self.forecaster is None:
            return 0.0
        try:
            return float(self.forecaster.predict_day(day_offset=day_offset))
        except Exception as exc:
            log_event(logger, logging.WARNING, "revenue_legacy_predict_failed", error=str(exc))
            return 0.0

    def forecast_next_7_days(self) -> List[Dict[str, Any]]:
        if self.forecaster is None:
            return []
        try:
            return list(self.forecaster.forecast_next_7_days())
        except Exception as exc:
            log_event(logger, logging.WARNING, "revenue_legacy_7d_failed", error=str(exc))
            return []

    def forecast_monthly_estimate(self) -> float:
        if self.forecaster is None:
            return 0.0
        try:
            return float(self.forecaster.forecast_monthly_estimate())
        except Exception as exc:
            log_event(logger, logging.WARNING, "revenue_legacy_30d_failed", error=str(exc))
            return 0.0

    def detect_anomaly(self, actual_today: float, threshold_pct: float = 0.20) -> Dict[str, Any]:
        if self.forecaster is None:
            return {"anomaly": False, "reason": "forecaster unavailable"}
        try:
            return dict(self.forecaster.detect_anomaly(actual_today=actual_today, threshold_pct=threshold_pct))
        except Exception as exc:
            log_event(logger, logging.WARNING, "revenue_legacy_anomaly_failed", error=str(exc))
            return {"anomaly": False, "error": str(exc)}
