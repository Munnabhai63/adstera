"""
vision_model.py – Lightweight ONNX-based ad classifier for A4 Visual Ad Detection.

Falls back gracefully when ``onnxruntime`` or the model file are absent.
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import List

from ai_engine.a4_visual.bbox import AdLabel, AdNetwork, BoundingBox

logger = logging.getLogger(__name__)

# Optional imports — guarded so the module loads even without these packages.
try:
    import onnxruntime as ort  # type: ignore

    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False
    logger.warning(
        "onnxruntime not installed — VisionModel will be unavailable. "
        "Install with: pip install onnxruntime"
    )

try:
    from PIL import Image  # type: ignore
    import io as _io

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow not installed — VisionModel will be unavailable.")

import numpy as np

# YOLO-style output layout assumed: [batch, num_detections, 6]
# where each detection is [cx, cy, w, h, confidence, class_id]
_INPUT_SIZE = (416, 416)
_LABEL_MAP = {
    0: (AdLabel.AD, "banner"),
    1: (AdLabel.BANNER, "banner"),
    2: (AdLabel.INTERSTITIAL, "interstitial"),
    3: (AdLabel.POPUNDER, "popunder"),
    4: (AdLabel.NONE, "none"),
}

_NETWORK_HINTS = {
    AdNetwork.ADSTERRA: ["adsterra", "popunder", "araplhn"],
    AdNetwork.PROPELLER: ["propellerads", "propeller"],
    AdNetwork.HILLTOP: ["hilltopads", "hilltop"],
}


class VisionModel:
    """Lightweight ONNX-based ad detector.

    Args:
        model_path: Path to the ONNX model file. If the file does not exist or
                    ``onnxruntime`` / ``Pillow`` are not installed, the model is
                    marked unavailable and :meth:`infer` returns an empty list.
    """

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self.available = False
        self._session = None

        if not _ORT_AVAILABLE:
            logger.warning("VisionModel: onnxruntime unavailable, skipping load.")
            return
        if not _PIL_AVAILABLE:
            logger.warning("VisionModel: Pillow unavailable, skipping load.")
            return
        if not self.model_path.exists():
            logger.info(
                "VisionModel: model file not found at %s — rule fallback will be used.",
                self.model_path,
            )
            return

        try:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self.available = True
            logger.info("VisionModel: loaded model from %s", self.model_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("VisionModel: failed to load ONNX model: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(self, frame_bytes: bytes, timeout_ms: int = 300) -> List[BoundingBox]:
        """Run ad detection on a JPEG/PNG image.

        Args:
            frame_bytes: Raw JPEG or PNG bytes of the frame to analyse.
            timeout_ms:  Hard deadline in milliseconds. If the total time to
                         pre-process and infer exceeds this budget, an empty
                         list is returned immediately.

        Returns:
            List of :class:`BoundingBox` instances, possibly empty.
        """
        if not self.available or self._session is None:
            return []

        deadline = time.perf_counter() + timeout_ms / 1000.0

        # ── Pre-processing ──────────────────────────────────────────────
        try:
            img_tensor = self._preprocess(frame_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.debug("VisionModel.infer preprocess error: %s", exc)
            return []

        if time.perf_counter() >= deadline:
            logger.debug("VisionModel.infer: deadline exceeded before inference")
            return []

        # ── Inference ───────────────────────────────────────────────────
        try:
            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: img_tensor})
        except Exception as exc:  # noqa: BLE001
            logger.warning("VisionModel.infer ONNX run error: %s", exc)
            return []

        if time.perf_counter() >= deadline:
            logger.debug("VisionModel.infer: deadline exceeded after inference")
            return []

        # ── Post-processing ─────────────────────────────────────────────
        try:
            return self._postprocess(outputs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("VisionModel.infer postprocess error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preprocess(self, frame_bytes: bytes) -> np.ndarray:
        """Decode image bytes and prepare a normalised float32 tensor.

        Args:
            frame_bytes: Raw JPEG/PNG bytes.

        Returns:
            ``np.ndarray`` of shape ``(1, 3, 416, 416)`` and dtype ``float32``.
        """
        img = Image.open(_io.BytesIO(frame_bytes)).convert("RGB")
        img = img.resize(_INPUT_SIZE, Image.BILINEAR)
        arr = np.array(img, dtype=np.float32) / 255.0  # (H, W, C)
        arr = arr.transpose(2, 0, 1)  # (C, H, W)
        return arr[np.newaxis, ...]  # (1, C, H, W)

    def _postprocess(self, outputs: list) -> List[BoundingBox]:
        """Convert raw ONNX output tensors to :class:`BoundingBox` instances.

        Assumes a YOLO-style output with shape ``(1, N, 6+)`` where each row is
        ``[cx_norm, cy_norm, w_norm, h_norm, confidence, class_id, ...]``.
        Boxes with confidence < 0.3 are dropped.

        Args:
            outputs: Raw outputs from ``onnxruntime`` session.

        Returns:
            List of :class:`BoundingBox` ordered by confidence descending.
        """
        raw = outputs[0]  # shape varies
        if raw is None or raw.size == 0:
            return []

        # Flatten to (N, >=6)
        if raw.ndim == 3:
            raw = raw[0]  # remove batch dim
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)

        boxes: List[BoundingBox] = []
        img_w, img_h = _INPUT_SIZE

        for row in raw:
            if len(row) < 6:
                continue
            cx, cy, bw, bh, conf = float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])
            class_id = int(row[5]) if len(row) > 5 else 0

            if conf < 0.30:
                continue

            # De-normalise coordinates (assume normalised [0,1])
            x = int((cx - bw / 2) * img_w)
            y = int((cy - bh / 2) * img_h)
            w = int(bw * img_w)
            h = int(bh * img_h)
            x, y = max(0, x), max(0, y)

            label, slot_type = _LABEL_MAP.get(class_id, (AdLabel.AD, "banner"))
            boxes.append(
                BoundingBox(
                    x=x, y=y, w=w, h=h,
                    confidence=min(1.0, conf),
                    label=label,
                    network=AdNetwork.UNKNOWN,
                    slot_type=slot_type,
                )
            )

        boxes.sort(key=lambda b: b.confidence, reverse=True)
        return boxes
