"""
rule_fallback.py – DOM/accessibility-tree rule-based ad detector for A4.

No vision model required. Works from UIAutomator accessibility tree dumps or
raw XML page sources to locate ad elements by ID/class pattern matching.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ai_engine.a4_visual.bbox import AdLabel, AdNetwork, BoundingBox, DetectionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridden by AIConfig at runtime)
# ---------------------------------------------------------------------------
_DEFAULT_ID_PATTERNS = ["ad", "banner", "sponsor", "promoted"]
_DEFAULT_CLASS_PATTERNS = ["ad-", "adv-", "adunit", "adsense", "adsterra"]
_DEFAULT_MIN_AREA_PX = 2000
_DEFAULT_MAX_AREA_RATIO = 0.6
_NETWORK_HINTS: Dict[AdNetwork, List[str]] = {
    AdNetwork.ADSTERRA: ["adsterra", "popunder", "araplhn", "atcontainer-", "atlink-"],
    AdNetwork.PROPELLER: ["propellerads", "propeller"],
    AdNetwork.HILLTOP: ["hilltopads", "hilltop"],
}
_AD_CONTAINER_RE = re.compile(
    r"(?:^|[^a-z0-9])(atcontainer-|atlink-|invoke_layer|adsterra|araplhn|container-[0-9a-f]{12,})"
)
_DISCLOSURE_TEXTS = frozenset(
    {"sponsored", "sponsored advertisement", "advertisement", "ad", "ads"}
)


def _extract_hierarchy_xml(xml_str: str) -> str:
    """Strip any leading noise or trailing `/dev/tty` status after ``</hierarchy>``."""
    start = xml_str.find("<?xml")
    if start == -1:
        start = xml_str.find("<hierarchy")
    if start == -1:
        return xml_str
    end_tag = "</hierarchy>"
    end = xml_str.rfind(end_tag, start)
    if end != -1:
        return xml_str[start : end + len(end_tag)]
    return xml_str[start:]


def _infer_network(text: str) -> AdNetwork:
    """Guess the ad network from a node's text/resource-id/content-desc string."""
    t = text.lower()
    for network, hints in _NETWORK_HINTS.items():
        if any(h in t for h in hints):
            return network
    if re.search(r"\bcontainer-[0-9a-f]{12,}", t):
        return AdNetwork.ADSTERRA
    return AdNetwork.UNKNOWN


def _infer_label(slot_type: str) -> AdLabel:
    """Map a slot_type string to an :class:`AdLabel`."""
    mapping = {
        "banner": AdLabel.BANNER,
        "interstitial": AdLabel.INTERSTITIAL,
        "popunder": AdLabel.POPUNDER,
    }
    return mapping.get(slot_type, AdLabel.AD)


def _parse_bounds(bounds_str: str) -> Optional[tuple]:
    """Parse UIAutomator bounds string ``[x1,y1][x2,y2]`` → ``(x, y, w, h)``."""
    m = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
    if len(m) != 2:
        return None
    x1, y1 = int(m[0][0]), int(m[0][1])
    x2, y2 = int(m[1][0]), int(m[1][1])
    return (x1, y1, max(0, x2 - x1), max(0, y2 - y1))


class RuleFallbackDetector:
    """Accessibility/DOM rule-based ad detector.

    Args:
        id_patterns:     List of substrings to match against ``resource-id`` and ``text``.
        class_patterns:  List of substrings to match against ``class`` attribute.
        min_area_px:     Minimum element area in pixels; smaller elements are ignored.
        max_area_ratio:  Maximum ratio of element area to screen area; full-screen
                         overlays above this ratio are ignored.
        screen_w:        Screen width in pixels (used for area ratio filtering).
        screen_h:        Screen height in pixels.
    """

    def __init__(
        self,
        config: Any = None,
        id_patterns: Optional[List[str]] = None,
        class_patterns: Optional[List[str]] = None,
        min_area_px: int = _DEFAULT_MIN_AREA_PX,
        max_area_ratio: float = _DEFAULT_MAX_AREA_RATIO,
        screen_w: int = 1080,
        screen_h: int = 1920,
    ) -> None:
        if config is not None and not isinstance(config, (list, tuple)):
            if hasattr(config, "id_patterns"):
                id_patterns = config.id_patterns
            elif isinstance(config, dict):
                id_patterns = config.get("id_patterns")

            if hasattr(config, "class_patterns"):
                class_patterns = config.class_patterns
            elif isinstance(config, dict):
                class_patterns = config.get("class_patterns")

            if hasattr(config, "min_area_px"):
                min_area_px = config.min_area_px
            elif isinstance(config, dict) and "min_area_px" in config:
                min_area_px = config["min_area_px"]

            if hasattr(config, "max_area_ratio"):
                max_area_ratio = config.max_area_ratio
            elif isinstance(config, dict) and "max_area_ratio" in config:
                max_area_ratio = config["max_area_ratio"]
        elif isinstance(config, (list, tuple)):
            # config passed as id_patterns list
            id_patterns = config

        self.id_patterns = [p.lower() for p in (id_patterns or _DEFAULT_ID_PATTERNS)]
        self.class_patterns = [p.lower() for p in (class_patterns or _DEFAULT_CLASS_PATTERNS)]
        self.min_area_px = min_area_px
        self.max_area_ratio = max_area_ratio
        self.screen_w = int(screen_w)
        self.screen_h = int(screen_h)
        self.screen_area = self.screen_w * self.screen_h

    def set_screen_dimensions(self, screen_w: int, screen_h: int) -> None:
        """Update screen dimensions dynamically from frame or accessibility tree."""
        if screen_w > 0 and screen_h > 0:
            self.screen_w = int(screen_w)
            self.screen_h = int(screen_h)
            self.screen_area = self.screen_w * self.screen_h

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_from_tree(self, tree_xml_or_dict: Any) -> DetectionResult:
        """Helper to run detection directly on a tree XML string or dict."""
        if isinstance(tree_xml_or_dict, str):
            return self.detect({"page_source": tree_xml_or_dict})
        if isinstance(tree_xml_or_dict, list):
            return self.detect({"accessibility_tree": tree_xml_or_dict})
        if isinstance(tree_xml_or_dict, dict):
            return self.detect(tree_xml_or_dict)
        return self.detect({})

    def detect(self, frame_meta: Any = None) -> DetectionResult:
        """Run rule-based ad detection on accessibility metadata.

        Args:
            frame_meta: Dictionary or raw XML string.
        """
        if isinstance(frame_meta, str):
            frame_meta = {"page_source": frame_meta}
        elif frame_meta is None:
            frame_meta = {}
        """Run rule-based ad detection on accessibility metadata.

        Args:
            frame_meta: Dictionary that may contain:

                * ``accessibility_tree`` – list of dicts, each with keys
                  ``bounds`` (UIAutomator bounds string), ``text``,
                  ``resource-id``, and ``class``.
                * ``page_source`` – raw XML string from
                  ``adb shell uiautomator dump``.

        Returns:
            :class:`DetectionResult` with up to 3 boxes sorted by confidence
            (highest first). Returns an empty result on any error — never raises.
        """
        t0 = time.perf_counter()
        frame_id = str(uuid.uuid4())
        try:
            boxes = self._run(frame_meta or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("RuleFallbackDetector.detect error: %s", exc)
            boxes = []
        elapsed_ms = (time.perf_counter() - t0) * 1000
        boxes.sort(key=lambda b: b.confidence, reverse=True)
        return DetectionResult(
            boxes=boxes[:3],
            source="rule_fallback",
            inference_ms=elapsed_ms,
            frame_id=frame_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, frame_meta: Dict[str, Any]) -> List[BoundingBox]:
        """Core detection logic; may raise on bad input."""
        boxes: List[BoundingBox] = []

        # Dynamic screen dimension override from frame_meta
        sw = frame_meta.get("screen_w")
        sh = frame_meta.get("screen_h")
        if sw and sh:
            self.set_screen_dimensions(int(sw), int(sh))

        # Path 1 – pre-parsed accessibility tree
        tree: List[Dict[str, Any]] = frame_meta.get("accessibility_tree", [])
        for node in tree:
            box = self._eval_node_dict(node)
            if box is not None:
                boxes.append(box)

        # Path 2 – raw XML page source from UIAutomator dump
        page_source: str = frame_meta.get("page_source", "")
        if page_source and not boxes:
            boxes = self._parse_xml(page_source)

        return boxes

    def _match_strength(
        self,
        rid: str,
        text: str,
        cls: str,
        desc: str = "",
        clickable: bool = False,
    ) -> float:
        """Return heuristic confidence [0.0, 1.0] based on how many patterns match."""
        rid_l = rid.lower()
        cls_l = cls.lower()
        text_l = text.lower()
        desc_l = desc.lower()

        # Ignore passive disclosure label TextViews (e.g. "SPONSORED ADVERTISEMENT")
        # that sit above an ad slot so they never outrank the clickable ad container.
        if (
            cls_l.endswith("textview")
            and not rid_l
            and not clickable
            and text_l.strip() in _DISCLOSURE_TEXTS
        ):
            return 0.0

        id_cls_haystack = f"{rid_l} {cls_l}"
        text_desc_haystack = f"{text_l} {desc_l}"

        hits = 0
        for p in self.id_patterns:
            if len(p) <= 2:
                # Require token boundaries for ultra-short patterns like "ad" so words
                # like "read", "load", "loading", "head", "header", "broadcast", "thread",
                # "gradient", "radio", "adapter", "download", or "shadow" do NOT false-positive.
                token_re = re.compile(rf"(?i)(?:^|[^a-z0-9]){re.escape(p)}(?:$|[^a-z0-9])")
                id_match = bool(token_re.search(rid_l)) or bool(token_re.search(cls_l))
                txt_match = bool(re.search(rf"\b{re.escape(p)}s?\b", text_desc_haystack))
                if id_match or txt_match:
                    hits += 1
            elif p in id_cls_haystack or p in text_desc_haystack:
                hits += 1

        cls_hits = sum(
            1 for p in self.class_patterns if p in id_cls_haystack or p in text_desc_haystack
        )
        container_hits = 1 if _AD_CONTAINER_RE.search(f"{rid_l} {desc_l} {text_l}") else 0
        total = hits + cls_hits + container_hits
        # 1 hit → 0.55, 2 hits → 0.70, 3+ hits → 0.85 (+0.10 if clickable container)
        if total == 0:
            return 0.0
        base = min(0.85, 0.40 + total * 0.15)
        if clickable:
            base = min(0.95, round(base + 0.10, 4))
        return base

    def _make_box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        confidence: float,
        rid: str,
        text: str,
        desc: str = "",
    ) -> Optional[BoundingBox]:
        """Filter by size constraints and build a :class:`BoundingBox`."""
        area = w * h
        if area < self.min_area_px:
            return None
        if self.screen_area > 0 and area / self.screen_area > self.max_area_ratio:
            return None
        network = _infer_network(f"{rid} {text} {desc}")
        # Guess slot type from dimensions
        ratio = w / h if h else 0
        if ratio > 4:
            slot_type = "banner"
        elif area > 400_000:
            slot_type = "interstitial"
        else:
            slot_type = "banner"
        label = _infer_label(slot_type)
        return BoundingBox(
            x=x, y=y, w=w, h=h,
            confidence=confidence,
            label=label,
            network=network,
            slot_type=slot_type,
        )

    def _eval_node_dict(self, node: Dict[str, Any]) -> Optional[BoundingBox]:
        """Evaluate a single accessibility tree node dict."""
        rid = node.get("resource-id", "") or ""
        text = node.get("text", "") or ""
        desc = node.get("content-desc", "") or ""
        cls = node.get("class", "") or ""
        clickable_raw = node.get("clickable", False)
        clickable = (
            clickable_raw.lower() == "true"
            if isinstance(clickable_raw, str)
            else bool(clickable_raw)
        )
        confidence = self._match_strength(rid, text, cls, desc=desc, clickable=clickable)
        if confidence == 0.0:
            return None
        bounds_str = node.get("bounds", "")
        parsed = _parse_bounds(bounds_str) if bounds_str else None
        if parsed is None:
            # Try direct x, y, w, h keys
            try:
                parsed = (int(node["x"]), int(node["y"]), int(node["w"]), int(node["h"]))
            except (KeyError, ValueError):
                return None
        x, y, w, h = parsed
        return self._make_box(x, y, w, h, confidence, rid, text, desc=desc)

    def _parse_xml(self, xml_str: str) -> List[BoundingBox]:
        """Parse raw UIAutomator XML dump and extract candidate ad nodes."""
        boxes: List[BoundingBox] = []
        cleaned_xml = _extract_hierarchy_xml(xml_str)
        try:
            root = ET.fromstring(cleaned_xml)
        except ET.ParseError as exc:
            logger.debug("XML parse error in RuleFallbackDetector: %s", exc)
            return boxes

        # Calibrate screen dimensions from root/container bounds in the XML coordinate space
        for node in root.iter():
            bounds_str = node.get("bounds", "")
            parsed = _parse_bounds(bounds_str) if bounds_str else None
            if parsed is not None:
                x, y, w, h = parsed
                if x == 0 and y == 0 and w >= 200 and h >= 200:
                    if self.screen_area <= 0 or (w * h > self.screen_area):
                        self.set_screen_dimensions(w, h)

        for node in root.iter():
            rid = node.get("resource-id", "") or ""
            text = node.get("text", "") or ""
            desc = node.get("content-desc", "") or ""
            cls = node.get("class", "") or ""
            clickable = (node.get("clickable", "") or "").lower() == "true"
            confidence = self._match_strength(rid, text, cls, desc=desc, clickable=clickable)
            if confidence == 0.0:
                continue
            bounds_str = node.get("bounds", "")
            parsed = _parse_bounds(bounds_str) if bounds_str else None
            if parsed is None:
                continue
            x, y, w, h = parsed
            box = self._make_box(x, y, w, h, confidence, rid, text, desc=desc)
            if box is not None:
                boxes.append(box)
        return boxes
