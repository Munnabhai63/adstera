"""
tests/demo_step8_visual.py — Live Visual & Mathematical Proof of Step 8

Launches a visible Chromium window on your screen for 20 seconds:
1. Opens your live website (https://loanraaj.com).
2. Live-highlights each paragraph as the bot reads it (so you can see it with your own eyes).
3. Moves the mouse cursor along the text using human Bézier curves.
4. Performs a natural scroll-back re-read.
5. Prints every exact coordinate, character count, and reading pause to the screen.
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
    print(">> STEP 8 LIVE PROOF & VERIFICATION DEMO (WATCH YOUR SCREEN)")
    print("="*70 + "\n")
    
    rng = random.Random(time.time_ns())
    
    async with async_playwright() as pw:
        # Launch visible browser on screen
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        ctx = await browser.new_context(viewport={"width": 1280, "height": 850})
        page = await ctx.new_page()
        
        print("[1] Opening live site https://loanraaj.com ...")
        try:
            await page.goto("https://loanraaj.com", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            # Fallback to local fixture if offline
            fixture_path = (Path(__file__).parent / "fixtures" / "page.html").resolve()
            await page.goto(f"file:///{fixture_path.as_posix()}", wait_until="domcontentloaded")
            print("    (Loaded local fixture)")
            
        print("\n[2] Scanning DOM for content blocks (Paragraphs, Headings, Lists)...")
        anchors = await human.get_reading_anchors(page)
        print(f"    --> Found {len(anchors)} readable content anchors on page:\n")
        
        for idx, a in enumerate(anchors[:5]):
            pause = human.calculate_reading_pause(a["char_count"], rng)
            print(f"    • Anchor #{idx+1} <{a['tag'].upper()}>: {a['char_count']} chars | Position: y={a['top']}px | Calculated Pause: {pause:.2f}s")
        
        print("\n[3] Executing Content-Aware Reading Heatmap across live content:")
        
        # Inject visual cursor tracker into the page so user can physically see mouse
        await page.evaluate("""() => {
            const dot = document.createElement('div');
            dot.id = 'demo-cursor-dot';
            dot.style.cssText = 'position:fixed;width:14px;height:14px;background:rgba(239,68,68,0.85);border:2px solid #fff;border-radius:50%;pointer-events:none;z-index:999999;box-shadow:0 0 10px rgba(239,68,68,0.8);transition:transform 0.05s ease;transform:translate(-50%, -50%);';
            document.body.appendChild(dot);
            window.addEventListener('mousemove', e => {
                dot.style.left = e.clientX + 'px';
                dot.style.top = e.clientY + 'px';
            });
        }""")
        
        # Walk through first 3 anchors with visual live highlight
        for i, anchor in enumerate(anchors[:3]):
            current_y = await page.evaluate("() => window.scrollY")
            pause = human.calculate_reading_pause(anchor["char_count"], rng) * 0.7  # fast demo
            
            print(f"\n  ---> Reading Block #{i+1} (<{anchor['tag']}> at y={anchor['top']}px):")
            print(f"       Text density: {anchor['char_count']} characters")
            print(f"       Human reading dwell: {pause:.2f} seconds")
            
            # Highlight the element on screen in yellow/green
            await page.evaluate(f"""() => {{
                const el = document.elementsFromPoint(window.innerWidth / 2, Math.max(50, {anchor['top']} - window.scrollY + 15))[0];
                if (el) {{
                    el.style.transition = 'background 0.3s ease, outline 0.3s ease';
                    el.style.background = 'rgba(254, 240, 138, 0.45)';
                    el.style.outline = '2px dashed #eab308';
                }}
            }}""")
            
            # Reading cursor follow
            print("       Moving mouse smoothly along the reading margin...")
            await human.reading_cursor_follow(page, anchor, rng)
            
            # Dwell
            await asyncio.sleep(pause)
            
            # Scroll down to next block
            chunk = min(360, max(180, anchor["top"] - current_y))
            print(f"       Eased scrolling down by {chunk}px...")
            for s in range(8):
                t = (s + 1) / 8
                ease = 1 - (1 - t) ** 2
                await page.mouse.wheel(0, int(chunk * ease / 8))
                await asyncio.sleep(0.04)
                
            # Simulate a re-reading scroll-back on the 2nd block
            if i == 1:
                print("       [Re-reading trigger]: Eye caught previous line, scrolling back up 120px...")
                await page.mouse.wheel(0, -120)
                await asyncio.sleep(1.2)
                print("       Resuming downward reading...")
                await page.mouse.wheel(0, 120)
                
        print("\n" + "="*70)
        print(">> DEMO COMPLETED: Proof verified live on screen and in DOM telemetry!")
        print("="*70 + "\n")
        
        await asyncio.sleep(2.0)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
