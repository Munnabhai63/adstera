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
    Steps: 18–38. Delay per step: 8–30 ms. 4% chance of a mid-path micro-pause.
    """
    if rng is None:
        rng = random.Random()

    # Retrieve current mouse position from page state if not provided
    if start_x is None or start_y is None:
        start_x = rng.uniform(0, 800)
        start_y = rng.uniform(0, 600)

    steps = rng.randint(18, 38)
    path = _bezier_path(start_x, start_y, x1, y1, steps, rng)

    pause_at = rng.randint(steps // 4, 3 * steps // 4) if rng.random() < 0.04 else -1

    for i, (px, py) in enumerate(path):
        await page.mouse.move(px, py)
        delay_ms = rng.uniform(8, 30)
        await asyncio.sleep(delay_ms / 1000)
        if i == pause_at:
            await asyncio.sleep(rng.uniform(0.15, 0.6))


async def click_element(
    page: Page,
    selector: str,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Click an element at a random point inside its bounding box (20–80% x, 25–75% y).
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

        tx = box["x"] + box["width"] * rng.uniform(0.20, 0.80)
        ty = box["y"] + box["height"] * rng.uniform(0.25, 0.75)

        await move_mouse(page, tx, ty, rng,
                         start_x=rng.uniform(0, page.viewport_size["width"] if page.viewport_size else 800),
                         start_y=rng.uniform(0, page.viewport_size["height"] if page.viewport_size else 600))

        await asyncio.sleep(rng.uniform(0.05, 0.15))
        await page.mouse.click(tx, ty)
        return True
    except Exception as exc:
        logger.debug("click_element(%s) failed: %s", selector, exc)
        return False


async def scroll_page(
    page: Page,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Scroll through the page in human-like chunks with easing.
    Total scroll: 180–520 px per chunk, 1.2–6.0 s pauses, 18% chance of a scroll-back.
    """
    if rng is None:
        rng = random.Random()

    viewport_h = (page.viewport_size or {}).get("height", 768)
    page_h = await page.evaluate("() => document.body.scrollHeight")
    total = max(0, int(page_h) - viewport_h)
    if total <= 0:
        return

    current_y = 0
    while current_y < total:
        chunk = rng.randint(180, 520)
        # Easing: split chunk into substeps with quadratic ease-out
        substeps = rng.randint(8, 18)
        for s in range(substeps):
            t = (s + 1) / substeps
            ease = 1 - (1 - t) ** 2          # ease-out quad
            partial = int(chunk * ease / substeps)
            if partial > 0:
                await page.mouse.wheel(0, partial)
            await asyncio.sleep(rng.uniform(0.03, 0.09))

        current_y = min(current_y + chunk, total)
        pause = rng.uniform(1.2, 6.0)
        await asyncio.sleep(pause)

        # 18% chance of a partial scroll-back
        if rng.random() < 0.18:
            back = rng.randint(60, 200)
            await page.mouse.wheel(0, -back)
            await asyncio.sleep(rng.uniform(0.5, 1.5))
            current_y = max(0, current_y - back)


async def idle_drift(
    page: Page,
    rng: Optional[random.Random] = None,
    duration_s: float = 1.0,
) -> None:
    """
    Produce small idle mouse movements so there are always recent input events.
    Called every 8–20 s during dwell.
    """
    if rng is None:
        rng = random.Random()

    viewport = page.viewport_size or {"width": 800, "height": 600}
    x = rng.uniform(50, viewport["width"] - 50)
    y = rng.uniform(50, viewport["height"] - 50)
    jitter_x = x + rng.uniform(-20, 20)
    jitter_y = y + rng.uniform(-20, 20)

    await move_mouse(page, jitter_x, jitter_y, rng, start_x=x, start_y=y)
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

