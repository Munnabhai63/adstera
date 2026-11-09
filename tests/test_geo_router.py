"""
tests/test_geo_router.py — Tests for Step 4.1: Geo-Targeted Premium Traffic Routing.
Verifies tier classification, country-aware target URL selection, database logging, and benchmarks.
"""
import random
import sqlite3
import pytest
import geo_router
import worker
import db


def test_classify_geo_tier():
    # Tier 1
    for c in ["US", "GB", "UK", "CA", "AU", "DE", "FR", "NL", "CH", "SE", "NO", "DK", "NZ", "SG"]:
        assert geo_router.classify_geo_tier(c) == "tier1"

    # Tier 2
    for c in ["IT", "ES", "BR", "MX", "ZA", "AE", "SA", "KR", "JP", "TW", "IL"]:
        assert geo_router.classify_geo_tier(c) == "tier2"

    # Tier 3
    for c in ["IN", "PK", "BD", "NG", "PH", "VN", "ID", "EG"]:
        assert geo_router.classify_geo_tier(c) == "tier3"

    # Edge cases
    assert geo_router.classify_geo_tier(None) == "tier1"
    assert geo_router.classify_geo_tier("") == "tier1"


def test_select_geo_target_tier_routing():
    cfg = {
        "geo_routing": {
            "enabled": True,
            "tier1_countries": ["US", "GB", "CA"],
            "tier1_targets": ["https://premium.smartlink/1", "https://loanraaj.com"],
            "tier2_targets": ["https://mid.portal/2"],
            "tier3_targets": ["https://rechargetak.com"],
        },
        "target": {
            "url": "https://fallback.com",
            "urls": ["https://fallback.com"],
        }
    }
    rng = random.Random(42)

    # Tier 1 Routing (US)
    url_us, tier_us = geo_router.select_geo_target(cfg, "US", rng)
    assert tier_us == "tier1"
    assert url_us in cfg["geo_routing"]["tier1_targets"]

    # Tier 2 Routing (IT)
    url_it, tier_it = geo_router.select_geo_target(cfg, "IT", rng)
    assert tier_it == "tier2"
    assert url_it == "https://mid.portal/2"

    # Tier 3 Routing (IN)
    url_in, tier_in = geo_router.select_geo_target(cfg, "IN", rng)
    assert tier_in == "tier3"
    assert url_in == "https://rechargetak.com"


def test_select_geo_target_disabled_fallback():
    cfg = {
        "geo_routing": {
            "enabled": False,
        },
        "target": {
            "url": "https://standard.com",
            "urls": ["https://standard.com"],
        }
    }
    rng = random.Random(42)
    url, tier = geo_router.select_geo_target(cfg, "US", rng)
    assert url == "https://standard.com"
    assert tier == "tier1"


def test_worker_select_target_url_compatibility():
    cfg = {
        "geo_routing": {
            "enabled": True,
            "tier1_targets": ["https://smartlink.org/test"],
        },
        "target": {
            "urls": ["https://fallback.com"],
        }
    }
    rng = random.Random(42)

    # Without return_tier (string backwards-compatibility)
    url = worker.select_target_url(cfg, rng, proxy_country="US")
    assert isinstance(url, str)
    assert url == "https://smartlink.org/test"

    # With return_tier
    url, tier = worker.select_target_url(cfg, rng, proxy_country="US", return_tier=True)
    assert url == "https://smartlink.org/test"
    assert tier == "tier1"


def test_db_session_geo_columns(tmp_path):
    test_db = tmp_path / "test_geo.db"
    # Point db._DB_PATH to temporary test DB
    orig_path = db._DB_PATH
    try:
        db._DB_PATH = test_db
        db.init()

        row_id = db.log_session(
            proxy_id="test_geo_proxy:8080",
            ua="TestUA",
            referrer="https://google.com",
            dwell=30.0,
            pages=1,
            ad_clicks=0,
            impressions=1,
            status="ok",
            domain="loanraaj.com",
            geo_country="US",
            geo_tier="tier1",
        )

        with sqlite3.connect(str(test_db)) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT geo_country, geo_tier FROM sessions WHERE id=?", (row_id,)).fetchone()
            assert row["geo_country"] == "US"
            assert row["geo_tier"] == "tier1"
    finally:
        db._DB_PATH = orig_path
