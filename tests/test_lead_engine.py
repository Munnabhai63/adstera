"""
tests/test_lead_engine.py — Verification suite for Pillar 2 (High-Payout CPL Lead Engine).
"""

import asyncio
import os
import random
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

import db
from lead_engine import LeadConversionEngine


@pytest.fixture(autouse=True)
def setup_db():
    db.init()
    yield


def test_engine_initialization_defaults():
    engine = LeadConversionEngine()
    assert engine.enabled is True
    assert 0.05 <= engine.conversion_prob <= 0.25
    assert engine.max_leads_per_day >= 10


def test_should_attempt_conversion_guardrails():
    engine = LeadConversionEngine()
    rng_always = random.Random()
    rng_always.random = lambda: 0.01  # Below conversion_prob

    # When under daily cap, should attempt
    assert engine.should_attempt_conversion(rng=rng_always) is True

    rng_never = random.Random()
    rng_never.random = lambda: 0.99  # Above conversion_prob
    assert engine.should_attempt_conversion(rng=rng_never) is False


def test_offline_conversion_database_persistence():
    engine = LeadConversionEngine()
    test_dom = "tazaloan.com"
    res = engine.simulate_offline_conversion(domain=test_dom)

    assert res["domain"] == test_dom
    assert "@" in res["email"]
    assert res["fields_filled"] == 4
    assert res["bounty_est"] >= 2.50
    assert res["status"] == "submitted"

    # Query from db
    records = db.get_lead_conversions(domain=test_dom, limit=5)
    assert len(records) >= 1
    assert records[0]["email"] == res["email"]


def test_lead_form_detection_and_human_submission():
    async def _test():
        fixture_path = Path("tests/fixtures/advertiser_lead_page.html").resolve()
        assert fixture_path.exists(), "Advertiser fixture missing!"
        file_url = fixture_path.as_uri()

        engine = LeadConversionEngine()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(file_url)

            # Step 1: Detect form
            form_info = await engine.detect_lead_form(page)
            assert form_info["form_found"] is True
            assert form_info["email_selector"] is not None
            assert form_info["name_selector"] is not None
            assert form_info["zip_selector"] is not None
            assert form_info["submit_selector"] is not None

            # Step 2: Fill and Submit
            rng = random.Random(42)
            result = await engine.fill_and_submit_lead(
                page=page,
                domain="loanraaj.com",
                rng=rng,
            )

            assert result["success"] is True
            assert result["fields_filled"] >= 3
            assert result["bounty_est"] >= 2.50

            # Verify confirmation banner is now visible in the DOM
            success_box = await page.query_selector("#submissionSuccess")
            assert success_box is not None
            is_visible = await success_box.is_visible()
            assert is_visible is True

            await context.close()
            await browser.close()

    asyncio.run(_test())


def test_today_leads_summary():
    summary = db.today_leads_summary()
    assert "today_leads" in summary
    assert "estimated_bounty" in summary
    assert summary["today_leads"] >= 1
    assert summary["estimated_bounty"] > 0.0
