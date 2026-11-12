"""
detector.py — A2 Anomaly Detector: EWMA z-score + optional Isolation Forest.

This is the main entry point for Phase 2 anomaly detection.  It orchestrates:

1. :class:`~ai_engine.a2_anomaly.metrics.MetricsBuffer` — rolling baseline.
2. EWMA z-score checks for each metric defined in config.
3. Absolute threshold checks (rpm_floor, load_time_ceiling_ms, etc.).
4. Optional ``sklearn`` IsolationForest (graceful import — not required).
5. :class:`~ai_engine.safe_mode.SafeModeStateMachine` integration.
6. :class:`~ai_engine.store.AIStore` anomaly logging.
7. :class:`~ai_engine.a2_anomaly.alerts.AlertDispatcher` for WARNING+.

Usage::

    from ai_engine.a2_anomaly.detector import AnomalyDetector
    from ai_engine.config import load_ai_config
    from ai_engine.store import AIStore
    from ai_engine.safe_mode import SafeModeStateMachine
    from ai_engine.interfaces import MetricsSnapshot

    cfg = load_ai_config("ai_engine_config.yaml")
    store = AIStore(cfg.ai_engine.db_path)
    safe_mode = SafeModeStateMachine(cfg.a2_anomaly.safe_mode, store=store)
    detector = AnomalyDetector(cfg, store=store, safe_mode=safe_mode)

    snapshot = MetricsSnapshot(rpm=0.1, ctr=0.12, ...)
    result = detector.check(snapshot)
    detector.update_baseline(snapshot)
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, TYPE_CHECKING

from ai_engine.interfaces import AnomalyResult, MetricsSnapshot
from ai_engine.a2_anomaly.metrics import MetricsBuffer
from ai_engine.a2_anomaly.alerts import AlertDispatcher

if TYPE_CHECKING:
    from ai_engine.config import AIConfig
    from ai_engine.store import AIStore
    from ai_engine.safe_mode import SafeModeStateMachine

# Optional sklearn import — gracefully degraded when not installed
try:
    from sklearn.ensemble import IsolationForest as _IsolationForest  # type: ignore

    _SKLEARN_AVAILABLE = True
except ImportError:
    _IsolationForest = None  # type: ignore[assignment,misc]
    _SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

_SEVERITY_CRITICAL = "CRITICAL"
_SEVERITY_WARNING = "WARNING"
_SEVERITY_OK = "OK"


class AnomalyDetector:
    """A2 Anomaly Detector combining EWMA z-score and Isolation Forest.

    Args:
        config:    Full :class:`~ai_engine.config.AIConfig` instance.
        store:     Optional :class:`~ai_engine.store.AIStore` for logging.
        safe_mode: Optional :class:`~ai_engine.safe_mode.SafeModeStateMachine`
                   to enter on CRITICAL anomalies.
    """

    def __init__(
        self,
        config: Any,
        store: Optional["AIStore"] = None,
        safe_mode: Optional["SafeModeStateMachine"] = None,
        db_path: Optional[str] = None,
    ) -> None:
        if hasattr(config, "a2_anomaly"):
            self._cfg = config
            self._a2 = config.a2_anomaly
        else:
            self._cfg = None
            self._a2 = config

        self._store = store
        if self._store is None and db_path:
            try:
                from ai_engine.store import AIStore

                self._store = AIStore(db_path)
            except Exception as exc:
                logger.warning("detector: could not init AIStore(%r) — %s", db_path, exc)
                self._store = None

        self._safe_mode = safe_mode

        self._buffer = MetricsBuffer(
            capacity=self._a2.isolation_forest.n_estimators * 2
            if getattr(self._a2.isolation_forest, "enabled", False)
            else 200,
            ewma_alpha=getattr(self._a2, "ewma_alpha", 0.15),
        )
        self._dispatcher = AlertDispatcher(getattr(self._a2, "alert", None))

        # Isolation Forest state
        self._iso_forest: Optional[object] = None
        self._iso_trained: bool = False
        self._iso_min_samples: int = max(
            getattr(self._a2.isolation_forest, "n_estimators", 100), 50
        )

        if getattr(self._a2.isolation_forest, "enabled", False) and not _SKLEARN_AVAILABLE:
            logger.warning(
                "detector: isolation_forest.enabled=true but sklearn is not installed "
                "— falling back to z-score only"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, metrics: MetricsSnapshot) -> AnomalyResult:
        """Run all anomaly checks against *metrics* and return the result.

        Checks performed (in order):
        1. EWMA z-score for each configured metric field.
        2. Absolute floor/ceiling thresholds.
        3. Isolation Forest score (if trained and enabled).

        Side effects on WARNING+:
        * Logs each anomaly to :attr:`_store`.
        * Dispatches alert via :attr:`_dispatcher`.
        * On CRITICAL: calls :meth:`~ai_engine.safe_mode.SafeModeStateMachine.enter`.

        Args:
            metrics: The :class:`~ai_engine.interfaces.MetricsSnapshot` to evaluate.

        Returns:
            :class:`~ai_engine.interfaces.AnomalyResult` with ``ok``,
            ``severity``, ``reasons``, and ``scores``.
        """
        reasons: List[str] = []
        scores: dict[str, float] = {}
        severity = _SEVERITY_OK

        # 1. EWMA z-score checks
        for field in self._a2.metrics:
            val = getattr(metrics, field, None)
            if val is None:
                continue
            val = float(val)
            z = self._buffer.z_score(field, val)
            scores[f"z_{field}"] = z

            if z >= self._a2.z_threshold:
                lvl = _SEVERITY_CRITICAL if z >= self._a2.z_threshold * 1.5 else _SEVERITY_WARNING
                reasons.append(
                    f"{field} z-score={z:.2f} (value={val:.4f}, threshold={self._a2.z_threshold})"
                )
                severity = _merge_severity(severity, lvl)

        # 2. Absolute threshold checks
        abs_reasons, abs_severity = self._check_absolute_thresholds(metrics)
        reasons.extend(abs_reasons)
        severity = _merge_severity(severity, abs_severity)

        # 3. Isolation Forest
        if self._iso_trained and self._a2.isolation_forest.enabled and _SKLEARN_AVAILABLE:
            iso_score, iso_reason = self._check_isolation_forest(metrics)
            scores["iso_score"] = iso_score
            if iso_reason:
                reasons.append(iso_reason)
                severity = _merge_severity(severity, _SEVERITY_WARNING)

        ok = severity == _SEVERITY_OK
        result = AnomalyResult(
            ok=ok,
            severity=severity,
            reasons=reasons,
            metrics=metrics,
            scores=scores,
        )

        # Side effects
        if not ok:
            self._log_anomalies(result)
            self._dispatcher.dispatch(result)

            if severity == _SEVERITY_CRITICAL and self._safe_mode is not None:
                reason_summary = "; ".join(reasons[:2])
                self._safe_mode.enter(f"A2 CRITICAL: {reason_summary}")

        return result

    def update_baseline(self, metrics: MetricsSnapshot) -> None:
        """Add *metrics* to the rolling buffer and optionally retrain the forest.

        Call this **after** :meth:`check` on every snapshot so the baseline
        evolves as new data arrives.

        Args:
            metrics: The :class:`~ai_engine.interfaces.MetricsSnapshot` to ingest.
        """
        self._buffer.push(metrics)
        self._maybe_retrain_forest()

    # Backwards compatibility alias
    ingest = update_baseline

    # ------------------------------------------------------------------
    # Absolute threshold checks
    # ------------------------------------------------------------------

    def _check_absolute_thresholds(
        self, metrics: MetricsSnapshot
    ) -> tuple[List[str], str]:
        """Check hard thresholds independent of the rolling baseline.

        Args:
            metrics: Snapshot to check.

        Returns:
            Tuple of ``(reasons_list, highest_severity_string)``.
        """
        reasons: List[str] = []
        severity = _SEVERITY_OK

        # CTR hard cap spike
        hard_cap = getattr(getattr(self._cfg, "ctr_guard", None), "hard_cap", 0.045)
        if metrics.ctr >= hard_cap:
            reasons.append(
                f"ctr={metrics.ctr:.4f} >= hard_cap={hard_cap:.4f}"
            )
            severity = _merge_severity(severity, _SEVERITY_CRITICAL)

        # RPM floor
        if metrics.rpm < self._a2.rpm_floor:
            reasons.append(
                f"rpm={metrics.rpm:.4f} below floor={self._a2.rpm_floor}"
            )
            severity = _merge_severity(severity, _SEVERITY_WARNING)

        # Load time ceiling
        if metrics.load_time_ms > self._a2.load_time_ceiling_ms:
            reasons.append(
                f"load_time_ms={metrics.load_time_ms:.0f} above ceiling="
                f"{self._a2.load_time_ceiling_ms:.0f}"
            )
            severity = _merge_severity(severity, _SEVERITY_WARNING)

        # Empty ad spike
        if metrics.empty_ad_rate >= self._a2.empty_ad_spike_rate:
            reasons.append(
                f"empty_ad_rate={metrics.empty_ad_rate:.2%} >= spike_rate="
                f"{self._a2.empty_ad_spike_rate:.2%}"
            )
            severity = _merge_severity(severity, _SEVERITY_CRITICAL)

        # Repeated creative
        if metrics.repeated_creative_rate >= self._a2.repeated_creative_threshold:
            reasons.append(
                f"repeated_creative_rate={metrics.repeated_creative_rate:.2%} >= "
                f"threshold={self._a2.repeated_creative_threshold:.2%}"
            )
            severity = _merge_severity(severity, _SEVERITY_WARNING)

        return reasons, severity

    # ------------------------------------------------------------------
    # Isolation Forest
    # ------------------------------------------------------------------

    def _feature_vector(self, metrics: MetricsSnapshot) -> List[float]:
        """Extract a numeric feature vector from *metrics*.

        Args:
            metrics: Source snapshot.

        Returns:
            List of floats aligned to :attr:`_a2.metrics` field order.
        """
        return [
            float(getattr(metrics, f, 0.0)) for f in self._a2.metrics
        ]

    def _maybe_retrain_forest(self) -> None:
        """Retrain the Isolation Forest when enough samples have accumulated."""
        if not (self._a2.isolation_forest.enabled and _SKLEARN_AVAILABLE):
            return
        if len(self._buffer) < self._iso_min_samples:
            return

        # Build training matrix from buffer internals (access deque directly)
        X = [
            self._feature_vector(snap)
            for snap in self._buffer._buf  # type: ignore[attr-defined]
        ]
        try:
            forest = _IsolationForest(
                contamination=self._a2.isolation_forest.contamination,
                n_estimators=self._a2.isolation_forest.n_estimators,
                random_state=42,
            )
            forest.fit(X)
            self._iso_forest = forest
            self._iso_trained = True
            logger.debug(
                "detector: isolation forest retrained on %d samples", len(X)
            )
        except Exception as exc:
            logger.error("detector: isolation forest training failed — %s", exc)

    def _check_isolation_forest(
        self, metrics: MetricsSnapshot
    ) -> tuple[float, str]:
        """Score *metrics* with the trained Isolation Forest.

        Args:
            metrics: Snapshot to score.

        Returns:
            Tuple of ``(score, reason_string)``.
            ``score`` is the raw decision function value (negative = outlier).
            ``reason_string`` is non-empty only when an anomaly is flagged.
        """
        try:
            vec = [self._feature_vector(metrics)]
            score = float(self._iso_forest.decision_function(vec)[0])  # type: ignore[union-attr]
            pred = int(self._iso_forest.predict(vec)[0])  # type: ignore[union-attr]
            if pred == -1:
                return score, f"IsolationForest flagged outlier (score={score:.3f})"
            return score, ""
        except Exception as exc:
            logger.error("detector: isolation forest inference failed — %s", exc)
            return 0.0, ""

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_anomalies(self, result: AnomalyResult) -> None:
        """Persist each triggered reason to the store.

        Args:
            result: The anomaly result whose reasons should be logged.
        """
        if self._store is None:
            return
        # Log the top-level result once per check
        combined_metrics = ";".join(result.reasons[:5])
        z_repr = result.scores.get("z_ctr") or result.scores.get("iso_score") or 0.0
        try:
            self._store.log_anomaly(
                metric=combined_metrics[:128],
                value=result.metrics.ctr,
                z_score=z_repr,
                severity=result.severity,
                action="safe_mode_enter"
                if result.severity == _SEVERITY_CRITICAL
                else "",
                details=str(result.scores)[:512],
            )
        except Exception as exc:
            logger.error("detector: failed to log anomaly to store — %s", exc)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _merge_severity(current: str, new: str) -> str:
    """Return the higher of two severity strings.

    Order: ``OK`` < ``WARNING`` < ``CRITICAL``.

    Args:
        current: Existing severity level.
        new:     Candidate severity level.

    Returns:
        The higher severity of the two.
    """
    _rank = {_SEVERITY_OK: 0, _SEVERITY_WARNING: 1, _SEVERITY_CRITICAL: 2}
    if _rank.get(new, 0) > _rank.get(current, 0):
        return new
    return current


if __name__ == "__main__":
    import argparse
    from ai_engine.config import load_ai_config

    parser = argparse.ArgumentParser(description="A2 Anomaly Detector CLI")
    parser.add_argument("--config", default="ai_engine_config.yaml", help="Path to config")
    parser.add_argument("--rpm", type=float, default=1.5, help="Sample RPM")
    parser.add_argument("--ctr", type=float, default=0.02, help="Sample CTR")
    args = parser.parse_args()

    cfg = load_ai_config(args.config)
    detector = AnomalyDetector(cfg)
    snap = MetricsSnapshot(rpm=args.rpm, ctr=args.ctr)
    res = detector.check(snap)
    print(f"A2 Anomaly check result: ok={res.ok}, severity={res.severity}, reasons={res.reasons}")

