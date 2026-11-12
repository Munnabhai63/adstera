"""
metrics.py — Rolling metrics buffer and EWMA computation for the A2 anomaly detector.

Provides:

* :class:`MetricsBuffer` — a fixed-size circular buffer of
  :class:`~ai_engine.interfaces.MetricsSnapshot` objects that exposes rolling
  statistics (mean, standard deviation, EWMA) for each monitored metric field.

Usage::

    from ai_engine.a2_anomaly.metrics import MetricsBuffer
    from ai_engine.interfaces import MetricsSnapshot

    buf = MetricsBuffer(capacity=200, ewma_alpha=0.15)
    buf.push(snapshot)
    stats = buf.stats()
    print(stats["ctr"]["ewma"], stats["ctr"]["mean"], stats["ctr"]["std"])
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import asdict
from typing import Any, Deque, Dict

from ai_engine.interfaces import MetricsSnapshot

# Metric field names that the buffer tracks (must match MetricsSnapshot fields)
TRACKED_FIELDS: tuple[str, ...] = (
    "rpm",
    "ctr",
    "empty_ad_rate",
    "load_time_ms",
    "error_rate",
    "repeated_creative_rate",
)


class MetricsBuffer:
    """Circular buffer of :class:`MetricsSnapshot` objects with rolling statistics.

    The buffer holds up to *capacity* snapshots (oldest are evicted when full).
    For each tracked field it maintains:

    * **mean** — simple rolling mean.
    * **std**  — population standard deviation (Welford's online algorithm).
    * **ewma** — exponentially-weighted moving average with factor *ewma_alpha*.

    Args:
        capacity:   Maximum number of snapshots to retain (default 200).
        ewma_alpha: EWMA smoothing factor α (default 0.15).  Higher values
                    make the EWMA more responsive; lower values smoother.
    """

    def __init__(
        self,
        capacity: int = 200,
        ewma_alpha: float = 0.15,
        alpha: float | None = None,
        maxlen: int | None = None,
    ) -> None:
        if alpha is not None:
            ewma_alpha = alpha
        if maxlen is not None:
            capacity = maxlen
        self._capacity = max(1, capacity)
        self._alpha = float(ewma_alpha)
        self._buf: Deque[MetricsSnapshot] = deque(maxlen=self._capacity)

        # Online Welford accumulators: {field: (count, mean, M2)}
        self._welford: Dict[str, list[float]] = {
            f: [0.0, 0.0, 0.0] for f in TRACKED_FIELDS
        }
        # EWMA state: {field: current_ewma}
        self._ewma: Dict[str, float] = {f: 0.0 for f in TRACKED_FIELDS}
        self._ewma_initialised: Dict[str, bool] = {f: False for f in TRACKED_FIELDS}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def push(self, snapshot: MetricsSnapshot) -> None:
        """Add *snapshot* to the buffer and update all rolling statistics.

        When the buffer is at capacity the oldest snapshot's contribution is
        **not** removed from the Welford accumulators — this keeps the online
        variance estimate stable while the EWMA naturally de-weights old data.

        Args:
            snapshot: The new :class:`MetricsSnapshot` to ingest.
        """
        self._buf.append(snapshot)
        raw = asdict(snapshot)

        for field in TRACKED_FIELDS:
            val = float(raw.get(field, 0.0))

            # Welford online mean / variance update
            cnt, mean, m2 = self._welford[field]
            cnt += 1
            delta = val - mean
            mean += delta / cnt
            delta2 = val - mean
            m2 += delta * delta2
            self._welford[field] = [cnt, mean, m2]

            # EWMA update
            if not self._ewma_initialised[field]:
                self._ewma[field] = val
                self._ewma_initialised[field] = True
            else:
                self._ewma[field] = self._alpha * val + (1.0 - self._alpha) * self._ewma[field]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Dict[str, float]]:
        """Return rolling statistics for every tracked metric.

        Returns:
            Nested dict ``{field: {"mean": float, "std": float, "ewma": float}}``.
            ``std`` is ``0.0`` when fewer than two observations exist.
        """
        result: Dict[str, Dict[str, float]] = {}
        for field in TRACKED_FIELDS:
            cnt, mean, m2 = self._welford[field]
            std = math.sqrt(m2 / cnt) if cnt >= 2 else 0.0
            result[field] = {
                "mean": mean,
                "std": std,
                "ewma": self._ewma[field],
                "count": cnt,
            }
        return result

    def z_score(self, field: str, value: float) -> float:
        """Return the z-score of *value* relative to the rolling baseline.

        Uses the EWMA as the centre and the rolling std as the spread so that
        recent data is emphasised over the full Welford history.

        Args:
            field: One of the tracked metric names.
            value: The observed value to score.

        Returns:
            Z-score (unsigned distance in standard deviations).
            Returns ``0.0`` if std is effectively zero.
        """
        s = self.stats().get(field, {})
        centre = s.get("ewma", 0.0)
        spread = s.get("std", 0.0)
        if spread < 1e-9:
            return 0.0
        return abs(value - centre) / spread

    def latest(self) -> "MetricsSnapshot | None":
        """Return the most-recently pushed snapshot, or ``None`` if empty.

        Returns:
            Latest :class:`~ai_engine.interfaces.MetricsSnapshot` or ``None``.
        """
        if self._buf:
            return self._buf[-1]
        return None

    def update(self, snapshot: MetricsSnapshot) -> None:
        """Alias for push() for backwards compatibility."""
        self.push(snapshot)

    @property
    def ewma(self) -> Dict[str, float]:
        """Return dict of current EWMA values for tracked fields."""
        return dict(self._ewma)

    def __len__(self) -> int:
        """Return the current number of snapshots in the buffer."""
        return len(self._buf)

    @property
    def capacity(self) -> int:
        """Maximum number of snapshots the buffer can hold."""
        return self._capacity

    @property
    def ewma_alpha(self) -> float:
        """The EWMA smoothing factor α in use."""
        return self._alpha
