"""Unit tests for Phase 3 Live/Paper Orchestrator wiring and fail-safe gates."""
from __future__ import annotations

import asyncio
import json
import pytest

from phase3.wiring.live_orchestrator import (
    LiveModeRefusedError,
    Phase3LiveOrchestrator,
    main as cli_main,
    resolve_execution_mode,
)


def test_default_mode_is_paper_and_executes_zero_touches(
    tmp_phase3_config,
    make_touch,
    make_capture,
    json_log_capture,
    deterministic_seed: int,
) -> None:
    touch = make_touch()
    capture = make_capture()

    orch = Phase3LiveOrchestrator(tmp_phase3_config, seed=deterministic_seed)
    assert orch.mode == "paper"
    assert orch.paper is True

    results = asyncio.run(
        orch.run_loop(touch=touch, capture=capture, device_id="test-dev-0", domain="example.com", max_steps=3, step_delay_s=0.0)
    )
    assert len(results) == 3
    assert touch.taps == []
    assert all(r["executed_touch"] is False for r in results)
    assert all(r["action"] in ("paper_click", "skip", "defer") for r in results)

    assert orch.store.count_sessions() == 3
    assert orch.store.count_decisions() == 3
    assert orch.store.count_executed_touches() == 0

    parsed_logs = [json.loads(line) for line in json_log_capture]
    step_logs = [entry for entry in parsed_logs if entry.get("event") == "phase3_step_completed"]
    assert len(step_logs) == 3
    assert all(bool(entry.get("correlation_id")) for entry in step_logs)


def test_live_mode_refused_without_confirm_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_phase3_config,
    make_touch,
    make_capture,
    deterministic_seed: int,
) -> None:
    monkeypatch.delenv("PHASE3_LIVE_CONFIRM_TOKEN", raising=False)

    # Strict check refuses
    with pytest.raises(LiveModeRefusedError):
        resolve_execution_mode(True, tmp_phase3_config, strict=True)

    # Non-strict orchestrator degrades safely to paper mode
    orch = Phase3LiveOrchestrator(tmp_phase3_config, live=True, seed=deterministic_seed)
    assert orch.mode == "paper"
    assert orch.paper is True
    assert orch.live_refused_reason != ""

    touch = make_touch()
    capture = make_capture()
    res = asyncio.run(orch.run_step(touch=touch, capture=capture, device_id="test-dev-0", domain="example.com"))
    assert res["executed_touch"] is False
    assert touch.taps == []

    # CLI --live without env token must exit non-zero
    rc = cli_main(["--live", "--steps", "1"])
    assert rc == 2


def test_live_mode_with_token_executes_touch_only_when_a4_and_a2_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_phase3_config,
    make_touch,
    make_capture,
    empty_ui_tree: str,
    deterministic_seed: int,
) -> None:
    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")

    touch = make_touch()
    capture_with_ad = make_capture()
    orch = Phase3LiveOrchestrator(tmp_phase3_config, live=True, strict_live=True, seed=deterministic_seed)
    assert orch.mode == "live"
    assert orch.paper is False

    # Case 1: Verified A4 bbox + healthy A2 -> executes real touch inside bbox
    res_ok = asyncio.run(
        orch.run_step(
            touch=touch,
            capture=capture_with_ad,
            device_id="test-dev-live",
            domain="example.com",
            metrics_override={"rpm": 2.5, "ctr": 0.01, "load_time_ms": 200.0, "error_rate": 0.0},
        )
    )
    if res_ok["action"] == "click":
        assert res_ok["executed_touch"] is True
        assert len(touch.taps) == 1
        tx, ty, _ = touch.taps[0]
        bx, by, bw, bh = res_ok["bbox"]
        assert bx <= tx <= bx + bw
        assert by <= ty <= by + bh
    else:
        assert res_ok["executed_touch"] is False

    # Case 2: No A4 bbox -> touch must NOT fire
    taps_before = len(touch.taps)
    capture_empty = make_capture(ui_tree=empty_ui_tree)
    res_nobbox = asyncio.run(
        orch.run_step(
            touch=touch,
            capture=capture_empty,
            device_id="test-dev-live",
            domain="example.com",
            metrics_override={"rpm": 2.5, "ctr": 0.01, "load_time_ms": 200.0, "error_rate": 0.0},
        )
    )
    assert res_nobbox["a4_verified"] is False
    assert res_nobbox["action"] == "skip"
    assert res_nobbox["executed_touch"] is False
    assert len(touch.taps) == taps_before

    # Case 3: A2 critical anomaly (CTR spike + empty ad spike) -> triggers SAFE MODE and suppresses touch
    res_crit = asyncio.run(
        orch.run_step(
            touch=touch,
            capture=capture_with_ad,
            device_id="test-dev-live",
            domain="example.com",
            metrics_override={"rpm": 0.01, "ctr": 0.08, "empty_ad_rate": 0.65, "load_time_ms": 15000.0, "error_rate": 0.90},
        )
    )
    assert res_crit["a2_severity"] == "CRITICAL"
    assert res_crit["safe_mode"] is True
    assert res_crit["action"] == "skip"
    assert res_crit["executed_touch"] is False
    assert len(touch.taps) == taps_before


def test_failsafe_catches_step_exceptions_and_enters_safe_mode(
    tmp_phase3_config,
    make_touch,
    make_capture,
    json_log_capture,
    deterministic_seed: int,
) -> None:
    touch = make_touch()
    broken_capture = make_capture(fail=True)

    orch = Phase3LiveOrchestrator(tmp_phase3_config, seed=deterministic_seed)
    res = asyncio.run(
        orch.run_step(touch=touch, capture=broken_capture, device_id="dev-err", domain="example.com")
    )

    assert res["safe_mode"] is True
    assert res["executed_touch"] is False
    assert res["action"] == "skip"
    assert "Simulated capture failure" in res["error"]
    assert orch.ai.is_safe_mode() is True
    assert touch.taps == []

    parsed_logs = [json.loads(line) for line in json_log_capture]
    failsafe_logs = [entry for entry in parsed_logs if entry.get("event") == "phase3_step_failsafe"]
    assert len(failsafe_logs) == 1
    assert failsafe_logs[0]["correlation_id"] == res["correlation_id"]


def test_cli_paper_default_exits_zero(tmp_path) -> None:
    import yaml

    cfg_file = tmp_path / "p3_cfg.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "phase3": {
                    "default_mode": "paper",
                    "db_path": str(tmp_path / "cli.db"),
                    "state_dir": str(tmp_path / "state"),
                    "log_level": "INFO",
                }
            }
        ),
        encoding="utf-8",
    )
    rc = cli_main(["--config", str(cfg_file), "--steps", "2"])
    assert rc == 0


def test_auto_wraps_device_touch_capture_bridge_when_adb_device_alive(
    tmp_phase3_config,
    fake_png_bytes: bytes,
    sample_ad_ui_tree: str,
    deterministic_seed: int,
) -> None:
    class _FakeAdapter:
        def __init__(self) -> None:
            self.screenshots = 0
            self.dumps = 0
            self.taps = 0

        def is_alive(self, serial: str) -> bool:
            return serial == "FAKE-ADB-SERIAL"

        def screenshot(self, serial: str) -> bytes:
            self.screenshots += 1
            return fake_png_bytes + b"\x00DEVICE_FRAME"

        def dump_ui(self, serial: str) -> str:
            self.dumps += 1
            return sample_ad_ui_tree

        def tap(self, serial: str, x: int, y: int, duration_ms: int = 100) -> bool:
            self.taps += 1
            return True

    adapter = _FakeAdapter()
    orch = Phase3LiveOrchestrator(
        tmp_phase3_config,
        device_adapter=adapter,  # type: ignore[arg-type]
        seed=deterministic_seed,
    )
    res = asyncio.run(
        orch.run_step(device_id="FAKE-ADB-SERIAL", domain="example.com")
    )
    assert res["capture_source"] == "device_bridge"
    assert res["frame_bytes"] == len(fake_png_bytes) + 13
    assert res["a4_verified"] is True
    assert res["executed_touch"] is False
    assert adapter.screenshots == 1
    assert adapter.dumps == 1
    assert adapter.taps == 0


def test_three_consecutive_live_clicks_do_not_trip_small_sample_a2_safemode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_phase3_config,
    make_touch,
    make_capture,
    deterministic_seed: int,
) -> None:
    """Verify 3 live steps succeed without small-sample CTR tripping A2 SAFE MODE or double-counting."""
    monkeypatch.setenv("PHASE3_LIVE_CONFIRM_TOKEN", "CONFIRM_LIVE_EXECUTION")

    class _MockFeed:
        async def get_domain_metrics(self, domain: str = "default"):
            return {
                "domain": domain,
                "impressions": 100,
                "clicks": 2,
                "ctr": 0.02,
                "ecpm": 1.20,
                "revenue": 0.12,
                "rpm": 1.20,
                "source": "mock",
            }

    touch = make_touch()
    capture = make_capture()
    orch = Phase3LiveOrchestrator(
        tmp_phase3_config,
        live=True,
        strict_live=True,
        adsterra_feed=_MockFeed(),  # type: ignore[arg-type]
        seed=deterministic_seed,
    )
    # Seed positive bandit weight for banner so A1 selects 'click' deterministically on all 3 steps
    orch.ai.a1.update("banner", 0.5)
    assert orch.ai.a1.ctr_guard.min_samples == 20

    steps = []
    for _ in range(3):
        res = asyncio.run(
            orch.run_step(
                touch=touch,
                capture=capture,
                device_id="live-dev-qa",
                domain="loanraaj.com",
            )
        )
        steps.append(res)

    assert all(r["a2_ok"] is True for r in steps)
    assert all(r["a2_severity"] == "OK" for r in steps)
    assert all(r["safe_mode"] is False for r in steps)
    assert all(r["action"] == "click" for r in steps)
    assert all(r["executed_touch"] is True for r in steps)
    assert len(touch.taps) == 3
    # No double-counting: 3 executed clicks == exactly 3 events in CTRGuard
    assert len(orch.ai.a1.ctr_guard._events) == 3
    assert steps[-1]["ctr_guard"]["hard_cap"] == pytest.approx(0.045)
    assert steps[-1]["ctr_guard"]["would_breach"] is False
    assert steps[-1]["ctr_guard"]["deferred"] is False

    # A2 still trips SAFE MODE immediately on genuine anomalous snapshot
    crit = asyncio.run(
        orch.run_step(
            touch=touch,
            capture=capture,
            device_id="live-dev-qa",
            domain="loanraaj.com",
            metrics_override={"rpm": 0.01, "ctr": 0.09, "empty_ad_rate": 0.70, "load_time_ms": 15000.0},
        )
    )
    assert crit["a2_severity"] == "CRITICAL"
    assert crit["safe_mode"] is True
    assert crit["executed_touch"] is False



