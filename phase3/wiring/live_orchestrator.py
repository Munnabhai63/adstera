"""Phase 3 Live/Paper Orchestrator wiring Phase 1, Phase 2, and Phase 3 stores.

Loop contract:
    capture -> A4 detect -> A2 check (CRITICAL -> SAFE MODE) ->
    A1 decide (click only if A4 bbox verified AND A2 OK) ->
    (paper: log only | live: execute touch) ->
    reward update -> Phase3Store SQLite + JSON-lines logs with correlation IDs.

Safety defaults:
    - Default mode is ``--paper`` (decisions logged, NO real touch executed).
    - ``--live`` requires BOTH the explicit ``--live`` flag/parameter AND the
      environment variable configured in ``phase3/config.yaml``
      (``PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION``).
    - Without both gates satisfied, live execution is refused / safely kept in
      paper mode and zero touch actions are executed.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import random
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.interfaces import AgentState, MetricsSnapshot
from phase3.adapters.adsterra_feed import AdsterraFeedAdapter, load_dotenv_into_environ
from phase3.adapters.phase1_device import DeviceTouchCaptureBridge, Phase1DeviceAdapter
from phase3.adapters.phase2_ai import Phase2AIAdapter
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import (
    configure_json_logging,
    log_event,
    new_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger("phase3.wiring.live_orchestrator")

_SIMULATED_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
    b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


class LiveModeRefusedError(PermissionError):
    """Raised when ``--live`` is requested without valid env confirmation."""


def resolve_execution_mode(
    requested_live: bool,
    cfg: Phase3Config,
    *,
    strict: bool = False,
) -> Tuple[str, bool, str]:
    """Resolve effective ``(mode, paper, refusal_reason)`` safely.

    Returns:
        ``("live", False, "")`` only if ``requested_live`` is True AND
        ``cfg.is_live_confirmed()`` is True. Otherwise returns
        ``("paper", True, reason)``, or raises ``LiveModeRefusedError`` when
        ``strict=True`` and ``requested_live=True``.
    """
    if not requested_live:
        return "paper", True, ""

    if cfg.is_live_confirmed():
        return "live", False, ""

    env_var = cfg.phase3.live_confirm_env_var
    reason = (
        f"Live mode refused: missing or invalid environment confirmation "
        f"({env_var} must equal configured confirmation phrase). Staying in paper mode."
    )
    if strict:
        raise LiveModeRefusedError(reason)
    return "paper", True, reason


def _sample_click_point(
    bbox: Tuple[int, int, int, int],
    rng: random.Random,
) -> Tuple[int, int]:
    """Sample a human-like interior point (20-80% x, 25-75% y) inside *bbox*."""
    x, y, w, h = bbox
    fx = 0.20 + rng.random() * 0.60
    fy = 0.25 + rng.random() * 0.50
    px = max(x, min(x + max(1, w) - 1, int(x + fx * w)))
    py = max(y, min(y + max(1, h) - 1, int(y + fy * h)))
    return px, py


def build_device_bridge(
    cfg: Phase3Config,
    device_id: str,
    *,
    paper: bool,
    adb_path: str = "",
    device_adapter: Optional[Phase1DeviceAdapter] = None,
) -> Optional[DeviceTouchCaptureBridge]:
    """Wrap *device_id* in a :class:`DeviceTouchCaptureBridge` when attached over ADB."""
    if not device_id:
        return None
    adapter = device_adapter if device_adapter is not None else Phase1DeviceAdapter(cfg, adb_path=adb_path)
    try:
        if adapter.is_alive(device_id):
            return DeviceTouchCaptureBridge(adapter, device_id, paper=paper)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "device_bridge_probe_failed",
            device_id=device_id,
            error=str(exc),
        )
    return None


class Phase3LiveOrchestrator:
    """Async Phase 3 orchestrator with strict paper-mode default and fail-safe loop."""

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        config_path: Optional[str | Path] = None,
        live: bool = False,
        strict_live: bool = False,
        store: Optional[Phase3Store] = None,
        ai_adapter: Optional[Phase2AIAdapter] = None,
        adsterra_feed: Optional[AdsterraFeedAdapter] = None,
        device_adapter: Optional[Phase1DeviceAdapter] = None,
        adb_path: str = "",
        auto_device_bridge: bool = True,
        auto_load_env: Optional[bool] = None,
        env_path: Optional[str | Path] = None,
        seed: Optional[int] = None,
        state_dir: Optional[str | Path] = None,
    ) -> None:
        load_dotenv_into_environ(env_path, force=auto_load_env)
        self.cfg = cfg if cfg is not None else load_phase3_config(config_path)
        self.mode, self.paper, self.live_refused_reason = resolve_execution_mode(
            bool(live), self.cfg, strict=strict_live
        )

        self._seed = 42 if seed is None else int(seed)
        self._rng = random.Random(self._seed)
        self._running = False
        self._step_count = 0
        self._adb_path = adb_path
        self._auto_device_bridge = bool(auto_device_bridge)
        self._device_adapter = device_adapter
        self._device_bridges: Dict[str, DeviceTouchCaptureBridge] = {}

        resolved_state_dir = Path(state_dir) if state_dir is not None else Path(self.cfg.phase3.state_dir)
        resolved_state_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = resolved_state_dir

        db_path = self.cfg.phase3.db_path
        self.store = store if store is not None else Phase3Store(db_path)

        ai_state_dir = str(resolved_state_dir / "ai_engine")
        self.ai = (
            ai_adapter
            if ai_adapter is not None
            else Phase2AIAdapter(
                self.cfg,
                seed=self._seed,
                state_dir=ai_state_dir,
                db_path=str(Path(ai_state_dir) / "ai_phase2.db"),
                paper=self.paper,
            )
        )
        self.adsterra = adsterra_feed if adsterra_feed is not None else AdsterraFeedAdapter(self.cfg)
        if hasattr(self.ai, "a1") and hasattr(self.ai.a1, "load_weights"):
            try:
                self.ai.a1.load_weights()
            except Exception as exc:
                logger.debug("Phase3LiveOrchestrator bandit load_weights: %s", exc)

        if self.live_refused_reason:
            log_event(
                logger,
                logging.ERROR,
                "live_mode_refused",
                mode=self.mode,
                paper=self.paper,
                reason=self.live_refused_reason,
            )
        else:
            log_event(
                logger,
                logging.INFO,
                "phase3_orchestrator_initialized",
                mode=self.mode,
                paper=self.paper,
                db_path=str(self.store.db_path),
            )

    def stop(self) -> None:
        """Signal the orchestration loop to halt cleanly after the current step."""
        self._running = False
        log_event(logger, logging.INFO, "phase3_orchestrator_stop_requested")

    def _resolve_device_bridge(self, device_id: str) -> Optional[DeviceTouchCaptureBridge]:
        """Return a cached :class:`DeviceTouchCaptureBridge` when *device_id* is live on ADB."""
        if not self._auto_device_bridge or not device_id:
            return None
        cached = self._device_bridges.get(device_id)
        if cached is not None:
            return cached
        if self._device_adapter is None:
            self._device_adapter = Phase1DeviceAdapter(self.cfg, adb_path=self._adb_path)
        bridge = build_device_bridge(
            self.cfg,
            device_id,
            paper=self.paper,
            adb_path=self._adb_path,
            device_adapter=self._device_adapter,
        )
        if bridge is not None:
            self._device_bridges[device_id] = bridge
            log_event(
                logger,
                logging.INFO,
                "device_bridge_attached",
                device_id=device_id,
                paper=self.paper,
            )
        return bridge

    async def _fetch_metrics_snapshot(
        self,
        *,
        domain: str,
        device_id: str,
        load_time_ms: float = 250.0,
        error_rate: float = 0.0,
    ) -> MetricsSnapshot:
        """Assemble ``MetricsSnapshot`` from Adsterra feed + A1 CTR guard."""
        ctr_local = self.ai.current_ctr()
        ctr_guard = getattr(getattr(self.ai, "a1", None), "ctr_guard", None)
        guard_events = len(getattr(ctr_guard, "_events", ()))
        guard_min_samples = int(getattr(ctr_guard, "min_samples", 20))
        feed_metrics: Dict[str, Any] = {}
        try:
            feed_metrics = await self.adsterra.get_domain_metrics(domain)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "adsterra_metrics_fetch_failed",
                domain=domain,
                device_id=device_id,
                error=str(exc),
            )

        rpm = float(feed_metrics.get("rpm") or self.cfg.adsterra.default_ecpm_usd or 0.5)
        feed_ctr = float(feed_metrics.get("ctr") or 0.0)
        # Avoid tripping A2 on small-sample local CTR (e.g., 1/1 = 100%) before CTRGuard's
        # min_samples window fills; CTRGuard and A2 still evaluate every step.
        if guard_events >= guard_min_samples and ctr_local > 0:
            ctr = max(ctr_local, feed_ctr)
        else:
            ctr = feed_ctr
        return MetricsSnapshot(
            rpm=rpm,
            ctr=ctr,
            empty_ad_rate=0.0,
            load_time_ms=float(load_time_ms),
            error_rate=float(error_rate),
            repeated_creative_rate=0.0,
            domain=domain,
            device_id=device_id,
        )

    async def run_step(
        self,
        *,
        touch: Optional[Any] = None,
        capture: Optional[Any] = None,
        device_id: str = "device-0",
        domain: str = "default",
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        ip_address: str = "",
        subnet_24: str = "",
        subnet_20: str = "",
        session_age_s: float = 30.0,
        metrics_override: Optional[MetricsSnapshot | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute one full capture -> A4 -> A2 -> A1 -> (paper|live) -> reward -> log step."""
        cid = correlation_id or new_correlation_id("p3")
        sid = session_id or f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        tok = set_correlation_id(cid)
        step_start = time.time()

        try:
            self.store.start_session(
                session_id=sid,
                correlation_id=cid,
                device_id=device_id,
                mode=self.mode,
                domain=domain,
                ip_address=ip_address,
                subnet_24=subnet_24,
                subnet_20=subnet_20,
                started_at=step_start,
            )

            # 1. Capture screen + UI tree (prefer real DeviceTouchCaptureBridge when attached)
            if capture is None:
                auto_bridge = self._resolve_device_bridge(device_id)
                if auto_bridge is not None:
                    capture = auto_bridge
                    if touch is None:
                        touch = auto_bridge

            frame: Optional[bytes] = None
            ui_tree: str = ""
            capture_source = "simulated"
            if capture is not None:
                capture_source = (
                    "device_bridge" if isinstance(capture, DeviceTouchCaptureBridge) else "custom"
                )
                raw_frame = capture.screenshot()
                if asyncio.iscoroutine(raw_frame):
                    raw_frame = await raw_frame
                frame = raw_frame
                if not frame:
                    from phase3.adapters.phase1_device import DeviceDisconnectedError

                    raise DeviceDisconnectedError(
                        f"Empty frame captured from device '{device_id}'"
                    )
                if hasattr(capture, "dump_ui"):
                    raw_ui = capture.dump_ui()
                    if asyncio.iscoroutine(raw_ui):
                        raw_ui = await raw_ui
                    ui_tree = raw_ui or ""
            else:
                frame = _SIMULATED_1X1_PNG

            if capture_source != "simulated" and frame == _SIMULATED_1X1_PNG:
                capture_source = "simulated_fallback"

            frame_meta: Dict[str, Any] = {"ui_tree": ui_tree, "page_source": ui_tree} if ui_tree else {}

            # 2. A4 visual / rule detection
            det_info = self.ai.detect_ads(frame, frame_meta, ui_tree=ui_tree or None)
            a4_verified = bool(det_info.get("verified", False))
            a4_bbox = det_info.get("bbox")
            a4_conf = float(det_info.get("confidence", 0.0))
            a4_source = str(det_info.get("source", "none"))
            slot_type = str(det_info.get("label", "none"))

            # 3. A2 anomaly check
            if metrics_override is not None:
                if isinstance(metrics_override, dict):
                    snapshot = MetricsSnapshot(
                        rpm=float(metrics_override.get("rpm", 1.0)),
                        ctr=float(metrics_override.get("ctr", 0.02)),
                        empty_ad_rate=float(metrics_override.get("empty_ad_rate", 0.0)),
                        load_time_ms=float(metrics_override.get("load_time_ms", 250.0)),
                        error_rate=float(metrics_override.get("error_rate", 0.0)),
                        repeated_creative_rate=float(metrics_override.get("repeated_creative_rate", 0.0)),
                        domain=domain,
                        device_id=device_id,
                    )
                else:
                    snapshot = metrics_override
            else:
                snapshot = await self._fetch_metrics_snapshot(domain=domain, device_id=device_id)

            anomaly = self.ai.check_anomaly(snapshot)
            a2_ok = bool(anomaly.ok) and (anomaly.severity != "CRITICAL") and (not self.ai.is_safe_mode())

            # 4. Assemble AgentState
            dom_hash = int(hashlib.sha256(domain.encode("utf-8")).hexdigest()[:8], 16) & 0xFFFF
            dev_hash = int(hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:8], 16)
            state = AgentState(
                domain_id=dom_hash,
                slot_type=slot_type,
                time_of_day_h=time.gmtime().tm_hour,
                recent_ctr=float(snapshot.ctr),
                recent_rpm=float(snapshot.rpm),
                device_id_hash=dev_hash,
                session_age_s=float(session_age_s),
                bbox_confidence=a4_conf,
            )

            # 5. A1 decision (strictly gated by A4 bbox, A2 OK, SafeMode, and paper/live mode)
            decision = self.ai.decide_action(
                state,
                det_info,
                paper=self.paper,
                device_id=device_id,
                a2_ok=a2_ok,
            )

            # 6. Execute action (ONLY in live mode when confirmed + A4 bbox verified + A2 OK + SafeMode off)
            executed_touch = False
            tap_coords: Optional[Tuple[int, int]] = None

            if (
                not self.paper
                and self.mode == "live"
                and self.cfg.is_live_confirmed()
                and decision.action == "click"
                and a4_verified
                and a4_bbox is not None
                and a2_ok
                and not self.ai.is_safe_mode()
                and touch is not None
            ):
                px, py = _sample_click_point(a4_bbox, self._rng)
                tap_res = touch.tap(px, py)
                if asyncio.iscoroutine(tap_res):
                    await tap_res
                executed_touch = True
                tap_coords = (px, py)
                self.ai.record_click()
            elif decision.action == "click" and self.paper:
                # Defensive safeguard: paper mode can never emit a real click
                decision.action = "paper_click"

            if not executed_touch and decision.action in ("click", "paper_click", "skip"):
                self.ai.record_impression()

            # 7. Reward update
            rpm_scale = float(getattr(self.ai.ai_cfg.a1_linTS, "reward_rpm_scale", 1000.0) or 1000.0)
            skip_penalty = 0.1 if decision.action == "skip" else 0.0
            reward = (float(snapshot.rpm) / rpm_scale) - skip_penalty
            arm_id = getattr(decision, "decision_id", "") or slot_type
            self.ai.update_reward(arm_id, reward, state=state, device_id=device_id)

            # 8. Log to Phase3Store SQLite + JSON lines with correlation ID
            safe_mode_active = self.ai.is_safe_mode()
            self.store.log_decision_reward(
                session_id=sid,
                correlation_id=cid,
                device_id=device_id,
                domain=domain,
                slot_type=decision.slot_type or slot_type,
                action=decision.action,
                executed_touch=executed_touch,
                bbox=decision.bbox or a4_bbox,
                a4_source=a4_source,
                a4_confidence=a4_conf,
                a2_severity=anomaly.severity,
                safe_mode=safe_mode_active,
                rpm=float(snapshot.rpm),
                ctr=float(snapshot.ctr),
                reward_value=float(reward),
                reason=decision.reason,
            )
            self.store.finish_session(
                sid,
                status="completed",
                dwell_seconds=max(0.0, time.time() - step_start),
            )

            self._step_count += 1
            log_event(
                logger,
                logging.INFO,
                "phase3_step_completed",
                correlation_id=cid,
                session_id=sid,
                device_id=device_id,
                domain=domain,
                mode=self.mode,
                capture_source=capture_source,
                frame_bytes=len(frame),
                action=decision.action,
                executed_touch=executed_touch,
                tap_coords=list(tap_coords) if tap_coords else None,
                a4_verified=a4_verified,
                a4_source=a4_source,
                a4_confidence=round(a4_conf, 4),
                a2_severity=anomaly.severity,
                safe_mode=safe_mode_active,
                reward=round(reward, 6),
                step=self._step_count,
            )

            ctr_guard = getattr(getattr(self.ai, "a1", None), "ctr_guard", None)
            ctr_guard_telemetry = (
                {
                    "hard_cap": float(getattr(ctr_guard, "hard_cap", 0.045)),
                    "soft_cap": float(getattr(ctr_guard, "soft_cap", 0.036)),
                    "min_samples": int(getattr(ctr_guard, "min_samples", 20)),
                    "sample_count": len(getattr(ctr_guard, "_events", ())),
                    "local_ctr": round(float(ctr_guard.current_ctr()), 6),
                    "would_breach": bool(ctr_guard.would_breach()),
                    "deferred": bool(ctr_guard.is_deferred()),
                }
                if ctr_guard is not None
                else {}
            )

            return {
                "step": self._step_count,
                "session_id": sid,
                "correlation_id": cid,
                "mode": self.mode,
                "paper": self.paper,
                "capture_source": capture_source,
                "frame_bytes": len(frame),
                "action": decision.action,
                "executed_touch": executed_touch,
                "tap_coords": tap_coords,
                "bbox": decision.bbox or a4_bbox,
                "a4_verified": a4_verified,
                "a4_source": a4_source,
                "a4_confidence": a4_conf,
                "a2_severity": anomaly.severity,
                "a2_ok": a2_ok,
                "safe_mode": safe_mode_active,
                "ctr_guard": ctr_guard_telemetry,
                "reward": reward,
                "rpm": float(snapshot.rpm),
                "ctr": float(snapshot.ctr),
                "error": "",
            }

        except Exception as exc:
            # Fail-safe: never crash; enter SAFE MODE, persist degraded state, and log JSON
            try:
                self.ai.enter_safe_mode(reason=f"step_exception: {exc}")
            except Exception:
                pass
            try:
                self.store.log_decision_reward(
                    session_id=sid,
                    correlation_id=cid,
                    device_id=device_id,
                    domain=domain,
                    slot_type="none",
                    action="skip",
                    executed_touch=False,
                    bbox=None,
                    a4_source="none",
                    a4_confidence=0.0,
                    a2_severity="CRITICAL",
                    safe_mode=True,
                    rpm=0.0,
                    ctr=0.0,
                    reward_value=0.0,
                    reason=f"fail_safe_exception: {exc}",
                )
                self.store.finish_session(
                    sid,
                    status="degraded",
                    dwell_seconds=max(0.0, time.time() - step_start),
                    error=str(exc),
                )
            except Exception:
                pass

            log_event(
                logger,
                logging.ERROR,
                "phase3_step_failsafe",
                correlation_id=cid,
                session_id=sid,
                device_id=device_id,
                domain=domain,
                mode=self.mode,
                safe_mode=True,
                error=str(exc),
            )
            self._step_count += 1
            return {
                "step": self._step_count,
                "session_id": sid,
                "correlation_id": cid,
                "mode": self.mode,
                "paper": self.paper,
                "action": "skip",
                "executed_touch": False,
                "tap_coords": None,
                "bbox": None,
                "a4_verified": False,
                "a4_confidence": 0.0,
                "a2_severity": "CRITICAL",
                "a2_ok": False,
                "safe_mode": True,
                "reward": 0.0,
                "error": str(exc),
            }
        finally:
            try:
                from phase3.logging_utils import _CORRELATION_ID

                _CORRELATION_ID.reset(tok)
            except Exception:
                pass

    async def run_loop(
        self,
        *,
        touch: Optional[Any] = None,
        capture: Optional[Any] = None,
        device_id: str = "device-0",
        domain: str = "default",
        max_steps: int = 5,
        step_delay_s: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """Run bounded async orchestration loop until ``max_steps`` or ``stop()``."""
        self._running = True
        results: List[Dict[str, Any]] = []
        try:
            for _ in range(max(0, int(max_steps))):
                if not self._running:
                    break
                res = await self.run_step(
                    touch=touch,
                    capture=capture,
                    device_id=device_id,
                    domain=domain,
                )
                results.append(res)
                throttle = max(0.05, float(self.ai.get_throttle_factor()))
                delay = max(0.0, float(step_delay_s) / throttle) if throttle > 0 else float(step_delay_s)
                if delay > 0:
                    await asyncio.sleep(min(delay, 2.0))
        finally:
            self._running = False
            try:
                self.ai.save_weights(device_id=device_id)
            except Exception as exc:
                log_event(logger, logging.WARNING, "phase3_save_weights_failed", error=str(exc))
        return results


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 3 Live/Paper Orchestrator (paper mode is the safe default)."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to phase3/config.yaml (defaults to package config.yaml)",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--paper",
        action="store_true",
        help="Run in paper mode: log decisions only, NO real touches executed (default).",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Request live mode (requires PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION).",
    )
    parser.add_argument("--steps", type=int, default=5, help="Number of steps to run (default: 5)")
    parser.add_argument("--device", default="paper-device-0", help="Target device identifier")
    parser.add_argument("--domain", default="default", help="Target publisher domain")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    parser.add_argument("--adb-path", default="", help="Optional path to adb binary")
    parser.add_argument(
        "--require-device",
        action="store_true",
        help="Fail with exit code 3 if the target --device is not connected over ADB.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point returning process exit code."""
    load_dotenv_into_environ()
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    cfg = load_phase3_config(args.config)
    configure_json_logging(level=cfg.phase3.log_level)

    requested_live = bool(args.live)
    if requested_live and not cfg.is_live_confirmed():
        _, _, refusal = resolve_execution_mode(True, cfg, strict=False)
        log_event(logger, logging.ERROR, "cli_live_mode_refused", reason=refusal)
        print(f"ERROR: {refusal}", file=sys.stderr)
        return 2

    orch = Phase3LiveOrchestrator(
        cfg=cfg,
        live=requested_live,
        strict_live=requested_live,
        adb_path=args.adb_path,
        seed=args.seed,
    )

    bridge = build_device_bridge(
        cfg,
        args.device,
        paper=orch.paper,
        adb_path=args.adb_path,
    )
    if bridge is None:
        if args.require_device:
            log_event(
                logger,
                logging.ERROR,
                "cli_device_bridge_required_missing",
                device_id=args.device,
            )
            print(f"ERROR: ADB device '{args.device}' is not attached.", file=sys.stderr)
            return 3
        log_event(
            logger,
            logging.WARNING,
            "cli_device_bridge_unavailable",
            device_id=args.device,
            fallback="simulated_1x1_png",
        )
    else:
        log_event(
            logger,
            logging.INFO,
            "cli_device_bridge_attached",
            device_id=args.device,
            paper=orch.paper,
        )

    def _handle_sig(signum: int, _frame: Any) -> None:
        log_event(logger, logging.INFO, "cli_signal_received", signum=signum)
        orch.stop()

    try:
        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)
    except (ValueError, AttributeError):
        pass

    results = asyncio.run(
        orch.run_loop(
            touch=bridge,
            capture=bridge,
            device_id=args.device,
            domain=args.domain,
            max_steps=args.steps,
        )
    )
    log_event(
        logger,
        logging.INFO,
        "cli_orchestrator_finished",
        mode=orch.mode,
        steps=len(results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
