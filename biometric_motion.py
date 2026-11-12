"""
biometric_motion.py — B4: Biometric Motion & Touch Engine.

Implements research-audited biomechanical models for human-grade pointer and
touch input on both desktop Playwright surfaces and real Android Chrome via CDP
``Input.dispatchTouchEvent``.

Key invariants (all audited in B4 checklist):
  - OU tremor uses stationary-variance formula (not square-root ΔW noise).
  - Desktop CDP ``Input.dispatchMouseEvent`` timestamps use Unix epoch seconds
    (``time.time()``), NOT ``loop.time()``.
  - Hermite asymmetric fling: ``2.2t² - 1.2t³`` → slope ≈ 0.8 at t=1 so
    Chromium VelocityTracker fires fling (≥150 DIP/s).
  - ThumbArc X-curve lateral offset is sampled ONCE per swipe (not per frame).
  - Timestamps strictly monotonic; never clip >20% Gamma intervals at 4 ms.
  - force: 1.0 for capacitive tap; 0.3–0.9 on ``Input.dispatchTouchEvent``.
  - ``radiusX/Y`` included for realistic touch point geometry.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from playwright.async_api import Page

# ── Minimum-Jerk Trajectory ───────────────────────────────────────────────────

def minimum_jerk(t: float) -> float:
    """
    Flash & Hogan (1985) minimum-jerk position profile.
    t ∈ [0, 1] → position ∈ [0, 1].
    s(t) = 10t³ - 15t⁴ + 6t⁵
    """
    t = max(0.0, min(1.0, t))
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def minimum_jerk_velocity(t: float) -> float:
    """ds/dt = 30t² - 60t³ + 30t⁴  (unnormalized, peak ≈ 1.875 at t=0.5)."""
    t = max(0.0, min(1.0, t))
    return 30 * t**2 - 60 * t**3 + 30 * t**4


# ── Shannon–Fitts Duration Estimator ─────────────────────────────────────────

class ShannonFitts:
    """
    Shannon–Fitts law: MT = a + b·log2(D/W + 1).
    Default constants from MacKenzie (1992) empirical fit.
    """
    def __init__(self, a: float = 0.127, b: float = 0.096) -> None:
        self.a = a   # seconds
        self.b = b   # seconds / bit

    def movement_time(self, distance_px: float, target_width_px: float) -> float:
        """Return predicted movement time in seconds (≥ 0.08 s floor)."""
        if distance_px <= 0:
            return self.a
        id_bits = math.log2(distance_px / max(target_width_px, 1.0) + 1.0)
        mt = self.a + self.b * id_bits
        return max(0.08, mt)


# ── Two-Phase Sub-movement ────────────────────────────────────────────────────

@dataclass
class TwoPhaseSubmovement:
    """
    Meyer et al. (1988) two-phase model: ballistic primary movement (90% distance)
    + corrective secondary movement (remaining 10%) with brief inter-phase pause.
    """
    primary_fraction: float = 0.90
    secondary_fraction: float = 0.10
    pause_range: tuple[float, float] = (0.04, 0.12)   # seconds

    def split(
        self,
        x0: float, y0: float, x1: float, y1: float
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return (primary_end, final_end)."""
        px = x0 + (x1 - x0) * self.primary_fraction
        py = y0 + (y1 - y0) * self.primary_fraction
        return (px, py), (x1, y1)


# ── Ornstein–Uhlenbeck Tremor ─────────────────────────────────────────────────

class OrnsteinUhlenbeckTremor:
    """
    Physiological micro-tremor modelled as a discrete Ornstein-Uhlenbeck process.

    Audited fix (B4-1): Use stationary-variance scaling:
        σ² = sigma_rms² · (1 − e^{−2θΔt})
    NOT the square-root Wiener increment «sigma_rms * sqrt(dt) * N(0,1)».
    """

    def __init__(
        self,
        theta: float = 12.0,     # mean-reversion rate (Hz-ish for hand tremor)
        sigma_rms: float = 0.6,  # RMS amplitude in CSS pixels
        rng: Optional[random.Random] = None,
    ) -> None:
        self.theta = theta
        self.sigma_rms = sigma_rms
        self.rng = rng or random.Random()
        self.x: float = 0.0
        self.y: float = 0.0

    def step(self, dt: float) -> tuple[float, float]:
        """
        Advance the OU process by dt seconds and return (dx, dy) displacement.
        Uses stationary-variance envelope: var = σ²_rms · (1 − e^{−2θΔt}).
        """
        decay = math.exp(-self.theta * dt)
        # stationary-variance scaling (audited B4-1)
        variance = self.sigma_rms**2 * (1.0 - math.exp(-2.0 * self.theta * dt))
        std = math.sqrt(max(variance, 0.0))
        # Gaussian via Box-Muller (rng is seeded — no stdlib random)
        u1 = max(1e-12, self.rng.random())
        u2 = self.rng.random()
        z1 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        z2 = math.sqrt(-2.0 * math.log(u1)) * math.sin(2.0 * math.pi * u2)
        self.x = decay * self.x + std * z1
        self.y = decay * self.y + std * z2
        return self.x, self.y

    def reset(self) -> None:
        self.x = 0.0
        self.y = 0.0


# ── Hermite ThumbArc Fling (mobile CDP) ──────────────────────────────────────

@dataclass
class HermiteThumbArc:
    """
    Mobile swipe-scroll trajectory using Hermite asymmetric fling profile.

    Audited fixes (B4-3, B4-4, B4-5):
    - Profile: 2.2t² − 1.2t³  (slope ≈ 0.8 at t=1 → VelocityTracker ≥150 DIP/s)
    - ThumbArc X lateral offset sampled ONCE per swipe, not per frame.
    - Timestamps strictly monotonic; Gamma inter-frame intervals clipped to [4ms, 32ms].
    """

    start_x: float
    start_y: float
    end_y: float
    viewport_width: float = 390.0
    rng: Optional[random.Random] = None

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random()
        # Sample X lateral bias ONCE per swipe (B4-4 fix)
        self._x_offset: float = self.rng.uniform(-18.0, 18.0)
        self._fling_active_end_v: float = 0.0  # filled during waypoint generation

    @staticmethod
    def _hermite_fling(t: float) -> float:
        """
        Position profile f(t) = 2.2t² − 1.2t³.
        f'(1) = 4.4 − 3.6 = 0.8  → active end-velocity for Chromium fling.
        """
        t = max(0.0, min(1.0, t))
        return 2.2 * t**2 - 1.2 * t**3

    def waypoints(
        self, frame_hz: float = 60.0, duration_s: float = 0.28
    ) -> list[dict[str, Any]]:
        """
        Return list of CDP touch-point dicts with keys:
          x, y, timestamp_s (Unix epoch seconds), force, radiusX, radiusY.

        Timestamps monotonic, Gamma-distributed inter-frame intervals clamped
        to [4ms, 32ms] (never >20% clip rate).
        """
        rng = self.rng
        assert rng is not None
        total_dy = self.end_y - self.start_y
        n_frames = max(6, int(round(duration_s * frame_hz)))

        # Gamma inter-frame intervals (shape=4, scale=1/frame_hz)
        mean_dt = 1.0 / frame_hz
        raw_intervals: list[float] = []
        for _ in range(n_frames):
            # Gamma(shape=4) via sum of 4 exponentials (rng-seeded)
            g = sum(-math.log(max(1e-12, rng.random())) for _ in range(4)) / 4.0
            raw_intervals.append(g * mean_dt)

        # Clip to [4ms, 32ms] — ensure <20% clipping
        intervals = [max(0.004, min(0.032, iv)) for iv in raw_intervals]

        t_now = time.time()
        waypoints: list[dict[str, Any]] = []
        cum_time = 0.0
        total_time = sum(intervals)

        for i, iv in enumerate(intervals):
            cum_time += iv
            t_param = cum_time / total_time
            pos = self._hermite_fling(t_param)
            y = self.start_y + pos * total_dy
            # ThumbArc: sinusoidal lateral drift using ONCE-sampled offset (B4-4)
            x = self.start_x + self._x_offset * math.sin(math.pi * t_param)
            # Clamp x to viewport
            x = max(10.0, min(self.viewport_width - 10.0, x))
            ts = t_now + cum_time

            # Realistic capacitive force: ramp from 0.6 to full, hold, fade (B4-5)
            if t_param < 0.1:
                force = 0.5 + 0.4 * (t_param / 0.1)
            elif t_param > 0.85:
                force = 0.9 - 0.4 * ((t_param - 0.85) / 0.15)
            else:
                force = rng.uniform(0.80, 0.95)

            # radiusX/Y: typical phone capacitive touch blob ~8-14 CSS px
            radius_x = rng.uniform(7.0, 13.0)
            radius_y = rng.uniform(8.0, 14.0)

            waypoints.append({
                "x": x,
                "y": y,
                "timestamp_s": ts,
                "force": max(0.3, min(1.0, force)),
                "radiusX": radius_x,
                "radiusY": radius_y,
            })

        # Store active end-velocity (derivative at t≈1) in DIP/s for caller use
        self._fling_active_end_v = abs(total_dy) * 0.8 / total_time  # f'(1)=0.8
        return waypoints


# ── Desktop CDP Mouse Dispatcher ──────────────────────────────────────────────

class DesktopCDPMouseDispatcher:
    """
    Sends ``Input.dispatchMouseEvent`` directly over a CDP session.

    Audited fix (B4-2): timestamps use ``time.time()`` (Unix epoch seconds),
    NOT ``asyncio.get_event_loop().time()`` which is monotonic wall-clock since
    process start and would appear as ~0 to Chromium's input pipeline.
    """

    def __init__(self, cdp_session: Any) -> None:
        self._cdp = cdp_session

    async def move(self, x: float, y: float, modifiers: int = 0) -> None:
        await self._cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
            "modifiers": modifiers,
            "timestamp": time.time(),   # B4-2: Unix epoch seconds
            "button": "none",
            "buttons": 0,
            "clickCount": 0,
            "pointerType": "mouse",
        })

    async def down(self, x: float, y: float, button: str = "left") -> None:
        await self._cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "modifiers": 0,
            "timestamp": time.time(),   # B4-2: Unix epoch seconds
            "button": button,
            "buttons": 1,
            "clickCount": 1,
            "pointerType": "mouse",
        })

    async def up(self, x: float, y: float, button: str = "left") -> None:
        await self._cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "modifiers": 0,
            "timestamp": time.time(),   # B4-2: Unix epoch seconds
            "button": button,
            "buttons": 0,
            "clickCount": 1,
            "pointerType": "mouse",
        })


# ── Mobile CDP Touch Dispatcher ───────────────────────────────────────────────

class MobileCDPTouchDispatcher:
    """
    Sends ``Input.dispatchTouchEvent`` over a CDP session for real Android Chrome.

    Covers tap (touchstart + touchend) and fling scroll (series of touchmove
    with active end-velocity sufficient for Chromium VelocityTracker ≥150 DIP/s).
    """

    def __init__(self, cdp_session: Any) -> None:
        self._cdp = cdp_session

    def _make_point(
        self,
        x: float,
        y: float,
        pointer_id: int = 0,
        force: float = 1.0,
        radius_x: float = 10.0,
        radius_y: float = 10.0,
    ) -> dict[str, Any]:
        return {
            "x": round(x, 1),
            "y": round(y, 1),
            "id": pointer_id,
            "radiusX": round(radius_x, 1),
            "radiusY": round(radius_y, 1),
            "rotationAngle": 0.0,
            "force": round(max(0.3, min(1.0, force)), 3),
        }

    async def tap(
        self,
        x: float,
        y: float,
        rng: Optional[random.Random] = None,
        hold_ms: float = 85.0,
    ) -> None:
        """Single-finger tap at (x, y) with realistic hold duration."""
        if rng is None:
            rng = random.Random()
        force = rng.uniform(0.72, 0.95)
        rx = rng.uniform(7.0, 12.0)
        ry = rng.uniform(8.0, 13.0)
        pt = self._make_point(x, y, force=force, radius_x=rx, radius_y=ry)

        t_start = time.time()
        await self._cdp.send("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [pt],
            "timestamp": t_start,
            "modifiers": 0,
        })
        await asyncio.sleep(hold_ms / 1000.0)
        await self._cdp.send("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [pt],
            "timestamp": time.time(),
            "modifiers": 0,
        })

    async def fling_scroll(
        self,
        thumb_arc: HermiteThumbArc,
        pointer_id: int = 0,
    ) -> None:
        """
        Dispatch a full Hermite-arc fling scroll via CDP touchMove events.
        Ends with touchEnd carrying active end-velocity so Chromium fires fling.
        """
        wps = thumb_arc.waypoints()
        if not wps:
            return

        # touchStart
        first = wps[0]
        await self._cdp.send("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [self._make_point(
                first["x"], first["y"], pointer_id,
                first["force"], first["radiusX"], first["radiusY"]
            )],
            "timestamp": first["timestamp_s"],
            "modifiers": 0,
        })

        # Ensure monotonic timestamps across all moves
        last_ts = first["timestamp_s"]
        for wp in wps[1:-1]:
            ts = max(last_ts + 0.004, wp["timestamp_s"])
            last_ts = ts
            await self._cdp.send("Input.dispatchTouchEvent", {
                "type": "touchMove",
                "touchPoints": [self._make_point(
                    wp["x"], wp["y"], pointer_id,
                    wp["force"], wp["radiusX"], wp["radiusY"]
                )],
                "timestamp": ts,
                "modifiers": 0,
            })
            # Sleep realistically between frames
            await asyncio.sleep(0.014)  # ~16ms/2 to give event loop time

        # touchEnd with low-force lift (active end-velocity stays in Chromium state)
        last_wp = wps[-1]
        end_ts = max(last_ts + 0.004, last_wp["timestamp_s"])
        await self._cdp.send("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [self._make_point(
                last_wp["x"], last_wp["y"], pointer_id,
                0.1, last_wp["radiusX"], last_wp["radiusY"]
            )],
            "timestamp": end_ts,
            "modifiers": 0,
        })


# ── Reading Rhythm Model ──────────────────────────────────────────────────────

class ReadingRhythmModel:
    """
    Models natural saccadic reading rhythm for scroll timing.

    Empirical constants: average fixation ~220ms, saccade ~30ms,
    regression probability 15% (re-reading). Returns dwell duration
    for a text block of `char_count` characters.
    """
    AVG_CHARS_PER_FIXATION: float = 8.0    # chars per fixation (English)
    FIXATION_DURATION_S: float = 0.220     # seconds
    SACCADE_S: float = 0.030              # seconds between fixations
    REGRESSION_PROB: float = 0.15

    def dwell(
        self,
        char_count: int,
        rng: Optional[random.Random] = None,
        wpm_override: Optional[float] = None,
    ) -> float:
        """Return predicted dwell time in seconds for a block of text."""
        if rng is None:
            rng = random.Random()
        if wpm_override is not None:
            # WPM-based fallback: average word ≈ 5 chars
            words = char_count / 5.0
            base = (words / wpm_override) * 60.0
        else:
            n_fix = max(1, char_count / self.AVG_CHARS_PER_FIXATION)
            base = n_fix * (self.FIXATION_DURATION_S + self.SACCADE_S)
            if rng.random() < self.REGRESSION_PROB:
                base *= rng.uniform(1.1, 1.35)
        # Natural variance: ±15%
        jitter = rng.uniform(0.85, 1.15)
        return max(0.5, base * jitter)


# ── High-Level Convenience Helpers ───────────────────────────────────────────

async def desktop_biometric_move(
    page: Page,
    x1: float,
    y1: float,
    rng: Optional[random.Random] = None,
    tremor: Optional[OrnsteinUhlenbeckTremor] = None,
    fitts: Optional[ShannonFitts] = None,
    target_width: float = 24.0,
    cdp_session: Optional[Any] = None,
) -> None:
    """
    Move mouse from current cursor position to (x1, y1) using:
    - Two-phase sub-movement (90% ballistic + 10% corrective)
    - Minimum-Jerk position profile
    - OU tremor overlay
    - CDP timestamps at Unix epoch (B4-2) if cdp_session provided
    Falls back to Playwright page.mouse.move() when cdp_session=None.
    """
    if rng is None:
        rng = random.Random()
    if fitts is None:
        fitts = ShannonFitts()

    from human import get_current_cursor, _cursor_positions
    x0, y0 = get_current_cursor(page, rng)
    dist = math.hypot(x1 - x0, y1 - y0)
    duration = fitts.movement_time(dist, target_width)

    tps = TwoPhaseSubmovement()
    (px, py), _ = tps.split(x0, y0, x1, y1)

    ou = tremor or OrnsteinUhlenbeckTremor(rng=rng)
    ou.reset()

    if cdp_session is not None:
        dispatcher = DesktopCDPMouseDispatcher(cdp_session)
    else:
        dispatcher = None

    async def _move_phase(sx: float, sy: float, ex: float, ey: float, dur: float) -> None:
        steps = max(12, int(dur / 0.014))
        for i in range(steps + 1):
            t_param = i / steps
            pos = minimum_jerk(t_param)
            mx = sx + (ex - sx) * pos
            my = sy + (ey - sy) * pos
            # OU tremor overlay
            dt = dur / steps
            tdx, tdy = ou.step(dt)
            mx += tdx
            my += tdy
            mx = max(0.0, mx)
            my = max(0.0, my)
            if dispatcher is not None:
                await dispatcher.move(mx, my)
            else:
                await page.mouse.move(mx, my)
            await asyncio.sleep(dt)

    # Phase 1: ballistic (90%)
    phase1_dur = duration * 0.70
    await _move_phase(x0, y0, px, py, phase1_dur)

    # Inter-phase pause
    await asyncio.sleep(rng.uniform(*tps.pause_range))

    # Phase 2: corrective (10%)
    phase2_dur = duration * 0.30
    await _move_phase(px, py, x1, y1, phase2_dur)

    _cursor_positions[id(page)] = (x1, y1)


async def mobile_fling_scroll(
    page: Page,
    direction: str = "down",
    distance_px: float = 320.0,
    rng: Optional[random.Random] = None,
    cdp_session: Optional[Any] = None,
) -> None:
    """
    Dispatch a mobile-grade HermiteThumbArc fling scroll via CDP or fall back
    to page.mouse.wheel() for desktop surfaces.

    Args:
        direction: "down" or "up"
        distance_px: scroll distance in CSS pixels
        cdp_session: CDP session for real Android Chrome; if None uses mouse.wheel
    """
    if rng is None:
        rng = random.Random()

    vp = page.viewport_size or {"width": 390, "height": 844}
    mid_x = vp["width"] / 2.0
    start_y = vp["height"] * rng.uniform(0.45, 0.60)
    dy = distance_px if direction == "down" else -distance_px
    end_y = start_y + dy

    if cdp_session is not None:
        arc = HermiteThumbArc(
            start_x=mid_x,
            start_y=start_y,
            end_y=end_y,
            viewport_width=float(vp["width"]),
            rng=rng,
        )
        dispatcher = MobileCDPTouchDispatcher(cdp_session)
        await dispatcher.fling_scroll(arc)
    else:
        # Desktop fallback: eased mouse.wheel
        sign = 1 if direction == "down" else -1
        chunks = rng.randint(6, 12)
        per_chunk = abs(distance_px) / chunks
        for i in range(chunks):
            t = (i + 1) / chunks
            ease = minimum_jerk(t) - minimum_jerk(i / chunks)
            scroll_this = int(per_chunk * ease * chunks)
            if scroll_this:
                try:
                    await page.mouse.wheel(0, sign * scroll_this)
                except Exception:
                    pass
            await asyncio.sleep(rng.uniform(0.018, 0.055))
