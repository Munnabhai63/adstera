"""
human.py — Bezier mouse paths, eased scrolling, click selection, human typing.
All timing uses asyncio.sleep, never time.sleep.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from typing import Optional, Any

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
        # BHV-2: Fitts's Law velocity profile (acceleration -> ballistic flight -> deceleration)
        pct = i / steps
        if pct < 0.20:
            delay_ms = rng.uniform(20, 48)  # Acceleration phase
        elif pct < 0.80:
            delay_ms = rng.uniform(6, 16)   # Ballistic flight phase
        else:
            delay_ms = rng.uniform(16, 42)  # Precision landing / deceleration phase
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


async def _safe_eval(page: Page, expr: str, default: Any = 0) -> Any:
    """Safely evaluate JS expression on page, tolerating in-flight redirects or context resets."""
    try:
        return await page.evaluate(expr)
    except Exception:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=2500)
            return await page.evaluate(expr)
        except Exception:
            return default


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

    y_before = await _safe_eval(page, "() => window.scrollY", 0)

    # If Arrow keys, user may press 1 to 3 times in rhythm
    repeat = rng.randint(1, 3) if "Arrow" in key else 1

    for r in range(repeat):
        hold_time = rng.uniform(0.06, 0.14)
        try:
            await page.keyboard.down(key)
            await asyncio.sleep(hold_time)
            await page.keyboard.up(key)
        except Exception:
            break
        if r < repeat - 1:
            await asyncio.sleep(rng.uniform(0.08, 0.18))

    await asyncio.sleep(rng.uniform(0.15, 0.35))
    y_after = await _safe_eval(page, "() => window.scrollY", y_before)
    return int(abs(y_after - y_before))


async def get_reading_anchors(page: Page) -> list[dict]:
    """
    Extract substantive readable content elements (<p>, <h2>, <h3>, <li>, <blockquote>, <article>)
    with their vertical positions, dimensions, and character counts to model an eye-tracking heatmap.
    """
    script = """() => {
        const selectors = ['p', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'li', 'article', 'section', '.meta', '[class*="article"]'];
        const elements = document.querySelectorAll(selectors.join(','));
        const anchors = [];
        const seenTops = new Set();
        
        elements.forEach(el => {
            const rect = el.getBoundingClientRect();
            const text = (el.innerText || el.textContent || '').trim();
            // Filter out empty, tiny, or hidden elements
            if (rect.height < 10 || rect.width < 50 || text.length < 15) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

            const top = Math.round(rect.top + window.scrollY);
            const band = Math.round(top / 20) * 20;
            if (seenTops.has(band)) return;
            seenTops.add(band);

            anchors.push({
                tag: el.tagName.toLowerCase(),
                top: top,
                left: Math.round(rect.left),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                char_count: text.length,
            });
        });

        anchors.sort((a, b) => a.top - b.top);
        return anchors;
    }"""
    try:
        res = await _safe_eval(page, script, default=[])
        return res if isinstance(res, list) else []
    except Exception:
        return []


def calculate_reading_pause(char_count: int, rng: Optional[random.Random] = None) -> float:
    """
    Calculate realistic human reading fixation dwell (in seconds) based on character density.
    Scales smoothly from quick skims (1.2s) to deep paragraph comprehension (5.5s–6.5s).
    """
    if rng is None:
        rng = random.Random()
    if char_count <= 40:
        return float(rng.uniform(1.2, 2.2))
    elif char_count <= 200:
        return float(rng.uniform(2.2, 3.8))
    else:
        scaled = 3.5 + min(2.5, (char_count - 200) / 180.0)
        return float(scaled * rng.uniform(0.92, 1.18))


async def reading_cursor_follow(
    page: Page,
    anchor: dict,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Simulate unconscious mouse tracking / margin gaze alignment while a human reads a text block.
    Moves the cursor smoothly toward the anchor's readable boundary.
    """
    if rng is None:
        rng = random.Random()
    vp = page.viewport_size or {"width": 1280, "height": 800}
    current_scrollY = await _safe_eval(page, "() => window.scrollY", 0)
    
    screen_y = anchor["top"] - current_scrollY
    if 0 <= screen_y <= vp["height"] - 40:
        target_x = max(40.0, min(vp["width"] - 60.0, float(anchor["left"] + rng.uniform(20, min(anchor.get("width", 200), 250)))))
        target_y = max(40.0, min(vp["height"] - 40.0, float(screen_y + rng.uniform(10, min(anchor.get("height", 40), 50)))))
        await move_mouse(page, target_x, target_y, rng)


async def scroll_page_content_aware(
    page: Page,
    rng: Optional[random.Random] = None,
    speed_multiplier: float = 1.0,
) -> None:
    """
    Smart Content-Aware Reading Heatmap Scrolling (Step 8).
    - Traverses the page by identifying text blocks (<p>, <h2>, <h3>, <li>).
    - Pauses dynamically according to character count.
    - 30% chance of cursor reading follow.
    - 18%–25% chance of smart scroll-back on dense sections.
    - Uses hybrid navigation (75% eased mouse wheel, 25% keyboard Space/PageDown).
    """
    if rng is None:
        rng = random.Random()

    viewport_h = (page.viewport_size or {}).get("height", 768)
    page_h = await _safe_eval(page, "() => (document.body ? document.body.scrollHeight : 0) || (document.documentElement ? document.documentElement.scrollHeight : 0) || 768", 768)
    total = max(0, int(page_h) - viewport_h)
    if total <= 0:
        return

    # Extract content anchors
    anchors = await get_reading_anchors(page)
    current_y = await _safe_eval(page, "() => window.scrollY", 0)
    anchor_idx = 0

    while current_y < total:
        # Identify next anchor below current viewport top
        target_anchor = None
        while anchor_idx < len(anchors):
            if anchors[anchor_idx]["top"] > current_y + 40:
                target_anchor = anchors[anchor_idx]
                anchor_idx += 1
                break
            anchor_idx += 1

        # 25% keyboard scroll, 75% mouse wheel scroll
        use_keyboard = rng.random() < 0.25

        if use_keyboard:
            scrolled_dist = await keyboard_scroll(page, direction="down", rng=rng)
            current_y = await _safe_eval(page, "() => window.scrollY", current_y + 120)
            if scrolled_dist <= 0:
                chunk = rng.randint(180, 480)
                try:
                    await page.mouse.wheel(0, chunk)
                except Exception:
                    break
                current_y = min(current_y + chunk, total)
        else:
            chunk = rng.randint(180, 480)
            substeps = rng.randint(8, 16)
            for s in range(substeps):
                t = (s + 1) / substeps
                ease = 1 - (1 - t) ** 2
                partial = int(chunk * ease / substeps)
                if partial > 0:
                    try:
                        await page.mouse.wheel(0, partial)
                    except Exception:
                        break
                await asyncio.sleep(rng.uniform(0.02, 0.06))
            current_y = await _safe_eval(page, "() => window.scrollY", current_y + chunk)

        # Dynamic reading dwell pause based on content in view
        if target_anchor:
            pause = calculate_reading_pause(target_anchor["char_count"], rng) * speed_multiplier
            # 30% chance of cursor reading alignment
            if rng.random() < 0.30:
                try:
                    await reading_cursor_follow(page, target_anchor, rng)
                except Exception:
                    pass
        else:
            pause = rng.uniform(1.2, 4.0) * speed_multiplier

        await asyncio.sleep(pause)

        # 18%–25% chance of partial scroll-back (rereading)
        if rng.random() < 0.20:
            back_key = rng.random() < 0.30
            if back_key:
                await keyboard_scroll(page, direction="up", rng=rng)
            else:
                back = rng.randint(60, 180)
                try:
                    await page.mouse.wheel(0, -back)
                except Exception:
                    pass
            await asyncio.sleep(rng.uniform(0.5, 1.4) * speed_multiplier)
            current_y = await _safe_eval(page, "() => window.scrollY", current_y)

    # Terminal footer dwell (1.5s - 3.0s)
    await asyncio.sleep(rng.uniform(1.5, 3.0) * speed_multiplier)


async def scroll_page(
    page: Page,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Scroll through the page with Step 8 Smart Content-Aware Reading Heatmap.
    """
    await scroll_page_content_aware(page, rng=rng, speed_multiplier=1.0)


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


# ── Step 10: Bored Real Visitor Emulation, Tab Blur & Typing Cadence ───────────

async def simulate_tab_blur(
    page: Page,
    rng: Optional[random.Random] = None,
    duration_s: Optional[float] = None,
) -> bool:
    """
    Simulate natural human tab inattention / window blur (glancing at phone, switching tabs).
    Toggles window and document focus states cleanly using CDP and DOM events.
    """
    if rng is None:
        rng = random.Random()
    sleep_dur = duration_s if duration_s is not None else float(rng.uniform(1.5, 3.8))
    
    try:
        cdp = await page.context.new_cdp_session(page)
        # Deactivate window focus (blur)
        await cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": False})
        await _safe_eval(page, "() => { window.dispatchEvent(new Event('blur')); document.dispatchEvent(new Event('visibilitychange')); }")
        await asyncio.sleep(sleep_dur)
        # Restore window focus
        await cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        await _safe_eval(page, "() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); }")
        await cdp.detach()
        return True
    except Exception as exc:
        logger.debug("simulate_tab_blur fallback: %s", exc)
        try:
            await _safe_eval(page, "() => { window.dispatchEvent(new Event('blur')); }")
            await asyncio.sleep(sleep_dur)
            await _safe_eval(page, "() => { window.dispatchEvent(new Event('focus')); }")
            return True
        except Exception:
            return False


async def simulate_bored_idle_fidgets(
    page: Page,
    rng: Optional[random.Random] = None,
    count: int = 2,
) -> dict:
    """
    Simulate natural idle micro-fidgets (lazy cursor wandering/twitches) while a bored human
    dwells on a page. Maintains continuous cursor tracking without teleportation.
    """
    if rng is None:
        rng = random.Random()
    vp = page.viewport_size or {"width": 1280, "height": 800}
    cur_x, cur_y = get_current_cursor(page, rng)
    steps_taken = 0

    for _ in range(max(1, count)):
        drift_x = max(35.0, min(vp["width"] - 35.0, cur_x + rng.uniform(-75.0, 75.0)))
        drift_y = max(35.0, min(vp["height"] - 35.0, cur_y + rng.uniform(-50.0, 50.0)))
        await move_mouse(page, drift_x, drift_y, rng, start_x=cur_x, start_y=cur_y)
        cur_x, cur_y = drift_x, drift_y
        steps_taken += 1
        await asyncio.sleep(rng.uniform(0.25, 0.75))

    return {"steps": steps_taken, "final_x": cur_x, "final_y": cur_y}


async def type_text_human(
    page: Page,
    selector: str,
    text: str,
    rng: Optional[random.Random] = None,
) -> dict:
    """
    Type text with realistic human typing cadence:
    - 60ms–220ms per character delay.
    - 4% chance of realistic typo followed by natural backspace correction.
    - 7% chance of a 350ms–500ms hesitation pause.
    Returns typing telemetry.
    """
    if rng is None:
        rng = random.Random()

    try:
        await page.click(selector)
    except Exception:
        pass

    typo_count = 0
    hesitation_count = 0

    for char in text:
        # 4% chance of typo on alphabetic characters
        if char.isalpha() and rng.random() < 0.04:
            typo_char = rng.choice("abcdefghijklmnopqrstuvwxyz")
            await page.keyboard.type(typo_char)
            typo_count += 1
            await asyncio.sleep(rng.uniform(0.08, 0.18))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(rng.uniform(0.06, 0.14))

        await page.keyboard.type(char)
        delay = rng.uniform(0.06, 0.20)

        # 7% chance of human cognitive hesitation pause
        if rng.random() < 0.07:
            delay += rng.uniform(0.35, 0.50)
            hesitation_count += 1

        await asyncio.sleep(delay)

    return {
        "chars_typed": len(text),
        "typos_corrected": typo_count,
        "hesitations": hesitation_count,
    }


async def type_text(
    page: Page,
    selector: str,
    text: str,
    rng: Optional[random.Random] = None,
) -> None:
    """
    Standard typing entrypoint aliasing type_text_human.
    """
    await type_text_human(page, selector, text, rng)



async def reading_speed_scroll(
    page: Page,
    rng: Optional[random.Random] = None,
    wpm: Optional[float] = None,
) -> float:
    """
    ADV-3: Human Reading Pace Scroll.
    Calculates total article word count, maps to human reading rate (180–280 WPM),
    and scrolls through content chunks with natural pauses.
    Includes 12% probability of scrolling back up to re-read key points.
    Returns total seconds spent reading.
    """
    if rng is None:
        rng = random.Random()
    if wpm is None:
        wpm = rng.uniform(180, 260)

    try:
        word_count = await page.evaluate("() => document.body.innerText.split(/\\s+/).length")
    except Exception:
        word_count = 1200

    estimated_seconds = (max(300, word_count) / wpm) * 60.0
    chunks = rng.randint(3, 6)
    time_per_chunk = min(8.0, estimated_seconds / chunks)

    for c in range(chunks):
        scroll_px = rng.randint(220, 480)
        await page.mouse.wheel(0, scroll_px)
        await asyncio.sleep(rng.uniform(time_per_chunk * 0.4, time_per_chunk * 0.9))

        if rng.random() < 0.12:
            await page.mouse.wheel(0, -rng.randint(80, 180))
            await asyncio.sleep(rng.uniform(0.8, 1.8))

    return estimated_seconds


async def text_reading_mouse(
    page: Page,
    rng: Optional[random.Random] = None,
) -> None:
    """
    ADV-5: Mouse Heatmap Clustering.
    Finds visible paragraphs/headings on the page and drifts mouse horizontally
    from left to right across text lines as an active reader, defeating
    entropy and heatmap bot detection filters.
    """
    if rng is None:
        rng = random.Random()

    try:
        boxes = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('p, h2, h3, li'));
            return els.map(el => {
                const r = el.getBoundingClientRect();
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            }).filter(b => b.y > 0 && b.y < window.innerHeight && b.w > 100);
        }""")
        if not boxes:
            return

        sample_boxes = rng.sample(boxes, min(2, len(boxes)))
        for b in sample_boxes:
            start_x = b["x"] + rng.uniform(10, 40)
            end_x = b["x"] + min(b["w"] - 20, rng.uniform(150, 400))
            y_pos = b["y"] + rng.uniform(5, b["h"] - 5)

            await move_mouse(page, start_x, y_pos, rng)
            await asyncio.sleep(rng.uniform(0.15, 0.4))

            steps = rng.randint(6, 14)
            for s in range(steps):
                curr_x = start_x + (end_x - start_x) * ((s + 1) / steps)
                curr_y = y_pos + rng.uniform(-1.5, 1.5)
                await page.mouse.move(curr_x, curr_y)
                await asyncio.sleep(rng.uniform(0.04, 0.08))
            await asyncio.sleep(rng.uniform(0.2, 0.5))
    except Exception as exc:
        logger.debug("text_reading_mouse notice: %s", exc)
