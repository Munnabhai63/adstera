"""
tests/test_gsc_monitor.py — Step 6.3 / Layer 5: Google Search Console (GSC) Monitor Tests

Covers:
1. GSCMonitor initialization and caching (isolated to tmp_path in pytest)
2. fetch_domain_performance returns impressions, clicks, CTR, and SERP position
3. audit_all_domains aggregates metrics across fleet
4. Deindexed domain detection triggers warning flag
5. Cache persistence to json
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import gsc_auth
import gsc_monitor
from gsc_monitor import GSCMonitor


@pytest.fixture(autouse=True)
def _isolate_gsc_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gsc_monitor, "GSC_STATE_PATH", tmp_path / "gsc_metrics.json")
    monkeypatch.setattr(gsc_monitor, "WEEKLY_REPORT_STATE_PATH", tmp_path / "gsc_weekly_report_state.json")
    monkeypatch.setattr(gsc_monitor, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(gsc_auth, "DEFAULT_SA_PATH", tmp_path / "gsc_service_account.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_OAUTH_TOKEN_PATH", tmp_path / "gsc_oauth_token.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_OAUTH_CLIENT_PATH", tmp_path / "gsc_oauth_client.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_ENV_PATH", tmp_path / ".env")
    for env_key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GSC_SERVICE_ACCOUNT_JSON",
        "GSC_ACCESS_TOKEN",
        "GSC_SERVICE_ACCOUNT_KEY",
        "GSC_CLIENT_ID",
        "GSC_CLIENT_SECRET",
        "GSC_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(env_key, raising=False)


def _offline_monitor(state_path: Optional[Path] = None) -> GSCMonitor:
    return GSCMonitor(cfg={"gsc": {"enabled": True, "service_account_json": "__none__.json"}}, state_path=state_path)


def test_gsc_fetch_domain_performance():
    """fetch_domain_performance returns valid organic SEO metrics."""
    monitor = _offline_monitor()
    perf = monitor.fetch_domain_performance("loanraaj.com")

    assert perf["domain"] == "loanraaj.com"
    assert perf["impressions"] > 0
    assert perf["clicks"] >= 0
    assert 0.0 <= perf["ctr"] <= 1.0
    assert perf["avg_position"] > 0.0
    assert perf["is_indexed"]
    assert perf["is_mock"] is True
    assert perf["data_source"] == "mock_estimate"
    print(f"  [OK] GSC performance for loanraaj.com: {perf['impressions']} imps, {perf['clicks']} clicks, pos {perf['avg_position']}")


def test_gsc_audit_all_domains_aggregation():
    """audit_all_domains checks all 10 domains and aggregates clicks and impressions."""
    monitor = _offline_monitor()
    report = monitor.audit_all_domains()

    assert report["total_domains"] >= 10
    assert report["total_organic_impressions_7d"] > 0
    assert report["total_organic_clicks_7d"] > 0
    assert report["deindexed_count"] == 0
    print(f"  [OK] GSC fleet audit verified across {report['total_domains']} domains")


def test_gsc_deindexed_alert():
    """audit_all_domains identifies deindexed domains and alerts."""
    monitor = _offline_monitor()
    with patch.object(monitor, "fetch_domain_performance") as mock_fetch:
        mock_fetch.return_value = {
            "domain": "penalty-site.com",
            "period_days": 7,
            "impressions": 0,
            "clicks": 0,
            "ctr": 0.0,
            "avg_position": 0.0,
            "indexed_pages": 0,
            "is_indexed": False,
            "is_mock": False,
            "last_synced": "2026-11-10T00:00:00",
        }
        with patch("alert_bot.TelegramAlertBot") as MockBot:
            mock_bot_inst = MagicMock()
            MockBot.return_value = mock_bot_inst

            report = monitor.audit_all_domains()
            assert report["deindexed_count"] >= 1
            assert "penalty-site.com" in report["deindexed_domains"]
            mock_bot_inst.send_message.assert_called_once()
            print("  [OK] Deindexed domain penalty detection and alert verified")


def test_gsc_cache_persistence():
    """GSCMonitor caches metrics to json file and reloads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cache = gsc_monitor.GSC_STATE_PATH
        gsc_monitor.GSC_STATE_PATH = Path(tmpdir) / "gsc_test.json"
        try:
            m1 = _offline_monitor()
            m1.fetch_domain_performance("karzseva.com")

            assert gsc_monitor.GSC_STATE_PATH.exists()

            m2 = _offline_monitor()
            assert "karzseva.com" in m2._cached_metrics
            print("  [OK] GSC cache persistence verified")
        finally:
            gsc_monitor.GSC_STATE_PATH = orig_cache


if __name__ == "__main__":
    test_gsc_fetch_domain_performance()
    test_gsc_audit_all_domains_aggregation()
    test_gsc_deindexed_alert()
    test_gsc_cache_persistence()
    print("\nAll GSC monitor tests PASSED!")
