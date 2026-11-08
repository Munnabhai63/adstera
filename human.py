"""
human.py — Bezier mouse paths, eased scrolling, click selection, human typing.
All timing uses asyncio.sleep, never time.sleep.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# ── Cursor state tracking ──────────────────────────────────────────────────────
_cursor_positions: dict[int, tuple[float, float]] = {}


def get_current_cursor(page: Page, rng: Optional[random.Random] = None) -> tuple[float, float]:
    """Return the last known mouse position for this page, or an initial natural starting coordinate."""
    pos = _cursor_positions.get(id(page))
    if pos is not None:
        return pos
    if rng is None:
        rng = random.Random()
    vp = page.viewport_size or {"width": 1280, "height": 800}
    start_x = vp["width"] * rng.uniform(0.35, 0.65)
    start_y = vp["height"] * rng.uniform(0.35, 0.65)
    _cursor_positions[id(page)] = (start_x, start_y)
    return (start_x, start_y)


# ── Bezier helpers ─────────────────────────────────────────────────────────────

def _cubic_bezier(p0: tuple, p1: tuple, p2: tuple, p3: tuple, t: float) -> tuple[float, float]:
    """Evaluate a cubic Bezier curve at parameter t ∈ [0, 1]."""
    mt = 1 - t
    x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def _bezier_path(
    x0: float, y0: float, x1: float, y1: float, steps: int, rng: random.Random
) -> list[tuple[float, float]]:
    """
    Generate a list of (x, y) waypoints along a cubic Bezier path
    between (x0, y0) and (x1, y1) with two randomly perturbed control points.
    """
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy) or 1.0

    # Control points offset perpendicular to the main direction
    perp_scale = dist * rng.uniform(0.1, 0.4)
    angle = math.atan2(dy, dx)
    perp = angle + math.pi / 2

    cp1 = (
        x0 + dx * rng.uniform(0.2, 0.4) + math.cos(perp) * perp_scale * rng.uniform(-1, 1),
        y0 + dy * rng.uniform(0.2, 0.4) + math.sin(perp) * perp_scale * rng.uniform(-1, 1),
    )
    cp2 = (
        x0 + dx * rng.uniform(0.6, 0.8) + math.cos(perp) * perp_scale * rng.uniform(-1, 1),
        y0 + dy * rng.uniform(0.6, 0.8) + math.sin(perp) * perp_scale * rng.uniform(-1, 1),
    )

    p0, p3 = (x0, y0), (x1, y1)
    path = []
    for i in range(steps + 1):
        t = i / steps
        path.append(_cubic_bezier(p0, cp1, cp2, p3, t))
    return path


async def move_mouse(
    page: Page,
    x1: float,
    y1: float,
    rng: Optional[random.Random] = None,
    start_x: Optional[float] = None,
    start_y: Optional[float] = None,
) -> None:
    """
    Move the mouse from (start_x, start_y) to (x1, y1) along a cubic Bezier path.
    Preserves continuous cursor tracking across movements without unnatural teleportation.
    Steps: 18–38. Delay per step: 8–30 ms. 4% chance of a mid-path micro-pause.
    """
    if rng is None:
        rng = random.Random()

    # Retrieve current mouse position without teleporting
    if start_x is None or start_y is None:
        start_x, start_y = get_current_cursor(page, rng)

    steps = rng.randint(18, 38)
    path = _bezier_path(start_x, start_y, x1, y1, steps, rng)

    pause_at = rng.randint(steps // 4, 3 * steps // 4) if rng.random() < 0.04 else -1

    for i, (px, py) in enumerate(path):
        await page.mouse.move(px, py)
        delay_ms = rng.uniform(8, 30)
        await asyncio.sleep(delay_ms / 1000)
        if i == pause_at:
            await asyncio.sleep(rng.uniform(0.15, 0.6))

    _cursor_positions[id(page)] = (x1, y1)


async def micro_tremor(
    page: Page,
    x: float,
    y: float,
    count: int = 3,
    rng: Optional[random.Random] = None,
) -> tuple[float, float]:
    """
    Simulate natural human physiological micro-tremor (0.5–1.8 px micro-movements)
    over 120ms–240ms while resting or hovering on a point before interacting.
    """
    if rng is None:
        rng = random.Random()
    cur_x, cur_y = x, y
    for _ in range(count):
        dx = rng.uniform(-1.5, 1.5)
        dy = rng.uniform(-1.5, 1.5)
        cur_x = max(0.0, x + dx)
        cur_y = max(0.0, y + dy)
        await page.mouse.move(cur_x, cur_y)
        await asyncio.sleep(rng.uniform(0.03, 0.07))
    _cursor_positions[id(page)] = (cur_x, cur_y)
    return cur_x, cur_y


async def click_point(
    page: Page,
    x: float,
    y: float,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Execute a human-grade ergonomic click at (x, y):
    1. Continuous Bézier trajectory from current cursor position.
    2. Pre-click hover dwell (120ms–240ms) with hand micro-tremors.
    3. Mouse down.
    4. Human finger depress hold duration (60ms–130ms).
    5. Mouse up.
    6. Post-click micro settlement dwell (40ms–90ms).
    """
    if rng is None:
        rng = random.Random()

    # 1. Smooth Bézier glide to target
    await move_mouse(page, x, y, rng)

    # 2. Pre-click settlement with physiological micro-tremors
    tremor_steps = rng.randint(2, 4)
    await micro_tremor(page, x, y, count=tremor_steps, rng=rng)
    await asyncio.sleep(rng.uniform(0.04, 0.10))

    # 3. Mouse down
    await page.mouse.down()

    # 4. Finger hold duration
    await asyncio.sleep(rng.uniform(0.06, 0.13))

    # 5. Mouse up
    await page.mouse.up()

    # 6. Post-click settlement dwell
    await asyncio.sleep(rng.uniform(0.04, 0.09))


async def click_element(
    page: Page,
    selector: str,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Click an element at a biological point inside its bounding box (20–80% x, 25–75% y)
    with pre-click settlement and micro-tremors.
    Returns True on success.
    """
    if rng is None:
        rng = random.Random()

    try:
        elem = await page.query_selector(selector)
        if elem is None:
            return False
        box = await elem.bounding_box()
        if box is None:
            return False

        # Ergonomic randomized distribution (never exact center 50/50)
        tx = box["x"] + box["width"] * rng.uniform(0.20, 0.80)
        ty = box["y"] + box["height"] * rng.uniform(0.25, 0.75)

        await click_point(page, tx, ty, rng)
        return True
    except Exception as exc:
        logger.debug("click_element(%s) failed: %s", selector, exc)
        return False


async def keyboard_scroll(
    page: Page,
    direction: str = "down",
    key: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> int:
    """
    Perform human-grade keyboard scrolling using Space, PageDown, or Arrow keys.
    Simulates natural physical finger hold duration (60ms–140ms).
    Returns the estimated or measured scroll distance.
    """
    if rng is None:
        rng = random.Random()

    if key is None:
        if direction == "down":
            key_choices = ["Space", "PageDown", "ArrowDown"]
            weights = [0.45, 0.35, 0.20]
            key = rng.choices(key_choices, weights=weights, k=1)[0]
        else:
            key_choices = ["ArrowUp", "PageUp"]
            weights = [0.70, 0.30]
            key = rng.choices(key_choices, weights=weights, k=1)[0]

    y_before = await page.evaluate("() => window.scrollY")

    # If Arrow keys, user may press 1 to 3 times in rhythm
    repeat = rng.randint(1, 3) if "Arrow" in key else 1

    for r in range(repeat):
        hold_time = rng.uniform(0.06, 0.14)
        await page.keyboard.down(key)
        await asyncio.sleep(hold_time)
        await page.keyboard.up(key)
        if r < repeat - 1:
            await asyncio.sleep(rng.uniform(0.08, 0.18))

    await asyncio.sleep(rng.uniform(0.15, 0.35))
    y_after = await page.evaluate("() => window.scrollY")
    return int(abs(y_after - y_before))


async def scroll_page(
    page: Page,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Scroll through the page in human-like chunks with hybrid navigation.
    Mixes smooth mouse wheel easing (75%) with keyboard navigation (25% - Spacebar, PageDown, ArrowDown).
    Pause duration: 1.2–6.0 s per chunk.
    18% chance of partial scroll-back (rereading paragraphs via wheel or ArrowUp).
    """
    if rng is None:
        rng = random.Random()

    viewport_h = (page.viewport_size or {}).get("height", 768)
    page_h = await page.evaluate("() => document.body.scrollHeight")
    total = max(0, int(page_h) - viewport_h)
    if total <= 0:
        return

    current_y = await page.evaluate("() => window.scrollY")

    while current_y < total:
        # 25% chance of keyboard scroll, 75% chance of mouse wheel scroll
        use_keyboard = rng.random() < 0.25

        if use_keyboard:
            # Keyboard navigation: Spacebar, PageDown, or ArrowDown
            scrolled_dist = await keyboard_scroll(page, direction="down", rng=rng)
            current_y = await page.evaluate("() => window.scrollY")
            if scrolled_dist <= 0:
                # Fallback if key didn't move viewport
                chunk = rng.randint(180, 520)
                await page.mouse.wheel(0, chunk)
                current_y = min(current_y + chunk, total)
        else:
            # Mouse wheel scroll with quadratic ease-out substeps
            chunk = rng.randint(180, 520)
            substeps = rng.randint(8, 18)
            for s in range(substeps):
                t = (s + 1) / substeps
                ease = 1 - (1 - t) ** 2  # ease-out quad
                partial = int(chunk * ease / substeps)
                if partial > 0:
                    await page.mouse.wheel(0, partial)
                await asyncio.sleep(rng.uniform(0.03, 0.09))
            current_y = await page.evaluate("() => window.scrollY")

        # Natural reading dwell pause
        pause = rng.uniform(1.2, 6.0)
        await asyncio.sleep(pause)

        # 18% chance of a partial scroll-back (rereading)
        if rng.random() < 0.18:
            back_key = rng.random() < 0.30
            if back_key:
                await keyboard_scroll(page, direction="up", rng=rng)
            else:
                back = rng.randint(60, 200)
                await page.mouse.wheel(0, -back)
            await asyncio.sleep(rng.uniform(0.5, 1.5))
            current_y = await page.evaluate("() => window.scrollY")


async def idle_drift(
    page: Page,
    rng: Optional[random.Random] = None,
    duration_s: float = 1.0,
) -> None:
    """
    Produce small idle mouse movements so there are always recent input events.
    Called every 8–20 s during dwell. Moves continuously from current cursor position.
    """
    if rng is None:
        rng = random.Random()

    viewport = page.viewport_size or {"width": 800, "height": 600}
    start_x, start_y = get_current_cursor(page, rng)
    jitter_x = max(30.0, min(viewport["width"] - 30.0, start_x + rng.uniform(-40, 40)))
    jitter_y = max(30.0, min(viewport["height"] - 30.0, start_y + rng.uniform(-40, 40)))

    await move_mouse(page, jitter_x, jitter_y, rng, start_x=start_x, start_y=start_y)
    await asyncio.sleep(duration_s * rng.uniform(0.8, 1.2))


async def type_text(
    page: Page,
    selector: str,
    text: str,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Type text with human-like per-character delays and occasional typo+backspace.
    """
    if rng is None:
        rng = random.Random()

    await page.click(selector)
    for char in text:
        # Occasional typo
        if rng.random() < 0.04:
            wrong = rng.choice("abcdefghijklmnopqrstuvwxyz")
            await page.keyboard.type(wrong)
            await asyncio.sleep(rng.uniform(0.06, 0.22))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(rng.uniform(0.08, 0.18))

        await page.keyboard.type(char)
        delay = rng.uniform(0.06, 0.22)
        # Occasional hesitation
        if rng.random() < 0.07:
            delay += 0.4
        await asyncio.sleep(delay)

