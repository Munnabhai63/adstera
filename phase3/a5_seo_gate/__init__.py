"""Phase 3 A5 SEO Gate package: High-RPM Keyword Predictor & Anti-AI Quality Gate."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Tuple

from phase3.config_loader import (
    A5SEOGateConfig,
    AdsterraFeedConfig,
    Phase3Config,
    load_phase3_config,
)


def resolve_a5_config(cfg: Any = None) -> Tuple[A5SEOGateConfig, AdsterraFeedConfig]:
    """Normalize ``cfg`` (None, Phase3Config, A5SEOGateConfig, or dict) into typed configs."""
    if cfg is None:
        loaded = load_phase3_config()
        return loaded.a5_seo_gate, loaded.adsterra

    if isinstance(cfg, Phase3Config):
        return cfg.a5_seo_gate, cfg.adsterra

    if isinstance(cfg, A5SEOGateConfig):
        return cfg, AdsterraFeedConfig()

    if isinstance(cfg, dict):
        base = load_phase3_config()
        a5_raw = cfg.get("a5_seo_gate") if isinstance(cfg.get("a5_seo_gate"), dict) else cfg
        ads_raw = cfg.get("adsterra") if isinstance(cfg.get("adsterra"), dict) else {}

        a5_kwargs = asdict(base.a5_seo_gate)
        for key, val in a5_raw.items():
            if key in a5_kwargs and val is not None:
                a5_kwargs[key] = type(a5_kwargs[key])(val)

        ads_kwargs = asdict(base.adsterra)
        for key, val in ads_raw.items():
            if key in ads_kwargs and val is not None:
                ads_kwargs[key] = type(ads_kwargs[key])(val)

        return A5SEOGateConfig(**a5_kwargs), AdsterraFeedConfig(**ads_kwargs)

    loaded = load_phase3_config()
    return loaded.a5_seo_gate, loaded.adsterra


from phase3.a5_seo_gate.quality_gate import AntiAIQualityGate, gate
from phase3.a5_seo_gate.rpm_predictor import GammaPoissonRPMPredictor, rank_keywords

__all__ = [
    "AntiAIQualityGate",
    "GammaPoissonRPMPredictor",
    "gate",
    "rank_keywords",
    "resolve_a5_config",
]
