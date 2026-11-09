"""
tests/demo_step10_visual.py — Live Visual & Screen Proof of Step 10 Bored Real Visitor Emulation

Launches a visible Chromium window on your screen:
1. Opens an interactive test page.
2. Demonstrates realistic human query typing into the search box with character delays and hesitations.
3. Demonstrates bored idle mouse fidgets (lazy cursor wandering) with visual cursor tracking.
4. Demonstrates tab inattention / window blur and focus restoration.
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


async def main():
    print("\n" + "="*70)
    print(">> STEP 10 LIVE PROOF: BORED REAL VISITOR & TYPING CADENCE (WATCH SCREEN)")
    print("="*70 + "\n")

    rng = random.Random(time.time_ns())

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        ctx = await browser.new_context(viewport={"width": 1280, "height": 850})
        page = await ctx.new_page()

        print("[1] Opening interactive visitor test page...")
        await page.goto("about:blank")
        await page.set_content("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <title>Step 10 Bored Visitor Live Demo</title>
          <style>
            body { font-family: system-ui, sans-serif; background: #0b0f19; color: #f8fafc; padding: 40px; }
            .card { background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 30px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h2 { color: #38bdf8; margin-top: 0; }
            input { width: 100%; box-sizing: border-box; padding: 14px 18px; font-size: 16px; background: #04070d; border: 2px solid #334155; border-radius: 8px; color: #fff; margin-bottom: 20px; outline: none; }
            input:focus { border-color: #38bdf8; }
            .status-box { padding: 12px 16px; border-radius: 6px; font-size: 14px; margin-bottom: 12px; background: #1e293b; color: #94a3b8; }
            .highlight { color: #4ade80; font-weight: bold; }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>⚡ Step 10: Human Typing & Bored Visitor Demo</h2>
            <p style="color: #94a3b8; font-size: 14px;">Watch the bot type human-style search keywords, perform lazy idle fidgets, and simulate tab blur.</p>
            <input id="demo-search" type="text" placeholder="Watch human typing cadence here..." />
            <div id="status-typing" class="status-box">Status: Waiting to type...</div>
            <div id="status-blur" class="status-box">Window Focus: <span class="highlight">FOCUSED (Active)</span></div>
          </div>
          <script>
            window.addEventListener('blur', () => {
              const el = document.getElementById('status-blur');
              if (el) el.innerHTML = 'Window Focus: <span style="color:#f87171;font-weight:bold;">BLURRED / INACTIVE (Glancing away)</span>';
            });
            window.addEventListener('focus', () => {
              const el = document.getElementById('status-blur');
              if (el) el.innerHTML = 'Window Focus: <span class="highlight">FOCUSED (User Returned)</span>';
            });
          </script>
        </body>
        </html>
        """)

        # Inject visual cursor tracker
        await page.evaluate("""() => {
            const dot = document.createElement('div');
            dot.id = 'demo-cursor-dot';
            dot.style.cssText = 'position:fixed;width:14px;height:14px;background:rgba(56,189,248,0.9);border:2px solid #fff;border-radius:50%;pointer-events:none;z-index:999999;box-shadow:0 0 12px rgba(56,189,248,0.9);transition:transform 0.05s ease;transform:translate(-50%, -50%);';
            document.body.appendChild(dot);
            window.addEventListener('mousemove', e => {
                dot.style.left = e.clientX + 'px';
                dot.style.top = e.clientY + 'px';
            });
        }""")

        # 1. Typing Demonstration
        search_query = "best instant personal loan in India 2026"
        print(f"\n[2] Simulating Realistic Search Query Typing: '{search_query}'...")
        await page.evaluate("() => { document.getElementById('status-typing').innerHTML = 'Status: <span style=\"color:#38bdf8;\">Typing in progress (Human cadence 60-220ms)...</span>'; }")
        
        t0 = time.time()
        res = await human.type_text_human(page, "#demo-search", search_query, rng=rng)
        t_elapsed = time.time() - t0
        
        print(f"    --> Finished typing in {t_elapsed:.2f}s (~{len(search_query)/t_elapsed:.1f} chars/sec)")
        print(f"    --> Cognitive hesitations: {res['hesitations']} | Typos corrected: {res['typos_corrected']}")
        hes_count = res["hesitations"]
        status_html = f"Status: <span class='highlight'>Typing Complete ({t_elapsed:.1f}s, {hes_count} hesitations)</span>"
        await page.evaluate("(text) => { document.getElementById('status-typing').innerHTML = text; }", status_html)

        await asyncio.sleep(1.0)

        # 2. Idle Fidgets Demonstration
        print("\n[3] Simulating Bored Visitor Idle Mouse Fidgets (Lazy twitches)...")
        print("    Moving cursor smoothly through 3 natural wandering waypoints...")
        await human.simulate_bored_idle_fidgets(page, rng=rng, count=3)
        print("    --> Idle micro-drifts complete.")

        await asyncio.sleep(1.0)

        # 3. Tab Blur Demonstration
        print("\n[4] Simulating Tab Inattention & Window Focus Blur...")
        print("    --> Deactivating window focus for 2.5 seconds (glancing away)...")
        await human.simulate_tab_blur(page, rng=rng, duration_s=2.5)
        print("    --> Restored window focus! User back to page.")

        print("\n" + "="*70)
        print(">> DEMO COMPLETED: Step 10 Bored Visitor & Typing Cadence Verified Live!")
        print("="*70 + "\n")

        await asyncio.sleep(2.0)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
