"""Typed configuration loader for Phase 3.

Loads ``phase3/config.yaml`` and resolves environment-only secrets.
Never hardcodes API keys, tokens, or device serials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


@dataclass
class Phase3CoreConfig:
    default_mode: str = "paper"
    live_confirm_env_var: str = "PHASE3_LIVE_CONFIRM_TOKEN"
    live_confirm_required_phrase: str = "CONFIRM_LIVE_EXECUTION"
    db_path: str = "state/phase3/phase3.db"
    ai_engine_config: str = "ai_engine_config.yaml"
    legacy_config: str = "config.yaml"
    state_dir: str = "state/phase3"
    log_level: str = "INFO"
    json_logs: bool = True


@dataclass
class AdsterraFeedConfig:
    api_key_env_var: str = "ADSTERRA_API_KEY"
    cache_ttl_seconds: int = 300
    default_ecpm_usd: float = 0.50
    default_ctr: float = 0.02
    fallback_mock_on_missing_key: bool = True


@dataclass
class AlertsConfig:
    telegram_token_env_var: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env_var: str = "TELEGRAM_CHAT_ID"
    webhook_url_env_var: str = "PHASE3_ALERT_WEBHOOK_URL"


@dataclass
class SafetyConfig:
    aggregate_ctr_hard_cap: float = 0.045
    aggregate_ctr_soft_cap: float = 0.036
    per_device_ctr_hard_cap: float = 0.045
    ctr_window_size: int = 200
    anomaly_z_threshold: float = 2.5
    safe_mode_throttle_factor: float = 0.30
    safe_mode_exit_clean_windows: int = 5
    require_a4_bbox_for_gesture: bool = True
    require_a2_ok_for_gesture: bool = True


@dataclass
class A6SchedulerConfig:
    base_sessions_per_hour: float = 90.0
    diurnal_curve: List[float] = field(
        default_factory=lambda: [
            0.25, 0.18, 0.14, 0.12, 0.14, 0.28, 0.52, 0.78,
            0.95, 1.00, 0.92, 0.86, 0.82, 0.85, 0.90, 0.94,
            0.98, 1.00, 0.95, 0.84, 0.68, 0.52, 0.40, 0.32,
        ]
    )
    weekday_scale: List[float] = field(
        default_factory=lambda: [1.0, 1.05, 1.08, 1.06, 1.0, 0.72, 0.66]
    )
    min_delay_seconds: float = 0.5
    max_delay_seconds: float = 600.0
    burst_probability: float = 0.15
    burst_multiplier: float = 1.8


@dataclass
class CGNATTrackerConfig:
    slash24_cooldown_seconds: int = 1800
    slash20_cooldown_seconds: int = 600
    slot_ttl_seconds: int = 3600
    allow_missing_ip_in_paper: bool = True


@dataclass
class A3ForecasterConfig:
    quantiles: List[float] = field(default_factory=lambda: [0.10, 0.50, 0.90])
    min_history_days: int = 7
    max_history_days: int = 60
    irls_max_iter: int = 100
    irls_tol: float = 1e-6
    irls_epsilon: float = 1e-5
    default_impressions_per_day: float = 1000.0
    fallback_iqr_spread: float = 0.20


@dataclass
class A5SEOGateConfig:
    gamma_prior_alpha: float = 1.5
    gamma_prior_beta: float = 1.0
    gsc_ctr_weight: float = 0.45
    adsterra_rpm_weight: float = 0.55
    position_decay_base: float = 0.85
    burstiness_min: float = 0.20
    burstiness_max: float = 1.80
    zipf_entropy_min: float = 4.50
    zipf_entropy_max: float = 10.50
    zipf_slope_min: float = 0.55
    zipf_slope_max: float = 1.55
    min_word_count: int = 80
    min_sentence_count: int = 5


@dataclass
class B2HealthConfig:
    max_consecutive_failures: int = 3
    quarantine_cooldown_seconds: int = 300
    recovery_probe_interval_seconds: int = 60


@dataclass
class B2FarmConfig:
    target_daily_sessions: int = 2000
    min_devices: int = 1
    max_devices: int = 10
    poll_interval_seconds: float = 1.0
    session_timeout_seconds: float = 90.0
    usb_port_map: Dict[str, int] = field(default_factory=dict)
    health: B2HealthConfig = field(default_factory=B2HealthConfig)


@dataclass
class B1AndroidConfig:
    enabled: bool = True
    fallback_to_adb: bool = True
    package_name: str = "com.adsterra.phoneagent"
    control_transport: str = "websocket"
    device_listen_port: int = 8765
    host_port_base: int = 9320
    connect_timeout_seconds: float = 3.0
    command_timeout_seconds: float = 5.0
    gesture_min_duration_ms: int = 45
    gesture_max_duration_ms: int = 140
    scroll_min_duration_ms: int = 280
    scroll_max_duration_ms: int = 650
    auth_token: str = ""


@dataclass
class Phase3Config:
    phase3: Phase3CoreConfig = field(default_factory=Phase3CoreConfig)
    adsterra: AdsterraFeedConfig = field(default_factory=AdsterraFeedConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    a6_scheduler: A6SchedulerConfig = field(default_factory=A6SchedulerConfig)
    cgnat_tracker: CGNATTrackerConfig = field(default_factory=CGNATTrackerConfig)
    a3_forecaster: A3ForecasterConfig = field(default_factory=A3ForecasterConfig)
    a5_seo_gate: A5SEOGateConfig = field(default_factory=A5SEOGateConfig)
    b2_farm: B2FarmConfig = field(default_factory=B2FarmConfig)
    b1_android: B1AndroidConfig = field(default_factory=B1AndroidConfig)

    def resolve_env_secret(self, env_var_name: str) -> str:
        """Read secret strictly from process environment (never from YAML)."""
        if not env_var_name:
            return ""
        return os.environ.get(env_var_name, "").strip()

    def is_live_confirmed(self) -> bool:
        """Return True iff the typed live-mode confirmation token is present in env."""
        actual = self.resolve_env_secret(self.phase3.live_confirm_env_var)
        expected = self.phase3.live_confirm_required_phrase
        return bool(actual) and actual == expected


def _apply_dict(target: Any, data: Dict[str, Any]) -> Any:
    if not isinstance(data, dict):
        return target
    for key, val in data.items():
        if not hasattr(target, key):
            continue
        cur = getattr(target, key)
        if hasattr(cur, "__dataclass_fields__") and isinstance(val, dict):
            _apply_dict(cur, val)
        else:
            setattr(target, key, val)
    return target


def load_phase3_config(path: Optional[str | Path] = None) -> Phase3Config:
    """Load Phase3Config from YAML file, falling back to safe defaults if missing."""
    cfg = Phase3Config()
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if cfg_path.is_file():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            _apply_dict(cfg, raw)
    return cfg
