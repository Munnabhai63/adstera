"""
ctr_guard.py — Rolling window CTR guard for Phase 2 AI Engine.

Tracks recent impressions and clicks to ensure click-through rate does not
breach configurable safety caps (soft_cap and hard_cap).
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CTRGuard:
    """Thread-safe rolling window tracking recent impressions and clicks to guard CTR.

    Attributes:
        window_size:   Maximum number of events to retain in the rolling window.
        hard_cap:      Maximum allowable CTR (0.0–1.0) before deferring actions.
        soft_cap:      Warning threshold for CTR.
        defer_seconds: Cooldown duration in seconds when deferred.
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        window_size: int = 200,
        hard_cap: float = 0.045,
        soft_cap: float = 0.036,
        defer_seconds: float = 30.0,
        min_samples: int = 20,
    ) -> None:
        if config is not None:
            self.window_size = getattr(config, "window_size", window_size)
            self.hard_cap = getattr(config, "hard_cap", hard_cap)
            self.soft_cap = getattr(config, "soft_cap", soft_cap)
            self.defer_seconds = float(getattr(config, "defer_seconds", defer_seconds))
        else:
            self.window_size = window_size
            self.hard_cap = hard_cap
            self.soft_cap = soft_cap
            self.defer_seconds = float(defer_seconds)

        self.min_samples = min(min_samples, max(5, self.window_size // 4))
        self._lock = threading.Lock()
        self._events: collections.deque[bool] = collections.deque(maxlen=self.window_size)
        self._defer_until: Optional[float] = None

    def record_impression(self, clicked: bool = False) -> None:
        """Record an impression event in the rolling window."""
        with self._lock:
            self._events.append(bool(clicked))

    def record_click(self) -> None:
        """Record a click event in the rolling window."""
        with self._lock:
            self._events.append(True)

    def current_ctr(self) -> float:
        """Compute the current CTR over the rolling window (0.0 to 1.0).

        Returns 0.0 if no impressions have been recorded.
        """
        with self._lock:
            n = len(self._events)
            if n == 0:
                return 0.0
            clicks = sum(1 for e in self._events if e)
            return float(clicks) / float(n)

    def would_breach(self, hard_cap: Optional[float] = None) -> bool:
        """Check if adding 1 click to the window would cause CTR > hard_cap.

        Args:
            hard_cap: Threshold to check against. Defaults to self.hard_cap.

        Returns:
            True if adding 1 click would cause CTR > hard_cap.
        """
        cap = self.hard_cap if hard_cap is None else hard_cap
        with self._lock:
            n = len(self._events)
            if n < self.min_samples:
                return False

            current_clicks = sum(1 for e in self._events if e)
            if (current_clicks / n) > cap:
                return True

            if n == self.window_size:
                oldest = self._events[0]
                projected_clicks = current_clicks + 1 - (1 if oldest else 0)
                projected_n = self.window_size
            else:
                projected_clicks = current_clicks + 1
                projected_n = n + 1

            projected_ctr = float(projected_clicks) / float(projected_n)
            return projected_ctr > cap

    def set_defer(self, seconds: Optional[float] = None) -> None:
        """Set deferral expiry timestamp."""
        sec = self.defer_seconds if seconds is None else float(seconds)
        with self._lock:
            self._defer_until = time.time() + sec
            logger.info("CTRGuard: deferred for %.1fs until %.1f", sec, self._defer_until)

    def defer_until(self) -> Optional[float]:
        """Return unix timestamp when deferral expires, or None if not deferred or expired."""
        with self._lock:
            if self._defer_until is None:
                return None
            if time.time() >= self._defer_until:
                self._defer_until = None
                return None
            return self._defer_until

    def is_deferred(self) -> bool:
        """Return True if currently deferred."""
        return self.defer_until() is not None

    def reset(self) -> None:
        """Clear all events and cancel any active deferral."""
        with self._lock:
            self._events.clear()
            self._defer_until = None
            logger.debug("CTRGuard: reset")
