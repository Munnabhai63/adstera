"""End-to-end --paper farm verification across Phase 3 subsystems.

Exercises 4 mocked devices + mocked Adsterra feed for 100 iterations through
DeviceFarm, CGNATTracker, NHPPScheduler, A2 AnomalyDetector, A1 LinTSBandit,
CTRGuard, B1 PhoneAgentClient guardrails, Phase3Store SQLite, and structured
JSON-lines logging, plus A3/A5/LiveOrchestrator paper-mode integration.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

import mobile_adb
from ai_engine.interfaces import DetectionResult
from phase3.a3_forecaster.irls_quantile import IRLSQuantileForecaster
from phase3.a5_seo_gate.quality_gate import gate as a5_quality_gate
from phase3.a5_seo_gate.rpm_predictor import rank_keywords
from phase3.a6_scheduler.cgnat_tracker import CGNATTracker
from phase3.a6_scheduler.nhpp import NHPPScheduler
from phase3.adapters.adsterra_feed import AdsterraFeedAdapter
from phase3.b1_android.PhoneAgentClient import PhoneAgentClient
from phase3.b2_farm.farm import DeviceFarm
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import JsonLinesFormatter
from phase3.wiring.live_orchestrator import Phase3LiveOrchestrator


class _MockAdsterraApiClient:
    """Deterministic mock Adsterra API client returning realistic domain metrics."""

    def __init__(self) -> None:
        self.calls: int = 0

    def is_mock_mode(self) -> bool:
        return True

    async def fetch_daily_stats(
        self,
        *,
        start_date: str,
        finish_date: str,
        group_by: str = "domain",
        force_mock: bool = False,
    ) -> Dict[str, Any]:
        self.calls += 1
        return {
            "status": "ok",
            "mode": "e2e_mock_feed",
            "items": [
                {
                    "domain": "example.com",
                    "date": start_date,
                    "impressions": 1000,
                    "clicks": 22,
                    "ctr": 2.2,
                    "cpm": 1.85,
                    "revenue": 1.85,
                }
            ],
        }


class _E2EMockDevice:
    """Mocked Android phone with unique carrier IP and ad frame."""

    def __init__(self, serial: str, ip: str, domain: str = "example.com") -> None:
        self.serial = serial
        self.ip = ip
        self.domain = domain
        self.captures = 0

    def get_ip(self) -> str:
        return self.ip

    def get_domain(self) -> str:
        return self.domain

    def is_alive(self, serial: Optional[str] = None) -> bool:
        return True

    def screenshot(self) -> bytes:
        self.captures += 1
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
            b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
            b"\x00\x00IEND\xaeB`\x82"
        )

    def detect_ad(self, frame: bytes) -> DetectionResult:
        return DetectionResult(
            label="banner",
            confidence=0.91,
            bbox=(120, 420, 320, 100),
            source="model",
        )


class _SpyB1Client:
    """Wraps real PhoneAgentClient and records any attempted touch calls."""

    def __init__(self, serial: str, host_port: int, cfg: Phase3Config) -> None:
        self.serial = serial
        self.host_port = host_port
        self.inner = PhoneAgentClient(serial=serial, host_port=host_port, cfg=cfg)
        self.touch_attempts: List[Tuple[str, Tuple[Any, ...], Dict[str, Any]]] = []

    def tap(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        self.touch_attempts.append(("tap", args, dict(kwargs)))
        raise AssertionError(f"Real tap() must NEVER be called in --paper mode ({self.serial})")

    def swipe(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        self.touch_attempts.append(("swipe", args, dict(kwargs)))
        raise AssertionError(f"Real swipe() must NEVER be called in --paper mode ({self.serial})")

    def dispatch_gesture(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        self.touch_attempts.append(("dispatch_gesture", args, dict(kwargs)))
        raise AssertionError(
            f"Real dispatch_gesture() must NEVER be called in --paper mode ({self.serial})"
        )

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "serial": self.serial, "host_port": self.host_port}

    def close(self) -> None:
        self.inner.close()


def _build_e2e_config(tmp_path: Path) -> Phase3Config:
    from common.paths import atomic_write_json

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "e2e_phase3.db")
    cfg.phase3.state_dir = str(tmp_path / "e2e_state")
    atomic_write_json(
        Path(cfg.phase3.state_dir) / "ai_engine" / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    cfg.phase3.default_mode = "paper"
    # Keep NHPP and polling delays fast for 100 deterministic E2E iterations
    cfg.a6_scheduler.min_delay_seconds = 0.001
    cfg.a6_scheduler.max_delay_seconds = 0.005
    cfg.b2_farm.poll_interval_seconds = 0.001
    cfg.b2_farm.target_daily_sessions = 2000
    # Disable inter-session cooldown so 4 devices complete 100 sessions quickly
    # while still enforcing active-slot /24 & /20 collision checks in SQLite
    cfg.cgnat_tracker.slash24_cooldown_seconds = 0
    cfg.cgnat_tracker.slash20_cooldown_seconds = 0
    return cfg


def test_e2e_paper_farm_100_iterations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full --paper E2E run across 4 devices + mocked Adsterra feed for 100 iterations."""
    monkeypatch.delenv("PHASE3_LIVE_CONFIRM_TOKEN", raising=False)
    monkeypatch.delenv("ADSTERRA_API_KEY", raising=False)

    adb_touch_calls: List[List[str]] = []

    def _guard_run_adb(
        args: List[str], custom_path: str = "", timeout: float = 12.0
    ) -> Tuple[int, str]:
        if "input" in args or "tap" in args or "swipe" in args:
            adb_touch_calls.append(list(args))
            raise AssertionError(f"Real ADB input command executed in paper mode: {args}")
        return 0, ""

    monkeypatch.setattr(mobile_adb, "run_adb", _guard_run_adb)

    cfg = _build_e2e_config(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)
    cgnat = CGNATTracker(cfg, store)
    scheduler = NHPPScheduler(cfg, rng=random.Random(42))
    mock_api_client = _MockAdsterraApiClient()
    adsterra_feed = AdsterraFeedAdapter(cfg, client=mock_api_client)

    # 4 mocked devices on 4 distinct /20 carrier subnets
    device_specs = {
        "e2e-phone-1": "100.64.16.11",
        "e2e-phone-2": "100.64.32.22",
        "e2e-phone-3": "100.64.48.33",
        "e2e-phone-4": "100.64.64.44",
    }
    mock_devices = {
        serial: _E2EMockDevice(serial, ip) for serial, ip in device_specs.items()
    }
    spy_b1_clients: Dict[str, _SpyB1Client] = {}

    def _make_b1(serial: str, host_port: int) -> _SpyB1Client:
        client = _SpyB1Client(serial, host_port, cfg)
        spy_b1_clients[serial] = client
        return client

    # Capture structured JSON-lines logs emitted by phase3.b2_farm and phase3 root
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setFormatter(JsonLinesFormatter())
    farm_logger = logging.getLogger("phase3.b2_farm")
    old_farm_handlers = list(farm_logger.handlers)
    old_farm_level = farm_logger.level
    old_farm_propagate = farm_logger.propagate
    farm_logger.handlers = [handler]
    farm_logger.setLevel(logging.INFO)
    farm_logger.propagate = False

    try:
        farm = DeviceFarm(
            cfg,
            store=store,
            cgnat_tracker=cgnat,
            scheduler=scheduler,
            devices=list(device_specs.keys()),
            device_factory=lambda serial: mock_devices[serial],
            b1_client_factory=_make_b1,
            adsterra_feed=adsterra_feed,
            paper=True,
        )
        assert farm.paper is True

        asyncio.run(farm.start(max_iterations=100))
        health = farm.health()
    finally:
        farm_logger.handlers = old_farm_handlers
        farm_logger.setLevel(old_farm_level)
        farm_logger.propagate = old_farm_propagate

    # 1. Farm ran 100 iterations in paper mode across all 4 devices
    assert health["mode"] == "paper"
    assert health["total_devices"] == 4
    assert health["iterations_completed"] == 100
    assert mock_api_client.calls >= 1

    # 2. ZERO real touch calls executed (neither B1 client nor ADB input)
    assert adb_touch_calls == []
    assert all(len(c.touch_attempts) == 0 for c in spy_b1_clients.values())
    assert store.count_executed_touches() == 0

    # 3. Structured JSON-lines logs with correlation IDs emitted
    raw_lines = [ln.strip() for ln in log_buf.getvalue().splitlines() if ln.strip()]
    assert len(raw_lines) >= 102
    parsed_logs = [json.loads(ln) for ln in raw_lines]
    session_logs = [entry for entry in parsed_logs if entry.get("event") == "session_completed"]
    assert len(session_logs) == 100
    assert all(isinstance(entry.get("correlation_id"), str) and entry["correlation_id"].startswith("p3_") for entry in session_logs)
    assert all(entry.get("executed_touch") is False for entry in session_logs)
    assert all("ts" in entry and "level" in entry and "device_id" in entry for entry in session_logs)

    # 4. SQLite DB rows populated accurately in p3_sessions & p3_decisions_rewards
    assert store.count_sessions() == 100
    assert store.count_decisions() == 100

    with store.connect() as conn:
        sessions = conn.execute("SELECT * FROM p3_sessions").fetchall()
        rewards = conn.execute("SELECT * FROM p3_decisions_rewards").fetchall()
        cgnat_rows = conn.execute("SELECT * FROM p3_cgnat_slots").fetchall()
        farm_devices = conn.execute("SELECT * FROM p3_farm_devices").fetchall()

    assert len(sessions) == 100
    assert len(rewards) == 100
    assert len(cgnat_rows) == 100
    assert len(farm_devices) == 4

    session_ids = {row["session_id"] for row in sessions}
    assert all(row["mode"] == "paper" for row in sessions)
    assert all(row["status"] == "completed" for row in sessions)
    assert all(bool(row["correlation_id"]) for row in sessions)
    assert {row["device_id"] for row in sessions} == set(device_specs.keys())

    assert all(row["executed_touch"] == 0 for row in rewards)
    assert all(row["action"] in ("paper_click", "skip", "defer") for row in rewards)
    assert all(row["session_id"] in session_ids for row in rewards)
    assert all(bool(row["correlation_id"]) for row in rewards)
    assert all(abs(float(row["rpm"]) - 1.85) < 1e-6 for row in rewards)

    # All CGNAT slots were cleanly released at end of sessions
    assert all(row["active"] == 0 and row["released_at"] is not None for row in cgnat_rows)
    assert sum(int(row["total_sessions"]) for row in farm_devices) == 100

    # Farm-wide aggregate CTR cap guardrail actively blocks clicks once min_samples is reached
    ordered_rewards = sorted(rewards, key=lambda r: int(r["id"]))
    min_samples = farm.aggregate_ctr_guard.min_samples
    post_warmup_clicks = sum(
        1
        for r in ordered_rewards[min_samples:]
        if r["action"] in ("click", "paper_click")
    )
    defer_count = sum(1 for r in ordered_rewards if r["action"] == "defer")
    total_clicks = sum(
        1 for r in ordered_rewards if r["action"] in ("click", "paper_click")
    )
    if total_clicks >= int(min_samples * cfg.safety.aggregate_ctr_hard_cap) + 1:
        assert defer_count > 0
        assert post_warmup_clicks == 0
    else:
        assert health["aggregate_ctr"] <= cfg.safety.aggregate_ctr_hard_cap + (
            1.0 / max(1, cfg.safety.ctr_window_size)
        )


def test_e2e_cross_module_a3_a5_and_live_orchestrator_paper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_png_bytes: bytes,
    sample_ad_ui_tree: str,
) -> None:
    """Verify A3 forecaster, A5 SEO/RPM gate, and Phase3LiveOrchestrator integrate cleanly in --paper."""
    monkeypatch.delenv("PHASE3_LIVE_CONFIRM_TOKEN", raising=False)
    cfg = _build_e2e_config(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)

    # A5 Anti-AI gate + Gamma-Poisson RPM predictor
    human_article = (
        "Small publishers rarely fail from a lack of pageviews; they fail because slow "
        "layouts push real readers away before the first paragraph finishes loading. "
        "Earlier this spring, our field audit compared mobile load times across twelve sites. "
        "Two stood out immediately! Why did those two convert better? They trimmed blocking "
        "scripts, kept headlines concise, and placed responsive units below the fold where "
        "readers naturally paused while scrolling down to read the comparison tables. "
        "Over ninety days, bounce rates dropped noticeably while viewability climbed past "
        "seventy percent without annoying popups or clutter. "
        "Look at the numbers from week four. Pages carrying three heavy third-party widgets "
        "stalled for nearly five seconds on mid-range Android handsets over congested cellular "
        "towers, whereas stripped templates painted useful text in under nine hundred milliseconds! "
        "Does every niche behave identically? Not quite. Personal finance guides tolerate longer "
        "reference charts, provided headings break up dense prose into scannable steps, while "
        "local utility tutorials win when the exact checklist appears right after a brief intro. "
        "Track real user scroll depth before moving any ad slot, verify cache hit ratios after "
        "each deploy, and retire stale scripts promptly so mobile battery drain never drives "
        "loyal visitors straight back to the search results page."
    )
    gate_res = a5_quality_gate(human_article, cfg=cfg)
    assert gate_res["pass"] is True, gate_res

    ranked = rank_keywords(
        [
            {"keyword": "low rpm", "gsc_impressions": 800, "gsc_clicks": 8, "position": 12, "historical_ecpm": 0.4},
            {"keyword": "high rpm", "gsc_impressions": 2400, "gsc_clicks": 120, "position": 2, "historical_ecpm": 3.5},
        ],
        cfg=cfg,
    )
    assert ranked[0]["keyword"] == "high rpm"

    # A3 IRLS quantile forecaster fed from AdsterraFeedAdapter revenue series
    feed = AdsterraFeedAdapter(cfg, client=_MockAdsterraApiClient())
    series = asyncio.run(feed.get_revenue_series(days=10, force_mock=True))
    forecaster = IRLSQuantileForecaster(cfg, store=store)
    forecast = forecaster.forecast(series, horizon_days=7)
    assert forecast["method"] == "irls_quantile"
    assert forecast["p10"] <= forecast["p50"] <= forecast["p90"]

    with store.connect() as conn:
        fc_count = conn.execute("SELECT COUNT(*) FROM p3_forecasts").fetchone()[0]
    assert fc_count == 1

    # Phase3LiveOrchestrator in default --paper mode (requested live without token -> refused to paper)
    class _SpyTouch:
        def __init__(self) -> None:
            self.calls = 0

        def tap(self, x: int, y: int, duration_ms: int = 100) -> None:
            self.calls += 1

    class _MockCapture:
        def screenshot(self) -> bytes:
            return fake_png_bytes

        def dump_ui(self) -> str:
            return sample_ad_ui_tree

    spy_touch = _SpyTouch()
    orch = Phase3LiveOrchestrator(cfg, live=True, strict_live=False, store=store, adsterra_feed=feed, seed=42)
    assert orch.mode == "paper"
    assert orch.paper is True

    results = asyncio.run(
        orch.run_loop(
            touch=spy_touch,
            capture=_MockCapture(),
            device_id="e2e-orch-dev",
            domain="example.com",
            max_steps=3,
            step_delay_s=0.0,
        )
    )
    assert len(results) == 3
    assert spy_touch.calls == 0
    assert store.count_executed_touches() == 0
    assert store.count_sessions() == 3
    assert store.count_decisions() == 3
