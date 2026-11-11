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
        engine.email_client._save_email_to_cache("lead_cached_test@momroad.org", "momroad.org", expiry_minutes=60)

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


def test_ua_pool_27k_and_4d_hardware_lock():
    import ua_provider
    import fingerprint as fp_mod
    from pool import Proxy, GeoInfo

    d_pool = ua_provider.get_desktop_uas()
    m_pool = ua_provider.get_mobile_uas()
    assert len(d_pool) >= 8000
    assert len(m_pool) >= 18000
    assert len(d_pool) + len(m_pool) >= 27000

    # Verify deterministic seed_key rotation across the 27,103 pool
    ua_1 = ua_provider.get_matching_ua("131", is_mobile=True, seed_key="ip_slot_1")
    ua_2 = ua_provider.get_matching_ua("131", is_mobile=True, seed_key="ip_slot_2")
    assert "Chrome/131." in ua_1
    assert "Chrome/131." in ua_2
    assert ua_1 == ua_provider.get_matching_ua("131", is_mobile=True, seed_key="ip_slot_1")

    # Verify 4-Dimension Hardware & Client Hint Lock on Mobile Android UA
    p = Proxy(host="1.39.154.111", port=8080)
    p.geo = GeoInfo(country="IN", region="MH", city="Mumbai", timezone="Asia/Kolkata", locale="en-IN")
    fp = fp_mod.build(p, force_mobile=True)
    fp_mod.sync_fingerprint_to_ua(fp, ua_1)

    assert fp.is_mobile is True
    assert fp.platform == "Linux armv8l"
    assert fp.max_touch_points == 5
    assert any(gpu in fp.webgl_renderer for gpu in ("Adreno", "Mali"))
    ch_headers = fp_mod.build_client_hint_headers(fp)
    assert ch_headers["Sec-CH-UA-Mobile"] == "?1"
    assert ch_headers["Sec-CH-UA-Platform"] == '"Android"'
    assert '"131"' in ch_headers["Sec-CH-UA"]

