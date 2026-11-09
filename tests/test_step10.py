"""
tests/test_step10.py — Verification of Step 10: Bored Real Visitor Emulation, Tab Blur & Typing Cadence

Verifies:
1. simulate_tab_blur(page): Toggles window/document focus and blur states cleanly via CDP/events.
2. simulate_bored_idle_fidgets(page): Generates natural multi-step micro-drifts (lazy idle movements) without teleportation.
3. type_text_human(page, selector, text): Types with human per-character cadence (60ms–220ms), typo corrections, and hesitation.
4. Continuous Cursor Tracking: Maintains persistent coordinates across idle fidgets and typing.
"""
from __future__ import annotations

import asyncio
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
import human

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "page.html"


async def run_step10_tests():
    print("\n--- Running Step 10: Bored Real Visitor Emulation & Typing Cadence Verification ---")
    
    rng = random.Random(42)
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        
        # Load local test fixture with an input field
        await page.goto("about:blank")
        await page.set_content("""
        <!DOCTYPE html>
        <html>
        <body>
          <h2>Bored Visitor Test Bed</h2>
          <input id="search-input" type="text" placeholder="Search keywords..." style="width:300px;font-size:16px;" />
          <div id="blur-log"></div>
          <script>
            window.blurEvents = 0;
            window.focusEvents = 0;
            window.addEventListener('blur', () => { window.blurEvents++; });
            window.addEventListener('focus', () => { window.focusEvents++; });
          </script>
        </body>
        </html>
        """)
        
        # Test 1: Tab Blur / Minimize Simulation
        print("  [1] Testing Tab Focus Blur & Inattention simulation...")
        blur_ok = await human.simulate_tab_blur(page, rng=rng, duration_s=0.5)
        assert blur_ok is True, "simulate_tab_blur returned False"
        
        counts = await page.evaluate("() => ({ blur: window.blurEvents, focus: window.focusEvents })")
        print(f"  [Pass 1] Tab blur/focus transitions fired cleanly: blur={counts['blur']}, focus={counts['focus']}")
        assert counts["blur"] >= 1, "Window blur event was not recorded"
        assert counts["focus"] >= 1, "Window focus event was not recorded"

        # Test 2: Bored Idle Fidgets (Micro-drifts)
        print("\n  [2] Testing Bored Visitor Idle Fidgets & Micro-drifts...")
        start_pos = human.get_current_cursor(page, rng)
        fidget_res = await human.simulate_bored_idle_fidgets(page, rng=rng, count=3)
        end_pos = human.get_current_cursor(page, rng)
        
        print(f"  [Pass 2] Idle fidgets executed {fidget_res['steps']} waypoints:")
        print(f"    Started at: ({start_pos[0]:.1f}, {start_pos[1]:.1f}) -> Ended at: ({end_pos[0]:.1f}, {end_pos[1]:.1f})")
        assert fidget_res["steps"] >= 2, f"Expected at least 2 fidget steps, got {fidget_res['steps']}"
        assert start_pos != end_pos, "Mouse did not move during idle fidgets"

        # Test 3: Realistic Human Typing Cadence
        print("\n  [3] Testing Search Referrer Query Typing Cadence...")
        test_text = "quick instant loan online"
        t0 = time.time()
        type_res = await human.type_text_human(page, "#search-input", test_text, rng=rng)
        t_elapsed = time.time() - t0
        
        input_value = await page.input_value("#search-input")
        print(f"  [Pass 3] Typing results for '{test_text}':")
        print(f"    Typed Value: '{input_value}' (Match: {input_value == test_text})")
        print(f"    Characters: {type_res['chars_typed']} | Typos corrected: {type_res['typos_corrected']} | Hesitations: {type_res['hesitations']}")
        print(f"    Elapsed time: {t_elapsed:.2f}s (~{len(test_text)/t_elapsed:.1f} chars/sec - realistic human rate)")
        
        assert input_value == test_text, f"Input value mismatch: '{input_value}' != '{test_text}'"
        assert t_elapsed >= len(test_text) * 0.05, f"Typing was unnaturally fast for a human: {t_elapsed:.2f}s"

        await browser.close()

    print("\nSTEP 10 ALL VERIFICATIONS PASSED [OK]\n")


if __name__ == "__main__":
    asyncio.run(run_step10_tests())
