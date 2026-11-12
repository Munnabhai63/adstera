"""
tests/test_biometric_motion.py — Unit tests for Step 1.2 (B4): biometric_motion.py.

Covers every audited math and timestamp invariant from B4 checklist:
  B4-1: OU tremor stationary-variance formula
  B4-2: Desktop CDP timestamps use Unix epoch (time.time()), not loop.time()
  B4-3: Hermite fling profile slope ≈ 0.8 at t=1 → VelocityTracker ≥ 150 DIP/s
  B4-4: ThumbArc X lateral offset sampled once per swipe, not per frame
  B4-5: Timestamps strictly monotonic; force 0.3–1.0; radiusX/Y present
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import biometric_motion as bm


# ── minimum_jerk ─────────────────────────────────────────────────────────────

def test_minimum_jerk_boundary_values():
    """s(0)==0, s(1)==1, s(0.5) == 0.5 (symmetric by definition)."""
    assert bm.minimum_jerk(0.0) == pytest.approx(0.0)
    assert bm.minimum_jerk(1.0) == pytest.approx(1.0)
    # Symmetry: s(0.5) = 10/8 - 15/16 + 6/32 = 1.25 - 0.9375 + 0.1875 = 0.5
    assert bm.minimum_jerk(0.5) == pytest.approx(0.5, abs=1e-9)


def test_minimum_jerk_monotone():
    """s(t) is strictly non-decreasing on [0,1]."""
    vals = [bm.minimum_jerk(i / 100) for i in range(101)]
    for a, b_val in zip(vals, vals[1:]):
        assert b_val >= a - 1e-10


# ── ShannonFitts ──────────────────────────────────────────────────────────────

def test_shannon_fitts_zero_distance():
    """Zero distance returns a constant (equals a)."""
    fitts = bm.ShannonFitts(a=0.127, b=0.096)
    mt = fitts.movement_time(0, 20)
    assert mt == pytest.approx(0.127)


def test_shannon_fitts_positive_and_floored():
    """Movement time ≥ 0.08 s and increases with distance."""
    fitts = bm.ShannonFitts()
    mt_near = fitts.movement_time(10, 24)
    mt_far = fitts.movement_time(500, 24)
    assert mt_near >= 0.08
    assert mt_far > mt_near


# ── OrnsteinUhlenbeckTremor ───────────────────────────────────────────────────

def test_ou_tremor_stationary_variance(monkeypatch):
    """
    B4-1: Stationary variance of OU process ≈ sigma_rms² (ergodic property).
    Run many steps and check empirical variance is within 25% of sigma_rms².
    """
    rng = random.Random(42)
    theta = 12.0
    sigma_rms = 0.6
    dt = 1 / 60.0  # 60 Hz

    ou = bm.OrnsteinUhlenbeckTremor(theta=theta, sigma_rms=sigma_rms, rng=rng)
    xs = []
    for _ in range(5000):
        dx, _ = ou.step(dt)
        xs.append(dx)

    empirical_var = sum(x**2 for x in xs) / len(xs)
    target_var = sigma_rms**2
    # Empirical variance ≈ stationary variance within 25%
    assert abs(empirical_var - target_var) / target_var < 0.25, (
        f"OU empirical_var={empirical_var:.4f} expected ≈ {target_var:.4f}"
    )


def test_ou_tremor_step_uses_stationary_formula():
    """
    B4-1: Verify the step() function uses (1 - exp(-2θΔt)) scaling, not sqrt(dt).
    For large dt approaching ∞ the step variance → sigma_rms² (saturates at stationary).
    For large dt approaching ∞ the sqrt(dt) formula would diverge.
    """
    ou = bm.OrnsteinUhlenbeckTremor(theta=12.0, sigma_rms=0.6, rng=random.Random(1))
    # For dt very large, stationary variance = sigma_rms² * (1 - exp(-2*12*100)) ≈ sigma_rms²
    # With sqrt(dt) this would be sigma_rms * sqrt(100) = 6.0 std → out of [0, 1] routinely
    # With stationary formula std ≈ sigma_rms * 1.0 = 0.6
    samples = []
    for _ in range(200):
        ou.reset()
        dx, _ = ou.step(100.0)   # huge dt
        samples.append(abs(dx))
    # With correct formula |dx| median should be ~sigma_rms scale (< 2.0)
    median = sorted(samples)[len(samples) // 2]
    assert median < 2.0, f"Stationary variance not saturating; median |dx|={median:.3f}"


def test_ou_tremor_reset():
    """reset() zeroes internal state."""
    ou = bm.OrnsteinUhlenbeckTremor(rng=random.Random(7))
    for _ in range(20):
        ou.step(0.016)
    ou.reset()
    assert ou.x == 0.0
    assert ou.y == 0.0


# ── HermiteThumbArc ───────────────────────────────────────────────────────────

def test_hermite_fling_profile_slope_at_t1():
    """
    B4-3: f(t) = 2.2t² - 1.2t³ → f'(1) = 4.4 - 3.6 = 0.8.
    Chromium VelocityTracker fires fling when velocity ≥ ~150 DIP/s.
    With typical dy=320px and 280ms fling: v_end = 320 * 0.8 / 0.28 ≈ 914 DIP/s >> 150.
    """
    # Numerical derivative near t=1
    dt = 0.0001
    f1 = bm.HermiteThumbArc._hermite_fling(1.0 - dt)
    f2 = bm.HermiteThumbArc._hermite_fling(1.0)
    slope = (f2 - f1) / dt
    assert slope == pytest.approx(0.8, abs=0.02), f"Hermite slope at t=1: {slope:.4f}"


def test_hermite_fling_at_zero_and_one():
    """f(0) = 0, f(1) = 2.2 - 1.2 = 1.0."""
    assert bm.HermiteThumbArc._hermite_fling(0.0) == pytest.approx(0.0)
    assert bm.HermiteThumbArc._hermite_fling(1.0) == pytest.approx(1.0)


def test_thumb_arc_x_offset_sampled_once(monkeypatch):
    """
    B4-4: _x_offset is set once in __post_init__ and NOT re-sampled in waypoints().
    Call waypoints() twice; both runs must use the SAME _x_offset.
    """
    rng = random.Random(99)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=400.0, end_y=720.0,
                               viewport_width=390.0, rng=rng)
    offset_initial = arc._x_offset

    wps1 = arc.waypoints()
    wps2 = arc.waypoints()

    # Offset unchanged between calls
    assert arc._x_offset == offset_initial

    # Both waypoint sets encode the same x-bias (compare first mid-swipe x)
    mid1 = wps1[len(wps1) // 2]["x"]
    mid2 = wps2[len(wps2) // 2]["x"]
    assert abs(mid1 - mid2) < 1.0, "X offset not stable between waypoints() calls"


def test_thumb_arc_waypoints_monotonic_timestamps():
    """B4-5: All timestamps in waypoints() are strictly non-decreasing."""
    rng = random.Random(42)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=200.0, end_y=520.0,
                               viewport_width=390.0, rng=rng)
    wps = arc.waypoints()
    timestamps = [w["timestamp_s"] for w in wps]
    for a, b_ts in zip(timestamps, timestamps[1:]):
        assert b_ts >= a - 1e-9, f"Non-monotonic: {a} then {b_ts}"


def test_thumb_arc_waypoints_force_in_range():
    """B4-5: force values must be in [0.3, 1.0]."""
    rng = random.Random(5)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=200.0, end_y=520.0,
                               viewport_width=390.0, rng=rng)
    for wp in arc.waypoints():
        assert 0.3 <= wp["force"] <= 1.0, f"force out of range: {wp['force']}"


def test_thumb_arc_waypoints_has_radius():
    """B4-5: Every waypoint has radiusX and radiusY > 0."""
    rng = random.Random(3)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=200.0, end_y=500.0,
                               viewport_width=390.0, rng=rng)
    for wp in arc.waypoints():
        assert wp["radiusX"] > 0
        assert wp["radiusY"] > 0


def test_thumb_arc_x_clamped_to_viewport():
    """x values never go outside [10, viewport_width - 10]."""
    rng = random.Random(77)
    vw = 390.0
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=200.0, end_y=800.0,
                               viewport_width=vw, rng=rng)
    for wp in arc.waypoints():
        assert 10.0 <= wp["x"] <= vw - 10.0


def test_thumb_arc_active_end_velocity_above_threshold():
    """
    B4-3: active end-velocity should be >> 150 DIP/s for typical fling.
    With dy=320, dt=0.28s: v = 320 * 0.8 / 0.28 ≈ 914 DIP/s.
    Test with looser bound (> 150 DIP/s) to handle different duration seeds.
    """
    rng = random.Random(42)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=200.0, end_y=520.0,
                               viewport_width=390.0, rng=rng)
    arc.waypoints()   # populates _fling_active_end_v
    assert arc._fling_active_end_v > 150.0, (
        f"End velocity too low for Chromium fling: {arc._fling_active_end_v:.1f} DIP/s"
    )


# ── Desktop CDP timestamp invariant ──────────────────────────────────────────

@pytest.mark.anyio
async def test_desktop_cdp_dispatcher_uses_unix_epoch_timestamp():
    """
    B4-2: Timestamps sent via Input.dispatchMouseEvent must use time.time()
    (Unix epoch seconds), not asyncio.get_event_loop().time() (~0 at start).
    """
    sent_params: list[dict] = []

    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock(side_effect=lambda method, params: sent_params.append(params) or {})

    dispatcher = bm.DesktopCDPMouseDispatcher(mock_cdp)

    t_before = time.time()
    await dispatcher.move(100.0, 200.0)
    await dispatcher.down(100.0, 200.0)
    await dispatcher.up(100.0, 200.0)
    t_after = time.time()

    assert len(sent_params) == 3
    for params in sent_params:
        ts = params["timestamp"]
        # Must be Unix epoch (> 1_700_000_000), not loop.time() (< 1000)
        assert ts > 1_700_000_000, f"Timestamp {ts} looks like loop.time() not Unix epoch"
        assert t_before <= ts <= t_after + 0.1


# ── Mobile CDP touch dispatcher ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_mobile_cdp_tap_sends_touchstart_and_touchend():
    """MobileCDPTouchDispatcher.tap() sends touchStart then touchEnd."""
    calls: list[tuple[str, dict]] = []

    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock(side_effect=lambda method, params: calls.append((method, params)) or {})

    dispatcher = bm.MobileCDPTouchDispatcher(mock_cdp)
    rng = random.Random(42)
    await dispatcher.tap(195.0, 400.0, rng=rng, hold_ms=50.0)

    types = [c[1]["type"] for c in calls]
    assert "touchStart" in types
    assert "touchEnd" in types
    assert types.index("touchStart") < types.index("touchEnd")


@pytest.mark.anyio
async def test_mobile_cdp_fling_scroll_has_monotonic_timestamps():
    """CDP fling scroll dispatches monotonic timestamps across all events."""
    dispatched: list[float] = []

    async def capture_send(method, params):
        if "timestamp" in params:
            dispatched.append(params["timestamp"])
        return {}

    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock(side_effect=capture_send)

    rng = random.Random(42)
    arc = bm.HermiteThumbArc(start_x=195.0, start_y=300.0, end_y=620.0,
                               viewport_width=390.0, rng=rng)
    dispatcher = bm.MobileCDPTouchDispatcher(mock_cdp)
    await dispatcher.fling_scroll(arc)

    assert len(dispatched) >= 3  # start + moves + end
    for a, b_ts in zip(dispatched, dispatched[1:]):
        assert b_ts >= a - 1e-9, f"Non-monotonic timestamps in fling: {a} → {b_ts}"


# ── ReadingRhythmModel ────────────────────────────────────────────────────────

def test_reading_rhythm_model_scales_with_char_count():
    """Longer text → longer dwell."""
    rrm = bm.ReadingRhythmModel()
    rng = random.Random(1)
    short = rrm.dwell(100, rng=rng)
    long_ = rrm.dwell(2000, rng=random.Random(1))
    assert long_ > short


def test_reading_rhythm_model_minimum_dwell():
    """Minimum dwell is 0.5 s even for empty block."""
    rrm = bm.ReadingRhythmModel()
    assert rrm.dwell(0, rng=random.Random(0)) >= 0.5


def test_reading_rhythm_wpm_override():
    """WPM override produces sensible values."""
    rrm = bm.ReadingRhythmModel()
    rng = random.Random(5)
    t = rrm.dwell(1000, rng=rng, wpm_override=200.0)
    # 1000 chars / 5 chars_per_word = 200 words; at 200 WPM = 60 s raw; ×jitter → >50 s
    assert t > 50.0


# ── human.py integration ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_human_move_mouse_mobile_noop():
    """
    B4 mobile no-op: move_mouse with is_mobile=True and cdp_session set
    should NOT call page.mouse.move at all.
    """
    import human

    page = MagicMock()
    page.viewport_size = {"width": 390, "height": 844}
    page.mouse = AsyncMock()

    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock(return_value={})

    rng = random.Random(42)
    await human.move_mouse(page, 195.0, 400.0, rng=rng,
                           cdp_session=mock_cdp, is_mobile=True)
    page.mouse.move.assert_not_called()


@pytest.mark.anyio
async def test_human_click_point_mobile_routes_to_touch_dispatcher():
    """
    B4 mobile tap: click_point with is_mobile=True + cdp_session should call
    Input.dispatchTouchEvent (touchStart + touchEnd), not page.mouse.down/up.
    """
    import human

    touch_calls: list[str] = []

    async def capture_send(method, params):
        if method == "Input.dispatchTouchEvent":
            touch_calls.append(params["type"])
        return {}

    page = MagicMock()
    page.viewport_size = {"width": 390, "height": 844}
    page.mouse = AsyncMock()

    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock(side_effect=capture_send)

    rng = random.Random(42)
    await human.click_point(page, 195.0, 400.0, rng=rng,
                            cdp_session=mock_cdp, is_mobile=True)

    assert "touchStart" in touch_calls
    assert "touchEnd" in touch_calls
    page.mouse.down.assert_not_called()
    page.mouse.up.assert_not_called()
