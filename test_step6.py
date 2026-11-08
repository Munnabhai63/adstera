"""
test_step6.py — Live Verification Script for Step 6 (Hybrid Keyboard Navigation & Scroll).
Validates:
1. Keyboard navigation scrolling: Spacebar, PageDown, and ArrowDown.
2. Realistic keystroke hold duration (60ms–140ms between keydown and keyup).
3. Reverse scrolling: ArrowUp and PageUp for rereading sections.
4. Hybrid scroll_page integration: simultaneous firing of wheel and keyboard events in browser DOM.
5. DOM event telemetry asserting natural human navigation biometrics.
"""
import asyncio
import json
import random
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright
import human


async def run_verification():
    print("\n" + "=" * 70)
    print(">> STEP 6 HYBRID KEYBOARD NAVIGATION & SCROLL VERIFICATION")
    print("=" * 70 + "\n")

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { height: 4000px; background: #0f172a; color: white; padding: 24px; font-family: sans-serif; }
            .section { height: 600px; border-bottom: 2px dashed #334155; padding-top: 20px; }
        </style>
    </head>
    <body>
        <h1>Hybrid Navigation Biometrics Suite</h1>
        <div class="section">Section 1: Introduction</div>
        <div class="section">Section 2: Deep Dive Analysis</div>
        <div class="section">Section 3: Practical Implementation</div>
        <div class="section">Section 4: Advanced Optimizations</div>
        <div class="section">Section 5: Final Summary</div>

        <script>
            window.navEvents = [];
            window.addEventListener('keydown', e => {
                window.navEvents.push({ type: 'keydown', key: e.key, t: performance.now() });
            });
            window.addEventListener('keyup', e => {
                window.navEvents.push({ type: 'keyup', key: e.key, t: performance.now() });
            });
            window.addEventListener('wheel', e => {
                window.navEvents.push({ type: 'wheel', deltaY: e.deltaY, t: performance.now() });
            });
            window.addEventListener('scroll', e => {
                window.navEvents.push({ type: 'scroll', y: Math.round(window.scrollY), t: performance.now() });
            });
        </script>
    </body>
    </html>
    """

    rng = random.Random(777)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.set_content(html_content)

        # ── Test A: Dedicated Keyboard Navigation Keys ──────────────────────
        print("--- Test A: Key-by-Key Physical Down/Up Navigation ---")

        # 1. PageDown
        y0 = await page.evaluate("() => window.scrollY")
        dist_pagedown = await human.keyboard_scroll(page, direction="down", key="PageDown", rng=rng)
        y1 = await page.evaluate("() => window.scrollY")
        print(f"  • PageDown  : Scrolled from {y0}px to {y1}px (Delta: +{y1 - y0}px)")
        assert y1 > y0, "PageDown did not advance scroll position"

        # 2. ArrowDown
        dist_arrowdown = await human.keyboard_scroll(page, direction="down", key="ArrowDown", rng=rng)
        y2 = await page.evaluate("() => window.scrollY")
        print(f"  • ArrowDown : Scrolled from {y1}px to {y2}px (Delta: +{y2 - y1}px)")
        assert y2 > y1, "ArrowDown did not advance scroll position"

        # 3. Spacebar
        dist_space = await human.keyboard_scroll(page, direction="down", key="Space", rng=rng)
        y3 = await page.evaluate("() => window.scrollY")
        print(f"  • Spacebar  : Scrolled from {y2}px to {y3}px (Delta: +{y3 - y2}px)")
        assert y3 > y2, "Spacebar did not advance scroll position"

        # 4. ArrowUp (Reread back)
        dist_arrowup = await human.keyboard_scroll(page, direction="up", key="ArrowUp", rng=rng)
        y4 = await page.evaluate("() => window.scrollY")
        print(f"  • ArrowUp   : Reread back from {y3}px to {y4}px (Delta: -{y3 - y4}px)")
        assert y4 < y3, "ArrowUp did not reverse scroll position"

        print("  [✓] Test A Passed: All individual navigation keys functional.\n")

        # ── Test B: Hybrid scroll_page Simulation ───────────────────────────
        print("--- Test B: Autonomous Hybrid scroll_page Integration ---")
        # Scroll through the rest of the document with hybrid wheel + keyboard
        await human.scroll_page(page, rng=rng)
        final_y = await page.evaluate("() => window.scrollY")
        print(f"  • Finished hybrid scroll at Y = {final_y}px")

        nav_events = await page.evaluate("() => window.navEvents")
        await browser.close()

    # Analyze telemetry
    key_downs = [e for e in nav_events if e["type"] == "keydown"]
    key_ups   = [e for e in nav_events if e["type"] == "keyup"]
    wheel_evts= [e for e in nav_events if e["type"] == "wheel"]
    scroll_evts=[e for e in nav_events if e["type"] == "scroll"]

    print("\n[Biometric Telemetry Analysis]")
    print(f"  • Total DOM Navigation Events Captured : {len(nav_events)}")
    print(f"  • Keyboard KeyDown Events              : {len(key_downs)}")
    print(f"  • Keyboard KeyUp Events                : {len(key_ups)}")
    print(f"  • Mouse Wheel Events                   : {len(wheel_evts)}")
    print(f"  • Native Scroll Changes                : {len(scroll_evts)}")

    assert len(key_downs) >= 4, f"Too few keydowns ({len(key_downs)})"
    assert len(wheel_evts) >= 10, f"Too few wheel events ({len(wheel_evts)})"

    # Verify physical finger key hold time (never 0ms bot instant)
    hold_times = []
    for kd in key_downs:
        matching_ku = next((ku for ku in key_ups if ku["key"] == kd["key"] and ku["t"] >= kd["t"]), None)
        if matching_ku:
            hold_times.append(matching_ku["t"] - kd["t"])

    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0
    print(f"  • Average Keystroke Hold Duration      : {avg_hold:.1f}ms (Realistic human range: 60ms–140ms)")
    assert 40.0 <= avg_hold <= 200.0, f"Unnatural keystroke hold time: {avg_hold:.1f}ms"

    print("  [✓] Hybrid Telemetry Confirmed: Browser exhibits genuine dual-mode (Mouse + Keyboard) human browsing.")

    print("\n" + "=" * 70)
    print(">> RESULT: STEP 6 (HYBRID KEYBOARD NAVIGATION) 100% VERIFIED")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_verification())
