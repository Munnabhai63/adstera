"""
bandit.py — Linear Thompson Sampling (LinTS) Contextual Bandit for Phase 2.

Manages contextual decision-making for ad interaction (click vs skip vs defer)
with Bayesian parameter sampling, exploration-exploitation trade-off,
safety caps via CTRGuard, and atomic weight persistence.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

import numpy as np

from ai_engine.a1_linTS.ctr_guard import CTRGuard
from ai_engine.a1_linTS.persistence import WeightStore
from ai_engine.a1_linTS.state_encoder import encode
from ai_engine.interfaces import AdDecision, AgentState

logger = logging.getLogger(__name__)


class StateEncoder:
    """Wrapper class around state_encoder.encode."""

    def __init__(self, config: Optional[Any] = None) -> None:
        self.config = config
        self.n_features = getattr(config, "n_features", 8) if config else 8
        self.rpm_scale = (
            getattr(config, "reward_rpm_scale", 1000.0) if config else 1000.0
        )

    def encode(
        self,
        state: Any,
        n_features: Optional[int] = None,
        rpm_scale: Optional[float] = None,
    ) -> np.ndarray:
        nf = n_features if n_features is not None else self.n_features
        rs = rpm_scale if rpm_scale is not None else self.rpm_scale
        return encode(state, n_features=nf, rpm_scale=rs)


class LinTSBandit:
    """Linear Thompson Sampling Contextual Bandit.

    Maintains per-arm precision matrix A and reward vector b.
    Samples theta ~ N(A^-1 @ b, alpha^2 * A^-1) and selects arm maximising theta^T @ x.
    """

    def __init__(self, config: Optional[Any] = None, seed: Optional[int] = None) -> None:
        """Initialise LinTSBandit.

        Args:
            config: Root AIConfig or a1_linTS config.
            seed:   Optional integer seed for numpy random generator.
        """
        from ai_engine.config import load_ai_config

        if config is None:
            self.cfg = load_ai_config(None)
        elif hasattr(config, "a1_linTS"):
            self.cfg = config
        else:
            # Maybe passed A1LinTSConfig directly
            self.cfg = load_ai_config(None)
            self.cfg.a1_linTS = config

        a1_cfg = self.cfg.a1_linTS
        self.alpha: float = getattr(a1_cfg, "alpha", 1.0)
        self.lambda_reg: float = getattr(a1_cfg, "lambda_reg", 1.0)
        self.n_features: int = getattr(a1_cfg, "n_features", 8)
        self.persist_every_n: int = getattr(a1_cfg, "persist_every_n", 10)

        # Build arms list: slot arms + (domain, slot) pairs
        domain_arms: list[str] = getattr(a1_cfg, "domain_arms", []) or ["default"]
        slot_arms: list[str] = getattr(
            a1_cfg,
            "ad_slot_arms",
            ["banner", "interstitial", "popunder", "native", "none"],
        )

        self._arms: list[str] = []
        # Priority slot arms first
        for s in slot_arms:
            if s not in self._arms:
                self._arms.append(s)

        # Domain composite arms
        for d in domain_arms:
            for s in slot_arms:
                arm_id = f"{d}:{s}"
                if arm_id not in self._arms:
                    self._arms.append(arm_id)

        # Seeded RNG
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        # Initialize CTRGuard
        self._ctr_guard = CTRGuard(getattr(self.cfg, "ctr_guard", None))

        # Initialize WeightStore
        state_dir = getattr(getattr(self.cfg, "ai_engine", None), "state_dir", "state/ai_engine")
        self.weights_dir = Path(state_dir) / "weights"
        self.weight_store = WeightStore(store_dir=self.weights_dir)

        # State encoder
        self.encoder = StateEncoder(a1_cfg)

        # Per-arm weights dictionary: {f"{arm}:A": np.ndarray, f"{arm}:b": np.ndarray}
        self._weights: dict[str, np.ndarray] = {}
        self._init_weights()

        # Decision cache: decision_id -> (arm_id, state, x)
        self._decision_cache: dict[str, Tuple[str, Any, np.ndarray]] = {}
        self._last_state: Optional[Any] = None
        self._last_x: Optional[np.ndarray] = None
        self._last_arm: str = self._arms[0]
        self._step_count: int = 0

    @property
    def ctr_guard(self) -> CTRGuard:
        """Return the attached CTRGuard instance."""
        return self._ctr_guard

    def _init_weights(self) -> None:
        """Initialize prior precision matrices and reward vectors for all arms."""
        for arm in self._arms:
            A = self.lambda_reg * np.eye(self.n_features, dtype=np.float64)
            b = np.zeros(self.n_features, dtype=np.float64)
            self._weights[f"{arm}:A"] = A
            self._weights[f"{arm}:b"] = b

    def record_click(self) -> None:
        """Delegate click recording to CTRGuard."""
        self._ctr_guard.record_click()

    def record_impression(self) -> None:
        """Delegate impression recording to CTRGuard."""
        self._ctr_guard.record_impression()

    def decide(
        self,
        state: AgentState,
        detection: Any = None,
        paper: bool = False,
        device_id: str = "",
    ) -> AdDecision:
        """Produce an ad action decision given current agent state and visual detection.

        Args:
            state:      Current AgentState.
            detection:  Optional DetectionResult from A4.
            paper:      When True, returns 'paper_click' instead of 'click'.
            device_id:  ADB device serial.

        Returns:
            AdDecision instance.
        """
        hard_cap = getattr(self.cfg.ctr_guard, "hard_cap", 0.045)
        defer_sec = getattr(self.cfg.ctr_guard, "defer_seconds", 30.0)

        # 1. Check CTR Guard
        if self._ctr_guard.is_deferred() or self._ctr_guard.would_breach(hard_cap):
            if not self._ctr_guard.is_deferred():
                self._ctr_guard.set_defer(defer_sec)
            dec_id = f"dec_defer_{int(time.time() * 1000)}"
            return AdDecision(
                action="defer",
                bbox=None,
                slot_type="",
                domain="",
                timing_ms=int(defer_sec * 1000),
                reason="CTR guard limit reached or deferred",
                decision_id=dec_id,
            )

        # 2. Encode state vector x
        x = self.encoder.encode(state, n_features=self.n_features)
        self._last_state = state
        self._last_x = x

        # 3. Filter candidate arms based on visual detection
        det_label = getattr(detection, "label", "none") or "none"
        det_bbox = getattr(detection, "bbox", None)
        det_conf = getattr(detection, "confidence", 0.0)
        min_conf = getattr(getattr(self.cfg, "a4_visual", None), "confidence_threshold", 0.55)

        candidates: list[str] = []
        if det_label and det_label != "none":
            for arm in self._arms:
                if arm == det_label or arm.endswith(f":{det_label}"):
                    candidates.append(arm)

        if not candidates:
            candidates = list(self._arms)

        # 4. Linear Thompson Sampling: sample theta for candidates
        best_arm = candidates[0]
        best_score = -float("inf")

        for arm in candidates:
            A_key = f"{arm}:A"
            b_key = f"{arm}:b"
            if A_key not in self._weights:
                self._weights[A_key] = self.lambda_reg * np.eye(self.n_features, dtype=np.float64)
                self._weights[b_key] = np.zeros(self.n_features, dtype=np.float64)

            A = self._weights[A_key]
            b = self._weights[b_key]

            try:
                A_inv = np.linalg.pinv(A)
            except Exception:
                A_inv = np.linalg.inv(A + 1e-4 * np.eye(self.n_features))

            mu = A_inv @ b
            cov = (self.alpha ** 2) * A_inv
            # Enforce symmetry and positive-definiteness
            cov = 0.5 * (cov + cov.T) + 1e-6 * np.eye(self.n_features)

            try:
                theta = self.rng.multivariate_normal(mu, cov)
            except Exception:
                theta = mu

            score = float(np.dot(theta, x))
            if score > best_score:
                best_score = score
                best_arm = arm

        self._last_arm = best_arm

        # Parse slot_type and domain from arm
        if ":" in best_arm:
            arm_domain, arm_slot = best_arm.split(":", 1)
        else:
            arm_domain = "default"
            arm_slot = best_arm

        # 5. Determine action and timing based on bbox & confidence
        has_verified_bbox = (det_bbox is not None) and (det_conf >= min_conf) and (arm_slot != "none")

        dec_id = f"dec_{best_arm}_{uuid.uuid4().hex[:8]}"
        self._decision_cache[dec_id] = (best_arm, state, x)

        if has_verified_bbox:
            action = "paper_click" if paper else "click"
            # Random timing between 800ms and 3500ms
            timing_ms = int(self.rng.integers(800, 3501))
            reason = f"LinTS selected arm '{best_arm}' (score={best_score:.3f}, conf={det_conf:.2f})"
            bbox = det_bbox
        else:
            action = "skip"
            timing_ms = 0
            bbox = None
            if arm_slot == "none":
                reason = f"LinTS selected fallback arm '{best_arm}'"
            elif det_bbox is None:
                reason = f"LinTS selected arm '{best_arm}' but no bounding box detected"
            else:
                reason = f"LinTS selected arm '{best_arm}' but confidence {det_conf:.2f} < {min_conf}"

        return AdDecision(
            action=action,
            bbox=bbox,
            slot_type=arm_slot,
            domain=arm_domain,
            timing_ms=timing_ms,
            reason=reason,
            decision_id=dec_id,
        )

    def update(
        self,
        arm_id: str,
        reward: float,
        state: Optional[AgentState] = None,
        device_id: str = "",
    ) -> None:
        """Update precision matrix A and reward vector b for the given arm or decision.

        Args:
            arm_id:    Arm identifier or decision_id.
            reward:    Scalar reward value.
            state:     Optional AgentState (if None, looked up from decision cache).
            device_id: ADB device serial.
        """
        # Resolve arm and feature vector x
        resolved_arm = arm_id
        x: Optional[np.ndarray] = None

        if arm_id in self._decision_cache:
            cached_arm, cached_state, cached_x = self._decision_cache[arm_id]
            resolved_arm = cached_arm
            x = cached_x
            if state is None:
                state = cached_state

        if x is None:
            if state is not None:
                x = self.encoder.encode(state, n_features=self.n_features)
            elif self._last_x is not None:
                x = self._last_x
            else:
                x = np.ones(self.n_features, dtype=np.float64)

        # Ensure arm exists in weights
        A_key = f"{resolved_arm}:A"
        b_key = f"{resolved_arm}:b"
        if A_key not in self._weights:
            # Try to match resolved_arm to an existing arm
            matched = False
            for a in self._arms:
                if resolved_arm == a or resolved_arm.endswith(f":{a}") or a.endswith(f":{resolved_arm}"):
                    resolved_arm = a
                    A_key = f"{a}:A"
                    b_key = f"{a}:b"
                    matched = True
                    break
            if not matched:
                # Use last arm or create on-the-fly
                resolved_arm = self._last_arm or self._arms[0]
                A_key = f"{resolved_arm}:A"
                b_key = f"{resolved_arm}:b"

        if A_key not in self._weights:
            self._weights[A_key] = self.lambda_reg * np.eye(self.n_features, dtype=np.float64)
            self._weights[b_key] = np.zeros(self.n_features, dtype=np.float64)

        # In-place precision matrix and reward vector update
        x_col = np.asarray(x, dtype=np.float64).reshape(-1, 1)
        self._weights[A_key] += x_col @ x_col.T
        self._weights[b_key] += float(reward) * x_col.ravel()

        self._step_count += 1
        if self._step_count % self.persist_every_n == 0:
            self.save_weights(device_id=device_id)

    def save_weights(self, device_id: str = "") -> None:
        """Persist all in-memory arm weights to disk via WeightStore."""
        for key in list(self._weights.keys()):
            if key.endswith(":A"):
                arm = key[:-2]
                A = self._weights.get(f"{arm}:A")
                b = self._weights.get(f"{arm}:b")
                if A is not None and b is not None:
                    self.weight_store.save(device_id, arm, A, b)
                    if not device_id or device_id.lower() == "global":
                        self.weight_store.save_global(arm, A, b)
        logger.debug("LinTSBandit: weights saved for device=%s", device_id or "global")

    def load_weights(self, device_id: str = "") -> None:
        """Load arm weights from disk into in-memory dictionary."""
        arms = self.weight_store.list_arms(device_id)
        if not arms:
            arms = self.weight_store.list_arms("global")

        # Also ensure all configured arms are covered
        all_arms = set(self._arms).union(arms)

        for arm in all_arms:
            loaded = self.weight_store.load(device_id, arm)
            if loaded is None:
                loaded = self.weight_store.load_global(arm)

            if loaded is not None:
                A, b = loaded
                self._weights[f"{arm}:A"] = np.asarray(A, dtype=np.float64)
                self._weights[f"{arm}:b"] = np.asarray(b, dtype=np.float64)
            else:
                if f"{arm}:A" not in self._weights:
                    self._weights[f"{arm}:A"] = self.lambda_reg * np.eye(self.n_features, dtype=np.float64)
                    self._weights[f"{arm}:b"] = np.zeros(self.n_features, dtype=np.float64)

        logger.debug("LinTSBandit: loaded weights for %d arms", len(all_arms))


# Re-exports for convenient module access
__all__ = ["LinTSBandit", "StateEncoder", "CTRGuard", "WeightStore"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A1 LinTS Bandit Runner")
    parser.add_argument("--config", default="ai_engine_config.yaml", help="Path to config")
    parser.add_argument("--paper", action="store_true", help="Paper trading mode")
    parser.add_argument("--dry-run", action="store_true", help="Execute single dry run step")
    args = parser.parse_args()

    from ai_engine.config import load_ai_config
    from ai_engine.interfaces import DetectionResult

    config = load_ai_config(args.config)
    bandit = LinTSBandit(config, seed=42)

    sample_state = AgentState(
        domain_id=1,
        slot_type="banner",
        time_of_day_h=12,
        recent_ctr=0.02,
        recent_rpm=1.5,
        device_id_hash=12345,
        session_age_s=30.0,
        bbox_confidence=0.85,
    )
    sample_det = DetectionResult(
        label="banner",
        confidence=0.85,
        bbox=(50, 100, 300, 250),
        source="rule_fallback",
    )

    decision = bandit.decide(sample_state, sample_det, paper=args.paper)
    print(f"A1 LinTS decision: action={decision.action}, arm={decision.slot_type}, timing={decision.timing_ms}ms")
    print(f"Reason: {decision.reason}")
    if args.dry_run:
        bandit.update(decision.decision_id, reward=0.05)
        bandit.save_weights()
        print("Dry run update and persistence completed successfully.")
