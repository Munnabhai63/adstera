"""B2 Multi-Phone USB Hub Farm Orchestrator.

Scales 1..10 Android devices connected over a powered USB 3.0 hub, addressing
each device by ADB serial (``-s <serial>``) and a dedicated port tuple from
``b2_farm.usb_port_map`` in ``phase3/config.yaml``.

Safety & anti-detection invariants:
- Defaults to ``--paper`` mode (``paper=True``): decisions are evaluated and
  logged, zero real touches are executed.
- ``--live`` requires BOTH ``paper=False`` AND the env confirmation token
  ``PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION``; otherwise falls back
  safely to paper mode.
- Every device session requires an exclusive CGNAT IP slot from
  ``acquire_slot(device_id)`` BEFORE starting; colliding or cooling-down
  subnets block session start.
- Per-device isolated sessions, ports, A1 bandit weights, and per-device
  CTRGuard, PLUS a farm-wide aggregate CTRGuard.
- One CRITICAL A2 anomaly on any device triggers farm-wide SAFE MODE,
  suppressing clicks across ALL devices and throttling session cadence.
- Health monitor auto-quarantines failing devices after
  ``max_consecutive_failures`` for ``quarantine_cooldown_seconds`` and
  auto-recovers once cooldown elapses and a liveness probe succeeds.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from ai_engine.a1_linTS.bandit import LinTSBandit
from ai_engine.a1_linTS.ctr_guard import CTRGuard
from ai_engine.a2_anomaly.detector import AnomalyDetector
from ai_engine.config import AIConfig, load_ai_config
from ai_engine.interfaces import (
    AdDecision,
    AgentState,
    AnomalyResult,
    DetectionResult,
    MetricsSnapshot,
)
from ai_engine.safe_mode import SafeModeStateMachine

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import (
    _CORRELATION_ID,
    configure_json_logging,
    log_event,
    new_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger("phase3.b2_farm")


# ---------------------------------------------------------------------------
# Helpers & Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceAssignment:
    """Port and ADB addressing assigned to one physical/mocked phone."""

    device_id: str
    usb_port: str
    cdp_port: int
    b1_port: int
    adb_args: Tuple[str, ...]


@dataclass
class DeviceHealthState:
    """Mutable health & quarantine state persisted to ``p3_farm_devices``."""

    device_id: str
    usb_port: str
    cdp_port: int
    b1_port: int
    status: str = "healthy"  # healthy | quarantined | offline
    consecutive_failures: int = 0
    quarantined_until: float = 0.0
    last_probe_at: float = 0.0
    total_sessions: int = 0
    total_clicks: int = 0
    last_seen_at: float = 0.0
    last_error: str = ""
    active_session_id: str = ""


class _DualStopHandle:
    """Allows ``farm.stop()`` to work whether awaited or called synchronously."""

    def __init__(self, coro_factory: Callable[[], Awaitable[None]]) -> None:
        self._coro_factory = coro_factory

    def __await__(self):
        return self._coro_factory().__await__()


def _invoke_factory(factory: Callable[..., Any], **available_kwargs: Any) -> Any:
    """Call *factory* passing only the parameters its signature accepts."""
    sig = inspect.signature(factory)
    params = sig.parameters
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if accepts_var_kw:
        return factory(**available_kwargs)

    call_kwargs: Dict[str, Any] = {}
    positional_only_args: List[Any] = []
    for name, param in params.items():
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            if name in available_kwargs:
                positional_only_args.append(available_kwargs[name])
        elif param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            if name in available_kwargs:
                call_kwargs[name] = available_kwargs[name]

    if not call_kwargs and not positional_only_args:
        # Handle single-arg lambdas/callables whose param name isn't in available_kwargs
        required = [
            p
            for p in params.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(required) == 1:
            for fallback_key in ("device_id", "serial", "cfg"):
                if fallback_key in available_kwargs:
                    return factory(available_kwargs[fallback_key])
        return factory()

    return factory(*positional_only_args, **call_kwargs)


def _extract_serial(item: Any) -> str:
    """Extract ADB serial string from a device descriptor or object."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("serial") or item.get("device_id") or item.get("id") or "").strip()
    for attr in ("serial", "device_id", "id"):
        val = getattr(item, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def build_usb_assignments(
    device_ids: Sequence[str],
    cfg: Phase3Config,
) -> List[DeviceAssignment]:
    """Map discovered device serials onto dedicated USB/CDP/B1 ports from config."""
    max_devs = max(1, int(cfg.b2_farm.max_devices))
    port_items = list(cfg.b2_farm.usb_port_map.items())
    base_b1_port = int(cfg.b1_android.host_port_base)

    assignments: List[DeviceAssignment] = []
    seen: set[str] = set()
    for idx, raw_id in enumerate(device_ids):
        serial = str(raw_id).strip()
        if not serial or serial in seen:
            continue
        if len(assignments) >= max_devs:
            break
        seen.add(serial)
        if idx < len(port_items):
            usb_port, cdp_port = port_items[idx]
        else:
            usb_port = f"port_{idx + 1}"
            cdp_port = (int(port_items[-1][1]) + (idx - len(port_items) + 1)) if port_items else (9222 + idx)
        b1_port = base_b1_port + idx
        assignments.append(
            DeviceAssignment(
                device_id=serial,
                usb_port=str(usb_port),
                cdp_port=int(cdp_port),
                b1_port=b1_port,
                adb_args=("-s", serial),
            )
        )
    return assignments


# ---------------------------------------------------------------------------
# Fallback Adapters (used only if sibling modules or mocks are not supplied)
# ---------------------------------------------------------------------------


class _FallbackCGNATTracker:
    """In-memory + SQLite CGNAT /24 and /20 tracker used if a6_scheduler is absent."""

    def __init__(self, cfg: Phase3Config, store: Phase3Store) -> None:
        self._cfg = cfg.cgnat_tracker
        self._store = store
        self._active: Dict[str, Tuple[str, str, str, float]] = {}
        self._cooldowns_24: Dict[str, float] = {}
        self._cooldowns_20: Dict[str, float] = {}

    @staticmethod
    def _subnets(ip_address: str) -> Tuple[str, str]:
        addr = ipaddress.IPv4Address(ip_address.strip())
        s24 = str(ipaddress.IPv4Network(f"{addr}/24", strict=False))
        s20 = str(ipaddress.IPv4Network(f"{addr}/20", strict=False))
        return s24, s20

    def is_subnet_on_cooldown(
        self, ip_address: str, now_ts: Optional[float] = None
    ) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        if not ip_address:
            return False
        try:
            s24, s20 = self._subnets(ip_address)
        except Exception:
            return False
        if self._cooldowns_24.get(s24, 0.0) > now:
            return True
        if self._cooldowns_20.get(s20, 0.0) > now:
            return True
        return False

    def acquire_slot(
        self,
        device_id: str,
        ip_address: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        ttl = float(self._cfg.slot_ttl_seconds)
        # Expire stale active locks
        for dev in list(self._active.keys()):
            if now - self._active[dev][3] >= ttl:
                self.release_slot(dev, now_ts=now)

        ip_str = (ip_address or "").strip()
        if not ip_str:
            if not self._cfg.allow_missing_ip_in_paper:
                return False
            digest = hashlib.sha256(device_id.encode("utf-8")).digest()
            ip_str = f"100.64.{digest[0]}.{max(1, digest[1] % 254)}"

        try:
            s24, s20 = self._subnets(ip_str)
        except Exception:
            return False

        # Block if another device holds an active slot on same /24 or /20
        for other_dev, (_, other_24, other_20, _) in self._active.items():
            if other_dev != device_id and (other_24 == s24 or other_20 == s20):
                return False

        if self.is_subnet_on_cooldown(ip_str, now_ts=now):
            return False

        self._active[device_id] = (ip_str, s24, s20, now)
        try:
            with self._store.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO p3_cgnat_slots
                    (device_id, ip_address, subnet_24, subnet_20, active, acquired_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (device_id, ip_str, s24, s20, now),
                )
        except Exception:
            pass
        return True

    def release_slot(self, device_id: str, now_ts: Optional[float] = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        slot = self._active.pop(device_id, None)
        if slot is not None:
            _, s24, s20, _ = slot
            self._cooldowns_24[s24] = now + float(self._cfg.slash24_cooldown_seconds)
            self._cooldowns_20[s20] = now + float(self._cfg.slash20_cooldown_seconds)
        try:
            with self._store.connect() as conn:
                conn.execute(
                    """
                    UPDATE p3_cgnat_slots
                    SET active = 0, released_at = ?
                    WHERE device_id = ? AND active = 1
                    """,
                    (now, device_id),
                )
        except Exception:
            pass


class _FallbackScheduler:
    """Bounded diurnal-weighted delay fallback used if a6_scheduler is absent."""

    def __init__(self, cfg: Phase3Config) -> None:
        self._cfg = cfg.a6_scheduler

    def intensity_at(self, ts: Optional[float] = None) -> float:
        now = time.time() if ts is None else float(ts)
        lt = time.localtime(now)
        hour = lt.tm_hour % 24
        wday = lt.tm_wday % 7
        diurnal = self._cfg.diurnal_curve[hour] if len(self._cfg.diurnal_curve) == 24 else 1.0
        wscale = self._cfg.weekday_scale[wday] if len(self._cfg.weekday_scale) == 7 else 1.0
        return max(1e-6, float(self._cfg.base_sessions_per_hour) * float(diurnal) * float(wscale))

    def schedule_next(self, now_ts: Optional[float] = None) -> float:
        rate_per_sec = self.intensity_at(now_ts) / 3600.0
        delay = 1.0 / max(1e-6, rate_per_sec)
        return max(
            float(self._cfg.min_delay_seconds),
            min(float(self._cfg.max_delay_seconds), delay),
        )


class _DefaultPaperDeviceHandle:
    """Safe fallback device handle used when no real ADB/mock handle is provided."""

    def __init__(self, serial: str, adb_args: Tuple[str, ...]) -> None:
        self.serial = serial
        self.adb_args = adb_args

    def is_alive(self, serial: Optional[str] = None) -> bool:
        return True

    def get_ip(self) -> str:
        digest = hashlib.sha256(self.serial.encode("utf-8")).digest()
        return f"100.64.{digest[0]}.{max(1, digest[1] % 254)}"

    def screenshot(self) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
            b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
            b"\x00\x00IEND\xaeB`\x82"
        )

    def get_domain(self) -> str:
        return "example.com"


class _DefaultPaperB1Client:
    """No-op B1 client used in paper mode or when b1_android is absent."""

    def __init__(self, serial: str, host_port: int) -> None:
        self.serial = serial
        self.host_port = host_port
        self.connected = False

    def connect(self) -> bool:
        self.connected = True
        return True

    def tap(
        self,
        x: int,
        y: int,
        duration_ms: int = 80,
        *,
        a4_verified_bbox: bool = False,
        a2_ok: bool = False,
    ) -> bool:
        raise RuntimeError("Paper B1 stub refuses real tap execution")

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "serial": self.serial, "host_port": self.host_port}

    def close(self) -> None:
        self.connected = False


class _FallbackA4Detector:
    """Deterministic lightweight fallback A4 detector when frame has no live model."""

    def detect(self, frame: bytes, meta: Optional[Dict[str, Any]] = None) -> DetectionResult:
        return DetectionResult(
            label="banner",
            confidence=0.80,
            bbox=(120, 420, 320, 100),
            source="rule_fallback",
        )


@dataclass
class _DeviceRuntime:
    """Per-device isolated runtime container."""

    assignment: DeviceAssignment
    health: DeviceHealthState
    device_handle: Any
    b1_client: Any
    ai_component: Any
    a4_detector: Any
    ctr_guard: CTRGuard
    last_ip: str = ""


# ---------------------------------------------------------------------------
# DeviceFarm Orchestrator
# ---------------------------------------------------------------------------


class DeviceFarm:
    """Multi-phone USB 3.0 hub farm orchestrator for Phase 3 (B2)."""

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        store: Optional[Phase3Store] = None,
        cgnat_tracker: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        device_factory: Optional[Callable[..., Any]] = None,
        ai_factory: Optional[Callable[..., Any]] = None,
        b1_client_factory: Optional[Callable[..., Any]] = None,
        devices: Optional[Sequence[Any]] = None,
        paper: Optional[bool] = None,
        a2_detector: Optional[Any] = None,
        safe_mode: Optional[SafeModeStateMachine] = None,
        adsterra_feed: Optional[Any] = None,
        time_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    ) -> None:
        self.cfg: Phase3Config = cfg if cfg is not None else load_phase3_config()
        self._now: Callable[[], float] = time_fn or time.time
        self._sleep: Callable[[float], Awaitable[None]] = sleep_fn or asyncio.sleep

        # Paper mode default & strict --live confirmation guard
        requested_paper = (
            (self.cfg.phase3.default_mode != "live") if paper is None else bool(paper)
        )
        if not requested_paper and not self.cfg.is_live_confirmed():
            log_event(
                logger,
                logging.WARNING,
                "live_mode_refused_forcing_paper",
                env_var=self.cfg.phase3.live_confirm_env_var,
            )
            self.paper = True
        else:
            self.paper = requested_paper

        # SQLite persistence store
        self.store: Phase3Store = (
            store if store is not None else Phase3Store(self.cfg.phase3.db_path)
        )

        # CGNAT tracker (prefer phase3.a6_scheduler.cgnat_tracker if present)
        if cgnat_tracker is not None:
            self.cgnat_tracker = cgnat_tracker
        else:
            try:
                from phase3.a6_scheduler.cgnat_tracker import CGNATTracker

                self.cgnat_tracker = CGNATTracker(self.cfg, self.store)
            except Exception:
                self.cgnat_tracker = _FallbackCGNATTracker(self.cfg, self.store)

        # NHPP scheduler (prefer phase3.a6_scheduler.nhpp if present)
        if scheduler is not None:
            self.scheduler = scheduler
        else:
            try:
                from phase3.a6_scheduler.nhpp import NHPPScheduler

                self.scheduler = NHPPScheduler(self.cfg)
            except Exception:
                self.scheduler = _FallbackScheduler(self.cfg)

        self._adsterra_feed = adsterra_feed
        self._device_factory = device_factory
        self._ai_factory = ai_factory
        self._b1_client_factory = b1_client_factory

        # AI Engine config for A1 / A2 / SafeMode
        self._ai_cfg: AIConfig = self._build_ai_config()

        # Farm-wide SafeMode state machine (canonical path inside cfg.phase3.state_dir)
        if safe_mode is not None:
            self.safe_mode = safe_mode
        else:
            sm_dir = Path(self.cfg.phase3.state_dir) / "ai_engine"
            self.safe_mode = SafeModeStateMachine(
                self._ai_cfg.a2_anomaly.safe_mode,
                state_dir=str(sm_dir),
            )

        # Farm-wide A2 Anomaly Detector
        self.a2_detector = (
            a2_detector
            if a2_detector is not None
            else AnomalyDetector(self._ai_cfg, safe_mode=self.safe_mode)
        )

        # Farm-wide Aggregate CTRGuard
        self.aggregate_ctr_guard = CTRGuard(
            window_size=int(self.cfg.safety.ctr_window_size),
            hard_cap=float(self.cfg.safety.aggregate_ctr_hard_cap),
            soft_cap=float(self.cfg.safety.aggregate_ctr_soft_cap),
        )

        # Runtime state & coordination
        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._worker_tasks: List[asyncio.Task[None]] = []
        self._iter_lock: asyncio.Lock = asyncio.Lock()
        self._ctr_lock: asyncio.Lock = asyncio.Lock()
        self._cgnat_lock: asyncio.Lock = asyncio.Lock()
        self._iterations_claimed: int = 0
        self._iterations_completed: int = 0
        self._consecutive_idle_polls: int = 0

        # Discover & register 1..N devices
        self._devices: Dict[str, _DeviceRuntime] = {}
        self._init_devices(devices)

    def _build_ai_config(self) -> AIConfig:
        ai_cfg = load_ai_config(self.cfg.phase3.ai_engine_config)
        ai_cfg.ctr_guard.hard_cap = float(self.cfg.safety.aggregate_ctr_hard_cap)
        ai_cfg.ctr_guard.soft_cap = float(self.cfg.safety.aggregate_ctr_soft_cap)
        ai_cfg.ctr_guard.window_size = int(self.cfg.safety.ctr_window_size)
        ai_cfg.a2_anomaly.z_threshold = float(self.cfg.safety.anomaly_z_threshold)
        ai_cfg.a2_anomaly.safe_mode.throttle_session_rate = float(
            self.cfg.safety.safe_mode_throttle_factor
        )
        ai_cfg.a2_anomaly.safe_mode.exit_clean_windows = int(
            self.cfg.safety.safe_mode_exit_clean_windows
        )
        ai_cfg.ai_engine.state_dir = str(
            Path(self.store.db_path).resolve().parent / "ai_state"
        )
        return ai_cfg

    def _discover_device_items(self, explicit_devices: Optional[Sequence[Any]]) -> List[Any]:
        if explicit_devices is not None:
            return list(explicit_devices)

        if self._device_factory is not None:
            sig = inspect.signature(self._device_factory)
            required = [
                p
                for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            if not required:
                produced = self._device_factory()
                if isinstance(produced, (list, tuple, set)):
                    return list(produced)
                if produced is not None:
                    return [produced]

        # Try phase3.adapters.phase1_device or mobile_adb.list_devices
        try:
            from phase3.adapters.phase1_device import Phase1DeviceAdapter

            found = Phase1DeviceAdapter(self.cfg).list_devices()
            if found:
                return list(found)
        except Exception:
            pass

        try:
            import mobile_adb

            adb_devs = mobile_adb.list_devices()
            online = [d["id"] for d in adb_devs if d.get("status") == "device"]
            if online:
                return online
        except Exception:
            pass

        return []

    def _init_devices(self, explicit_devices: Optional[Sequence[Any]]) -> None:
        raw_items = self._discover_device_items(explicit_devices)
        item_by_id: Dict[str, Any] = {}
        serials: List[str] = []
        for item in raw_items:
            serial = _extract_serial(item)
            if serial and serial not in item_by_id:
                serials.append(serial)
                item_by_id[serial] = item

        assignments = build_usb_assignments(serials, self.cfg)
        min_devs = int(self.cfg.b2_farm.min_devices)
        if len(assignments) < min_devs:
            log_event(
                logger,
                logging.WARNING,
                "farm_below_min_devices",
                discovered=len(assignments),
                min_devices=min_devs,
            )

        now = self._now()
        for idx, assignment in enumerate(assignments):
            serial = assignment.device_id
            raw_item = item_by_id.get(serial)

            # Device handle
            if raw_item is not None and not isinstance(raw_item, (str, dict)):
                dev_handle = raw_item
            elif self._device_factory is not None:
                sig = inspect.signature(self._device_factory)
                required = [
                    p
                    for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if required:
                    dev_handle = _invoke_factory(
                        self._device_factory,
                        device_id=serial,
                        serial=serial,
                        usb_port=assignment.usb_port,
                        cdp_port=assignment.cdp_port,
                        b1_port=assignment.b1_port,
                        adb_args=assignment.adb_args,
                        cfg=self.cfg,
                    )
                else:
                    dev_handle = _DefaultPaperDeviceHandle(serial, assignment.adb_args)
            else:
                dev_handle = _DefaultPaperDeviceHandle(serial, assignment.adb_args)

            # B1 client
            if self._b1_client_factory is not None:
                b1_client = _invoke_factory(
                    self._b1_client_factory,
                    serial=serial,
                    device_id=serial,
                    host_port=assignment.b1_port,
                    cfg=self.cfg,
                )
            else:
                b1_client = self._default_b1_client(serial, assignment.b1_port)

            # Per-device isolated A1 / AI component
            if self._ai_factory is not None:
                ai_component = _invoke_factory(
                    self._ai_factory,
                    device_id=serial,
                    serial=serial,
                    cfg=self.cfg,
                    ai_cfg=self._ai_cfg,
                )
            else:
                ai_component = self._default_device_bandit(serial, idx)

            # Per-device A4 detector
            a4_detector = self._default_a4_detector()

            # Per-device CTRGuard
            per_dev_ctr = CTRGuard(
                window_size=int(self.cfg.safety.ctr_window_size),
                hard_cap=float(self.cfg.safety.per_device_ctr_hard_cap),
                soft_cap=float(self.cfg.safety.aggregate_ctr_soft_cap),
            )

            health = DeviceHealthState(
                device_id=serial,
                usb_port=assignment.usb_port,
                cdp_port=assignment.cdp_port,
                b1_port=assignment.b1_port,
                status="healthy",
                last_seen_at=now,
            )

            self.store.upsert_farm_device(
                device_id=serial,
                usb_port=assignment.usb_port,
                cdp_port=assignment.cdp_port,
                b1_port=assignment.b1_port,
                status=health.status,
                consecutive_failures=0,
                quarantined_until=0.0,
                total_sessions=0,
                total_clicks=0,
                last_seen_at=now,
            )

            self._devices[serial] = _DeviceRuntime(
                assignment=assignment,
                health=health,
                device_handle=dev_handle,
                b1_client=b1_client,
                ai_component=ai_component,
                a4_detector=a4_detector,
                ctr_guard=per_dev_ctr,
            )

    def _default_b1_client(self, serial: str, host_port: int) -> Any:
        if self.paper:
            return _DefaultPaperB1Client(serial, host_port)
        try:
            from phase3.b1_android.PhoneAgentClient import PhoneAgentClient  # type: ignore

            return PhoneAgentClient(serial, host_port=host_port, cfg=self.cfg)
        except Exception:
            return _DefaultPaperB1Client(serial, host_port)

    def _default_device_bandit(self, serial: str, idx: int) -> LinTSBandit:
        seed_bytes = hashlib.sha256(f"{serial}:{idx}".encode("utf-8")).digest()
        seed = int.from_bytes(seed_bytes[:4], "big")
        dev_ai_cfg = self._build_ai_config()
        dev_ai_cfg.ai_engine.state_dir = str(
            Path(self.store.db_path).resolve().parent / "ai_state" / f"dev_{idx}_{serial}"
        )
        return LinTSBandit(config=dev_ai_cfg, seed=seed)

    @staticmethod
    def _default_a4_detector() -> Any:
        try:
            from ai_engine.a4_visual.detector import VisualAdDetector

            return VisualAdDetector()
        except Exception:
            return _FallbackA4Detector()

    # ------------------------------------------------------------------
    # Public Lifecycle & Status API
    # ------------------------------------------------------------------

    async def start(self, max_iterations: Optional[int] = None) -> None:
        """Start per-device async worker tasks and run until stopped or max_iterations reached."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._iterations_claimed = 0
        self._iterations_completed = 0
        self._consecutive_idle_polls = 0

        log_event(
            logger,
            logging.INFO,
            "farm_started",
            mode=("paper" if self.paper else "live"),
            device_count=len(self._devices),
            max_iterations=max_iterations,
        )

        if not self._devices:
            self._running = False
            log_event(logger, logging.WARNING, "farm_no_devices_available")
            return

        self._worker_tasks = [
            asyncio.create_task(
                self._device_worker(ctx, max_iterations=max_iterations),
                name=f"b2-worker-{ctx.assignment.device_id}",
            )
            for ctx in self._devices.values()
        ]
        try:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        finally:
            self._running = False
            self._worker_tasks.clear()
            log_event(
                logger,
                logging.INFO,
                "farm_stopped",
                iterations_completed=self._iterations_completed,
            )

    def stop(self) -> _DualStopHandle:
        """Signal all farm workers to stop cleanly (sync or awaitable)."""
        self._running = False
        self._stop_event.set()
        return _DualStopHandle(self._cleanup_async)

    async def _cleanup_async(self) -> None:
        tasks = list(self._worker_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for ctx in self._devices.values():
            close_fn = getattr(ctx.b1_client, "close", None)
            if callable(close_fn):
                try:
                    res = close_fn()
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    pass

    def health(self) -> Dict[str, Any]:
        """Return structured farm & per-device health snapshot."""
        devices_snap: Dict[str, Dict[str, Any]] = {}
        healthy = 0
        quarantined = 0
        offline = 0
        for dev_id, ctx in self._devices.items():
            st = ctx.health.status
            if st == "healthy":
                healthy += 1
            elif st == "quarantined":
                quarantined += 1
            else:
                offline += 1
            devices_snap[dev_id] = {
                "device_id": ctx.health.device_id,
                "usb_port": ctx.health.usb_port,
                "cdp_port": ctx.health.cdp_port,
                "b1_port": ctx.health.b1_port,
                "adb_args": list(ctx.assignment.adb_args),
                "status": ctx.health.status,
                "consecutive_failures": ctx.health.consecutive_failures,
                "quarantined_until": ctx.health.quarantined_until,
                "total_sessions": ctx.health.total_sessions,
                "total_clicks": ctx.health.total_clicks,
                "last_seen_at": ctx.health.last_seen_at,
                "last_error": ctx.health.last_error,
                "ctr": ctx.ctr_guard.current_ctr(),
            }

        return {
            "running": self._running,
            "mode": "paper" if self.paper else "live",
            "safe_mode": self.safe_mode.is_active(),
            "safe_mode_reason": self.safe_mode.entry_reason,
            "throttle_factor": self.safe_mode.get_throttle_factor(),
            "aggregate_ctr": self.aggregate_ctr_guard.current_ctr(),
            "aggregate_ctr_deferred": self.aggregate_ctr_guard.is_deferred(),
            "iterations_completed": self._iterations_completed,
            "total_devices": len(self._devices),
            "healthy_devices": healthy,
            "quarantined_devices": quarantined,
            "offline_devices": offline,
            "devices": devices_snap,
        }

    # ------------------------------------------------------------------
    # Worker Loop & Session Execution
    # ------------------------------------------------------------------

    async def _device_worker(
        self,
        ctx: _DeviceRuntime,
        *,
        max_iterations: Optional[int],
    ) -> None:
        poll_interval = float(self.cfg.b2_farm.poll_interval_seconds)
        while self._running and not self._stop_event.is_set():
            if max_iterations is not None:
                async with self._iter_lock:
                    if self._iterations_claimed >= max_iterations:
                        return
                    if self._consecutive_idle_polls > max(25, max_iterations * 5):
                        log_event(
                            logger,
                            logging.WARNING,
                            "farm_idle_poll_limit_reached",
                            device_id=ctx.assignment.device_id,
                            idle_polls=self._consecutive_idle_polls,
                        )
                        return

            outcome = await self._run_device_step(ctx, max_iterations=max_iterations)

            if outcome in ("cap_reached", "target_daily_reached"):
                return
            if outcome in ("quarantined_skip", "cgnat_blocked", "quarantined_probe_failed"):
                async with self._iter_lock:
                    self._consecutive_idle_polls += 1
                await self._interruptible_sleep(poll_interval)
                continue

            async with self._iter_lock:
                self._consecutive_idle_polls = 0

            delay = self._compute_next_delay()
            if max_iterations is not None:
                # Keep test runs bounded by poll_interval when max_iterations is explicit
                delay = min(delay, poll_interval)
            await self._interruptible_sleep(delay)

    async def _interruptible_sleep(self, seconds: float) -> None:
        if seconds <= 0 or self._stop_event.is_set():
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        except Exception:
            await self._sleep(seconds)

    def _compute_next_delay(self) -> float:
        try:
            delay = float(self.scheduler.schedule_next(self._now()))
        except Exception:
            delay = float(self.cfg.a6_scheduler.min_delay_seconds)
        throttle = max(0.05, float(self.safe_mode.get_throttle_factor()))
        if self.safe_mode.is_active():
            delay = delay / throttle
        min_d = float(self.cfg.a6_scheduler.min_delay_seconds)
        max_d = float(self.cfg.a6_scheduler.max_delay_seconds)
        return max(min_d, min(max_d, delay))

    async def _acquire_cgnat_slot(
        self, device_id: str, ip_address: Optional[str], now_ts: float
    ) -> bool:
        async with self._cgnat_lock:
            fn = self.cgnat_tracker.acquire_slot
            sig = inspect.signature(fn)
            kwargs: Dict[str, Any] = {}
            if "ip_address" in sig.parameters:
                kwargs["ip_address"] = ip_address
            if "now_ts" in sig.parameters:
                kwargs["now_ts"] = now_ts
            res = fn(device_id, **kwargs)
            if inspect.isawaitable(res):
                res = await res
            return bool(res)

    async def _release_cgnat_slot(self, device_id: str, now_ts: float) -> None:
        async with self._cgnat_lock:
            fn = self.cgnat_tracker.release_slot
            sig = inspect.signature(fn)
            kwargs: Dict[str, Any] = {}
            if "now_ts" in sig.parameters:
                kwargs["now_ts"] = now_ts
            res = fn(device_id, **kwargs)
            if inspect.isawaitable(res):
                await res

    def _get_device_ip(self, ctx: _DeviceRuntime) -> str:
        handle = ctx.device_handle
        for method_name in ("get_ip", "get_public_ip"):
            fn = getattr(handle, method_name, None)
            if callable(fn):
                val = fn()
                if isinstance(val, dict):
                    return str(val.get("ip", "")).strip()
                if isinstance(val, str):
                    return val.strip()
        for attr in ("ip_address", "ip"):
            val = getattr(handle, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    def _probe_device(self, ctx: _DeviceRuntime) -> bool:
        handle = ctx.device_handle
        for method_name in ("probe", "is_alive"):
            fn = getattr(handle, method_name, None)
            if callable(fn):
                sig = inspect.signature(fn)
                if len(sig.parameters) >= 1:
                    return bool(fn(ctx.assignment.device_id))
                return bool(fn())
        status_fn = getattr(ctx.b1_client, "status", None)
        if callable(status_fn):
            res = status_fn()
            if isinstance(res, dict):
                return bool(res.get("ok", True))
            return bool(res)
        return True

    def _persist_device_health(self, ctx: _DeviceRuntime) -> None:
        h = ctx.health
        self.store.upsert_farm_device(
            device_id=h.device_id,
            usb_port=h.usb_port,
            cdp_port=h.cdp_port,
            b1_port=h.b1_port,
            status=h.status,
            consecutive_failures=h.consecutive_failures,
            quarantined_until=h.quarantined_until,
            total_sessions=h.total_sessions,
            total_clicks=h.total_clicks,
            last_seen_at=h.last_seen_at,
        )

    def _record_device_failure(
        self,
        ctx: _DeviceRuntime,
        error_msg: str,
        correlation_id: str,
        now: float,
    ) -> None:
        h = ctx.health
        h.consecutive_failures += 1
        h.last_error = error_msg
        h.last_seen_at = now
        max_fail = int(self.cfg.b2_farm.health.max_consecutive_failures)
        cooldown = float(self.cfg.b2_farm.health.quarantine_cooldown_seconds)

        if h.consecutive_failures >= max_fail:
            h.status = "quarantined"
            h.quarantined_until = now + cooldown
            log_event(
                logger,
                logging.WARNING,
                "device_quarantined",
                correlation_id=correlation_id,
                device_id=h.device_id,
                usb_port=h.usb_port,
                consecutive_failures=h.consecutive_failures,
                quarantined_until=h.quarantined_until,
                error=error_msg,
            )
        self._persist_device_health(ctx)

    async def _run_device_step(
        self,
        ctx: _DeviceRuntime,
        *,
        max_iterations: Optional[int],
    ) -> str:
        device_id = ctx.assignment.device_id
        correlation_id = new_correlation_id("p3")
        cid_token = set_correlation_id(correlation_id)
        now = self._now()

        try:
            # 1. Health & quarantine gate
            if ctx.health.status == "quarantined":
                if now < ctx.health.quarantined_until:
                    return "quarantined_skip"

                probe_ok = False
                try:
                    probe_ok = self._probe_device(ctx)
                except Exception as exc:
                    log_event(
                        logger,
                        logging.WARNING,
                        "device_recovery_probe_exception",
                        correlation_id=correlation_id,
                        device_id=device_id,
                        error=str(exc),
                    )
                ctx.health.last_probe_at = now
                if probe_ok:
                    ctx.health.status = "healthy"
                    ctx.health.consecutive_failures = 0
                    ctx.health.quarantined_until = 0.0
                    ctx.health.last_error = ""
                    ctx.health.last_seen_at = now
                    self._persist_device_health(ctx)
                    log_event(
                        logger,
                        logging.INFO,
                        "device_recovered",
                        correlation_id=correlation_id,
                        device_id=device_id,
                        usb_port=ctx.assignment.usb_port,
                    )
                else:
                    ctx.health.quarantined_until = now + float(
                        self.cfg.b2_farm.health.quarantine_cooldown_seconds
                    )
                    self._persist_device_health(ctx)
                    log_event(
                        logger,
                        logging.WARNING,
                        "device_recovery_probe_failed",
                        correlation_id=correlation_id,
                        device_id=device_id,
                        quarantined_until=ctx.health.quarantined_until,
                    )
                    return "quarantined_probe_failed"

            # 2. Daily cap check
            daily_target = int(self.cfg.b2_farm.target_daily_sessions)
            if daily_target > 0 and self._iterations_completed >= daily_target:
                return "target_daily_reached"

            # 3. CGNAT slot acquisition MUST precede session start
            ip_address = ""
            try:
                ip_address = self._get_device_ip(ctx)
            except Exception as exc:
                self._record_device_failure(ctx, f"ip_lookup_failed: {exc}", correlation_id, now)
                return "error"

            slot_acquired = await self._acquire_cgnat_slot(device_id, ip_address or None, now)
            if not slot_acquired:
                log_event(
                    logger,
                    logging.INFO,
                    "cgnat_slot_blocked",
                    correlation_id=correlation_id,
                    device_id=device_id,
                    ip_address=ip_address,
                    usb_port=ctx.assignment.usb_port,
                )
                return "cgnat_blocked"

            # 4. Claim global iteration slot after CGNAT passes
            session_id = ""
            try:
                if max_iterations is not None:
                    async with self._iter_lock:
                        if self._iterations_claimed >= max_iterations:
                            return "cap_reached"
                        self._iterations_claimed += 1

                session_id = f"sess_{device_id}_{uuid.uuid4().hex[:8]}"
                ctx.health.active_session_id = session_id
                await self._execute_session(
                    ctx,
                    session_id=session_id,
                    correlation_id=correlation_id,
                    ip_address=ip_address,
                    started_at=now,
                )
                async with self._iter_lock:
                    self._iterations_completed += 1
                return "ok"
            except Exception as exc:
                err_text = str(exc)
                log_event(
                    logger,
                    logging.ERROR,
                    "device_session_failed",
                    correlation_id=correlation_id,
                    device_id=device_id,
                    session_id=session_id,
                    usb_port=ctx.assignment.usb_port,
                    error=err_text,
                )
                if session_id:
                    try:
                        self.store.finish_session(
                            session_id,
                            status="failed",
                            dwell_seconds=0.0,
                            error=err_text,
                            ended_at=self._now(),
                        )
                    except Exception:
                        pass
                self._record_device_failure(ctx, err_text, correlation_id, self._now())
                return "error"
            finally:
                ctx.health.active_session_id = ""
                await self._release_cgnat_slot(device_id, self._now())
        finally:
            _CORRELATION_ID.reset(cid_token)

    async def _execute_session(
        self,
        ctx: _DeviceRuntime,
        *,
        session_id: str,
        correlation_id: str,
        ip_address: str,
        started_at: float,
    ) -> None:
        device_id = ctx.assignment.device_id
        subnet_24, subnet_20 = self._safe_subnets(ip_address)
        domain = self._get_domain(ctx)

        self.store.start_session(
            session_id=session_id,
            correlation_id=correlation_id,
            device_id=device_id,
            mode=("paper" if self.paper else "live"),
            domain=domain,
            ip_address=ip_address,
            subnet_24=subnet_24,
            subnet_20=subnet_20,
            started_at=started_at,
        )

        # Capture & A4 visual detection
        frame = self._capture_frame(ctx)
        detection = self._run_a4(ctx, frame, domain=domain, device_id=device_id)

        # Build metrics snapshot & evaluate farm-wide A2 anomaly detector
        snapshot = await self._build_metrics_snapshot(ctx, domain=domain)
        a2_result = self._evaluate_a2(ctx, snapshot, correlation_id=correlation_id)

        # Check farm-wide SAFE MODE + CTR guards + A4/A2 gates
        async with self._ctr_lock:
            agg_blocked = (
                self.aggregate_ctr_guard.is_deferred()
                or self.aggregate_ctr_guard.would_breach(self.cfg.safety.aggregate_ctr_hard_cap)
            )
            dev_blocked = (
                ctx.ctr_guard.is_deferred()
                or ctx.ctr_guard.would_breach(self.cfg.safety.per_device_ctr_hard_cap)
            )
            if agg_blocked and not self.aggregate_ctr_guard.is_deferred():
                self.aggregate_ctr_guard.set_defer()
            if dev_blocked and not ctx.ctr_guard.is_deferred():
                ctx.ctr_guard.set_defer()

        state = self._build_agent_state(ctx, domain=domain, detection=detection, snapshot=snapshot)
        decision = self._decide_a1(ctx, state, detection)

        safe_active = self.safe_mode.is_active()
        bbox = detection.bbox
        bbox_valid = (
            isinstance(bbox, (tuple, list))
            and len(bbox) == 4
            and int(bbox[2]) > 0
            and int(bbox[3]) > 0
        )
        conf_threshold = float(getattr(self._ai_cfg.a4_visual, "confidence_threshold", 0.55))
        a4_ok = (
            bbox_valid
            and str(detection.label or "none").lower() != "none"
            and float(detection.confidence) >= conf_threshold
        )
        a4_verified = a4_ok or (not self.cfg.safety.require_a4_bbox_for_gesture)
        a2_ok = a2_result.ok or (not self.cfg.safety.require_a2_ok_for_gesture)

        if safe_active:
            decision = AdDecision(
                action="skip",
                bbox=None,
                slot_type=decision.slot_type or "none",
                domain=domain,
                timing_ms=0,
                reason=f"farm SAFE MODE active ({self.safe_mode.entry_reason})",
                decision_id=decision.decision_id or f"dec_sm_{uuid.uuid4().hex[:8]}",
            )
        elif agg_blocked or dev_blocked:
            decision = AdDecision(
                action="defer",
                bbox=None,
                slot_type=decision.slot_type or "none",
                domain=domain,
                timing_ms=0,
                reason="CTR guard cap reached (farm or per-device)",
                decision_id=decision.decision_id or f"dec_ctr_{uuid.uuid4().hex[:8]}",
            )
        elif decision.action in ("click", "paper_click") and (not a4_verified or not a2_ok):
            decision = AdDecision(
                action="skip",
                bbox=None,
                slot_type=decision.slot_type or "none",
                domain=domain,
                timing_ms=0,
                reason=f"safety gate blocked click (a4_verified={a4_verified}, a2_ok={a2_ok})",
                decision_id=decision.decision_id or f"dec_gate_{uuid.uuid4().hex[:8]}",
            )

        # Execute touch strictly in live mode when confirmed & safe
        executed_touch = False
        if not self.paper and decision.action == "click" and decision.bbox is not None:
            if not safe_active and a4_verified and a2_ok and self.cfg.is_live_confirmed():
                executed_touch = await self._execute_live_touch(
                    ctx, decision.bbox, a4_verified=a4_verified, a2_ok=a2_ok
                )

        # Update CTR guards (rolling window)
        clicked_event = decision.action in ("click", "paper_click")
        async with self._ctr_lock:
            self.aggregate_ctr_guard.record_impression(clicked=clicked_event)
            ctx.ctr_guard.record_impression(clicked=clicked_event)

        # Reward update on isolated per-device A1 bandit
        reward = self._compute_reward(snapshot.rpm, decision.action)
        self._update_a1(ctx, decision, reward, state)

        # Log decision & finish session
        now_end = self._now()
        dwell = max(0.0, now_end - started_at)
        self.store.log_decision_reward(
            session_id=session_id,
            correlation_id=correlation_id,
            device_id=device_id,
            domain=domain,
            slot_type=decision.slot_type or "banner",
            action=decision.action,
            executed_touch=executed_touch,
            bbox=decision.bbox,
            a4_source=detection.source,
            a4_confidence=float(detection.confidence),
            a2_severity=a2_result.severity,
            safe_mode=safe_active,
            rpm=float(snapshot.rpm),
            ctr=float(ctx.ctr_guard.current_ctr()),
            reward_value=float(reward),
            reason=decision.reason,
            ts=now_end,
        )
        self.store.finish_session(
            session_id,
            status="completed",
            dwell_seconds=dwell,
            error="",
            ended_at=now_end,
        )

        # Update device health
        ctx.health.status = "healthy"
        ctx.health.consecutive_failures = 0
        ctx.health.last_error = ""
        ctx.health.total_sessions += 1
        if clicked_event:
            ctx.health.total_clicks += 1
        ctx.health.last_seen_at = now_end
        self._persist_device_health(ctx)

        log_event(
            logger,
            logging.INFO,
            "session_completed",
            correlation_id=correlation_id,
            session_id=session_id,
            device_id=device_id,
            usb_port=ctx.assignment.usb_port,
            cdp_port=ctx.assignment.cdp_port,
            b1_port=ctx.assignment.b1_port,
            adb_args=list(ctx.assignment.adb_args),
            action=decision.action,
            executed_touch=executed_touch,
            safe_mode=safe_active,
            a2_severity=a2_result.severity,
            device_ctr=round(ctx.ctr_guard.current_ctr(), 4),
            farm_ctr=round(self.aggregate_ctr_guard.current_ctr(), 4),
        )

    @staticmethod
    def _safe_subnets(ip_address: str) -> Tuple[str, str]:
        if not ip_address:
            return "", ""
        try:
            addr = ipaddress.IPv4Address(ip_address.strip())
            return (
                str(ipaddress.IPv4Network(f"{addr}/24", strict=False)),
                str(ipaddress.IPv4Network(f"{addr}/20", strict=False)),
            )
        except Exception:
            return "", ""

    @staticmethod
    def _get_domain(ctx: _DeviceRuntime) -> str:
        fn = getattr(ctx.device_handle, "get_domain", None)
        if callable(fn):
            val = fn()
            if isinstance(val, str) and val.strip():
                return val.strip()
        dom = getattr(ctx.device_handle, "domain", None)
        if isinstance(dom, str) and dom.strip():
            return dom.strip()
        return "example.com"

    @staticmethod
    def _capture_frame(ctx: _DeviceRuntime) -> bytes:
        fn = getattr(ctx.device_handle, "screenshot", None)
        if callable(fn):
            data = fn()
            if isinstance(data, (bytes, bytearray)) and len(data) > 0:
                return bytes(data)
            from phase3.adapters.phase1_device import DeviceDisconnectedError

            raise DeviceDisconnectedError(
                f"Device '{ctx.assignment.device_id}' returned empty/invalid screenshot"
            )
        return b""

    def _run_a4(self, ctx: _DeviceRuntime, frame: bytes, *, domain: str, device_id: str) -> DetectionResult:
        fn = getattr(ctx.device_handle, "detect_ad", None)
        if callable(fn):
            res = fn(frame)
            if isinstance(res, DetectionResult):
                return res
        det = ctx.a4_detector.detect(frame, {"domain": domain, "device_id": device_id})
        if isinstance(det, DetectionResult):
            return det
        return DetectionResult(
            label=getattr(det, "label", "banner"),
            confidence=float(getattr(det, "confidence", 0.0)),
            bbox=getattr(det, "bbox", None),
            source=str(getattr(det, "source", "rule_fallback")),
        )

    async def _build_metrics_snapshot(self, ctx: _DeviceRuntime, *, domain: str) -> MetricsSnapshot:
        device_id = ctx.assignment.device_id
        snap_fn = getattr(ctx.device_handle, "metrics_snapshot", None)
        if callable(snap_fn):
            snap = snap_fn()
            if inspect.isawaitable(snap):
                snap = await snap
            if isinstance(snap, MetricsSnapshot):
                return snap

        rpm = float(self.cfg.adsterra.default_ecpm_usd)
        ctr = float(self.cfg.adsterra.default_ctr)
        if self._adsterra_feed is not None:
            fetch_fn = (
                getattr(self._adsterra_feed, "get_domain_metrics", None)
                or getattr(self._adsterra_feed, "get_metrics", None)
                or getattr(self._adsterra_feed, "fetch", None)
            )
            if callable(fetch_fn):
                try:
                    sig = inspect.signature(fetch_fn)
                    if "domain" in sig.parameters:
                        feed_data = fetch_fn(domain=domain)
                    else:
                        feed_data = fetch_fn(domain)
                    if inspect.isawaitable(feed_data):
                        feed_data = await feed_data
                    if isinstance(feed_data, dict):
                        rpm = float(feed_data.get("rpm", feed_data.get("ecpm", rpm)))
                        ctr = float(feed_data.get("ctr", ctr))
                except Exception:
                    pass

        return MetricsSnapshot(
            rpm=rpm,
            ctr=ctr,
            empty_ad_rate=0.05,
            load_time_ms=450.0,
            error_rate=0.0,
            repeated_creative_rate=0.0,
            ts=self._now(),
            domain=domain,
            device_id=device_id,
        )

    def _evaluate_a2(
        self,
        ctx: _DeviceRuntime,
        snapshot: MetricsSnapshot,
        *,
        correlation_id: str,
    ) -> AnomalyResult:
        # Check optional per-device AI component A2 check first (for injected mocks)
        ai_check = getattr(ctx.ai_component, "check_anomaly", None)
        res: Optional[AnomalyResult] = None
        if callable(ai_check):
            candidate = ai_check(snapshot)
            if isinstance(candidate, AnomalyResult):
                res = candidate

        if res is None:
            res = self.a2_detector.check(snapshot)
            self.a2_detector.update_baseline(snapshot)

        if res.severity == "CRITICAL":
            reason = f"device={ctx.assignment.device_id}: " + "; ".join(res.reasons[:2] or ["critical anomaly"])
            self.safe_mode.enter(reason)
            log_event(
                logger,
                logging.CRITICAL,
                "farm_safe_mode_triggered",
                correlation_id=correlation_id,
                trigger_device_id=ctx.assignment.device_id,
                reasons=res.reasons,
            )
        self.safe_mode.tick(is_clean=bool(res.ok))
        return res

    @staticmethod
    def _build_agent_state(
        ctx: _DeviceRuntime,
        *,
        domain: str,
        detection: DetectionResult,
        snapshot: MetricsSnapshot,
    ) -> AgentState:
        dev_hash = int.from_bytes(
            hashlib.sha256(ctx.assignment.device_id.encode("utf-8")).digest()[:4], "big"
        )
        dom_hash = int.from_bytes(
            hashlib.sha256(domain.encode("utf-8")).digest()[:4], "big"
        )
        hour = time.localtime(snapshot.ts).tm_hour
        return AgentState(
            domain_id=dom_hash,
            slot_type=detection.label or "banner",
            time_of_day_h=hour,
            recent_ctr=float(ctx.ctr_guard.current_ctr() or snapshot.ctr),
            recent_rpm=float(snapshot.rpm),
            device_id_hash=dev_hash,
            session_age_s=15.0,
            bbox_confidence=float(detection.confidence),
        )

    def _decide_a1(
        self,
        ctx: _DeviceRuntime,
        state: AgentState,
        detection: DetectionResult,
    ) -> AdDecision:
        decide_fn = getattr(ctx.ai_component, "decide", None)
        if callable(decide_fn):
            sig = inspect.signature(decide_fn)
            kwargs: Dict[str, Any] = {}
            if "detection" in sig.parameters:
                kwargs["detection"] = detection
            if "paper" in sig.parameters:
                kwargs["paper"] = self.paper
            if "device_id" in sig.parameters:
                kwargs["device_id"] = ctx.assignment.device_id
            dec = decide_fn(state, **kwargs)
            if isinstance(dec, AdDecision):
                return dec
            return AdDecision(
                action=str(getattr(dec, "action", "skip")),
                bbox=getattr(dec, "bbox", detection.bbox),
                slot_type=str(getattr(dec, "slot_type", detection.label)),
                domain=str(getattr(dec, "domain", "example.com")),
                timing_ms=int(getattr(dec, "timing_ms", 0)),
                reason=str(getattr(dec, "reason", "ai_component")),
                decision_id=str(getattr(dec, "decision_id", "")),
            )
        return AdDecision(
            action="skip",
            bbox=None,
            slot_type=detection.label,
            domain="example.com",
            timing_ms=0,
            reason="no decide() method on ai_component",
        )

    async def _execute_live_touch(
        self,
        ctx: _DeviceRuntime,
        bbox: Tuple[int, int, int, int],
        *,
        a4_verified: bool,
        a2_ok: bool,
    ) -> bool:
        x, y, w, h = bbox
        cx = int(x + w * 0.5)
        cy = int(y + h * 0.5)
        dur = int(
            (int(self.cfg.b1_android.gesture_min_duration_ms)
             + int(self.cfg.b1_android.gesture_max_duration_ms))
            // 2
        )
        tap_fn = getattr(ctx.b1_client, "tap", None)
        if not callable(tap_fn):
            return False
        sig = inspect.signature(tap_fn)
        kwargs: Dict[str, Any] = {}
        if "duration_ms" in sig.parameters:
            kwargs["duration_ms"] = dur
        if "a4_verified_bbox" in sig.parameters:
            kwargs["a4_verified_bbox"] = a4_verified
        if "a2_ok" in sig.parameters:
            kwargs["a2_ok"] = a2_ok
        res = tap_fn(cx, cy, **kwargs)
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, dict):
            return bool(res.get("executed", res.get("ok", False)))
        if isinstance(res, bool):
            return res
        return True if res is None else bool(res)

    def _compute_reward(self, rpm: float, action: str) -> float:
        scale = float(getattr(self._ai_cfg.a1_linTS, "reward_rpm_scale", 1000.0)) or 1000.0
        penalty = 0.1 if action == "skip" else 0.0
        return (float(rpm) / scale) - penalty

    @staticmethod
    def _update_a1(
        ctx: _DeviceRuntime,
        decision: AdDecision,
        reward: float,
        state: AgentState,
    ) -> None:
        update_fn = getattr(ctx.ai_component, "update", None)
        if not callable(update_fn):
            return
        arm_id = decision.decision_id or decision.slot_type or "banner"
        sig = inspect.signature(update_fn)
        kwargs: Dict[str, Any] = {}
        if "state" in sig.parameters:
            kwargs["state"] = state
        if "device_id" in sig.parameters:
            kwargs["device_id"] = ctx.assignment.device_id
        update_fn(arm_id, reward, **kwargs)


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 B2 Multi-Phone USB Hub Farm")
    parser.add_argument("--config", default=None, help="Path to phase3/config.yaml")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--paper",
        action="store_true",
        help="Run in paper mode (safe default; no real touches executed)",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Attempt live mode (requires env confirmation token)",
    )
    parser.add_argument("--max-iterations", type=int, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = load_phase3_config(args.config)
    configure_json_logging(cfg.phase3.log_level)
    paper = not args.live

    farm = DeviceFarm(cfg, paper=paper)
    asyncio.run(farm.start(max_iterations=args.max_iterations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
