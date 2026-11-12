"""Phase 2 AI engine adapter wrapping A1 (LinTS), A2 (Anomaly), A4 (Visual), and SafeMode.

Synchronizes Phase 3 safety parameters from ``phase3/config.yaml`` into the
Phase 2 ``AIConfig`` without modifying any Phase 2 files.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ai_engine.a1_linTS.bandit import LinTSBandit
from ai_engine.a2_anomaly.detector import AnomalyDetector
from ai_engine.a4_visual.detector import VisualAdDetector
from ai_engine.config import AIConfig, load_ai_config
from ai_engine.interfaces import AdDecision, AgentState, AnomalyResult, DetectionResult, MetricsSnapshot
from ai_engine.safe_mode import SafeModeStateMachine
from ai_engine.store import AIStore
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.adapters.phase2_ai")


class Phase2AIAdapter:
    """Unified adapter around Phase 2 A4 -> A2 -> A1 -> SafeMode pipeline."""

    def __init__(
        self,
        phase3_cfg: Optional[Phase3Config] = None,
        ai_cfg: Optional[AIConfig] = None,
        *,
        seed: Optional[int] = None,
        state_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        paper: bool = True,
    ) -> None:
        self.phase3_cfg = phase3_cfg or load_phase3_config()
        # ASSUMPTION: ai_engine.config.load_ai_config returns an AIConfig dataclass.
        self.ai_cfg = ai_cfg or load_ai_config(self.phase3_cfg.phase3.ai_engine_config)
        self._sync_safety_config(paper=paper)

        resolved_state_dir = state_dir or str(Path(self.phase3_cfg.phase3.state_dir) / "ai_engine")
        Path(resolved_state_dir).mkdir(parents=True, exist_ok=True)
        self.ai_cfg.ai_engine.state_dir = resolved_state_dir

        resolved_db = db_path or str(Path(resolved_state_dir) / "ai_phase2.db")
        Path(resolved_db).parent.mkdir(parents=True, exist_ok=True)
        self.ai_cfg.ai_engine.db_path = resolved_db

        # ASSUMPTION: AIStore, SafeModeStateMachine, AnomalyDetector, VisualAdDetector,
        # and LinTSBandit accept AIConfig / sub-configs as documented in ai_engine/.
        self.store = AIStore(resolved_db)
        self.safe_mode = SafeModeStateMachine(
            self.ai_cfg.a2_anomaly.safe_mode,
            store=self.store,
            state_dir=resolved_state_dir,
        )
        self.a2 = AnomalyDetector(self.ai_cfg, store=self.store, safe_mode=self.safe_mode)
        self.a4 = VisualAdDetector.from_config(self.ai_cfg)
        self.a1 = LinTSBandit(self.ai_cfg, seed=seed)
        try:
            self.a1.load_weights()
        except Exception as exc:
            logger.debug("Phase2AIAdapter bandit load_weights: %s", exc)

    def _sync_safety_config(self, *, paper: bool) -> None:
        safety = self.phase3_cfg.safety
        self.ai_cfg.ai_engine.paper_trading = bool(paper)
        self.ai_cfg.ctr_guard.hard_cap = float(safety.aggregate_ctr_hard_cap)
        self.ai_cfg.ctr_guard.soft_cap = float(safety.aggregate_ctr_soft_cap)
        self.ai_cfg.ctr_guard.window_size = int(safety.ctr_window_size)
        self.ai_cfg.a2_anomaly.z_threshold = float(safety.anomaly_z_threshold)
        self.ai_cfg.a2_anomaly.safe_mode.throttle_session_rate = float(safety.safe_mode_throttle_factor)
        self.ai_cfg.a2_anomaly.safe_mode.exit_clean_windows = int(safety.safe_mode_exit_clean_windows)

    def detect_ads(
        self,
        frame: Optional[bytes],
        frame_meta: Optional[Dict[str, Any]] = None,
        ui_tree: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run A4 visual/rule detection and normalize to a standard dict."""
        meta = dict(frame_meta or {})
        if ui_tree and "ui_tree" not in meta and "page_source" not in meta:
            meta["ui_tree"] = ui_tree
            meta["page_source"] = ui_tree

        try:
            # ASSUMPTION: VisualAdDetector.detect accepts (frame, frame_meta, ui_tree).
            raw = self.a4.detect(frame, meta, ui_tree=ui_tree)
        except TypeError:
            raw = self.a4.detect(frame, meta)
        except Exception as exc:
            log_event(logger, logging.WARNING, "a4_detect_failed", error=str(exc))
            return {
                "raw": DetectionResult(label="none", confidence=0.0, bbox=None, source="none"),
                "label": "none",
                "confidence": 0.0,
                "bbox": None,
                "source": "none",
                "verified": False,
            }

        if raw is None:
            raw = DetectionResult(label="none", confidence=0.0, bbox=None, source="none")

        bbox = getattr(raw, "bbox", None)
        label = str(getattr(raw, "label", "none") or "none")
        confidence = float(getattr(raw, "confidence", 0.0) or 0.0)
        source = str(getattr(raw, "source", "none") or "none")
        threshold = float(getattr(self.ai_cfg.a4_visual, "confidence_threshold", 0.55))

        valid_bbox = (
            isinstance(bbox, (tuple, list))
            and len(bbox) == 4
            and int(bbox[2]) > 0
            and int(bbox[3]) > 0
        )
        normalized_bbox: Optional[Tuple[int, int, int, int]] = (
            (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])) if valid_bbox else None
        )
        verified = bool(
            normalized_bbox is not None
            and label != "none"
            and confidence >= threshold
        )
        return {
            "raw": raw,
            "label": label,
            "confidence": confidence,
            "bbox": normalized_bbox,
            "source": source,
            "verified": verified,
        }

    def check_anomaly(self, snapshot: MetricsSnapshot | Dict[str, Any]) -> AnomalyResult:
        """Evaluate *snapshot* with A2 and update SafeMode state machine."""
        if isinstance(snapshot, dict):
            snap = MetricsSnapshot(
                rpm=float(snapshot.get("rpm", 1.0)),
                ctr=float(snapshot.get("ctr", 0.02)),
                empty_ad_rate=float(snapshot.get("empty_ad_rate", 0.0)),
                load_time_ms=float(snapshot.get("load_time_ms", 250.0)),
                error_rate=float(snapshot.get("error_rate", 0.0)),
                repeated_creative_rate=float(snapshot.get("repeated_creative_rate", 0.0)),
                domain=str(snapshot.get("domain", "")),
                device_id=str(snapshot.get("device_id", "")),
            )
        else:
            snap = snapshot

        try:
            result = self.a2.check(snap)
            if result.severity == "CRITICAL":
                reason = "; ".join(result.reasons) if result.reasons else "CRITICAL anomaly"
                self.safe_mode.enter(reason=reason)
            self.safe_mode.tick(is_clean=bool(result.ok))
            if result.ok:
                self.a2.update_baseline(snap)
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "a2_check_failed", error=str(exc))
            self.safe_mode.enter(reason=f"A2 check exception: {exc}")
            return AnomalyResult(
                ok=False,
                severity="CRITICAL",
                reasons=[f"A2 check exception: {exc}"],
                metrics=snap,
            )

    def decide_action(
        self,
        state: AgentState,
        detection_info: Dict[str, Any] | Any,
        *,
        paper: bool = True,
        device_id: str = "",
        a2_ok: bool = True,
    ) -> AdDecision:
        """Produce a safety-gated A1 decision.

        Enforces:
        - SafeMode active -> ``skip``
        - ``safety.require_a2_ok_for_gesture`` and ``not a2_ok`` -> ``skip``
        - ``safety.require_a4_bbox_for_gesture`` and unverified A4 bbox -> ``skip``
        - ``paper=True`` -> never returns ``click`` (only ``paper_click``, ``skip``, or ``defer``)
        """
        if self.safe_mode.is_active():
            return AdDecision(
                action="skip",
                bbox=None,
                slot_type="none",
                domain="none",
                timing_ms=0,
                reason="SAFE MODE active - clicking suppressed",
                decision_id=f"dec_safemode_{int(time.time() * 1000)}",
            )

        if self.phase3_cfg.safety.require_a2_ok_for_gesture and not a2_ok:
            return AdDecision(
                action="skip",
                bbox=None,
                slot_type="none",
                domain="none",
                timing_ms=0,
                reason="A2 check not OK - gesture suppressed",
                decision_id=f"dec_a2_blocked_{int(time.time() * 1000)}",
            )

        if isinstance(detection_info, dict):
            raw_det = detection_info.get("raw")
            a4_verified = bool(detection_info.get("verified", False))
            det_bbox = detection_info.get("bbox")
            det_label = str(detection_info.get("label", "none"))
            det_conf = float(detection_info.get("confidence", 0.0))
        else:
            raw_det = detection_info
            det_bbox = getattr(detection_info, "bbox", None)
            det_label = str(getattr(detection_info, "label", "none") or "none")
            det_conf = float(getattr(detection_info, "confidence", 0.0) or 0.0)
            threshold = float(getattr(self.ai_cfg.a4_visual, "confidence_threshold", 0.55))
            a4_verified = bool(det_bbox is not None and det_label != "none" and det_conf >= threshold)

        if self.phase3_cfg.safety.require_a4_bbox_for_gesture and not a4_verified:
            return AdDecision(
                action="skip",
                bbox=None,
                slot_type=det_label,
                domain="default",
                timing_ms=0,
                reason="A4 bbox not verified - gesture suppressed",
                decision_id=f"dec_nobbox_{int(time.time() * 1000)}",
            )

        det_arg = raw_det if raw_det is not None else DetectionResult(
            label=det_label,
            confidence=det_conf,
            bbox=det_bbox,
            source="rule_fallback",
        )
        decision = self.a1.decide(state, det_arg, paper=bool(paper), device_id=device_id)
        if paper and decision.action == "click":
            decision.action = "paper_click"
        return decision

    def update_reward(
        self,
        arm_id: str,
        reward: float,
        state: Optional[AgentState] = None,
        device_id: str = "",
    ) -> None:
        self.a1.update(arm_id, float(reward), state=state, device_id=device_id)

    def record_impression(self) -> None:
        self.a1.record_impression()

    def record_click(self) -> None:
        self.a1.record_click()

    def current_ctr(self) -> float:
        return float(self.a1.ctr_guard.current_ctr())

    def is_safe_mode(self) -> bool:
        return bool(self.safe_mode.is_active())

    def enter_safe_mode(self, reason: str) -> None:
        self.safe_mode.enter(reason=reason)

    def exit_safe_mode(self, reason: str) -> None:
        self.safe_mode.exit(reason=reason)

    def get_throttle_factor(self) -> float:
        return float(self.safe_mode.get_throttle_factor())

    def save_weights(self, device_id: str = "") -> None:
        self.a1.save_weights(device_id=device_id)
