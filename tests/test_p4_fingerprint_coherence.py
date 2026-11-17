"""
tests/test_p4_fingerprint_coherence.py — Acceptance tests for Phase 4.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import pool
import fingerprint as fp_mod


def test_screen_and_viewport_coherence():
    p = pool._parse_proxy_line("user:pass@1.2.3.4:8080")
    for is_mob in (True, False):
        fp = fp_mod.build(p, force_mobile=is_mob)
        assert fp.screen_width >= fp.viewport_width
        assert fp.screen_height >= fp.viewport_height
        assert fp.avail_width <= fp.screen_width
        assert fp.avail_height <= fp.screen_height


def test_mobile_hardware_constraints():
    p = pool._parse_proxy_line("user:pass@1.2.3.4:8080")
    for _ in range(10):
        fp = fp_mod.build(p, force_mobile=True)
        assert fp.hardware_concurrency in (4, 8)
        assert fp.device_memory in (4, 6, 8)
        assert fp.device_memory >= 4


def test_ios_safari_coherence():
    p = pool._parse_proxy_line("user:pass@1.2.3.4:8080")
    ios_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 "
        "Mobile/15E148 Safari/604.1"
    )
    fp = fp_mod.build(p, force_mobile=True)
    fp = fp_mod.sync_fingerprint_to_ua(fp, ios_ua)
    js = fp_mod.init_script(fp)

    assert "Apple Computer, Inc." in js
    assert "window.chrome = undefined" in js
    assert "delete navigator.userAgentData" in js


def test_desktop_plugins_prototype_in_js():
    p = pool._parse_proxy_line("user:pass@1.2.3.4:8080")
    fp = fp_mod.build(p, force_mobile=False)
    js = fp_mod.init_script(fp)

    assert "PluginArray.prototype" in js
    assert "MimeTypeArray.prototype" in js
    assert "PDF Viewer" in js
    assert "namedItem" in js

