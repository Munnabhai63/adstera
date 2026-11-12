"""A6 NHPP Smart Scheduler using Lewis-Shedler thinning.

Generates human-plausible non-homogeneous Poisson inter-arrival delays driven by
a 24-hour diurnal curve, weekday scaling, and optional burst behavior.
"""
from __future__ import annotations

import datetime
import logging
import math
import random
import time
from typing import Any, List, Optional

from phase3.config_loader import A6SchedulerConfig, Phase3Config
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.a6_scheduler.nhpp")


def _extract_a6_config(cfg: Any) -> A6SchedulerConfig:
    """Resolve A6SchedulerConfig from Phase3Config, A6SchedulerConfig, dict, or None."""
    defaults = A6SchedulerConfig()
    if cfg is None:
        return defaults
    if isinstance(cfg, A6SchedulerConfig):
        return cfg
    if isinstance(cfg, Phase3Config):
        return cfg.a6_scheduler
    if hasattr(cfg, "a6_scheduler"):
        sub = getattr(cfg, "a6_scheduler")
        if isinstance(sub, A6SchedulerConfig):
            return sub
        if isinstance(sub, dict):
            return _dict_to_a6(sub, defaults)
    if isinstance(cfg, dict):
        sub = cfg.get("a6_scheduler", cfg)
        if isinstance(sub, dict):
            return _dict_to_a6(sub, defaults)
    return defaults


def _dict_to_a6(data: dict, defaults: A6SchedulerConfig) -> A6SchedulerConfig:
    return A6SchedulerConfig(
        base_sessions_per_hour=data.get("base_sessions_per_hour", defaults.base_sessions_per_hour),
        diurnal_curve=data.get("diurnal_curve", list(defaults.diurnal_curve)),
        weekday_scale=data.get("weekday_scale", list(defaults.weekday_scale)),
        min_delay_seconds=data.get("min_delay_seconds", defaults.min_delay_seconds),
        max_delay_seconds=data.get("max_delay_seconds", defaults.max_delay_seconds),
        burst_probability=data.get("burst_probability", defaults.burst_probability),
        burst_multiplier=data.get("burst_multiplier", defaults.burst_multiplier),
    )


class NHPPScheduler:
    """Lewis-Shedler thinning Non-Homogeneous Poisson Process scheduler."""

    def __init__(self, cfg: Any = None, rng: Optional[random.Random] = None) -> None:
        self.rng: random.Random = rng if rng is not None else random.Random()
        raw = _extract_a6_config(cfg)
        defaults = A6SchedulerConfig()

        # Sanitize numerical configuration with fail-safe fallbacks
        try:
            base_rate = float(raw.base_sessions_per_hour)
            if not math.isfinite(base_rate) or base_rate <= 0.0:
                raise ValueError(f"invalid base_sessions_per_hour={base_rate}")
            self.base_sessions_per_hour = base_rate
        except Exception as exc:
            log_event(logger, logging.WARNING, "nhpp_invalid_base_rate", error=str(exc))
            self.base_sessions_per_hour = defaults.base_sessions_per_hour

        self.diurnal_curve = self._sanitize_curve(
            raw.diurnal_curve, 24, defaults.diurnal_curve, "diurnal_curve"
        )
        self.weekday_scale = self._sanitize_curve(
            raw.weekday_scale, 7, defaults.weekday_scale, "weekday_scale"
        )

        try:
            min_d = float(raw.min_delay_seconds)
            max_d = float(raw.max_delay_seconds)
            if not (math.isfinite(min_d) and math.isfinite(max_d)) or min_d < 0.0 or max_d <= 0.0:
                raise ValueError(f"invalid delay bounds min={min_d}, max={max_d}")
            if min_d > max_d:
                min_d, max_d = max_d, min_d
            self.min_delay_seconds = min_d
            self.max_delay_seconds = max_d
        except Exception as exc:
            log_event(logger, logging.WARNING, "nhpp_invalid_delay_bounds", error=str(exc))
            self.min_delay_seconds = defaults.min_delay_seconds
            self.max_delay_seconds = defaults.max_delay_seconds

        try:
            bp = float(raw.burst_probability)
            bm = float(raw.burst_multiplier)
            if not math.isfinite(bp) or bp < 0.0 or bp > 1.0:
                raise ValueError(f"invalid burst_probability={bp}")
            if not math.isfinite(bm) or bm <= 0.0:
                raise ValueError(f"invalid burst_multiplier={bm}")
            self.burst_probability = bp
            self.burst_multiplier = bm
        except Exception as exc:
            log_event(logger, logging.WARNING, "nhpp_invalid_burst_cfg", error=str(exc))
            self.burst_probability = defaults.burst_probability
            self.burst_multiplier = defaults.burst_multiplier

        self._max_diurnal = max(self.diurnal_curve) if self.diurnal_curve else 1.0
        self._max_weekday = max(self.weekday_scale) if self.weekday_scale else 1.0

    def _sanitize_curve(
        self, curve: Any, expected_len: int, fallback: List[float], name: str
    ) -> List[float]:
        try:
            if not isinstance(curve, (list, tuple)) or len(curve) != expected_len:
                raise ValueError(f"{name} must have length {expected_len}")
            cleaned = [max(0.0, float(v)) for v in curve]
            if not all(math.isfinite(v) for v in cleaned) or max(cleaned) <= 0.0:
                raise ValueError(f"{name} has non-finite or all-zero entries")
            return cleaned
        except Exception as exc:
            log_event(logger, logging.WARNING, "nhpp_invalid_curve", curve=name, error=str(exc))
            return list(fallback)

    def intensity_at(self, ts: float) -> float:
        """Return instantaneous NHPP arrival rate lambda(t) in sessions per second."""
        try:
            ts_val = float(ts)
            if not math.isfinite(ts_val):
                raise ValueError(f"non-finite timestamp: {ts}")
            dt = datetime.datetime.fromtimestamp(ts_val)
            hour_weight = self.diurnal_curve[dt.hour % 24]
            day_weight = self.weekday_scale[dt.weekday() % 7]
            sessions_per_hour = self.base_sessions_per_hour * hour_weight * day_weight
            return max(0.0, sessions_per_hour / 3600.0)
        except Exception as exc:
            log_event(logger, logging.ERROR, "nhpp_intensity_error", error=str(exc))
            return max(1e-6, self.base_sessions_per_hour / 3600.0)

    def _fallback_delay(self) -> float:
        mid = max(self.min_delay_seconds, min(self.max_delay_seconds, 30.0))
        return float(mid)

    def schedule_next(self, now_ts: Optional[float] = None) -> float:
        """Sample next inter-arrival delay (seconds) via Lewis-Shedler thinning."""
        try:
            t0 = time.time() if now_ts is None else float(now_ts)
            if not math.isfinite(t0):
                raise ValueError(f"non-finite now_ts: {now_ts}")

            in_burst = self.burst_probability > 0.0 and self.rng.random() < self.burst_probability
            mult = self.burst_multiplier if in_burst else 1.0

            lambda_max = (
                self.base_sessions_per_hour * self._max_diurnal * self._max_weekday * mult
            ) / 3600.0
            if not math.isfinite(lambda_max) or lambda_max <= 0.0:
                return self._fallback_delay()

            elapsed = 0.0
            max_steps = 1000
            for _ in range(max_steps):
                u1 = self.rng.random()
                while u1 <= 0.0:
                    u1 = self.rng.random()
                dt = -math.log(u1) / lambda_max
                elapsed += dt

                if elapsed >= self.max_delay_seconds:
                    return float(self.max_delay_seconds)

                lam_t = self.intensity_at(t0 + elapsed) * mult
                accept_prob = min(1.0, max(0.0, lam_t / lambda_max))
                if self.rng.random() <= accept_prob:
                    break

            return float(max(self.min_delay_seconds, min(self.max_delay_seconds, elapsed)))
        except Exception as exc:
            log_event(logger, logging.ERROR, "nhpp_schedule_error", error=str(exc))
            return self._fallback_delay()
