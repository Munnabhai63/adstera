"""
interfaces.py — Protocol contracts and shared dataclasses for Phase 1 / Phase 2 boundary.

Phase 1 modules (db.py, mobile_adb.py, anomaly_detector.py) are never imported here;
only the structural Protocols they satisfy are defined so Phase 2 can type-check against
them without coupling.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence, Tuple, runtime_checkable


# ---------------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------------

BBox = Tuple[int, int, int, int]  # (x, y, w, h) in pixels


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AdDecision:
    """A decision produced by the AI engine for a single ad interaction.

    Attributes:
        action:     One of ``"click"``, ``"skip"``, or ``"defer"``.
        bbox:       Bounding box of the ad element (x, y, w, h). ``None`` for skip/defer.
        slot_type:  Ad slot type string (e.g. ``"banner"``, ``"popunder"``).
        domain:     Bare domain string of the publisher page (e.g. ``"example.com"``).
        timing_ms:  Milliseconds to wait before executing the action.
        reason:     Human-readable justification for logging and debugging.
    """

    action: str  # "click" | "skip" | "defer"
    bbox: Optional[BBox]
    slot_type: str
    domain: str
    timing_ms: int
    reason: str
    decision_id: str = ""


@dataclass
class AgentState:
    """Feature vector describing the current agent context for A1 LinTS.

    Attributes:
        domain_id:        Hashed integer identifier for the publisher domain.
        slot_type:        Ad slot type string.
        time_of_day_h:    Current hour (0–23) in the proxy's local timezone.
        recent_ctr:       CTR measured over the last rolling window.
        recent_rpm:       RPM measured over the last rolling window (USD).
        device_id_hash:   Stable integer hash of the ADB device serial.
        session_age_s:    Seconds elapsed since session start.
        bbox_confidence:  Visual confidence score (0.0–1.0) from A4; 0.0 if unavailable.
    """

    domain_id: int = 1
    slot_type: str = "banner"
    time_of_day_h: int = 12
    recent_ctr: float = 0.02
    recent_rpm: float = 1.5
    device_id_hash: int = 12345
    session_age_s: float = 30.0
    bbox_confidence: float = 0.8


@dataclass
class MetricsSnapshot:
    """Point-in-time metrics for a single session / window.

    Attributes:
        rpm:                    Revenue per mille impressions (USD).
        ctr:                    Click-through rate (0.0–1.0).
        empty_ad_rate:          Fraction of ad requests that returned no fill.
        load_time_ms:           Page (or ad) load time in milliseconds.
        error_rate:             Fraction of requests that resulted in an error.
        repeated_creative_rate: Fraction of impressions showing the same creative.
        ts:                     Unix timestamp when the snapshot was captured.
        domain:                 Publisher domain this snapshot belongs to.
        device_id:              ADB device serial (empty string if N/A).
    """

    rpm: float = 1.0
    ctr: float = 0.02
    empty_ad_rate: float = 0.0
    load_time_ms: float = 500.0
    error_rate: float = 0.0
    repeated_creative_rate: float = 0.0
    ts: float = field(default_factory=time.time)
    domain: str = ""
    device_id: str = ""


@dataclass
class AnomalyResult:
    """Result of a single anomaly detection check.

    Attributes:
        ok:        ``True`` when no anomaly was detected.
        severity:  One of ``"OK"``, ``"WARNING"``, or ``"CRITICAL"``.
        reasons:   List of human-readable descriptions of triggered anomalies.
        metrics:   The ``MetricsSnapshot`` that produced this result.
        scores:    Optional dict of per-metric z-scores or isolation scores.
    """

    ok: bool
    severity: str  # "OK" | "WARNING" | "CRITICAL"
    reasons: list[str]
    metrics: MetricsSnapshot
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Result of a visual (A4) ad detection inference.

    Attributes:
        label:      Predicted label (e.g. ``"banner"``).
        confidence: Model confidence score (0.0–1.0).
        bbox:       Detected bounding box, or ``None`` if no ad found.
        source:     ``"model"`` or ``"rule_fallback"``.
    """

    label: str
    confidence: float
    bbox: Optional[BBox]
    source: str  # "model" | "rule_fallback"


# ---------------------------------------------------------------------------
# Phase 1 Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Phase1TouchInterface(Protocol):
    """Structural contract satisfied by Phase 1 touch / input modules.

    Any object that implements these methods can be passed wherever a
    ``Phase1TouchInterface`` is expected.
    """

    def tap(self, x: int, y: int, duration_ms: int = 100) -> None:
        """Perform a tap gesture at screen coordinates ``(x, y)``.

        Args:
            x:           Horizontal pixel coordinate.
            y:           Vertical pixel coordinate.
            duration_ms: How long to hold the tap in milliseconds.
        """
        ...

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        """Perform a swipe from ``(x1, y1)`` to ``(x2, y2)``.

        Args:
            x1, y1:      Start coordinates.
            x2, y2:      End coordinates.
            duration_ms: Swipe duration in milliseconds.
        """
        ...


@runtime_checkable
class Phase1CaptureInterface(Protocol):
    """Structural contract satisfied by Phase 1 screen-capture modules."""

    def screenshot(self) -> bytes:
        """Capture the current device screen.

        Returns:
            Raw PNG bytes of the screenshot.
        """
        ...

    def dump_ui(self) -> str:
        """Dump the current UI hierarchy as an XML string.

        Returns:
            XML string representing the UI accessibility tree.
        """
        ...


@runtime_checkable
class Phase1DeviceInterface(Protocol):
    """Structural contract satisfied by Phase 1 device-management modules."""

    def list_devices(self) -> Sequence[str]:
        """Return serial numbers of all connected ADB devices.

        Returns:
            Sequence of device serial strings.
        """
        ...

    def is_alive(self, serial: str) -> bool:
        """Check whether the device is currently responsive.

        Args:
            serial: ADB device serial number.

        Returns:
            ``True`` if the device responds to a ping.
        """
        ...

    def get_device_info(self, serial: str) -> dict[str, Any]:
        """Return hardware and OS metadata for a device.

        Args:
            serial: ADB device serial number.

        Returns:
            Dictionary with keys such as ``model``, ``android_version``,
            ``resolution``, etc.
        """
        ...
