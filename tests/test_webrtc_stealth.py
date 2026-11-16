"""
tests/test_webrtc_stealth.py — Invariant tests for Step 3.2: WebRTC IP Leak Prevention.
Verifies RTCPeerConnection masking, prototype inheritance, SDP sanitization, and candidate filtering.
"""
import asyncio
import pytest
from pool import Proxy, GeoInfo
import fingerprint as fp_mod


@pytest.mark.browser
def test_webrtc_stealth_playwright():
    from playwright.async_api import async_playwright

    async def _run():
        proxy = Proxy(host="192.168.1.50", port=8080)
        proxy.geo = GeoInfo(country="US", region="CA", city="Los Angeles", timezone="America/Los_Angeles", locale="en-US")
        fp = fp_mod.build(proxy)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                ]
            )
            context = await browser.new_context()
            await context.add_init_script(fp_mod.init_script(fp))
            page = await context.new_page()

            res = await page.evaluate("""async () => {
                const results = {};
                if (typeof window.RTCPeerConnection === 'undefined') {
                    return { skipped: true };
                }

                results.rtcNative = window.RTCPeerConnection.toString().includes('[native code]');
                
                const pc = new window.RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                });

                results.instanceOf = (pc instanceof window.RTCPeerConnection);
                results.createOfferNative = pc.createOffer.toString().includes('[native code]');

                // Listen for candidates
                const candidates = [];
                pc.onicecandidate = (e) => {
                    if (e.candidate) {
                        candidates.push(e.candidate.candidate);
                    }
                };

                pc.createDataChannel("leak_test");
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                results.sdpHasNoHost = !offer.sdp.includes('typ host');
                results.sdpHasNoPrivateIP = !/(?:192\\.168\\.|10\\.|172\\.(?:1[6-9]|2\\d|3[01])\\.|127\\.0\\.0\\.1)/.test(offer.sdp);

                // Wait up to 1 second for any ICE candidates
                await new Promise(r => setTimeout(r, 1000));
                pc.close();

                results.candidatesCount = candidates.length;
                results.leakedHostCandidate = candidates.some(c => c.includes('typ host'));
                results.leakedPrivateIP = candidates.some(c => /(?:192\\.168\\.|10\\.|172\\.(?:1[6-9]|2\\d|3[01])\\.|127\\.0\\.0\\.1)/.test(c));

                return results;
            }""")

            assert res.get("rtcNative") is True, f"RTCPeerConnection not [native code]: {res}"
            assert res.get("instanceOf") is True, f"pc not instanceof RTCPeerConnection: {res}"
            assert res.get("createOfferNative") is True, f"createOffer not [native code]: {res}"
            assert res.get("sdpHasNoHost") is True, f"SDP leaked host candidate: {res}"
            assert res.get("sdpHasNoPrivateIP") is True, f"SDP leaked private IP: {res}"
            assert res.get("leakedHostCandidate") is False, f"Host candidate leaked: {res}"
            assert res.get("leakedPrivateIP") is False, f"Private IP leaked: {res}"

            await context.close()
            await browser.close()

    asyncio.run(_run())
