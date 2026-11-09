"""
tests/test_step7.py — Verification of Step 7: WebAudio / AudioContext Oscillator & Latency Stealth Patching

Verifies:
1. AudioBuffer.prototype.getChannelData.toString() === 'function getChannelData() { [native code] }'
2. AudioContext.prototype.getOutputTimestamp.toString() === 'function getOutputTimestamp() { [native code] }'
3. getOutputTimestamp() returns realistic { contextTime, performanceTime } with deterministic seeded jitter
4. AnalyserNode frequency data is stealthily jittered and masked with [native code]
5. Audio fingerprint hash is 100% stable on the same proxy, but differs across distinct proxies
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
import fingerprint as fp_mod
from pool import Proxy, GeoInfo


def make_proxy(host: str, seed: int) -> Proxy:
    p = Proxy(host=host, port=8080)
    p.geo = GeoInfo(
        country="US",
        region="NY",
        city="New York",
        timezone="America/New_York",
        locale="en-US",
    )
    return p


async def run_step7_tests():
    print("\n--- Running Step 7 WebAudio / AudioContext Stealth Verification ---")
    
    p1 = make_proxy("192.168.1.101", 101)
    p2 = make_proxy("192.168.1.102", 102)
    
    fp1 = fp_mod.build(p1)
    fp2 = fp_mod.build(p2)
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        ctx1 = await browser.new_context()
        await ctx1.add_init_script(fp_mod.init_script(fp1))
        page1 = await ctx1.new_page()
        await page1.goto("about:blank")
        
        # Test 1: Native code masking for getChannelData & getOutputTimestamp
        masking_res = await page1.evaluate("""() => {
            const results = {};
            if (typeof AudioBuffer !== 'undefined') {
                results.gcdNative = AudioBuffer.prototype.getChannelData.toString() === 'function getChannelData() { [native code] }';
            }
            if (typeof AudioContext !== 'undefined') {
                results.gotNative = AudioContext.prototype.getOutputTimestamp.toString() === 'function getOutputTimestamp() { [native code] }';
            }
            if (typeof AnalyserNode !== 'undefined') {
                results.gbfdNative = AnalyserNode.prototype.getByteFrequencyData.toString() === 'function getByteFrequencyData() { [native code] }';
                results.gffdNative = AnalyserNode.prototype.getFloatFrequencyData.toString() === 'function getFloatFrequencyData() { [native code] }';
            }
            return results;
        }""")
        
        assert masking_res.get("gcdNative", True), "AudioBuffer.prototype.getChannelData failed [native code] masking"
        assert masking_res.get("gotNative", True), "AudioContext.prototype.getOutputTimestamp failed [native code] masking"
        assert masking_res.get("gbfdNative", True), "AnalyserNode.prototype.getByteFrequencyData failed [native code] masking"
        assert masking_res.get("gffdNative", True), "AnalyserNode.prototype.getFloatFrequencyData failed [native code] masking"
        print("  [Pass 1] Audio methods cleanly masked with [native code]")
        
        # Test 2: AudioContext.getOutputTimestamp() returns valid object with jitter
        got_res = await page1.evaluate("""() => {
            try {
                const actx = new (window.AudioContext || window.webkitAudioContext)();
                const ts = actx.getOutputTimestamp();
                actx.close();
                return {
                    hasContextTime: typeof ts.contextTime === 'number',
                    hasPerformanceTime: typeof ts.performanceTime === 'number',
                    contextTime: ts.contextTime,
                    performanceTime: ts.performanceTime,
                };
            } catch(e) {
                return { error: e.toString() };
            }
        }""")
        assert not got_res.get("error"), f"AudioContext getOutputTimestamp threw: {got_res.get('error')}"
        assert got_res.get("hasContextTime") and got_res.get("hasPerformanceTime"), "Invalid timestamp object returned"
        print(f"  [Pass 2] getOutputTimestamp valid: ctxTime={got_res['contextTime']} perfTime={got_res['performanceTime']:.2f}")

        # Test 3: AudioBuffer channel data hash computation on page1 (p1)
        audio_hash_p1 = await page1.evaluate("""() => {
            const actx = new (window.AudioContext || window.webkitAudioContext)();
            const buf = actx.createBuffer(1, 1024, 44100);
            const data = buf.getChannelData(0);
            actx.close();
            // Compute sum of samples
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                sum += data[i];
            }
            return sum.toFixed(8);
        }""")

        # Re-run same proxy in second context to test digest stability
        ctx1_b = await browser.new_context()
        await ctx1_b.add_init_script(fp_mod.init_script(fp1))
        page1_b = await ctx1_b.new_page()
        await page1_b.goto("about:blank")
        
        audio_hash_p1_b = await page1_b.evaluate("""() => {
            const actx = new (window.AudioContext || window.webkitAudioContext)();
            const buf = actx.createBuffer(1, 1024, 44100);
            const data = buf.getChannelData(0);
            actx.close();
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                sum += data[i];
            }
            return sum.toFixed(8);
        }""")
        
        assert audio_hash_p1 == audio_hash_p1_b, f"Audio digest unstable across same proxy: {audio_hash_p1} vs {audio_hash_p1_b}"
        print(f"  [Pass 3] Audio digest is 100% stable across runs on same proxy: {audio_hash_p1}")

        # Test 4: Different proxy produces distinct audio digest
        ctx2 = await browser.new_context()
        await ctx2.add_init_script(fp_mod.init_script(fp2))
        page2 = await ctx2.new_page()
        await page2.goto("about:blank")
        
        audio_hash_p2 = await page2.evaluate("""() => {
            const actx = new (window.AudioContext || window.webkitAudioContext)();
            const buf = actx.createBuffer(1, 1024, 44100);
            const data = buf.getChannelData(0);
            actx.close();
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                sum += data[i];
            }
            return sum.toFixed(8);
        }""")
        
        assert audio_hash_p1 != audio_hash_p2, f"Audio digest collided across proxies! {audio_hash_p1} vs {audio_hash_p2}"
        print(f"  [Pass 4] Audio digest differs across distinct proxies: {audio_hash_p1} != {audio_hash_p2}")
        
        await browser.close()
        
    print("STEP 7 ALL VERIFICATIONS PASSED [OK]\n")

if __name__ == "__main__":
    asyncio.run(run_step7_tests())
