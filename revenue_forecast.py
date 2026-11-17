"""
revenue_forecast.py — Step 5.5: Revenue Forecasting & Anomaly Detection Model

Provides predictive revenue modeling from historical impressions, CPM, and CPA conversions:
- Ordinary Least Squares (OLS) linear trend estimation
- Trailing Moving Average (TMA) for baseline projection
- Day-of-week seasonality adjustment (weekday vs weekend variance)
- Multi-horizon forecasts: Next 7 Days and 30-Day Monthly Projection
- Real-time Anomaly Detection: Flags drops >20% below forecast (identifies silent bans/filter drops)
"""
from __future__ import annotations

import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Optional

import db

logger = logging.getLogger(__name__)

FORECAST_STATE_PATH = Path(__file__).parent / "state" / "revenue_forecast.json"

# Default weekday multipliers [Mon, Tue, Wed, Thu, Fri, Sat, Sun] from config scheduler
DEFAULT_WEEKDAY_SCALE = [1.00, 1.05, 1.08, 1.06, 1.00, 0.72, 0.66]


class RevenueForecaster:
    """Predictive revenue modeling and anomaly detection."""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        scheduler_cfg = self.cfg.get("scheduler", {})
        self.weekday_scale: list[float] = scheduler_cfg.get("weekday_scale", DEFAULT_WEEKDAY_SCALE)
        self.slope: float = 0.0
        self.intercept: float = 0.0
        self.trailing_avg: float = 0.0
        self.fitted: bool = False
        self.sample_count: int = 0

    def fit(self, history: list[dict] | None = None) -> "RevenueForecaster":
        """
        Fit linear trend line and moving average on historical daily revenue.
        If history is None, fetches up to 30 days from db.get_daily_revenue_history().
        """
        records = history if history is not None else db.get_daily_revenue_history(days=30)
        self.sample_count = len(records)

        if not records:
            # Cold start fallback: assume modest default baseline
            cpm = float(self.cfg.get("target", {}).get("cpm_rate", 2.50))
            cap = int(self.cfg.get("scheduler", {}).get("daily_cap", 2000))
            baseline = (cap * cpm) / 1000.0  # e.g. 2000 * 2.5 / 1000 = $5.00
            self.slope = 0.0
            self.intercept = baseline
            self.trailing_avg = baseline
            self.fitted = True
            return self

        y_vals = [float(r.get("total_revenue", 0.0)) for r in records]
        n = len(y_vals)

        # 7-day trailing average (or all available if <7)
        recent_window = y_vals[-7:] if n >= 7 else y_vals
        self.trailing_avg = sum(recent_window) / len(recent_window)

        if n < 2:
            self.slope = 0.0
            self.intercept = y_vals[0]
            self.fitted = True
            return self

        # OLS Linear Regression
        x_vals = list(range(n))
        x_bar = sum(x_vals) / n
        y_bar = sum(y_vals) / n

        numerator = sum((x - x_bar) * (y - y_bar) for x, y in zip(x_vals, y_vals))
        denominator = sum((x - x_bar) ** 2 for x in x_vals)

        if denominator > 1e-9:
            self.slope = numerator / denominator
            self.intercept = y_bar - (self.slope * x_bar)
        else:
            self.slope = 0.0
            self.intercept = y_bar

        self.fitted = True
        logger.debug(
            "RevenueForecaster fitted on %d samples: slope=%.4f, intercept=%.4f, trailing_avg=%.4f",
            n, self.slope, self.intercept, self.trailing_avg,
        )
        return self

    def predict_day(self, day_offset: int = 1, target_date: datetime.date | None = None) -> float:
        """
        Predict revenue for a day in the future (day_offset >= 1).
        Applies trend line bounded by non-negativity and day-of-week seasonality.
        """
        if not self.fitted:
            self.fit()

        future_x = (self.sample_count - 1) + day_offset
        trend_val = max(0.0, self.intercept + (self.slope * future_x))

        # Blend trend projection (40%) with trailing moving average (60%) for stability
        blended = (trend_val * 0.40) + (self.trailing_avg * 0.60)

        # Apply seasonality factor
        date_for_day = target_date or (datetime.date.today() + datetime.timedelta(days=day_offset))
        weekday_idx = date_for_day.weekday()  # Monday = 0, Sunday = 6
        multiplier = self.weekday_scale[weekday_idx] if weekday_idx < len(self.weekday_scale) else 1.0

        projected = max(0.0, blended * multiplier)
        return round(projected, 4)

    def forecast_next_7_days(self) -> list[dict[str, Any]]:
        """Produce day-by-day forecast for the upcoming 7 days."""
        if not self.fitted:
            self.fit()

        forecasts = []
        today = datetime.date.today()
        for i in range(1, 8):
            dt = today + datetime.timedelta(days=i)
            pred = self.predict_day(day_offset=i, target_date=dt)
            # 85% - 115% confidence interval
            forecasts.append({
                "date": dt.isoformat(),
                "day_name": dt.strftime("%A"),
                "projected_usd": pred,
                "confidence_low": round(pred * 0.85, 2),
                "confidence_high": round(pred * 1.15, 2),
            })
        return forecasts

    def forecast_monthly_estimate(self) -> float:
        """Estimate 30-day forward cumulative revenue in USD."""
        if not self.fitted:
            self.fit()
        total = sum(self.predict_day(day_offset=i) for i in range(1, 31))
        return round(total, 2)

    def detect_anomaly(
        self,
        actual_today: float,
        threshold_pct: float = 0.20,
        target_date: datetime.date | None = None,
    ) -> dict[str, Any]:
        """
        Compare actual revenue achieved today against projected revenue.
        If actual is > threshold_pct (default 20%) below projected, return anomaly details.
        """
        if not self.fitted:
            self.fit()

        eval_date = target_date or datetime.date.today()
        projected_today = self.predict_day(day_offset=0, target_date=eval_date)
        if projected_today <= 0.05:
            return {"anomaly": False, "reason": "Insufficient baseline revenue"}

        deficit = projected_today - actual_today
        deficit_pct = deficit / projected_today

        # Weekend seasonality calibration: On weekends (Sat/Sun), weekday_scale reduces
        # the seasonal projection (0.72 / 0.66). Deficit severity is evaluated against
        # both the seasonally adjusted expectation and the moving average baseline.
        weekday_idx = eval_date.weekday()
        multiplier = self.weekday_scale[weekday_idx] if weekday_idx < len(self.weekday_scale) else 1.0
        crit_threshold = 0.45 * multiplier if multiplier < 1.0 else 0.45

        if deficit_pct > threshold_pct:
            baseline_drop = (self.trailing_avg - actual_today) / self.trailing_avg if self.trailing_avg > 0 else deficit_pct
            is_critical = (deficit_pct >= 0.45) or (deficit_pct >= crit_threshold and baseline_drop >= 0.45)
            return {
                "anomaly": True,
                "severity": "CRITICAL" if is_critical else "WARNING",
                "actual_today": round(actual_today, 4),
                "projected_today": round(projected_today, 4),
                "deficit_pct": round(deficit_pct * 100, 1),
                "message": (
                    f"Revenue dropped {deficit_pct * 100:.1f}% below forecast "
                    f"(${actual_today:.2f} actual vs ${projected_today:.2f} projected). "
                    "Check for proxy blocks, smartlink expiration, or network account review."
                ),
            }

        return {
            "anomaly": False,
            "actual_today": round(actual_today, 4),
            "projected_today": round(projected_today, 4),
            "deviation_pct": round(deficit_pct * 100, 1),
        }

    def save_forecast_state(self) -> None:
        """Cache current projections to json for dashboard access."""
        try:
            FORECAST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "generated_at": datetime.datetime.now().isoformat(),
                "trailing_avg_usd": round(self.trailing_avg, 4),
                "trend_slope": round(self.slope, 6),
                "projected_next_7_days": self.forecast_next_7_days(),
                "projected_30_day_total_usd": self.forecast_monthly_estimate(),
            }
            FORECAST_STATE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed saving forecast report: %s", exc)


def build_from_config(cfg: dict) -> RevenueForecaster:
    return RevenueForecaster(cfg=cfg)
