"""
ab_test_engine.py — Step 5.3: A/B Test Engine for Click & Dwell Strategies

Provides automated experimentation between distinct browsing and ad engagement strategies:
- Variant A ('conservative'): Lower click rate (4%), lower dwell, minimal risk
- Variant B ('balanced'): Standard profile (6% click, 30-110s dwell)
- Variant C ('high_engagement'): Higher click rate (7.5%), longer dwell (40-130s)

Features:
- Probabilistic selection with auto-promotion
- Strict anti-IVT safety guard: Variants with CTR > 5.0% are disqualified from promotion
- Metrics analysis based on db.sessions (degraded rate, CTR, impression volume)
- Persists state in state/ab_test_state.json
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import random
import time
from typing import Optional

import db

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).parent / "state" / "ab_test_state.json"


@dataclass
class StrategyVariant:
    variant_id: str
    click_prob: float
    min_dwell: float
    max_dwell: float
    scroll_prob: float
    weight: float
    description: str


_DEFAULT_VARIANTS = [
    StrategyVariant(
        variant_id="conservative",
        click_prob=0.040,
        min_dwell=25.0,
        max_dwell=85.0,
        scroll_prob=0.80,
        weight=0.30,
        description="Ultra-safe low engagement footprint for sensitive proxies",
    ),
    StrategyVariant(
        variant_id="balanced",
        click_prob=0.060,
        min_dwell=30.0,
        max_dwell=110.0,
        scroll_prob=0.85,
        weight=0.45,
        description="Standard natural audience engagement baseline",
    ),
    StrategyVariant(
        variant_id="high_engagement",
        click_prob=0.075,
        min_dwell=40.0,
        max_dwell=130.0,
        scroll_prob=0.90,
        weight=0.25,
        description="High dwell and elevated CTR for trusted residential IP pools",
    ),
]


class ABTestEngine:
    """Orchestrates strategy experiments, parameter overrides, and winning variant promotion."""

    def __init__(self, variants: list[StrategyVariant] | None = None, enabled: bool = True):
        self.variants: list[StrategyVariant] = variants or copy.deepcopy(_DEFAULT_VARIANTS)
        self.enabled: bool = enabled
        self.winning_variant_id: Optional[str] = None
        self.promoted_at: float = 0.0
        self.promotion_ttl_seconds: float = 7 * 86400.0  # 7-day TTL before re-learning
        self._load_state()

    def get_variant_by_id(self, variant_id: str) -> Optional[StrategyVariant]:
        for v in self.variants:
            if v.variant_id == variant_id:
                return v
        return None

    def select_variant(self, rng: random.Random) -> StrategyVariant:
        """
        Select a strategy variant with 10% epsilon-greedy exploration and TTL expiry.
        If A/B testing is disabled, returns 'balanced' or the first variant.
        When a winner is promoted, retains 10% exploration of non-winner variants.
        """
        if not self.enabled:
            return self.get_variant_by_id("balanced") or self.variants[0]

        # Check TTL expiry of winning variant promotion
        if self.winning_variant_id and self.promoted_at > 0:
            if time.time() - self.promoted_at > self.promotion_ttl_seconds:
                logger.info("A/B Test Engine promotion TTL expired for '%s' — re-opening exploration", self.winning_variant_id)
                self.winning_variant_id = None
                self.promoted_at = 0.0
                self._save_state()

        if self.winning_variant_id:
            winner = self.get_variant_by_id(self.winning_variant_id)
            if winner:
                # 10% epsilon exploration even during winning promotion
                if rng.random() >= 0.10:
                    return winner
                alternatives = [v for v in self.variants if v.variant_id != winner.variant_id]
                if alternatives:
                    return rng.choice(alternatives)
                return winner

        weights = [v.weight for v in self.variants]
        return rng.choices(self.variants, weights=weights, k=1)[0]

    def apply_variant_to_config(self, cfg: dict, variant: StrategyVariant) -> dict:
        """
        Create a shallow copy of config with the variant's click_prob, min_dwell, max_dwell,
        and scroll_prob applied.
        """
        scoped_cfg = copy.deepcopy(cfg)
        target = scoped_cfg.setdefault("target", {})
        target["click_prob"] = variant.click_prob
        target["min_dwell"] = variant.min_dwell
        target["max_dwell"] = variant.max_dwell
        target["scroll_prob"] = variant.scroll_prob
        return scoped_cfg

    def evaluate_and_promote(self, min_samples: int = 50, last_n: int = 500) -> dict:
        """
        Evaluates metrics from db.get_ab_test_metrics().
        Selects the best performing variant that satisfies:
        1. Minimum sample count reached (>= min_samples)
        2. Safe CTR (<= 0.050 / 5.0%)
        3. Lowest degradation rate combined with highest dwell & valid engagement.
        """
        metrics = db.get_ab_test_metrics(last_n=last_n)
        scores: dict[str, float] = {}
        disqualified: dict[str, str] = {}

        for v in self.variants:
            v_id = v.variant_id
            m = metrics.get(v_id)
            if not m or m["sessions"] < min_samples:
                disqualified[v_id] = f"Insufficient data ({m['sessions'] if m else 0}/{min_samples})"
                continue

            # Hard safety constraint: Disqualify any variant exceeding 5.0% CTR
            if m["ctr"] > 0.050:
                disqualified[v_id] = f"CTR too high ({m['ctr']:.1%} > 5.0%)"
                continue

            # Score formula: Heavily reward low degradation rate and healthy CTR
            reliability = 1.0 - m["degraded_pct"]  # 0.0 to 1.0
            ctr_efficiency = m["ctr"] / 0.050      # normalized to 1.0 at 5% CTR
            dwell_factor = min(m["avg_dwell"] / 60.0, 1.5)

            score = (reliability * 0.60) + (ctr_efficiency * 0.25) + (dwell_factor * 0.15)
            scores[v_id] = round(score, 4)

        winner = None
        if scores:
            winner = max(scores, key=lambda k: scores[k])
            self.winning_variant_id = winner
            self.promoted_at = time.time()
            self._save_state()
            logger.info("A/B Test Engine promoted winning variant: %s (score=%.4f)", winner, scores[winner])

        return {
            "winner": winner,
            "scores": scores,
            "disqualified": disqualified,
            "metrics": metrics,
        }

    def _save_state(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "winning_variant_id": self.winning_variant_id,
                "promoted_at": getattr(self, "promoted_at", 0.0),
                "variants": [asdict(v) for v in self.variants],
            }
            STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to save AB test state: %s", exc)

    def _load_state(self) -> None:
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.winning_variant_id = data.get("winning_variant_id")
                self.promoted_at = float(data.get("promoted_at", 0.0) or 0.0)
        except Exception:
            pass


def build_from_config(cfg: dict) -> ABTestEngine:
    """Construct ABTestEngine from config.yaml ab_testing block."""
    ab_cfg = cfg.get("ab_testing", {})
    enabled = bool(ab_cfg.get("enabled", True))
    return ABTestEngine(enabled=enabled)
