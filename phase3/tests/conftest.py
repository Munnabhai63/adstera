"""Shared deterministic pytest fixtures for Phase 3 tests.

Contains zero hardcoded device serials or API secrets.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import JsonLinesFormatter


@pytest.fixture
def deterministic_seed() -> int:
    return 42


@pytest.fixture
def tmp_phase3_config(tmp_path: Path) -> Phase3Config:
    from common.paths import atomic_write_json

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "phase3_test.db")
    cfg.phase3.state_dir = str(tmp_path / "state_phase3")
    cfg.phase3.default_mode = "paper"
    atomic_write_json(
        Path(cfg.phase3.state_dir) / "ai_engine" / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    return cfg


@pytest.fixture
def phase3_store(tmp_phase3_config: Phase3Config) -> Phase3Store:
    return Phase3Store(tmp_phase3_config.phase3.db_path)


@pytest.fixture
def fake_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
        b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
        b"\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture
def sample_ad_ui_tree() -> str:
    return (
        '<hierarchy rotation="0">'
        '<node resource-id="com.example:id/adsterra_banner" '
        'class="ad-banner adunit" text="Sponsored Ad" '
        'bounds="[100,400][980,650]" />'
        "</hierarchy>"
    )


@pytest.fixture
def empty_ui_tree() -> str:
    return '<hierarchy rotation="0"><node text="Plain article body" bounds="[0,0][100,100]" /></hierarchy>'


class RecordingTouch:
    """In-memory touch stub recording all tap/swipe invocations."""

    def __init__(self, *, fail: bool = False) -> None:
        self.taps: List[Tuple[int, int, int]] = []
        self.swipes: List[Tuple[int, int, int, int, int]] = []
        self.fail = fail

    def tap(self, x: int, y: int, duration_ms: int = 100) -> None:
        if self.fail:
            raise RuntimeError("Simulated touch failure")
        self.taps.append((int(x), int(y), int(duration_ms)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        if self.fail:
            raise RuntimeError("Simulated swipe failure")
        self.swipes.append((int(x1), int(y1), int(x2), int(y2), int(duration_ms)))


class RecordingCapture:
    """In-memory capture stub returning deterministic PNG + UI XML."""

    def __init__(
        self,
        frame: bytes,
        ui_tree: str,
        *,
        fail: bool = False,
    ) -> None:
        self.frame = frame
        self.ui_tree = ui_tree
        self.fail = fail
        self.calls = 0

    def screenshot(self) -> bytes:
        self.calls += 1
        if self.fail:
            raise RuntimeError("Simulated capture failure")
        return self.frame

    def dump_ui(self) -> str:
        if self.fail:
            raise RuntimeError("Simulated dump_ui failure")
        return self.ui_tree


@pytest.fixture
def make_touch():
    def _factory(*, fail: bool = False) -> RecordingTouch:
        return RecordingTouch(fail=fail)
    return _factory


@pytest.fixture
def make_capture(fake_png_bytes: bytes, sample_ad_ui_tree: str):
    def _factory(*, ui_tree: str | None = None, fail: bool = False) -> RecordingCapture:
        return RecordingCapture(
            frame=fake_png_bytes,
            ui_tree=sample_ad_ui_tree if ui_tree is None else ui_tree,
            fail=fail,
        )
    return _factory


@pytest.fixture
def json_log_capture():
    """Attach a temporary JSONLines handler to ``phase3`` logger and return emitted lines."""
    lines: List[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    root = logging.getLogger("phase3")
    prev_level = root.level
    root.setLevel(logging.INFO)
    handler = _ListHandler()
    handler.setFormatter(JsonLinesFormatter())
    root.addHandler(handler)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)
