"""
tests/test_ad_network_manager.py — Tests for Step 4.3: Multi-Ad-Network Rotation.
Verifies network weighting (50/30/20), probabilistic selection, smartlink retrieval,
fallback when disabled, and database logging.
"""
import random
import sqlite3
import pytest

from ad_network_manager import AdNetworkManager, DEFAULT_NETWORKS
import db


def test_get_networks_defaults():
    mgr = AdNetworkManager()
    nets = mgr.get_networks()
    assert "adsterra" in nets
    assert "propellerads" in nets
    assert "hilltopads" in nets
    assert nets["adsterra"]["weight"] == 0.50
    assert nets["propellerads"]["weight"] == 0.30
    assert nets["hilltopads"]["weight"] == 0.20


def test_select_network_probabilistic_distribution():
    mgr = AdNetworkManager()
    rng = random.Random(42)

    counts = {"adsterra": 0, "propellerads": 0, "hilltopads": 0}
    iterations = 5000

    for _ in range(iterations):
        net = mgr.select_network(rng)
        counts[net] += 1

    # Check 50% / 30% / 20% distribution within +/- 3% tolerance
    pct_adsterra = counts["adsterra"] / iterations
    pct_propeller = counts["propellerads"] / iterations
    pct_hilltop = counts["hilltopads"] / iterations

    assert 0.47 <= pct_adsterra <= 0.53, f"Adsterra distribution off: {pct_adsterra:.3f}"
    assert 0.27 <= pct_propeller <= 0.33, f"Propeller distribution off: {pct_propeller:.3f}"
    assert 0.17 <= pct_hilltop <= 0.23, f"Hilltop distribution off: {pct_hilltop:.3f}"


def test_select_smartlink_fallback():
    mgr = AdNetworkManager()
    rng = random.Random(42)

    link_adsterra = mgr.select_smartlink("adsterra", rng)
    assert link_adsterra and link_adsterra.startswith("http")

    link_propeller = mgr.select_smartlink("propellerads", rng)
    assert link_propeller and link_propeller.startswith("http")

    link_hilltop = mgr.select_smartlink("hilltopads", rng)
    assert link_hilltop and link_hilltop.startswith("http")

    # Non-existent network should fall back to adsterra
    fallback_link = mgr.select_smartlink("non_existent_network", rng)
    assert fallback_link and fallback_link in DEFAULT_NETWORKS["adsterra"]["smartlinks"]


def test_get_rotation_plan():
    mgr = AdNetworkManager()
    plan = mgr.get_rotation_plan()
    assert plan.get("adsterra") == 0.5
    assert plan.get("propellerads") == 0.3
    assert plan.get("hilltopads") == 0.2


def test_db_session_ad_network_column(tmp_path):
    test_db = tmp_path / "test_ad_net.db"
    orig_path = db._DB_PATH
    try:
        db._DB_PATH = test_db
        db.init()

        row_id = db.log_session(
            proxy_id="test_proxy:8080",
            ua="TestUA",
            referrer="https://bing.com",
            dwell=35.0,
            pages=1,
            ad_clicks=1,
            impressions=2,
            status="ok",
            domain="loanraaj.com",
            geo_country="US",
            geo_tier="tier1",
            ad_network="propellerads",
        )

        with sqlite3.connect(str(test_db)) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT ad_network FROM sessions WHERE id=?", (row_id,)).fetchone()
            assert row["ad_network"] == "propellerads"
    finally:
        db._DB_PATH = orig_path
