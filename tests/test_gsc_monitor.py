"""
tests/test_gsc_monitor.py — Step 6.3: Google Search Console (GSC) Monitor Tests

Covers:
1. GSCMonitor initialization and caching
2. fetch_domain_performance returns impressions, clicks, CTR, and SERP position
3. audit_all_domains aggregates metrics across fleet
4. Deindexed domain detection triggers warning flag
5. Cache persistence to state/gsc_metrics.json
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import gsc_monitor
from gsc_monitor import GSCMonitor


def test_gsc_fetch_domain_performance():
    """fetch_domain_performance returns valid organic SEO metrics."""
    monitor = GSCMonitor()
    perf = monitor.fetch_domain_performance("loanraaj.com")

    assert perf["domain"] == "loanraaj.com"
    assert perf["impressions"] > 0
    assert perf["clicks"] >= 0
    assert 0.0 <= perf["ctr"] <= 1.0
    assert perf["avg_position"] > 0.0
    assert perf["is_indexed"]
    print(f"  [OK] GSC performance for loanraaj.com: {perf['impressions']} imps, {perf['clicks']} clicks, pos {perf['avg_position']}")


def test_gsc_audit_all_domains_aggregation():
    """audit_all_domains checks all 10 domains and aggregates clicks and impressions."""
    monitor = GSCMonitor()
    report = monitor.audit_all_domains()

    assert report["total_domains"] >= 10
    assert report["total_organic_impressions_7d"] > 0
    assert report["total_organic_clicks_7d"] > 0
    assert report["deindexed_count"] == 0
    print(f"  [OK] GSC fleet audit verified across {report['total_domains']} domains")


def test_gsc_deindexed_alert():
    """audit_all_domains identifies deindexed domains and alerts."""
    monitor = GSCMonitor()
    # Inject a deindexed mock domain
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
            m1 = GSCMonitor()
            m1.fetch_domain_performance("karzseva.com")

            assert gsc_monitor.GSC_STATE_PATH.exists()

            # Second instance loads cached result
            m2 = GSCMonitor()
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
