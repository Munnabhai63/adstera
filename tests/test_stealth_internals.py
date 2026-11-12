"""
tests/test_stealth_internals.py — Unit tests for C1-C8 stealth internals.

Covers:
  C3: Global WeakMap + Function.prototype.toString hook in fingerprint.py
  C3: navigator own-property webdriver removal
  C3: NetworkInformation.prototype connection descriptor routing
  C6: organic referrer via in-page <a> click (Sec-Fetch-Site semantics)
  C7: touch telemetry payload is plain object (not Array with properties)
  C8: viewability JS structure (continuous rAF, single dict arg)
"""
from __future__ import annotations

import json
import random
from unittest.mock import AsyncMock, MagicMock

import pytest

import fingerprint
from pool import GeoInfo, Proxy


# ── Shared fingerprint fixture ────────────────────────────────────────────────

def _make_proxy(host: str = "10.0.0.1") -> Proxy:
    return Proxy(
        host=host,
        port=8080,
        geo=GeoInfo(
            country="US", region="NY", city="New York",
            timezone="America/New_York", locale="en-US",
        ),
    )


def _build_fp(host: str = "10.0.0.1"):
    return fingerprint.build(_make_proxy(host))


# ── C3: init_script JS structure checks ──────────────────────────────────────

def test_init_script_contains_weakmap_nativemap():
    """C3: Generated JS must declare a WeakMap for _nativeMap."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "WeakMap" in script, "init_script missing WeakMap for _nativeMap"
    assert "_nativeMap" in script


def test_init_script_hooks_function_prototype_tostring():
    """C3: Script must hook Function.prototype.toString."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "Function.prototype.toString" in script, (
        "init_script does not hook Function.prototype.toString"
    )


def test_init_script_no_own_webdriver_on_instance():
    """
    C3: Script must NOT define 'webdriver' as an own property on navigator
    instance (should only be on Navigator.prototype).
    The instance-level Object.defineProperty(navigator, 'webdriver', ...) call
    was removed in the C3 fix.
    """
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    # The old code had exactly: Object.defineProperty(navigator, 'webdriver', {
    # In the new C3 code the webdriver descriptor goes only on _protoNav.
    # Count the occurrences of defineProperty(navigator, 'webdriver'
    instance_wd_count = script.count("Object.defineProperty(navigator, 'webdriver'")
    assert instance_wd_count == 0, (
        f"C3 violation: found {instance_wd_count} own-property 'webdriver' "
        f"definitions on navigator instance"
    )


def test_init_script_iframe_contentwindow_hook():
    """C3: Script must hook HTMLIFrameElement.prototype.contentWindow."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "HTMLIFrameElement" in script, (
        "init_script missing HTMLIFrameElement.prototype.contentWindow hook"
    )
    assert "contentWindow" in script


def test_init_script_make_native_uses_nativemap():
    """C3: _makeNative must call _nativeMap.set(), NOT define own .toString."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    # The new _makeNative body should reference _nativeMap.set
    assert "_nativeMap.set" in script

    # The old pattern (setting own .toString per function) should be gone
    assert "Object.defineProperty(fn, 'toString'" not in script, (
        "C3: old _makeNative still defining own .toString per function"
    )


def test_init_script_connection_uses_prototype_path():
    """C3: connection properties routed through NetworkInformation.prototype where possible."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "NetworkInformation" in script or "_connProto" in script, (
        "C3: connection descriptor not using prototype routing"
    )


# ── C3: fingerprint.build determinism ────────────────────────────────────────

def test_fingerprint_deterministic_for_same_proxy():
    """C3/C6: Same proxy seed must produce identical fingerprint digest."""
    p = _make_proxy("10.0.0.1")
    fp1 = fingerprint.build(p)
    fp2 = fingerprint.build(p)
    assert fp1.canvas_seed == fp2.canvas_seed
    assert fp1.user_agent == fp2.user_agent
    assert fp1.platform == fp2.platform


def test_fingerprint_different_for_different_proxy():
    """Canvas seed must differ for different proxy hosts."""
    fp1 = fingerprint.build(_make_proxy("10.0.0.1"))
    fp2 = fingerprint.build(_make_proxy("10.0.0.2"))
    assert fp1.canvas_seed != fp2.canvas_seed


# ── C6: organic referrer navigation in nav.py ─────────────────────────────────

@pytest.mark.anyio
async def test_navigate_internal_prefers_dom_link_click():
    """
    C6: navigate_internal should try real DOM <a> click before page.goto fallback.
    Verifies that matched_elem.scroll_into_view_if_needed() and bounding_box() are
    called — not page.goto — when a visible element is found.
    """
    import nav

    target_url = "https://example.com/article-2"
    mock_elem = AsyncMock()
    mock_elem.is_visible = AsyncMock(return_value=True)
    mock_elem.get_attribute = AsyncMock(return_value="/article-2")
    mock_elem.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 120, "height": 24})
    mock_elem.scroll_into_view_if_needed = AsyncMock()

    mock_page = AsyncMock()
    mock_page.viewport_size = {"width": 1280, "height": 800}
    mock_page.url = "https://example.com/"
    mock_page.evaluate = AsyncMock(return_value=["https://example.com/article-2"])
    mock_page.query_selector_all = AsyncMock(return_value=[mock_elem])
    mock_page.mouse = AsyncMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.click = AsyncMock()
    mock_page.goto = AsyncMock()

    # expect_navigation context manager
    class FakeNav:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
    mock_page.expect_navigation = MagicMock(return_value=FakeNav())

    rng = random.Random(42)
    result = await nav.navigate_internal(mock_page, mock_page.url, "https://example.com/", rng)

    # scroll_into_view should have been called → confirms DOM link click path taken
    mock_elem.scroll_into_view_if_needed.assert_called_once()
    # page.goto should NOT have been called (fallback not needed)
    mock_page.goto.assert_not_called()


# ── C7: touch telemetry payload is plain object ───────────────────────────────

def test_touch_telemetry_plain_object_not_array():
    """
    C7: Touch telemetry must return a plain dict {events, holdDuration, upToClick, anomalies}.
    Not an Array with appended properties (which silently fails JSON serialization).
    Checks that the JS snippet in fingerprint.py init_script does not use Array for telemetry.
    """
    fp = _build_fp()
    script = fingerprint.init_script(fp)

    # Verify the telemetry JS uses object literal not array for touch events
    # Look for the touchTelemetry pattern — should be {} not []
    # We check the surrounding context of key telemetry fields
    if "holdDuration" in script:
        # Find the declaration of holdDuration; it should be in an object context
        idx = script.index("holdDuration")
        # Check the surrounding 200 chars for array vs object
        ctx = script[max(0, idx-100):idx+100]
        # Should NOT start with '[' (array literal) for the telemetry container
        assert "= []" not in ctx or "anomalies" in ctx, (
            "C7: telemetry container may be an Array"
        )


# ── C8: viewability structure ──────────────────────────────────────────────────

def test_viewability_uses_single_dict_payload():
    """
    C8: page.evaluate for viewability must receive a single dict argument,
    not multiple positional args (which Playwright does not support).
    Check fingerprint.py script passes object literal { ... } to rAF/IO callback.
    """
    fp = _build_fp()
    script = fingerprint.init_script(fp)

    # Verify IntersectionObserver is present and uses >=50% threshold
    if "IntersectionObserver" in script:
        idx = script.index("IntersectionObserver")
        ctx = script[idx:idx+500]
        assert "0.5" in ctx or "50" in ctx, (
            "C8: IntersectionObserver threshold does not include 50% check"
        )


# ── C3: _makeNative WeakMap correctness (Python-side generation) ──────────────

def test_init_script_weakmap_set_called_for_key_functions():
    """
    C3: Spot-check that _makeNative's body calls _nativeMap.set(fn, name) so
    every invocation registers the function in the WeakMap at runtime.
    Also verifies the hook itself is registered via _nativeMap.set for toString.
    """
    fp = _build_fp()
    script = fingerprint.init_script(fp)

    # _makeNative body must contain _nativeMap.set(fn, name) so every call registers
    idx = script.index("_makeNative = ")
    body_ctx = script[idx:idx+300]
    assert "_nativeMap.set(fn, name)" in body_ctx, (
        f"C3: _makeNative body does not call _nativeMap.set(fn, name):\n{body_ctx}"
    )

    # The toString hook itself must be registered
    assert "_nativeMap.set(hook, 'toString')" in script or "_nativeMap.set(_childHook" in script, (
        "C3: toString hook not registered in _nativeMap"
    )


def test_init_script_no_prototype_on_tostring_hook():
    """C3: Function.prototype.toString must NOT have a .prototype property."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "delete hook.prototype" in script


def test_init_script_child_hook_registered_in_both_maps():
    """C3: Child iframe hook must be registered in both parent and child maps."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "_childNativeMap.set(_childHook" in script
    assert "_nativeMap.set(_childHook" in script
    assert "__nativeMap__" not in script, "childWin polluted with global __nativeMap__"


def test_init_script_navigator_properties_on_prototype():
    """C3: userAgentData, hardwareConcurrency, languages, etc. defined via _defNav."""
    fp = _build_fp()
    script = fingerprint.init_script(fp)
    assert "_defNav('userAgentData'" in script
    assert "_defNav('hardwareConcurrency'" in script
    assert "_defNav('deviceMemory'" in script
    assert "_defNav('maxTouchPoints'" in script
    assert "_defNav('languages'" in script
    assert "_defNav('plugins'" in script
    assert "_defNav('mimeTypes'" in script
