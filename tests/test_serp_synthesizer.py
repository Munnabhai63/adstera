"""
tests/test_serp_synthesizer.py — Verification suite for Pillar 3 (Dynamic SERP Synthesizer).
"""

import asyncio
import random
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from serp_synthesizer import SerpSynthesizer, DOMAIN_QUERY_MATRIX


def test_serp_synthesizer_initialization_defaults():
    engine = SerpSynthesizer()
    assert engine.enabled is True
    assert 0.10 <= engine.organic_prob <= 0.80
    assert engine.default_engine in ("google", "bing")


def test_query_generation_all_10_domains():
    engine = SerpSynthesizer()
    for dom in DOMAIN_QUERY_MATRIX.keys():
        q = engine.generate_query(domain=dom, city="Chicago", state="IL")
        assert len(q) > 10
        assert "{" not in q and "}" not in q, f"Uninterpolated template in {dom}: {q}"


def test_build_organic_referrer_url_google_and_bing():
    engine = SerpSynthesizer()
    dom = "tazaloan.com"

    # Test Google Referrer
    google_ref = engine.build_organic_referrer_url(dom, city="Dallas", state="TX", engine="google")
    assert "https://www.google.com" in google_ref
    assert ("q=" in google_ref or "url=" in google_ref)

    # Test Bing Referrer
    bing_ref = engine.build_organic_referrer_url(dom, city="Dallas", state="TX", engine="bing")
    assert "https://www.bing.com/search?q=" in bing_ref


def test_should_use_organic_serp_probability():
    engine = SerpSynthesizer()
    rng_yes = random.Random()
    rng_yes.random = lambda: 0.05
    assert engine.should_use_organic_serp(rng=rng_yes) is True

    rng_no = random.Random()
    rng_no.random = lambda: 0.95
    assert engine.should_use_organic_serp(rng=rng_no) is False


@pytest.mark.browser
def test_navigate_via_serp_with_playwright_fixture():
    async def _test():
        fixture_path = str(Path("tests/fixtures/serp_results_page.html").resolve())
        engine = SerpSynthesizer()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            res = await engine.navigate_via_serp(
                page=page,
                target_url="https://loanraaj.com",
                domain="loanraaj.com",
                city="Dallas",
                state="TX",
                fixture_path=fixture_path,
                rng=random.Random(42),
            )

            assert res["success"] is True
            assert res["domain"] == "loanraaj.com"
            assert res["organic_clicked"] is True
            assert "https://www.google.com" in res["referrer_header"]

            await context.close()
            await browser.close()

    asyncio.run(_test())
