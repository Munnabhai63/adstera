"""Unit and integration tests for Phase 3 B2 Multi-Phone USB Hub Farm."""
from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from ai_engine.interfaces import AdDecision, AnomalyResult, DetectionResult, MetricsSnapshot
from phase3.b2_farm import DeviceFarm, build_usb_assignments
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import JsonLinesFormatter


class _MockDevice:
    """Deterministic mock Android device for B2 farm tests."""

    def __init__(
        self,
        serial: str,
        ip: str,
        *,
        fail_count: int = 0,
        probe_ok: bool = True,
        anomalous_ctr: Optional[float] = None,
    ) -> None:
        self.serial = serial
        self.ip = ip
        self.fail_remaining = fail_count
        self.probe_ok = probe_ok
        self.anomalous_ctr = anomalous_ctr
        self.sessions_attempted = 0
        self.domain = "example.com"

    def get_ip(self) -> str:
        return self.ip

    def get_domain(self) -> str:
        return self.domain

    def is_alive(self, serial: Optional[str] = None) -> bool:
        return self.probe_ok

    def screenshot(self) -> bytes:
        self.sessions_attempted += 1
        if self.fail_remaining > 0:
            self.fail_remaining -= 1
            raise RuntimeError(f"simulated ADB error on {self.serial}")
        return b"\x89PNG\r\n\x1a\n"

    def detect_ad(self, frame: bytes) -> DetectionResult:
        return DetectionResult(
            label="banner",
            confidence=0.92,
            bbox=(100, 300, 320, 100),
            source="model",
        )

    def metrics_snapshot(self) -> MetricsSnapshot:
        ctr = self.anomalous_ctr if self.anomalous_ctr is not None else 0.02
        return MetricsSnapshot(
            rpm=1.20,
            ctr=ctr,
            empty_ad_rate=0.05,
            load_time_ms=400.0,
            error_rate=0.0,
            repeated_creative_rate=0.0,
            domain=self.domain,
            device_id=self.serial,
        )


class _MockB1Client:
    """Tracks any tap calls so tests can verify paper mode never touches."""

    def __init__(self, serial: str, host_port: int) -> None:
        self.serial = serial
        self.host_port = host_port
        self.taps: List[Dict[str, Any]] = []
        self.closed = False

    def tap(
        self,
        x: int,
        y: int,
        duration_ms: int = 80,
        *,
        a4_verified_bbox: bool = False,
        a2_ok: bool = False,
    ) -> bool:
        self.taps.append(
            {
                "x": x,
                "y": y,
                "duration_ms": duration_ms,
                "a4_verified_bbox": a4_verified_bbox,
                "a2_ok": a2_ok,
            }
        )
        return True

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "serial": self.serial, "host_port": self.host_port}

    def close(self) -> None:
        self.closed = True


class _FixedClickBandit:
    """Minimal isolated per-device AI bandit mock with inspectable weights."""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.weights = np.zeros(4, dtype=np.float64)
        self.decisions = 0
        self.updates = 0

    def decide(self, state: Any, detection: DetectionResult, paper: bool = True, device_id: str = "") -> AdDecision:
        self.decisions += 1
        return AdDecision(
            action="paper_click" if paper else "click",
            bbox=detection.bbox,
            slot_type=detection.label or "banner",
            domain="example.com",
            timing_ms=1000,
            reason="mock_click",
            decision_id=f"dec_{self.device_id}_{self.decisions}",
        )

    def update(self, arm_id: str, reward: float, state: Any = None, device_id: str = "") -> None:
        self.updates += 1
        # Mutate device-specific vector so cross-device weight sharing would be caught
        idx = sum(ord(c) for c in self.device_id) % 4
        self.weights[idx] += 1.0 + float(reward)


class _FastScheduler:
    def schedule_next(self, now_ts: Optional[float] = None) -> float:
        return 0.001


def _make_cfg(tmp_path: Path) -> Phase3Config:
    from common.paths import atomic_write_json

    cfg = load_phase3_config()
    cfg.phase3.db_path = str(tmp_path / "phase3_test.db")
    cfg.phase3.state_dir = str(tmp_path / "state")
    atomic_write_json(
        Path(cfg.phase3.state_dir) / "ai_engine" / "safe_mode.json",
        {"active": False, "entry_reason": "", "entry_ts": 0.0, "clean_window_count": 0},
    )
    cfg.a6_scheduler.min_delay_seconds = 0.001
    cfg.a6_scheduler.max_delay_seconds = 10.0
    cfg.b2_farm.poll_interval_seconds = 0.001
    cfg.cgnat_tracker.slash24_cooldown_seconds = 0
    cfg.cgnat_tracker.slash20_cooldown_seconds = 0
    return cfg


def test_per_device_isolation_ports_sessions_and_a1_weights(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)

    # Distinct /20 subnets (16, 32, 48, 64)
    mock_devices = {
        "dev-ser-1": _MockDevice("dev-ser-1", "100.64.16.10"),
        "dev-ser-2": _MockDevice("dev-ser-2", "100.64.32.10"),
        "dev-ser-3": _MockDevice("dev-ser-3", "100.64.48.10"),
        "dev-ser-4": _MockDevice("dev-ser-4", "100.64.64.10"),
    }
    b1_clients: Dict[str, _MockB1Client] = {}
    bandits: Dict[str, Any] = {}

    def make_b1(serial: str, host_port: int) -> _MockB1Client:
        c = _MockB1Client(serial, host_port)
        b1_clients[serial] = c
        return c

    farm = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        devices=list(mock_devices.keys()),
        device_factory=lambda serial: mock_devices[serial],
        b1_client_factory=make_b1,
        paper=True,
    )

    # Capture per-device real LinTSBandit instances
    for dev_id, rt in farm._devices.items():
        bandits[dev_id] = rt.ai_component

    asyncio.run(farm.start(max_iterations=8))

    health = farm.health()
    assert health["mode"] == "paper"
    assert health["total_devices"] == 4
    assert health["healthy_devices"] == 4
    assert health["iterations_completed"] == 8

    # Verify separate ports & ADB serial flags
    usb_ports = set()
    cdp_ports = set()
    b1_ports = set()
    for dev_id, dinfo in health["devices"].items():
        usb_ports.add(dinfo["usb_port"])
        cdp_ports.add(dinfo["cdp_port"])
        b1_ports.add(dinfo["b1_port"])
        assert dinfo["adb_args"] == ["-s", dev_id]
        assert dinfo["total_sessions"] >= 1
    assert len(usb_ports) == 4
    assert len(cdp_ports) == 4
    assert len(b1_ports) == 4

    # Zero real touches in paper mode
    assert all(len(c.taps) == 0 for c in b1_clients.values())
    assert store.count_executed_touches() == 0
    assert store.count_sessions() == 8
    assert store.count_decisions() == 8

    # Verify separate A1 weights: mutate dev-ser-1 bandit, others unchanged
    b1_before = {k: {wk: wv.copy() for wk, wv in b._weights.items()} for k, b in bandits.items()}
    bandits["dev-ser-1"].update("banner", 0.99, device_id="dev-ser-1")
    assert not np.allclose(
        bandits["dev-ser-1"]._weights["banner:b"],
        b1_before["dev-ser-1"]["banner:b"],
    )
    for other in ("dev-ser-2", "dev-ser-3", "dev-ser-4"):
        assert np.allclose(bandits[other]._weights["banner:b"], b1_before[other]["banner:b"])

    # Verify p3_farm_devices rows in SQLite
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM p3_farm_devices").fetchall()
        assert len(rows) == 4


def test_cgnat_blocks_colliding_ip_slots(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.cgnat_tracker.slash24_cooldown_seconds = 1800
    cfg.cgnat_tracker.slash20_cooldown_seconds = 600
    store = Phase3Store(cfg.phase3.db_path)

    # dev-b shares the exact same /24 and /20 subnet as dev-a
    class _CollidingCGNAT:
        def __init__(self) -> None:
            self.blocked_calls: List[str] = []
            self.acquired: List[str] = []
            self._holder: Optional[str] = None

        def acquire_slot(self, device_id: str, ip_address: Optional[str] = None, now_ts: Optional[float] = None) -> bool:
            if device_id == "dev-colliding":
                self.blocked_calls.append(device_id)
                return False
            if self._holder is not None and self._holder != device_id:
                self.blocked_calls.append(device_id)
                return False
            self._holder = device_id
            self.acquired.append(device_id)
            return True

        def release_slot(self, device_id: str, now_ts: Optional[float] = None) -> None:
            if self._holder == device_id:
                self._holder = None

    tracker = _CollidingCGNAT()
    mock_devices = {
        "dev-primary": _MockDevice("dev-primary", "100.64.16.10"),
        "dev-colliding": _MockDevice("dev-colliding", "100.64.16.25"),
    }

    farm = DeviceFarm(
        cfg,
        store=store,
        cgnat_tracker=tracker,
        scheduler=_FastScheduler(),
        devices=["dev-primary", "dev-colliding"],
        device_factory=lambda serial: mock_devices[serial],
        paper=True,
    )

    asyncio.run(farm.start(max_iterations=3))

    assert len(tracker.blocked_calls) >= 1
    assert mock_devices["dev-colliding"].sessions_attempted == 0
    with store.connect() as conn:
        colliding_sessions = conn.execute(
            "SELECT COUNT(*) FROM p3_sessions WHERE device_id = 'dev-colliding'"
        ).fetchone()[0]
        primary_sessions = conn.execute(
            "SELECT COUNT(*) FROM p3_sessions WHERE device_id = 'dev-primary'"
        ).fetchone()[0]
    assert colliding_sessions == 0
    assert primary_sessions == 3


def test_fallback_cgnat_prevents_concurrent_same_subnet(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.cgnat_tracker.slash24_cooldown_seconds = 1800
    cfg.cgnat_tracker.slash20_cooldown_seconds = 600
    store = Phase3Store(cfg.phase3.db_path)

    farm = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        devices=["d1", "d2"],
        device_factory=lambda s: _MockDevice(s, "100.64.16.10" if s == "d1" else "100.64.16.50"),
        paper=True,
    )
    # Acquire slot for d1; d2 in same /24 & /20 MUST be rejected
    assert farm.cgnat_tracker.acquire_slot("d1", "100.64.16.10", now_ts=1000.0) is True
    assert farm.cgnat_tracker.acquire_slot("d2", "100.64.16.50", now_ts=1001.0) is False
    farm.cgnat_tracker.release_slot("d1", now_ts=1002.0)
    # Cooldown still active for /20 and /24
    assert farm.cgnat_tracker.acquire_slot("d2", "100.64.16.50", now_ts=1005.0) is False


def test_farm_wide_safe_mode_on_single_device_anomaly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")
    cfg = _make_cfg(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)

    # Device 1 reports CTR=0.40 (>= hard_cap 0.045 -> CRITICAL A2 anomaly!)
    # Devices 2, 3, 4 have normal metrics, yet MUST ALL suppress clicks once SAFE MODE triggers.
    mock_devices = {
        "dev-bad": _MockDevice("dev-bad", "100.64.16.10", anomalous_ctr=0.40),
        "dev-2": _MockDevice("dev-2", "100.64.32.10"),
        "dev-3": _MockDevice("dev-3", "100.64.48.10"),
        "dev-4": _MockDevice("dev-4", "100.64.64.10"),
    }
    b1_clients: Dict[str, _MockB1Client] = {}

    farm = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        devices=list(mock_devices.keys()),
        device_factory=lambda s: mock_devices[s],
        ai_factory=lambda device_id: _FixedClickBandit(device_id),
        b1_client_factory=lambda serial, host_port: b1_clients.setdefault(serial, _MockB1Client(serial, host_port)),
        paper=False,  # Even in live mode, SAFE MODE MUST suppress clicks on ALL devices
    )

    # Run dev-bad first or full farm so dev-bad triggers SAFE MODE
    asyncio.run(farm._run_device_step(farm._devices["dev-bad"], max_iterations=None))
    assert farm.safe_mode.is_active() is True
    assert farm.health()["safe_mode"] is True

    # Verify rate throttling is active
    throttled_delay = farm._compute_next_delay()
    assert throttled_delay > cfg.a6_scheduler.min_delay_seconds

    # Run remaining devices — ALL clicks must be suppressed across the farm
    for dev_id in ("dev-2", "dev-3", "dev-4"):
        asyncio.run(farm._run_device_step(farm._devices[dev_id], max_iterations=None))

    assert all(len(c.taps) == 0 for c in b1_clients.values())
    assert store.count_executed_touches() == 0
    decisions = store.recent_decisions(limit=10)
    assert len(decisions) == 4
    assert all(d["action"] == "skip" for d in decisions)
    assert all(d["safe_mode"] == 1 for d in decisions)


def test_auto_quarantine_and_auto_recovery(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.b2_farm.health.max_consecutive_failures = 3
    cfg.b2_farm.health.quarantine_cooldown_seconds = 300
    store = Phase3Store(cfg.phase3.db_path)

    clock = [1000.0]
    failing_dev = _MockDevice("dev-flaky", "100.64.16.10", fail_count=3, probe_ok=True)
    healthy_dev = _MockDevice("dev-ok", "100.64.32.10")

    farm = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        devices=["dev-flaky", "dev-ok"],
        device_factory=lambda s: failing_dev if s == "dev-flaky" else healthy_dev,
        paper=True,
        time_fn=lambda: clock[0],
    )

    # 3 consecutive failures on dev-flaky -> quarantined
    for _ in range(3):
        res = asyncio.run(farm._run_device_step(farm._devices["dev-flaky"], max_iterations=None))
        assert res == "error"

    h = farm.health()["devices"]["dev-flaky"]
    assert h["status"] == "quarantined"
    assert h["consecutive_failures"] == 3
    assert h["quarantined_until"] == pytest.approx(1300.0)

    # Healthy sibling continues running without crashing farm
    ok_res = asyncio.run(farm._run_device_step(farm._devices["dev-ok"], max_iterations=None))
    assert ok_res == "ok"

    # During cooldown, flaky device is skipped
    clock[0] = 1150.0
    skip_res = asyncio.run(farm._run_device_step(farm._devices["dev-flaky"], max_iterations=None))
    assert skip_res == "quarantined_skip"

    # Persist check in SQLite
    with store.connect() as conn:
        row = conn.execute(
            "SELECT status, consecutive_failures, quarantined_until FROM p3_farm_devices WHERE device_id = 'dev-flaky'"
        ).fetchone()
    assert row["status"] == "quarantined"
    assert row["consecutive_failures"] == 3

    # Cooldown elapses -> probe succeeds -> auto-recovery + resumes session
    clock[0] = 1305.0
    rec_res = asyncio.run(farm._run_device_step(farm._devices["dev-flaky"], max_iterations=None))
    assert rec_res == "ok"

    h_after = farm.health()["devices"]["dev-flaky"]
    assert h_after["status"] == "healthy"
    assert h_after["consecutive_failures"] == 0
    assert h_after["quarantined_until"] == 0.0
    assert h_after["total_sessions"] == 1


def test_paper_default_and_live_token_guard_and_ctr_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PHASE3_LIVE_CONFIRM_TOKEN", raising=False)
    cfg = _make_cfg(tmp_path)
    cfg.safety.per_device_ctr_hard_cap = 0.10
    cfg.safety.aggregate_ctr_hard_cap = 0.10
    cfg.safety.ctr_window_size = 20
    store = Phase3Store(cfg.phase3.db_path)

    b1_clients: Dict[str, _MockB1Client] = {}
    farm_refused = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        devices=["dev-1"],
        device_factory=lambda s: _MockDevice(s, "100.64.16.10"),
        ai_factory=lambda device_id: _FixedClickBandit(device_id),
        b1_client_factory=lambda serial, host_port: b1_clients.setdefault(serial, _MockB1Client(serial, host_port)),
        paper=False,  # Requested live without env token -> MUST force paper=True
    )
    assert farm_refused.paper is True
    asyncio.run(farm_refused.start(max_iterations=2))
    assert len(b1_clients["dev-1"].taps) == 0

    # Now test CTR guard enforcement when cap would be breached
    for _ in range(18):
        farm_refused.aggregate_ctr_guard.record_impression(clicked=False)
        farm_refused._devices["dev-1"].ctr_guard.record_impression(clicked=False)
    for _ in range(2):
        farm_refused.aggregate_ctr_guard.record_impression(clicked=True)
        farm_refused._devices["dev-1"].ctr_guard.record_impression(clicked=True)

    # Next click would breach 0.10 cap -> forced to 'defer'
    asyncio.run(farm_refused._run_device_step(farm_refused._devices["dev-1"], max_iterations=None))
    latest = store.recent_decisions(limit=1)[0]
    assert latest["action"] == "defer"


def test_structured_json_logging_with_correlation_id_and_scaling_cap(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)

    # Capture structured JSON logs emitted by phase3.b2_farm
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonLinesFormatter())
    farm_logger = logging.getLogger("phase3.b2_farm")
    old_handlers = list(farm_logger.handlers)
    farm_logger.handlers = [handler]
    farm_logger.setLevel(logging.INFO)
    farm_logger.propagate = False

    try:
        # 12 serials supplied, max_devices=10 -> capped cleanly to 10
        serials = [f"mock-usb-{i:02d}" for i in range(1, 13)]
        assignments = build_usb_assignments(serials, cfg)
        assert len(assignments) == 10
        assert assignments[0].usb_port == "port_1"
        assert assignments[9].usb_port == "port_10"

        farm = DeviceFarm(
            cfg,
            store=store,
            scheduler=_FastScheduler(),
            devices=["mock-usb-01", "mock-usb-02"],
            device_factory=lambda s: _MockDevice(
                s,
                "100.64.16.10" if s == "mock-usb-01" else "100.64.32.10",
                fail_count=1 if s == "mock-usb-01" else 0,
            ),
            paper=True,
        )
        asyncio.run(farm.start(max_iterations=3))
    finally:
        farm_logger.handlers = old_handlers

    lines = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) >= 2
    parsed = [json.loads(ln) for ln in lines]
    session_events = [p for p in parsed if p.get("event") in ("session_completed", "device_session_failed")]
    assert len(session_events) >= 2
    assert all(bool(p.get("correlation_id")) for p in session_events)


def test_async_adsterra_feed_a4_validation_live_touch_result_and_phase1_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")
    cfg = _make_cfg(tmp_path)
    store = Phase3Store(cfg.phase3.db_path)

    # 1. Verify Phase1DeviceAdapter.list_devices() is used when devices=None
    import phase3.adapters.phase1_device as p1_mod

    monkeypatch.setattr(p1_mod.Phase1DeviceAdapter, "list_devices", lambda self: ["p1-dev-01"])

    class _AsyncAdsterraFeed:
        async def get_domain_metrics(self, domain: str = "default") -> Dict[str, Any]:
            return {"domain": domain, "rpm": 2.75, "ecpm": 2.75, "ctr": 0.015}

    class _DeviceNoSnap:
        def __init__(self, serial: str) -> None:
            self.serial = serial
            self.detection = DetectionResult(
                label="banner",
                confidence=0.25,  # below threshold -> MUST block click!
                bbox=(10, 20, 100, 50),
                source="model",
            )

        def get_ip(self) -> str:
            return "100.64.16.10"

        def get_domain(self) -> str:
            return "pub.example"

        def screenshot(self) -> bytes:
            return b"\x89PNG"

        def detect_ad(self, frame: bytes) -> DetectionResult:
            return self.detection

    class _RefusingB1Client:
        def __init__(self, serial: str, host_port: int) -> None:
            self.calls = 0

        def tap(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            self.calls += 1
            return {"ok": False, "executed": False, "error": "refused"}

        def status(self) -> Dict[str, Any]:
            return {"ok": True}

        def close(self) -> None:
            pass

    dev_obj = _DeviceNoSnap("p1-dev-01")
    b1_obj = _RefusingB1Client("p1-dev-01", 9320)

    farm = DeviceFarm(
        cfg,
        store=store,
        scheduler=_FastScheduler(),
        adsterra_feed=_AsyncAdsterraFeed(),
        device_factory=lambda serial: dev_obj,
        ai_factory=lambda device_id: _FixedClickBandit(device_id),
        b1_client_factory=lambda serial, host_port: b1_obj,
        paper=False,
    )
    assert "p1-dev-01" in farm._devices

    # Run with low-confidence A4 detection -> safety gate blocks click, async feed populates RPM=2.75
    asyncio.run(farm._run_device_step(farm._devices["p1-dev-01"], max_iterations=None))
    row_low_conf = store.recent_decisions(limit=1)[0]
    assert row_low_conf["action"] == "skip"
    assert row_low_conf["rpm"] == pytest.approx(2.75)
    assert row_low_conf["executed_touch"] == 0
    assert b1_obj.calls == 0

    # Now provide valid A4 detection (high confidence + positive w,h), but B1 returns executed=False
    dev_obj.detection = DetectionResult(
        label="banner",
        confidence=0.90,
        bbox=(10, 20, 120, 60),
        source="model",
    )
    asyncio.run(farm._run_device_step(farm._devices["p1-dev-01"], max_iterations=None))
    row_refused_b1 = store.recent_decisions(limit=1)[0]
    assert b1_obj.calls == 1
    assert row_refused_b1["executed_touch"] == 0

