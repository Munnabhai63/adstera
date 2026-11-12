"""
config.py — Typed configuration loader for the AI Decision Engine.

Loads ``ai_engine_config.yaml`` into nested dataclasses.  Falls back to
hard-coded defaults for every field so the engine can run with no config file
present (useful in CI or during first-run).

Usage::

    from ai_engine.config import load_ai_config
    cfg = load_ai_config("ai_engine_config.yaml")
    print(cfg.a2_anomaly.z_threshold)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # PyYAML — already in requirements.txt
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AIEngineConfig:
    """Top-level engine settings."""

    paper_trading: bool = False
    log_level: str = "INFO"
    state_dir: str = "state/ai_engine"
    db_path: str = "sessions.db"


@dataclass
class A1LinTSConfig:
    """Linear Thompson Sampling (A1) bandit settings."""

    alpha: float = 1.0
    lambda_reg: float = 1.0
    n_features: int = 8
    domain_arms: list[str] = field(default_factory=list)
    ad_slot_arms: list[str] = field(
        default_factory=lambda: ["banner", "interstitial", "popunder", "native", "none"]
    )
    persist_every_n: int = 10
    reward_rpm_scale: float = 1000.0


@dataclass
class CTRGuardConfig:
    """CTR guard thresholds and behaviour."""

    window_size: int = 200
    hard_cap: float = 0.045
    soft_cap: float = 0.036
    defer_seconds: int = 30


@dataclass
class IsolationForestConfig:
    """Isolation Forest sub-settings for A2."""

    enabled: bool = True
    contamination: float = 0.05
    n_estimators: int = 100


@dataclass
class SafeModeConfig:
    """SAFE MODE activation and exit rules."""

    exit_clean_windows: int = 5
    window_seconds: int = 120
    pause_click_on_entry: bool = True
    throttle_session_rate: float = 0.3


@dataclass
class AlertConfig:
    """Alert dispatch settings for A2 anomalies."""

    telegram_enabled: bool = True
    webhook_url: str = ""
    email_enabled: bool = False


@dataclass
class A2AnomalyConfig:
    """Full A2 Anomaly Detector configuration."""

    ewma_alpha: float = 0.15
    z_threshold: float = 2.5
    isolation_forest: IsolationForestConfig = field(
        default_factory=IsolationForestConfig
    )
    safe_mode: SafeModeConfig = field(default_factory=SafeModeConfig)
    metrics: list[str] = field(
        default_factory=lambda: [
            "rpm",
            "ctr",
            "empty_ad_rate",
            "load_time_ms",
            "error_rate",
            "repeated_creative_rate",
        ]
    )
    rpm_floor: float = 0.5
    load_time_ceiling_ms: float = 8000.0
    empty_ad_spike_rate: float = 0.4
    repeated_creative_threshold: float = 0.6
    alert: AlertConfig = field(default_factory=AlertConfig)


@dataclass
class RuleFallbackConfig:
    """Rule-based fallback settings for A4 visual detector."""

    enabled: bool = True
    id_patterns: list[str] = field(
        default_factory=lambda: ["ad", "banner", "sponsor", "promoted"]
    )
    class_patterns: list[str] = field(
        default_factory=lambda: ["ad-", "adv-", "adunit", "adsense", "adsterra"]
    )
    min_area_px: int = 2000
    max_area_ratio: float = 0.6


@dataclass
class A4VisualConfig:
    """A4 Visual ad detector configuration."""

    confidence_threshold: float = 0.55
    inference_timeout_ms: int = 300
    model_path: str = "state/ai_engine/ad_detector.onnx"
    labels: list[str] = field(
        default_factory=lambda: ["ad", "banner", "interstitial", "popunder", "none"]
    )
    ad_network_hints: dict[str, list[str]] = field(
        default_factory=lambda: {
            "adsterra": ["adsterra", "popunder", "araplhn"],
            "propeller": ["propellerads", "propeller"],
            "hilltop": ["hilltopads", "hilltop"],
        }
    )
    rule_fallback: RuleFallbackConfig = field(default_factory=RuleFallbackConfig)


@dataclass
class AIConfig:
    """Root config object returned by :func:`load_ai_config`."""

    ai_engine: AIEngineConfig = field(default_factory=AIEngineConfig)
    a1_linTS: A1LinTSConfig = field(default_factory=A1LinTSConfig)
    ctr_guard: CTRGuardConfig = field(default_factory=CTRGuardConfig)
    a2_anomaly: A2AnomalyConfig = field(default_factory=A2AnomalyConfig)
    a4_visual: A4VisualConfig = field(default_factory=A4VisualConfig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge(dataclass_instance: Any, raw: dict[str, Any]) -> Any:
    """Recursively merge *raw* dict values into *dataclass_instance* fields.

    Unknown keys in *raw* are silently ignored so that future config additions
    don't break older engine versions.

    Args:
        dataclass_instance: A dataclass instance to update in place.
        raw:                Dictionary of values from the YAML file.

    Returns:
        The updated *dataclass_instance*.
    """
    import dataclasses

    if not dataclasses.is_dataclass(dataclass_instance) or not isinstance(raw, dict):
        return dataclass_instance

    for f in dataclasses.fields(dataclass_instance):
        if f.name not in raw:
            continue
        val = raw[f.name]
        current = getattr(dataclass_instance, f.name)
        if dataclasses.is_dataclass(current) and isinstance(val, dict):
            _merge(current, val)
        else:
            try:
                setattr(dataclass_instance, f.name, val)
            except Exception as exc:  # pragma: no cover
                logger.warning("config: could not set %s=%r — %s", f.name, val, exc)

    return dataclass_instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ai_config(path: Optional[str] = None) -> AIConfig:
    """Load the AI engine config from *path* (YAML) and return an :class:`AIConfig`.

    If *path* is ``None`` or the file does not exist, a fully-defaulted
    :class:`AIConfig` is returned and a warning is emitted.

    Args:
        path: Path to the YAML config file.  Relative paths are resolved
              from the current working directory.

    Returns:
        Populated :class:`AIConfig` instance.
    """
    cfg = AIConfig()

    if path is None:
        logger.warning("config: no path supplied — using all defaults")
        return cfg

    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path(os.getcwd()) / resolved

    if not resolved.exists():
        logger.warning("config: %s not found — using all defaults", resolved)
        return cfg

    if yaml is None:
        logger.error(
            "config: PyYAML not installed; cannot parse %s — using defaults", resolved
        )
        return cfg

    try:
        with resolved.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("config: failed to read %s — %s — using defaults", resolved, exc)
        return cfg

    # Map top-level YAML keys to dataclass fields
    _merge(cfg.ai_engine, raw.get("ai_engine", {}))
    _merge(cfg.a1_linTS, raw.get("a1_linTS", {}))
    _merge(cfg.ctr_guard, raw.get("ctr_guard", {}))

    # A2 has nested sub-configs
    a2_raw = raw.get("a2_anomaly", {})
    _merge(cfg.a2_anomaly, a2_raw)
    _merge(cfg.a2_anomaly.isolation_forest, a2_raw.get("isolation_forest", {}))
    _merge(cfg.a2_anomaly.safe_mode, a2_raw.get("safe_mode", {}))
    _merge(cfg.a2_anomaly.alert, a2_raw.get("alert", {}))

    # A4
    a4_raw = raw.get("a4_visual", {})
    _merge(cfg.a4_visual, a4_raw)
    _merge(cfg.a4_visual.rule_fallback, a4_raw.get("rule_fallback", {}))

    logger.info("config: loaded from %s", resolved)
    return cfg
