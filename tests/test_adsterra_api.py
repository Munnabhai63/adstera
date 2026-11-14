"""
tests/test_adsterra_api.py — Verification suite for Pillar 1 (Adsterra API Client & Reconciliation).
"""

import pytest
import sqlite3
import datetime
from adsterra_api import AdsterraApiClient
import db


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test_adsterra_api.db")
    db.init()
    yield


def test_client_initialization_defaults():
    client = AdsterraApiClient(api_key="")
    assert client.is_mock_mode() is True
    assert len(client.configured_domains) >= 1
    assert "loanraaj.com" in client.configured_domains


def test_mock_stats_generation():
    client = AdsterraApiClient(api_key="mock_test_key")
    stats = client._generate_mock_stats("2026-11-09", "2026-11-09")
    
    assert stats["status"] == "ok"
    assert len(stats["items"]) == len(client.configured_domains)

    for item in stats["items"]:
        assert item["impressions"] > 0
        assert item["clicks"] > 0
        assert 3.0 <= item["ctr"] <= 6.0
        assert item["cpm"] >= 4.50
        assert item["revenue"] > 0.0


def test_sync_and_reconciliation_persistence():
    client = AdsterraApiClient()
    today_str = datetime.date.today().isoformat()
    reconciled = client.sync_now(force_mock=True)

    assert len(reconciled) == len(client.configured_domains)
    first = reconciled[0]
    assert "sync_id" in first
    assert first["sync_id"] > 0
    assert first["domain"] in client.configured_domains
    assert first["status"] in ("ALIGNED", "DISCREPANCY_DETECTED")

    # Verify directly from SQLite table
    db_rows = db.get_latest_adsterra_sync(first["domain"], limit=5)
    assert len(db_rows) >= 1
    assert db_rows[0]["domain"] == first["domain"]
    assert db_rows[0]["api_revenue"] == first["api_revenue"]


def test_discrepancy_calculation():
    # Setup local stats in db
    test_dom = "tazaloan.com"
    today_str = datetime.date.today().isoformat()

    with db._conn() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO domain_stats (domain, date, sessions, ad_clicks, impressions)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_dom, today_str, 150, 6, 160),
        )

    client = AdsterraApiClient()
    reconciled = client.sync_now(force_mock=True)
    taza_rec = next(r for r in reconciled if r["domain"] == test_dom)

    # Discrepancy = (API - Local) / Local * 100
    expected_disc = round(((taza_rec["api_impressions"] - 160) / 160) * 100.0, 2)
    assert taza_rec["discrepancy_pct"] == expected_disc
    assert taza_rec["local_impressions"] == 160


def test_custom_api_key_override():
    client = AdsterraApiClient(api_key="real_production_token_123456789")
    assert client.api_key == "real_production_token_123456789"
    assert client.is_mock_mode() is False


def test_three_layer_zero_waste_audit_and_diagnostics():
    import asyncio
    from adsterra_api import diagnose_domain_metrics, load_local_adsterra_ZeroWaste_maps

    dom_map, place_map = load_local_adsterra_ZeroWaste_maps()
    assert dom_map.get("6190678") == "rechargetak.com"
    assert dom_map.get("6190730") == "tazarokda.com"
    assert len(place_map) >= 30

    # Log a verified beacon into SQLite
    db.log_adsterra_handshake(
        domain="rechargetak.com",
        proxy_id="mobile_adb",
        ad_url="https://bauval.org/21/65d56d25dab0c59a0903ae9786585b4c",
        status_code=200,
        verified=1,
    )

    client = AdsterraApiClient()
    audit = asyncio.run(client.fetch_full_live_audit(force_mock=True))
    assert audit["status"] == "ok"
    assert "summary" in audit
    assert len(audit["by_domain"]) >= 10

    diag_zero_clicks = diagnose_domain_metrics(28, 0, 0.0, 0.041, 4)
    assert diag_zero_clicks["health"] == "LOW_CTR_FLOOR_CPM"
    assert "0 Clicks" in diag_zero_clicks["diagnosis"]


def test_adsterra_maps_missing_file_fallback_and_warning(caplog):
    """When banner file is missing from state and fixtures, loader returns fallback map and logs warning."""
    import logging
    from adsterra_api import load_local_adsterra_ZeroWaste_maps

    with caplog.at_level(logging.WARNING):
        dom_map, place_map = load_local_adsterra_ZeroWaste_maps(
            banner_file_path="state/nonexistent_banners_file_xyz.json"
        )
    # Returns default fallback domains and smart-link placement
    assert dom_map.get("6190730") == "tazarokda.com"
    assert "32152060" in place_map
    assert any("not found" in r.message for r in caplog.records)


