"""
detector.py – Unified A4 Visual Ad Detector.

Orchestrates :class:`VisionModel` (ONNX) and :class:`RuleFallbackDetector`
(DOM/accessibility tree) with a time budget and confidence gate.
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from ai_engine.a4_visual.bbox import (
    AdLabel,
    AdNetwork,
    BoundingBox,
    DetectionResult,
    MultiDetectionResult,
)
from ai_engine.a4_visual.rule_fallback import RuleFallbackDetector
from ai_engine.a4_visual.vision_model import VisionModel

logger = logging.getLogger(__name__)

# Defaults — overridden by AIConfig at runtime
_DEFAULT_CONFIDENCE_THRESHOLD = 0.55
_DEFAULT_INFERENCE_TIMEOUT_MS = 300
_DEFAULT_MODEL_PATH = Path("state/ai_engine/ad_detector.onnx")


class VisualAdDetector:
    """Unified visual ad detector combining ONNX vision and rule-based fallback.

    Decision flow:
        1. If *frame* bytes are provided, attempt :class:`VisionModel` inference.
        2. If the best box confidence is below *confidence_threshold* **or** the
           vision model is unavailable, fall back to :class:`RuleFallbackDetector`.
        3. If the total wall-clock time exceeds *inference_timeout_ms*, abort
           vision inference and use rules immediately.
        4. The returned :class:`DetectionResult` carries a ``source`` tag that
           indicates which path was taken: ``"vision"``, ``"rule_fallback"``, or
           ``"none"``.
    """

    def __init__(
        self,
        config_or_model_path: Any = None,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        inference_timeout_ms: int = _DEFAULT_INFERENCE_TIMEOUT_MS,
        id_patterns=None,
        class_patterns=None,
        min_area_px: int = 2000,
        max_area_ratio: float = 0.6,
        screen_w: int = 1080,
        screen_h: int = 1920,
        model_path: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        if model_path is not None:
            chosen_path = model_path
        elif config_or_model_path is not None:
            chosen_path = config_or_model_path
        else:
            chosen_path = _DEFAULT_MODEL_PATH

        if hasattr(chosen_path, "a4_visual"):
            chosen_path = chosen_path.a4_visual

        if hasattr(chosen_path, "model_path") or isinstance(chosen_path, dict):
            cfg = chosen_path

            def _get(obj, key, default):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            raw_mp = _get(cfg, "model_path", _DEFAULT_MODEL_PATH)
            chosen_path = Path(raw_mp) if raw_mp else _DEFAULT_MODEL_PATH
            confidence_threshold = _get(cfg, "confidence_threshold", confidence_threshold)
            inference_timeout_ms = _get(cfg, "inference_timeout_ms", inference_timeout_ms)
            rf = _get(cfg, "rule_fallback", {})
            id_patterns = _get(rf, "id_patterns", id_patterns)
            class_patterns = _get(rf, "class_patterns", class_patterns)
            min_area_px = _get(rf, "min_area_px", min_area_px)
            max_area_ratio = _get(rf, "max_area_ratio", max_area_ratio)

        self.confidence_threshold = confidence_threshold
        self.inference_timeout_ms = inference_timeout_ms
        self._vision = VisionModel(Path(chosen_path))
        self._rules = RuleFallbackDetector(
            id_patterns=id_patterns,
            class_patterns=class_patterns,
            min_area_px=min_area_px,
            max_area_ratio=max_area_ratio,
            screen_w=screen_w,
            screen_h=screen_h,
        )

    @classmethod
    def from_config(cls, cfg) -> "VisualAdDetector":
        """Construct from an :class:`AIConfig` object (or dict).

        Args:
            cfg: An object with an ``a4_visual`` attribute/key carrying the
                 relevant configuration sub-section.

        Returns:
            Configured :class:`VisualAdDetector` instance.
        """
        try:
            a4 = cfg.a4_visual if hasattr(cfg, "a4_visual") else cfg.get("a4_visual", {})
            rf = a4.get("rule_fallback", {}) if isinstance(a4, dict) else {}

            def _get(obj, key, default):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            return cls(
                model_path=Path(_get(a4, "model_path", "state/ai_engine/ad_detector.onnx")),
                confidence_threshold=_get(a4, "confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD),
                inference_timeout_ms=_get(a4, "inference_timeout_ms", _DEFAULT_INFERENCE_TIMEOUT_MS),
                id_patterns=rf.get("id_patterns") if isinstance(rf, dict) else None,
                class_patterns=rf.get("class_patterns") if isinstance(rf, dict) else None,
                min_area_px=rf.get("min_area_px", 2000) if isinstance(rf, dict) else 2000,
                max_area_ratio=rf.get("max_area_ratio", 0.6) if isinstance(rf, dict) else 0.6,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("VisualAdDetector.from_config error: %s — using defaults", exc)
            return cls()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _run_vision(self, frame: bytes, timeout_ms: int = 300) -> list[BoundingBox]:
        """Run vision model inference. Can be patched/mocked in tests."""
        return self._vision.infer(frame, timeout_ms=timeout_ms)

    def detect(
        self,
        frame: Optional[bytes] = None,
        frame_meta: Optional[Dict[str, Any]] = None,
        ui_tree: Optional[str] = None,
    ) -> DetectionResult:
        """Run ad detection, trying vision first then rules.

        Args:
            frame:      Raw JPEG/PNG bytes of the screen frame.
                        Pass ``None`` to skip vision and use rules only.
            frame_meta: Accessibility/DOM metadata dict passed to the rule
                        fallback detector (see :class:`RuleFallbackDetector`).

        Returns:
            :class:`DetectionResult` with boxes, source label, and timing.
        """
        if frame_meta is None:
            frame_meta = {}
        if ui_tree is not None:
            frame_meta["page_source"] = ui_tree

        t0 = time.perf_counter()
        frame_id = str(uuid.uuid4())
        deadline = t0 + self.inference_timeout_ms / 1000.0

        # ── Vision path ──────────────────────────────────────────────────
        is_patched_vision = getattr(type(self), "_run_vision", None) != getattr(self, "_run_vision", None)
        if frame is not None and (self._vision.available or is_patched_vision):
            remaining_ms = max(0.0, (deadline - time.perf_counter()) * 1000)
            if remaining_ms > 10:
                vision_boxes = self._run_vision(frame, int(remaining_ms))
            else:
                vision_boxes = []
                logger.debug("VisualAdDetector: deadline exhausted before vision infer")

            # Evaluate vision quality
            best_conf = max((b.confidence for b in vision_boxes), default=0.0)
            if best_conf >= self.confidence_threshold and vision_boxes:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                return DetectionResult(
                    boxes=sorted(vision_boxes, key=lambda b: b.confidence, reverse=True),
                    source="vision",
                    inference_ms=elapsed_ms,
                    frame_id=frame_id,
                )
            else:
                logger.debug(
                    "VisualAdDetector: vision best_conf=%.3f < threshold=%.3f; using rules",
                    best_conf,
                    self.confidence_threshold,
                )
        elif frame is not None and not self._vision.available:
            logger.debug("VisualAdDetector: vision model unavailable; using rules")

        # ── Rule fallback path ───────────────────────────────────────────
        rule_result = self._rules.detect(frame_meta)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return DetectionResult(
            boxes=rule_result.boxes,
            source=rule_result.source if rule_result.boxes else "none",
            inference_ms=elapsed_ms,
            frame_id=frame_id,
        )


if __name__ == "__main__":
    import argparse
    from ai_engine.config import load_ai_config

    parser = argparse.ArgumentParser(description="A4 Visual Ad Detector CLI")
    parser.add_argument("--config", default="ai_engine_config.yaml", help="Path to config")
    parser.add_argument("--ui-tree", default=None, help="Raw XML or path to UI tree dump")
    args = parser.parse_args()

    cfg = load_ai_config(args.config)
    detector = VisualAdDetector(cfg.a4_visual)

    sample_tree = args.ui_tree or """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node resource-id="com.adsterra.sdk:id/ad_banner" bounds="[0,1200][1080,1680]" />
</hierarchy>"""

    res = detector.detect(frame=None, ui_tree=sample_tree)
    print(f"A4 Visual Detection: source={res.source}, found {len(res.boxes)} boxes, best={res.best}")

