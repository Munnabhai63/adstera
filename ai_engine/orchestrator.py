"""orchestrator.py — AI Decision Engine Orchestrator.

Wires together:
  A4 (VisualAdDetector) → A2 (AnomalyDetector) → A1 (LinTSBandit)
  → Touch/Action → Reward logging.

Loop contract (AGENTS.md Phase 2 spec):
  1. Capture screenshot via capture.screenshot() (or simulate frame if capture is None or fails).
  2. A4 Detect: detection = self.a4.detect(frame, frame_meta).
  3. Metrics check with A2:
     - Query recent metrics (store or rolling window).
     - Build MetricsSnapshot.
     - anomaly_result = self.a2.check(snapshot).
     - If anomaly_result.severity == "CRITICAL": safe_mode.enter(...).
     - safe_mode.tick(is_clean=anomaly_result.ok).
  4. State assembly:
     - Build AgentState(domain_id, slot_type, time_of_day_h, recent_ctr, recent_rpm,
                        device_id_hash, session_age_s, bbox_confidence).
  5. A1 Decide:
     - If safe_mode.is_active(): decision = skip
     - Else: decision = self.a1.decide(state, detection, paper=self.paper_trading, device_id=device_id)
  6. Execute action:
     - If decision.action == "click" and touch is not None and not self.paper_trading:
         touch.tap(x, y)
         self.a1.record_click()
     - Elif decision.action == "paper_click":
         pass
     - If decision.action in ("click", "paper_click", "skip"):
         self.a1.record_impression()
  7. Reward update:
     - Estimate RPM and compute normalized reward:
       reward = (rpm / cfg.a1_linTS.reward_rpm_scale) - (0.1 if decision.action == "skip" else 0.0)
     - self.a1.update(arm_id, reward, state, device_id)
     - Log decision and reward to store.
  8. Return summary dict of the step.

CLI:
  python -m ai_engine.orchestrator --config ai_engine_config.yaml --paper --steps 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ai_engine.a1_linTS.bandit import LinTSBandit
from ai_engine.a2_anomaly.detector import AnomalyDetector
from ai_engine.a4_visual.detector import VisualAdDetector
from ai_engine.config import AIConfig, load_ai_config
from ai_engine.interfaces import (
    AdDecision,
    AgentState,
    AnomalyResult,
    DetectionResult,
    MetricsSnapshot,
    Phase1CaptureInterface,
    Phase1DeviceInterface,
    Phase1TouchInterface,
)
from ai_engine.safe_mode import SafeMode, SafeModeStateMachine
from ai_engine.store import AIStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 1 Mock / Fallback Stubs
# ---------------------------------------------------------------------------


class _MockCapture:
    """Fallback capture stub providing a 1x1 simulated PNG frame."""

    def screenshot(self) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
            b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
            b"\x00\x00IEND\xaeB`\x82"
        )

    def dump_ui(self) -> str:
        return '<hierarchy rotation="0"><node /></hierarchy>'


class _MockTouch:
    """Fallback touch stub logging tap and swipe events."""

    def tap(self, x: int, y: int, duration_ms: int = 100) -> None:
        logger.debug("[MockTouch] tap(%d, %d, %dms)", x, y, duration_ms)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        logger.debug("[MockTouch] swipe((%d, %d) -> (%d, %d), %dms)", x1, y1, x2, y2, duration_ms)


class _MockDevice:
    """Fallback device management stub."""

    def list_devices(self) -> Sequence[str]:
        return ["mock-device-0"]

    def is_alive(self, serial: str) -> bool:
        return True

    def get_device_info(self, serial: str) -> dict[str, Any]:
        return {"model": "mock", "android_version": "11", "resolution": "1080x1920"}


# ---------------------------------------------------------------------------
# Session Context
# ---------------------------------------------------------------------------


class SessionContext:
    """Tracks per-session counters and timings."""

    def __init__(self, device_id: str = "default_device", domain: str = "default") -> None:
        self.device_id = device_id
        self.domain = domain
        self.start_ts: float = time.time()
        self.session_id: str = f"sess_{int(self.start_ts)}_{uuid.uuid4().hex[:6]}"
        self.step_count: int = 0
        self.impression_count: int = 0
        self.click_count: int = 0
        self.last_rpm: float = 0.0

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.start_ts)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Coordinates A4 (Visual) -> A2 (Anomaly) -> A1 (LinTS) -> Touch/Action -> Reward."""

    def __init__(
        self,
        config_path: str = "ai_engine_config.yaml",
        paper_trading: bool = False,
        *,
        ai_config_path: Optional[str] = None,
        paper: Optional[bool] = None,
        config: Optional[Any] = None,
    ) -> None:
        """Initialise Orchestrator components.

        Args:
            config_path:    Path to ai_engine_config.yaml.
            paper_trading:  Whether decisions run in paper mode (no physical taps).
            ai_config_path: Alias for config_path.
            paper:          Alias for paper_trading.
            config:         Pre-loaded AIConfig instance if available.
        """
        cfg_path = ai_config_path or config_path
        if config is not None:
            self.config: AIConfig = config
        else:
            self.config = load_ai_config(cfg_path)

        # Handle paper trading flags and overrides
        if paper_trading or (paper is True):
            self.paper_trading = True
            self.config.ai_engine.paper_trading = True
        else:
            self.paper_trading = bool(getattr(self.config.ai_engine, "paper_trading", False))

        # Convenience aliases
        self.cfg = self.config
        self.paper = self.paper_trading

        # Logging configuration
        logging.basicConfig(
            level=getattr(logging, self.config.ai_engine.log_level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        # Ensure state directory exists
        Path(self.config.ai_engine.state_dir).mkdir(parents=True, exist_ok=True)

        self._running: bool = False
        self._start_time: float = time.time()
        self._session_id: str = f"sess_{int(self._start_time)}_{uuid.uuid4().hex[:6]}"
        self._step_count: int = 0

        # Component initialisation
        self._init_components()

    def _init_components(self) -> None:
        """Instantiate store, safe_mode, a2, a4, and a1."""
        db_path = self.config.ai_engine.db_path
        self.store = AIStore(db_path)

        safe_mode_cfg = self.config.a2_anomaly.safe_mode
        self.safe_mode = SafeModeStateMachine(
            safe_mode_cfg,
            store=self.store,
            state_dir=self.config.ai_engine.state_dir,
        )

        self.a2 = AnomalyDetector(
            self.config,
            store=self.store,
            safe_mode=self.safe_mode,
        )

        self.a4 = VisualAdDetector.from_config(self.config)

        self.a1 = LinTSBandit(self.config)
        try:
            self.a1.load_weights()
        except Exception as exc:
            logger.debug("Orchestrator bandit load_weights: %s", exc)
        self.ctr_guard = self.a1.ctr_guard

        logger.info(
            "Orchestrator initialised (paper_trading=%s, db=%s)",
            self.paper_trading,
            db_path,
        )

    # ------------------------------------------------------------------
    # Step Execution
    # ------------------------------------------------------------------

    def estimate_rpm(self, ctr: float = 0.02) -> float:
        """Estimate current RPM using baseline eCPM."""
        ecpm = 0.50
        return max(0.0, ctr * ecpm * 1000.0)

    async def run_step(
        self,
        touch: Optional[Phase1TouchInterface] = None,
        capture: Optional[Phase1CaptureInterface] = None,
        device_id: str = "default_device",
    ) -> dict[str, Any]:
        """Execute a single step in the orchestration loop.

        Steps:
            1. Capture screenshot (or simulate frame if capture is None or fails).
            2. A4 Detect: detection = self.a4.detect(frame, frame_meta).
            3. Metrics check with A2:
               - Query recent metrics & build MetricsSnapshot.
               - Check anomalies; if CRITICAL, safe_mode.enter(...).
               - safe_mode.tick(is_clean=anomaly_result.ok).
            4. State assembly: build AgentState.
            5. A1 Decide:
               - If safe_mode.is_active(), decision = skip.
               - Else, decision = self.a1.decide(...).
            6. Execute action:
               - If click and touch is not None and not paper_trading, tap bbox center.
               - record_click() and record_impression().
            7. Reward update:
               - Compute normalized reward and update LinTS bandit.
               - Log decision and reward to store.
            8. Return summary dict.

        Fail-safe: Any unhandled exception is caught, logged, triggers safe_mode.enter,
        and returns an error summary dict instead of crashing.
        """
        try:
            # 1. Capture screenshot
            frame: Optional[bytes] = None
            ui_tree: str = ""
            if capture is not None:
                try:
                    frame = capture.screenshot()
                except Exception as exc:
                    logger.warning("capture.screenshot failed: %s — using simulated frame", exc)
                    frame = None

                if hasattr(capture, "dump_ui"):
                    try:
                        ui_tree = capture.dump_ui() or ""
                    except Exception as exc:
                        logger.warning("capture.dump_ui failed: %s", exc)

            if not frame:
                # Simulated 1x1 PNG frame
                frame = (
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
                    b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
                    b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
                    b"\x00\x00IEND\xaeB`\x82"
                )

            frame_meta: dict[str, Any] = {"ui_tree": ui_tree} if ui_tree else {}

            # 2. A4 Detect
            detection: Optional[DetectionResult] = None
            try:
                detection = self.a4.detect(frame, frame_meta)
            except TypeError:
                try:
                    detection = self.a4.detect(frame)
                except Exception as exc:
                    logger.warning("A4 detect failed: %s", exc)
                    detection = DetectionResult(label="none", confidence=0.0, bbox=None, source="none")
            except Exception as exc:
                logger.warning("A4 detect failed: %s", exc)
                detection = DetectionResult(label="none", confidence=0.0, bbox=None, source="none")

            if detection is None:
                detection = DetectionResult(label="none", confidence=0.0, bbox=None, source="none")

            # 3. Metrics check with A2
            ctr = self.ctr_guard.current_ctr() if hasattr(self, "ctr_guard") and self.ctr_guard else 0.0
            rpm = self.estimate_rpm(ctr=ctr)

            snapshot = MetricsSnapshot(
                rpm=rpm,
                ctr=ctr,
                empty_ad_rate=0.0,
                load_time_ms=200.0,
                error_rate=0.0,
                repeated_creative_rate=0.0,
                domain="default",
                device_id=device_id,
            )

            anomaly_result: Optional[AnomalyResult] = None
            try:
                anomaly_result = self.a2.check(snapshot)
            except Exception as exc:
                logger.warning("A2 check failed: %s", exc)

            if anomaly_result is not None and anomaly_result.severity == "CRITICAL":
                reason_str = "; ".join(anomaly_result.reasons) if anomaly_result.reasons else "CRITICAL anomaly"
                self.safe_mode.enter(reason=reason_str)

            is_clean = anomaly_result.ok if anomaly_result else True
            self.safe_mode.tick(is_clean=is_clean)

            # 4. State assembly
            domain_id = hash("default") & 0x0FFFF
            slot_type = getattr(detection, "label", "none") or "none"
            time_of_day_h = time.gmtime().tm_hour
            device_id_hash = hash(device_id) & 0xFFFFFFFF
            session_age_s = max(0.0, time.time() - self._start_time)
            bbox_confidence = float(getattr(detection, "confidence", 0.0) or 0.0)

            state = AgentState(
                domain_id=domain_id,
                slot_type=slot_type,
                time_of_day_h=time_of_day_h,
                recent_ctr=ctr,
                recent_rpm=rpm,
                device_id_hash=device_id_hash,
                session_age_s=session_age_s,
                bbox_confidence=bbox_confidence,
            )

            # 5. A1 Decide
            if self.safe_mode.is_active():
                decision = AdDecision(
                    action="skip",
                    bbox=None,
                    slot_type="none",
                    domain="none",
                    timing_ms=0,
                    reason="SAFE MODE active - clicking suppressed",
                    decision_id=f"dec_safemode_{int(time.time() * 1000)}",
                )
            else:
                decision = self.a1.decide(
                    state,
                    detection,
                    paper=self.paper_trading,
                    device_id=device_id,
                )

            # 6. Execute action
            tapped = False
            tap_coords: Optional[Tuple[int, int]] = None

            if decision.action == "click" and touch is not None and not self.paper_trading:
                if decision.bbox:
                    x = decision.bbox[0] + decision.bbox[2] // 2
                    y = decision.bbox[1] + decision.bbox[3] // 2
                    try:
                        touch.tap(x, y)
                        tapped = True
                        tap_coords = (x, y)
                    except Exception as exc:
                        logger.warning("touch.tap(%d, %d) failed: %s", x, y, exc)
                self.a1.record_click()
            elif decision.action == "paper_click":
                # Log only, do NOT touch
                pass

            if decision.action in ("click", "paper_click", "skip"):
                self.a1.record_impression()

            # 7. Reward update
            scale = getattr(self.config.a1_linTS, "reward_rpm_scale", 1000.0) or 1000.0
            skip_penalty = 0.1 if decision.action == "skip" else 0.0
            reward = (rpm / scale) - skip_penalty

            arm_id = getattr(decision, "decision_id", decision.slot_type or "default")
            try:
                self.a1.update(arm_id, reward, state, device_id)
            except Exception as exc:
                logger.warning("A1 update failed: %s", exc)

            # Log to store
            try:
                dec_row_id = self.store.log_decision(
                    session_id=self._session_id,
                    device_id=device_id,
                    domain="default",
                    slot_type=decision.slot_type or "none",
                    action=decision.action,
                    bbox=decision.bbox,
                    reason=decision.reason,
                )
                self.store.log_reward(
                    decision_id=dec_row_id,
                    rpm=rpm,
                    ctr=ctr,
                    impressions=getattr(self.ctr_guard, "_impressions", 1) if hasattr(self, "ctr_guard") else 1,
                    reward_value=reward,
                )
            except Exception as exc:
                logger.warning("store logging failed: %s", exc)

            self._step_count += 1

            # 8. Return summary dict
            return {
                "step": self._step_count,
                "decision": decision,
                "action": decision.action,
                "reward": reward,
                "safe_mode": self.safe_mode.is_active(),
                "ctr": ctr,
                "rpm": rpm,
                "detection": detection,
                "tapped": tapped,
                "tap_coords": tap_coords,
                "device_id": device_id,
            }

        except Exception as exc:
            logger.exception("Fail-safe caught unhandled error in run_step: %s", exc)
            try:
                self.safe_mode.enter(reason=f"Internal error: {exc}")
            except Exception:
                pass
            return {
                "step": self._step_count,
                "error": str(exc),
                "safe_mode": self.safe_mode.is_active() if hasattr(self, "safe_mode") else True,
                "action": "error",
            }

    # ------------------------------------------------------------------
    # Loop Execution
    # ------------------------------------------------------------------

    async def run_loop(
        self,
        touch: Optional[Phase1TouchInterface] = None,
        capture: Optional[Phase1CaptureInterface] = None,
        device_id: str = "default",
        max_steps: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Run the orchestration loop until stopped or max_steps reached.

        Args:
            touch:      Optional touch interface implementation.
            capture:    Optional screen capture interface implementation.
            device_id:  Device identifier.
            max_steps:  Optional maximum steps to run before exiting.

        Returns:
            List of step summary dictionaries.
        """
        active_touch = touch or _MockTouch()
        active_capture = capture or _MockCapture()

        self._running = True
        results: list[dict[str, Any]] = []
        session_pace = 1.0  # seconds

        logger.info(
            "run_loop started (device=%s, paper_trading=%s, max_steps=%s)",
            device_id,
            self.paper_trading,
            max_steps,
        )

        try:
            while self._running:
                if max_steps is not None and self._step_count >= max_steps:
                    break

                step_res = await self.run_step(
                    touch=active_touch,
                    capture=active_capture,
                    device_id=device_id,
                )
                results.append(step_res)

                # Throttle session rate when in safe mode
                throttle = self.safe_mode.get_throttle_factor() if hasattr(self, "safe_mode") else 1.0
                delay = max(0.01, session_pace * throttle)
                await asyncio.sleep(delay)

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("run_loop interrupted")
        finally:
            self._save_state()

        logger.info("run_loop finished (%d steps executed)", len(results))
        return results

    def stop(self) -> None:
        """Signal the orchestration loop to stop."""
        logger.info("Orchestrator.stop() requested")
        self._running = False

    def _save_state(self) -> None:
        """Persist bandit weights to disk."""
        try:
            if hasattr(self.a1, "save_weights"):
                self.a1.save_weights()
                logger.info("Bandit weights persisted successfully")
        except Exception as exc:
            logger.warning("Failed to save bandit weights: %s", exc)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def _install_signals(orch: Orchestrator) -> None:
    def _sig_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %d — stopping orchestrator...", signum)
        orch.stop()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass


async def _async_main() -> None:
    parser = argparse.ArgumentParser(description="AI Engine Orchestrator CLI")
    parser.add_argument(
        "--config",
        default="ai_engine_config.yaml",
        help="Path to ai_engine_config.yaml (default: ai_engine_config.yaml)",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="Run in paper-trading mode (no real taps executed)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=5,
        help="Maximum number of steps to execute (default: 5)",
    )
    parser.add_argument(
        "--device",
        default="default_device",
        help="Device serial or name (default: default_device)",
    )
    args = parser.parse_args()

    orch = Orchestrator(config_path=args.config, paper_trading=args.paper)
    _install_signals(orch)

    logger.info("Running orchestrator for %d steps...", args.steps)
    results = await orch.run_loop(
        touch=_MockTouch(),
        capture=_MockCapture(),
        device_id=args.device,
        max_steps=args.steps,
    )
    print(f"Orchestrator completed {len(results)} steps successfully.")
    for res in results:
        print(f"  Step {res.get('step')}: action={res.get('action')}, reward={res.get('reward'):.4f}, safe_mode={res.get('safe_mode')}")


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
