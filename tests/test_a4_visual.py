"""
tests/test_a4_visual.py — Unit tests for A4 Visual Ad Detector.

All tests use synthetic frames and mocked dependencies.
Seed=42 for all random operations.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 320, height: int = 480) -> bytes:
    """Return a minimal valid PNG byte string of given dimensions."""
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    raw_rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _make_tree_with_ad() -> str:
    """Return a fake XML UI accessibility tree containing an ad element."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" resource-id="com.browser:id/content" class="android.view.View"
        bounds="[0,0][1080,1920]">
    <node index="0" resource-id="com.adsterra.sdk:id/ad_banner"
          class="android.webkit.WebView"
          bounds="[0,1200][1080,1680]" />
    <node index="1" resource-id="com.browser:id/article_body"
          class="android.widget.TextView"
          bounds="[0,0][1080,1200]" />
  </node>
</hierarchy>"""


def _make_tree_no_ad() -> str:
    """Return a fake XML UI tree with no ad elements."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" resource-id="com.browser:id/content" class="android.view.View"
        bounds="[0,0][1080,1920]">
    <node index="0" resource-id="com.browser:id/article_body"
          class="android.widget.TextView"
          bounds="[0,0][1080,1920]" />
  </node>
</hierarchy>"""


# ---------------------------------------------------------------------------
# 1. BoundingBox.random_click_point within 20-80% x, 25-75% y
# ---------------------------------------------------------------------------


def test_bbox_random_click_point_within_bounds():
    """click point must always fall inside 20–80% x and 25–75% y of the bbox."""
    import random

    random.seed(42)

    from ai_engine.a4_visual.detector import BoundingBox

    # Create a 400×300 box at origin
    bbox = BoundingBox(x=0, y=0, w=400, h=300, label="banner", confidence=0.9)

    for _ in range(50):
        px, py = bbox.random_click_point()
        assert 0.20 * 400 <= px <= 0.80 * 400, f"px={px} out of 20-80% range"
        assert 0.25 * 300 <= py <= 0.75 * 300, f"py={py} out of 25-75% range"


# ---------------------------------------------------------------------------
# 2. Rule fallback detects banner in accessibility tree
# ---------------------------------------------------------------------------


def test_rule_fallback_detects_banner():
    """Accessibility tree with 'ad' resource-id returns a BoundingBox result."""
    from ai_engine.a4_visual.detector import RuleFallbackDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    detector = RuleFallbackDetector(cfg.a4_visual.rule_fallback)

    result = detector.detect_from_tree(_make_tree_with_ad())

    assert result is not None, "Expected a DetectionResult, got None"
    assert result.bbox is not None, "Expected bbox, got None"
    assert result.label != "none", f"Expected non-none label, got {result.label!r}"
    assert result.source == "rule_fallback"


# ---------------------------------------------------------------------------
# 3. Rule fallback returns empty on clean tree
# ---------------------------------------------------------------------------


def test_rule_fallback_no_match_returns_empty():
    """Tree with no ad nodes returns DetectionResult with label='none' and bbox=None."""
    from ai_engine.a4_visual.detector import RuleFallbackDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    detector = RuleFallbackDetector(cfg.a4_visual.rule_fallback)

    result = detector.detect_from_tree(_make_tree_no_ad())

    assert result is not None
    assert result.bbox is None or result.label == "none", (
        f"Expected no ad found, got label={result.label!r}, bbox={result.bbox}"
    )


# ---------------------------------------------------------------------------
# 4. Vision model absent → no crash, falls back to rule_fallback
# ---------------------------------------------------------------------------


def test_vision_model_unavailable_no_crash(tmp_path):
    """When ONNX model file is absent, VisualAdDetector falls back gracefully."""
    from ai_engine.a4_visual.detector import VisualAdDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    # Point model path to a non-existent file
    cfg.a4_visual.model_path = str(tmp_path / "nonexistent.onnx")

    detector = VisualAdDetector(cfg.a4_visual)
    frame = _make_png_bytes()
    result = detector.detect(frame, ui_tree=_make_tree_with_ad())

    assert result is not None
    assert result.source == "rule_fallback", (
        f"Expected rule_fallback source, got {result.source!r}"
    )


# ---------------------------------------------------------------------------
# 5. Vision model timeout → rule_fallback source
# ---------------------------------------------------------------------------


def test_detector_timeout_falls_back(tmp_path, monkeypatch):
    """Vision inference that takes >300ms must fall back to rule_fallback."""
    from ai_engine.a4_visual.detector import VisualAdDetector
    from ai_engine.config import load_ai_config

    cfg = load_ai_config(None)
    cfg.a4_visual.model_path = str(tmp_path / "nonexistent.onnx")
    cfg.a4_visual.inference_timeout_ms = 1  # 1ms timeout — always expires

    # Patch the _run_vision method (if it exists) to simulate slowness
    detector = VisualAdDetector(cfg.a4_visual)

    def _slow_vision(*args, **kwargs):
        time.sleep(0.05)  # 50ms > 1ms timeout
        return None

    if hasattr(detector, "_run_vision"):
        monkeypatch.setattr(detector, "_run_vision", _slow_vision)

    frame = _make_png_bytes()
    result = detector.detect(frame, ui_tree=_make_tree_with_ad())

    assert result.source == "rule_fallback", (
        f"Expected rule_fallback after timeout, got {result.source!r}"
    )


# ---------------------------------------------------------------------------
# 6. DetectionResult.best returns highest-confidence non-NONE box
# ---------------------------------------------------------------------------


def test_detection_result_best_property():
    """best property returns the DetectionResult with highest confidence (non-none label)."""
    from ai_engine.a4_visual.detector import BoundingBox, MultiDetectionResult

    boxes = [
        BoundingBox(x=0, y=0, w=200, h=100, label="banner", confidence=0.6),
        BoundingBox(x=0, y=200, w=200, h=100, label="interstitial", confidence=0.85),
        BoundingBox(x=0, y=400, w=200, h=100, label="none", confidence=0.95),
    ]

    result = MultiDetectionResult(boxes=boxes, source="model")
    best = result.best

    assert best is not None, "best should not be None"
    assert best.label != "none", f"best should not be 'none', got {best.label!r}"
    assert best.confidence == 0.85, (
        f"Expected confidence=0.85 (highest non-none), got {best.confidence}"
    )


def test_rule_fallback_chrome_webview_adsterra_and_dev_tty_suffix():
    """Handles uiautomator /dev/tty suffix, content-desc, and ranks clickable atLink over disclosure text."""
    from ai_engine.a4_visual.detector import RuleFallbackDetector
    from ai_engine.config import load_ai_config

    xml_with_tty = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" resource-id="com.android.chrome:id/toolbar_container" class="android.view.ViewGroup" bounds="[0,129][1440,293]" />
  <node index="6" text="SPONSORED ADVERTISEMENT" resource-id="" class="android.widget.TextView" clickable="false" bounds="[506,1161][934,1204]" />
  <node index="7" text="" resource-id="atContainer-99887766554433221100" class="android.view.View" clickable="false" bounds="[80,1218][1359,1480]" />
  <node index="8" text="" resource-id="atLink-99887766554433221100" content-desc="promo-link" class="android.view.View" clickable="true" bounds="[80,1218][1440,1494]" />
  <node index="9" text=" 5 min read • November 2026" resource-id="" class="android.widget.TextView" clickable="false" bounds="[149,2647][635,2693]" />
</hierarchy>UI hierchary dumped to: /dev/tty"""

    cfg = load_ai_config(None)
    detector = RuleFallbackDetector(cfg.a4_visual.rule_fallback)
    result = detector.detect_from_tree(xml_with_tty)

    assert result.source == "rule_fallback"
    assert result.bbox == (80, 1218, 1360, 276)
    assert result.confidence >= 0.55
    # Must not match "5 min read" or "toolbar_container" or pick disclosure TextView
    assert all(b.y != 2647 and b.y != 1161 and b.y != 129 for b in result.boxes)
