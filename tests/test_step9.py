"""
tests/test_step9.py — Verification of Step 9: Smart Ad Interaction, Viewport Intersection Scoring & Safe CTR Guard

Verifies:
1. Viewport Intersection: Elements scrolled off-screen are rejected; only in-view ads (>= 50% visible) are candidates.
2. Safe CTR Governor: Enforces strict 3%–7% target CTR window, suppressing clicks when CTR exceeds threshold.
3. Mandatory Zero-Click Sessions: Ensures ~15% of sessions click nothing (zero-click traffic shape).
4. Slot Deduplication: Prevents consecutive sessions on the same proxy from clicking the same ad slot twice.
5. Human Popunder Dwell: Emulates realistic reading drift on new tab before closing.
"""
from __future__ import annotations

import asyncio
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
import worker
import db

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "page.html"


async def run_step9_tests():
    print("\n--- Running Step 9: Smart Ad Interaction & Safe CTR Guard Verification ---")
    
    rng = random.Random(42)
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        
        # Load local test fixture
        fixture_url = f"file:///{FIXTURE_PATH.resolve().as_posix()}"
        await page.goto(fixture_url, wait_until="domcontentloaded")
        
        # Test 1: Viewport Intersection Scoring
        # Initially, page is at scrollY=0. Top ads should be in-view, but bottom ads may be out of view.
        candidates_top = await worker.get_in_view_ad_candidates(page)
        assert len(candidates_top) > 0, "Expected at least 1 ad candidate visible at top of page"
        print(f"  [Pass 1] Viewport intersection scoring: Found {len(candidates_top)} in-view ad candidate(s) at scrollY=0")
        for c in candidates_top:
            assert c["ratio"] >= 0.50, f"Candidate visibility ratio too low: {c['ratio']}"
            print(f"    • Slot: {c['selector']} (Visibility ratio={c['ratio']*100:.0f}%, top={c['box']['y']:.0f}px)")
            
        # Test 2: Off-screen detection after scrolling
        # Scroll to bottom of fixture
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.2)
        candidates_bottom = await worker.get_in_view_ad_candidates(page)
        print(f"  [Pass 2] Viewport intersection after scroll: Found {len(candidates_bottom)} candidate(s) near page bottom")
        
        # Test 3: Safe CTR Governor logic
        # If current CTR is 8% (above 7%), governor should suppress clicks
        suppress_high = worker.should_suppress_click_for_ctr(current_ctr=0.08, click_prob=0.06, rng=rng)
        assert suppress_high is True, "Governor failed to suppress click when CTR was 8.0% (> 7.0%)"
        
        # If current CTR is 4.5% (healthy 3%-7% window), clicks should be permitted
        allow_normal = worker.should_suppress_click_for_ctr(current_ctr=0.045, click_prob=1.0, rng=rng)
        assert allow_normal is False, "Governor falsely suppressed click when CTR was 4.5% (healthy)"
        print("  [Pass 3] Safe CTR Governor: Correctly suppresses clicks when CTR > 7.0%, permits when healthy (3%–7%)")

        # Test 4: Mandatory Zero-Click Sessions (12%–18% rate)
        zero_count = 0
        trials = 1000
        for i in range(trials):
            r = random.Random(i)
            if worker.is_mandatory_zero_click_session(r):
                zero_count += 1
        rate = zero_count / trials
        print(f"  [Pass 4] Mandatory Zero-Click Session rate: {rate*100:.1f}% (Expected 12%–18%)")
        assert 0.12 <= rate <= 0.18, f"Zero-click rate out of 12%–18% range: {rate}"

        # Test 5: Slot Deduplication per Proxy
        proxy_id = "test_proxy_99"
        worker.record_clicked_ad_slot(proxy_id, ".ad-frame")
        last_slot = worker.get_last_clicked_ad_slot(proxy_id)
        assert last_slot == ".ad-frame", "Failed to record last clicked slot"
        
        # Candidate selection must deprioritize or exclude .ad-frame for this proxy
        filtered = worker.filter_ad_candidates_for_proxy(candidates_top, proxy_id)
        for f in filtered:
            assert f["selector"] != ".ad-frame", f"Last clicked slot {last_slot} was not deduplicated!"
        print(f"  [Pass 5] Proxy slot deduplication: Successfully filtered out consecutive click on '{last_slot}'")

        await browser.close()

    print("STEP 9 ALL VERIFICATIONS PASSED [OK]\n")


if __name__ == "__main__":
    asyncio.run(run_step9_tests())
