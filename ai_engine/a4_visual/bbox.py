"""
bbox.py – Bounding-box data model for A4 Visual Ad Detection.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class AdLabel(str, Enum):
    """Classification label for a detected ad element."""

    AD = "ad"
    BANNER = "banner"
    INTERSTITIAL = "interstitial"
    POPUNDER = "popunder"
    NONE = "none"


class AdNetwork(str, Enum):
    """Known ad network identifiers."""

    ADSTERRA = "adsterra"
    PROPELLER = "propeller"
    HILLTOP = "hilltop"
    UNKNOWN = "unknown"


@dataclass
class BoundingBox:
    """A detected ad bounding box with associated metadata.

    Attributes:
        x:          Left edge in pixels.
        y:          Top edge in pixels.
        w:          Width in pixels.
        h:          Height in pixels.
        confidence: Detection confidence in range [0.0, 1.0].
        label:      Ad classification label.
        network:    Inferred ad network.
        slot_type:  Slot category string (e.g. ``"banner"``, ``"interstitial"``).
    """

    x: int
    y: int
    w: int
    h: int
    confidence: float
    label: Any = AdLabel.AD
    network: Any = AdNetwork.UNKNOWN
    slot_type: str = "banner"

    def __post_init__(self) -> None:
        if isinstance(self.label, str):
            try:
                self.label = AdLabel(self.label.lower())
            except ValueError:
                self.label = AdLabel.AD
        if isinstance(self.network, str):
            try:
                self.network = AdNetwork(self.network.lower())
            except ValueError:
                self.network = AdNetwork.UNKNOWN

    @property
    def area(self) -> int:
        """Return the pixel area of this bounding box."""
        return self.w * self.h

    @property
    def center(self) -> Tuple[int, int]:
        """Return the (x, y) pixel coordinate of the box centre."""
        return (self.x + self.w // 2, self.y + self.h // 2)

    def random_click_point(self, seed: int = 0) -> Tuple[int, int]:
        """Return a deterministic random click point within 20-80% x, 25-75% y of this box.

        Args:
            seed: Integer seed for deterministic sampling.

        Returns:
            ``(px, py)`` pixel coordinate guaranteed to be inside the box.
        """
        raw = int(
            hashlib.sha256(
                f"{seed}:{self.x}:{self.y}:{self.w}:{self.h}".encode()
            ).hexdigest(),
            16,
        )
        # x in [20%, 80%] of width
        frac_x = 0.20 + (raw & 0xFFFF) / 0xFFFF * 0.60
        # y in [25%, 75%] of height
        frac_y = 0.25 + ((raw >> 16) & 0xFFFF) / 0xFFFF * 0.50
        return (int(self.x + frac_x * self.w), int(self.y + frac_y * self.h))

    def to_dict(self) -> dict:
        """Serialise this box to a plain dictionary suitable for JSON / SQLite storage."""
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "confidence": self.confidence,
            "label": self.label.value,
            "network": self.network.value,
            "slot_type": self.slot_type,
            "area": self.area,
            "center": list(self.center),
        }


@dataclass
class DetectionResult:
    """The full result of one A4 inference pass.

    Attributes:
        boxes:        All detected bounding boxes, ordered by confidence desc.
        source:       Which detector produced the result:
                      ``"vision"`` | ``"rule_fallback"`` | ``"none"``.
        inference_ms: Wall-clock time spent on inference in milliseconds.
        frame_id:     Unique identifier for the frame that was analysed.
    """

    boxes: List[BoundingBox] = field(default_factory=list)
    source: str = "none"
    inference_ms: float = 0.0
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def best(self) -> Optional[BoundingBox]:
        """Return the highest-confidence box that is not :attr:`AdLabel.NONE`, or ``None``."""
        candidates = [b for b in self.boxes if b.label != AdLabel.NONE]
        return max(candidates, key=lambda b: b.confidence) if candidates else None

    @property
    def label(self) -> str:
        """Convenience property: label of the best box or 'none'."""
        b = self.best
        return b.label.value if b else "none"

    @property
    def bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """Convenience property: (x, y, w, h) of the best box or None."""
        b = self.best
        return (b.x, b.y, b.w, b.h) if b else None

    @property
    def confidence(self) -> float:
        """Convenience property: confidence of best box or 0.0."""
        b = self.best
        return b.confidence if b else 0.0

    def is_confident(self, threshold: float) -> bool:
        """Return ``True`` when the best box confidence meets *threshold*.

        Args:
            threshold: Minimum acceptable confidence (0.0–1.0).
        """
        b = self.best
        return b is not None and b.confidence >= threshold


# Alias for backward compatibility
MultiDetectionResult = DetectionResult

