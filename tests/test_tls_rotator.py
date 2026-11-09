"""
tests/test_tls_rotator.py — Tests for Step 3.4: TLS/JA3 Diversification.
Verifies channel selection determinism, platform awareness, and launch arguments.
"""
import pytest
import tls_rotator


def test_tls_channel_selection_determinism():
    proxy1 = "10.0.0.1:8080"
    proxy2 = "10.0.0.2:8080"

    ch1_a = tls_rotator.select_browser_channel(proxy1)
    ch1_b = tls_rotator.select_browser_channel(proxy1)
    assert ch1_a == ch1_b

    # Forced channel
    assert tls_rotator.select_browser_channel(proxy1, force_channel="chrome") == "chrome"
    assert tls_rotator.select_browser_channel(proxy1, force_channel="msedge") == "msedge"
    assert tls_rotator.select_browser_channel(proxy1, force_channel="chromium") is None


def test_tls_mobile_fallback():
    # Mobile platforms should default to None (bundled chromium)
    assert tls_rotator.select_browser_channel("1.2.3.4:8080", platform="Linux armv8l (Android)") is None
    assert tls_rotator.select_browser_channel("1.2.3.4:8080", platform="iPhone") is None


def test_tls_launch_args():
    args = tls_rotator.get_tls_launch_args("test_proxy_123")
    assert any("webrtc" in a for a in args)
    assert isinstance(args, list)
