"""Unit tests for Phase 3 config, SQLite migrations/store, and adapters."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_engine.interfaces import AgentState, MetricsSnapshot
from phase3.adapters import (
    AdsterraFeedAdapter,
    DeviceTouchCaptureBridge,
    Phase1DeviceAdapter,
    Phase2AIAdapter,
    RevenueLegacyAdapter,
    SEOLegacyAdapter,
)
from phase3.config_loader import load_phase3_config
from phase3.db.migrations.runner import Phase3Store, apply_migrations


def test_config_loader_and_env_only_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHASE3_LIVE_CONFIRM_TOKEN", raising=False)
    monkeypatch.delenv("ADSTERRA_API_KEY", raising=False)

    cfg = load_phase3_config()
    assert cfg.phase3.default_mode == "paper"
    assert cfg.is_live_confirmed() is False
    assert cfg.resolve_env_secret("ADSTERRA_API_KEY") == ""

    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "WRONG_TOKEN")
    assert cfg.is_live_confirmed() is False

    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")
    assert cfg.is_live_confirmed() is True


def test_sqlite_migrations_idempotent_and_store_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "p3.db"
    first = apply_migrations(db_file)
    second = apply_migrations(db_file)
    assert "001_init" in first
    assert second == []

    store = Phase3Store(db_file)
    store.start_session(
        session_id="sess_1",
        correlation_id="p3_corr1",
        device_id="dev-a",
        mode="paper",
        domain="example.com",
        ip_address="198.51.100.42",
        subnet_24="198.51.100.0/24",
        subnet_20="198.51.96.0/20",
    )
    store.log_decision_reward(
        session_id="sess_1",
        correlation_id="p3_corr1",
        device_id="dev-a",
        domain="example.com",
        slot_type="banner",
        action="paper_click",
        executed_touch=False,
        bbox=(100, 400, 880, 250),
        a4_source="rule_fallback",
        a4_confidence=0.85,
        a2_severity="OK",
        safe_mode=False,
        rpm=1.25,
        ctr=0.02,
        reward_value=0.00125,
        reason="unit-test",
    )
    store.finish_session("sess_1", status="completed", dwell_seconds=12.5)
    store.log_forecast(
        horizon_days=7,
        sample_count=14,
        method="irls_quantile",
        p10_revenue=1.1,
        p50_revenue=2.2,
        p90_revenue=3.3,
        p10_ecpm=0.4,
        p50_ecpm=0.8,
        p90_ecpm=1.2,
    )
    store.upsert_farm_device(device_id="dev-a", usb_port="port_1", cdp_port=9222, b1_port=9320)

    assert store.count_sessions() == 1
    assert store.count_decisions() == 1
    assert store.count_executed_touches() == 0
    recent = store.recent_decisions(limit=5)
    assert len(recent) == 1
    assert recent[0]["correlation_id"] == "p3_corr1"


def test_phase1_device_adapter_mocked_adb(monkeypatch: pytest.MonkeyPatch, tmp_phase3_config) -> None:
    import phase3.adapters.phase1_device as p1_mod

    adb_calls: list[list[str]] = []

    class _FakeMobileAdb:
        @staticmethod
        def list_devices(custom_path: str = ""):
            return [{"id": "emu-test-1", "status": "device"}, {"id": "emu-off", "status": "offline"}]

        @staticmethod
        def run_adb(args, custom_path: str = "", timeout: float = 12.0):
            adb_calls.append(list(args))
            if "get-state" in args:
                return 0, "device"
            if "ro.product.model" in args:
                return 0, "PixelTest"
            if "ro.build.version.release" in args:
                return 0, "14"
            if "wm" in args:
                return 0, "Physical size: 1080x1920"
            if "uiautomator" in args:
                return 0, '<hierarchy rotation="0"><node text="ok" /></hierarchy>UI hierchary dumped to: /dev/tty'
            return 0, "ok"

        @staticmethod
        def get_public_ip(timeout: float = 6.0):
            return {"ip": "203.0.113.10", "country": "US", "city": "Austin", "ok": True}

        @staticmethod
        def rotate_ip(device_id: str = "", wait_seconds: float = 4.0, custom_path: str = ""):
            return True, "203.0.113.10", "203.0.113.11", "rotated"

    monkeypatch.setattr(p1_mod, "mobile_adb", _FakeMobileAdb)

    adapter = Phase1DeviceAdapter(tmp_phase3_config)
    assert adapter.list_devices() == ["emu-test-1"]
    assert adapter.is_alive("emu-test-1") is True
    info = adapter.get_device_info("emu-test-1")
    assert info["model"] == "PixelTest"
    assert info["resolution"] == "1080x1920"
    assert adapter.get_public_ip()["ip"] == "203.0.113.10"
    ok, old_ip, new_ip, _ = adapter.rotate_ip("emu-test-1")
    assert ok and old_ip != new_ip

    # Paper bridge must block tap/swipe
    paper_bridge = DeviceTouchCaptureBridge(adapter, "emu-test-1", paper=True)
    with pytest.raises(RuntimeError):
        paper_bridge.tap(100, 200)

    # Live bridge executes ADB tap
    live_bridge = DeviceTouchCaptureBridge(adapter, "emu-test-1", paper=False)
    live_bridge.tap(150, 250)
    assert any("tap" in cmd for cmd in adb_calls)

    # dump_ui strips trailing /dev/tty noise after </hierarchy>
    dumped = adapter.dump_ui("emu-test-1")
    assert dumped.startswith("<hierarchy")
    assert dumped.endswith("</hierarchy>")


def test_adsterra_feed_adapter_mock_and_cache(monkeypatch: pytest.MonkeyPatch, tmp_phase3_config) -> None:
    monkeypatch.delenv("ADSTERRA_API_KEY", raising=False)
    calls = {"count": 0}

    class _FakeClient:
        def is_mock_mode(self) -> bool:
            return True

        async def fetch_daily_stats(self, **kwargs) -> Dict[str, Any]:
            calls["count"] += 1
            return {
                "status": "ok",
                "mode": "mock_simulated",
                "items": [
                    {
                        "domain": "example.com",
                        "impressions": 200,
                        "clicks": 6,
                        "ctr": 3.0,
                        "cpm": 2.40,
                        "revenue": 0.48,
                    }
                ],
            }

    feed = AdsterraFeedAdapter(tmp_phase3_config, client=_FakeClient())
    assert feed.has_live_credentials() is False

    m1 = asyncio.run(feed.get_domain_metrics("example.com"))
    m2 = asyncio.run(feed.get_domain_metrics("example.com"))
    assert calls["count"] == 1  # served from TTL cache
    assert m1["impressions"] == 200
    assert m1["ctr"] == pytest.approx(0.03)
    assert m2["ecpm"] == pytest.approx(2.40)

    series = asyncio.run(feed.get_revenue_series(days=3))
    assert len(series) == 3
    assert all("revenue" in row and "ecpm" in row for row in series)


def test_phase2_ai_adapter_gating_and_safe_mode(
    tmp_phase3_config,
    fake_png_bytes: bytes,
    sample_ad_ui_tree: str,
    empty_ui_tree: str,
    deterministic_seed: int,
) -> None:
    ai = Phase2AIAdapter(tmp_phase3_config, seed=deterministic_seed, paper=True)

    det_ok = ai.detect_ads(fake_png_bytes, ui_tree=sample_ad_ui_tree)
    assert det_ok["verified"] is True
    assert det_ok["bbox"] is not None

    det_none = ai.detect_ads(fake_png_bytes, ui_tree=empty_ui_tree)
    assert det_none["verified"] is False
    assert det_none["bbox"] is None

    state = AgentState(domain_id=1, slot_type="banner", recent_ctr=0.02, recent_rpm=2.0, bbox_confidence=det_ok["confidence"])

    # Unverified bbox -> skip
    dec_nobbox = ai.decide_action(state, det_none, paper=False, a2_ok=True)
    assert dec_nobbox.action == "skip"

    # A2 not ok -> skip
    dec_a2bad = ai.decide_action(state, det_ok, paper=False, a2_ok=False)
    assert dec_a2bad.action == "skip"

    # Paper mode -> never returns click
    dec_paper = ai.decide_action(state, det_ok, paper=True, a2_ok=True)
    assert dec_paper.action in ("paper_click", "skip", "defer")

    # Critical anomaly (CTR >= hard_cap / empty ad spike) triggers SAFE MODE
    crit = ai.check_anomaly(
        MetricsSnapshot(rpm=0.01, ctr=0.08, empty_ad_rate=0.65, load_time_ms=15000.0)
    )
    assert crit.severity == "CRITICAL"
    assert ai.is_safe_mode() is True
    dec_sm = ai.decide_action(state, det_ok, paper=False, a2_ok=True)
    assert dec_sm.action == "skip"


def test_seo_and_revenue_legacy_adapters(tmp_phase3_config) -> None:
    class _FakeMonitor:
        def fetch_domain_performance(self, domain: str, **kwargs):
            return {"domain": domain, "impressions": 300, "clicks": 9, "ctr": 0.03, "avg_position": 8.4}

        def audit_all_domains(self, **kwargs):
            return {"total_domains": 1, "domains": {"example.com": {"impressions": 300}}, "deindexed_domains": []}

    seo = SEOLegacyAdapter(tmp_phase3_config, monitor=_FakeMonitor())
    gsc = seo.get_gsc_domain_metrics("example.com")
    assert gsc["impressions"] == 300
    assert seo.audit_gsc_fleet()["total_domains"] == 1

    rev = RevenueLegacyAdapter(tmp_phase3_config)
    history = [{"total_revenue": 1.0 + 0.1 * i} for i in range(10)]
    rev.fit(history=history)
    seven = rev.forecast_next_7_days()
    assert len(seven) == 7
    assert rev.forecast_monthly_estimate() > 0.0
