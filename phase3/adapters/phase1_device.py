"""Phase 1 device, ADB, and Android CDP adapter.

Wraps root ``mobile_adb.py`` and ``android_cdp_bridge.py`` without modifying them.
Never hardcodes device serials or credentials.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import log_event

# ASSUMPTION: Root `mobile_adb` exposes `list_devices`, `run_adb`, `get_public_ip`,
# `rotate_ip`, and `get_adb_path`.
try:
    import mobile_adb  # type: ignore
except Exception:  # pragma: no cover
    mobile_adb = None  # type: ignore[assignment]

# ASSUMPTION: Root `android_cdp_bridge` exposes `AndroidCdpBridge`,
# `AndroidCdpSession`, and `probe_cdp_endpoint`.
try:
    import android_cdp_bridge  # type: ignore
except Exception:  # pragma: no cover
    android_cdp_bridge = None  # type: ignore[assignment]

logger = logging.getLogger("phase3.adapters.phase1_device")

_FALLBACK_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
    b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


class DeviceDisconnectedError(RuntimeError):
    """Raised when an ADB device is disconnected or fails to capture a valid frame."""


class Phase1DeviceAdapter:
    """Adapter over Phase 1 ``mobile_adb`` and ``android_cdp_bridge``.

    Satisfies ``ai_engine.interfaces.Phase1DeviceInterface`` while exposing
    async CDP helpers and safe ADB touch/capture fallbacks.
    """

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        adb_path: str = "",
        legacy_cfg: Optional[Dict[str, Any]] = None,
        cdp_bridge: Optional[Any] = None,
    ) -> None:
        self.cfg = cfg or load_phase3_config()
        self.adb_path = adb_path
        self.legacy_cfg = legacy_cfg or {}
        self._cdp_bridge = cdp_bridge

    @property
    def cdp_bridge(self) -> Any:
        if self._cdp_bridge is None and android_cdp_bridge is not None:
            # ASSUMPTION: AndroidCdpBridge(cfg=dict) accepts an empty or legacy config dict.
            self._cdp_bridge = android_cdp_bridge.AndroidCdpBridge(cfg=self.legacy_cfg)
        return self._cdp_bridge

    # ------------------------------------------------------------------
    # Phase1DeviceInterface methods
    # ------------------------------------------------------------------

    def list_devices(self) -> List[str]:
        """Return serial numbers of all authorized connected ADB devices."""
        if mobile_adb is None:
            return []
        try:
            # ASSUMPTION: mobile_adb.list_devices returns list[dict] with "id" and "status" keys.
            raw = mobile_adb.list_devices(custom_path=self.adb_path)
            serials: List[str] = []
            for item in raw or []:
                if isinstance(item, dict) and item.get("status") == "device" and item.get("id"):
                    serials.append(str(item["id"]))
            return serials
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_list_devices_failed", error=str(exc))
            return []

    def is_alive(self, serial: str) -> bool:
        """Check whether *serial* responds as an authorized ADB device."""
        if not serial or mobile_adb is None:
            return False
        try:
            # ASSUMPTION: mobile_adb.run_adb(["-s", serial, "get-state"]) returns (0, "device").
            code, out = mobile_adb.run_adb(["-s", serial, "get-state"], custom_path=self.adb_path, timeout=5.0)
            return code == 0 and "device" in (out or "").lower()
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_is_alive_failed", serial=serial, error=str(exc))
            return False

    def get_device_info(self, serial: str) -> Dict[str, Any]:
        """Return hardware and OS metadata for *serial* via ADB getprop/wm size."""
        info: Dict[str, Any] = {
            "serial": serial,
            "model": "unknown",
            "android_version": "unknown",
            "resolution": "1080x1920",
        }
        if not serial or mobile_adb is None:
            return info
        try:
            code_m, out_m = mobile_adb.run_adb(
                ["-s", serial, "shell", "getprop", "ro.product.model"],
                custom_path=self.adb_path,
                timeout=5.0,
            )
            if code_m == 0 and out_m.strip():
                info["model"] = out_m.strip()

            code_v, out_v = mobile_adb.run_adb(
                ["-s", serial, "shell", "getprop", "ro.build.version.release"],
                custom_path=self.adb_path,
                timeout=5.0,
            )
            if code_v == 0 and out_v.strip():
                info["android_version"] = out_v.strip()

            code_s, out_s = mobile_adb.run_adb(
                ["-s", serial, "shell", "wm", "size"],
                custom_path=self.adb_path,
                timeout=5.0,
            )
            if code_s == 0 and ":" in (out_s or ""):
                info["resolution"] = out_s.split(":", 1)[-1].strip()
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_device_info_failed", serial=serial, error=str(exc))
        return info

    # ------------------------------------------------------------------
    # IP & Carrier Helpers
    # ------------------------------------------------------------------

    def get_public_ip(self, timeout: float = 6.0) -> Dict[str, Any]:
        """Query current public IP and geo metadata via ``mobile_adb.get_public_ip``."""
        if mobile_adb is None:
            return {"ip": "", "country": "", "region": "", "city": "", "org": "", "ok": False}
        try:
            # ASSUMPTION: mobile_adb.get_public_ip(timeout=...) returns dict with ip/ok keys.
            res = mobile_adb.get_public_ip(timeout=timeout)
            return dict(res) if isinstance(res, dict) else {"ip": "", "ok": False}
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_get_public_ip_failed", error=str(exc))
            return {"ip": "", "country": "", "region": "", "city": "", "org": "", "ok": False}

    def rotate_ip(self, serial: str = "", wait_seconds: float = 4.0) -> Tuple[bool, str, str, str]:
        """Trigger cellular IP rotation via ``mobile_adb.rotate_ip``."""
        if mobile_adb is None:
            return False, "", "", "mobile_adb module unavailable"
        try:
            # ASSUMPTION: mobile_adb.rotate_ip returns (success, old_ip, new_ip, message).
            return mobile_adb.rotate_ip(
                device_id=serial,
                wait_seconds=wait_seconds,
                custom_path=self.adb_path,
            )
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_rotate_ip_failed", serial=serial, error=str(exc))
            return False, "", "", str(exc)

    # ------------------------------------------------------------------
    # ADB Touch & Screen Capture
    # ------------------------------------------------------------------

    def tap(self, serial: str, x: int, y: int, duration_ms: int = 100) -> bool:
        """Execute an ADB tap (or short same-point swipe when duration > 120ms)."""
        if not serial or mobile_adb is None:
            return False
        try:
            ix, iy = int(x), int(y)
            dur = max(20, int(duration_ms))
            if dur > 120:
                cmd = ["-s", serial, "shell", "input", "swipe", str(ix), str(iy), str(ix), str(iy), str(dur)]
            else:
                cmd = ["-s", serial, "shell", "input", "tap", str(ix), str(iy)]
            code, out = mobile_adb.run_adb(cmd, custom_path=self.adb_path, timeout=8.0)
            if code != 0:
                log_event(logger, logging.WARNING, "phase1_adb_tap_failed", serial=serial, code=code, output=out)
                return False
            return True
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_adb_tap_exception", serial=serial, error=str(exc))
            return False

    def swipe(
        self,
        serial: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> bool:
        """Execute an ADB swipe gesture."""
        if not serial or mobile_adb is None:
            return False
        try:
            cmd = [
                "-s",
                serial,
                "shell",
                "input",
                "swipe",
                str(int(x1)),
                str(int(y1)),
                str(int(x2)),
                str(int(y2)),
                str(max(50, int(duration_ms))),
            ]
            code, out = mobile_adb.run_adb(cmd, custom_path=self.adb_path, timeout=10.0)
            if code != 0:
                log_event(logger, logging.WARNING, "phase1_adb_swipe_failed", serial=serial, code=code, output=out)
                return False
            return True
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_adb_swipe_exception", serial=serial, error=str(exc))
            return False

    def screenshot(self, serial: str) -> bytes:
        """Capture PNG screenshot bytes from *serial* via ADB exec-out.

        Raises:
            DeviceDisconnectedError: If *serial* is empty, ADB is unavailable,
                the command fails/times out, or the output is not valid PNG bytes.
        """
        if not serial or not str(serial).strip():
            raise DeviceDisconnectedError("ADB serial is required for screenshot capture")
        if mobile_adb is None:
            raise DeviceDisconnectedError(
                f"mobile_adb module unavailable; cannot capture screenshot from {serial}"
            )
        try:
            adb_bin = mobile_adb.get_adb_path(self.adb_path)
            res = subprocess.run(
                [adb_bin, "-s", serial, "exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8.0,
            )
            if res.returncode == 0 and res.stdout.startswith(b"\x89PNG"):
                return res.stdout
            stderr_msg = (res.stderr or b"").decode("utf-8", errors="replace").strip()
            reason = stderr_msg or f"returncode={res.returncode}, bytes={len(res.stdout)}"
            log_event(
                logger,
                logging.WARNING,
                "phase1_screenshot_invalid",
                serial=serial,
                reason=reason,
            )
            raise DeviceDisconnectedError(
                f"ADB screenshot invalid or device disconnected (serial={serial}: {reason})"
            )
        except DeviceDisconnectedError:
            raise
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_screenshot_failed", serial=serial, error=str(exc))
            raise DeviceDisconnectedError(
                f"ADB screenshot failed for serial={serial}: {exc}"
            ) from exc

    def dump_ui(self, serial: str) -> str:
        """Dump accessibility XML hierarchy from *serial* via uiautomator."""
        if not serial or mobile_adb is None:
            return '<hierarchy rotation="0"><node /></hierarchy>'
        try:
            code, out = mobile_adb.run_adb(
                ["-s", serial, "exec-out", "uiautomator", "dump", "/dev/tty"],
                custom_path=self.adb_path,
                timeout=8.0,
            )
            if code == 0 and "<hierarchy" in (out or ""):
                idx = out.find("<hierarchy")
                end_tag = "</hierarchy>"
                end_idx = out.rfind(end_tag, idx)
                if end_idx != -1:
                    return out[idx : end_idx + len(end_tag)]
                return out[idx:]
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_dump_ui_failed", serial=serial, error=str(exc))
        return '<hierarchy rotation="0"><node /></hierarchy>'

    # ------------------------------------------------------------------
    # Async Android CDP Bridge Wrappers
    # ------------------------------------------------------------------

    async def probe_cdp(self, host_port: int, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """Probe localhost CDP ``/json/version`` endpoint."""
        if android_cdp_bridge is None:
            return None
        try:
            # ASSUMPTION: android_cdp_bridge.probe_cdp_endpoint is async and returns dict | None.
            return await android_cdp_bridge.probe_cdp_endpoint(host_port, timeout=timeout)
        except Exception as exc:
            log_event(logger, logging.WARNING, "phase1_cdp_probe_failed", host_port=host_port, error=str(exc))
            return None

    async def connect_cdp(self, pw: Any, serial: str = "") -> Optional[Any]:
        """Connect Playwright to Android Chrome via ``AndroidCdpBridge``."""
        bridge = self.cdp_bridge
        if bridge is None:
            return None
        return await bridge.connect(pw, serial=serial)

    async def disconnect_cdp(
        self,
        session: Any,
        *,
        remove_forward: bool = True,
        keep_cookies: bool = True,
    ) -> None:
        """Close owned CDP targets and tear down port-forward safely."""
        bridge = self.cdp_bridge
        if bridge is None or session is None:
            return
        await bridge.disconnect(session, remove_forward=remove_forward, keep_cookies=keep_cookies)


class DeviceTouchCaptureBridge:
    """Binds ``Phase1DeviceAdapter`` to a specific ``serial`` as a Phase 1 touch+capture object.

    Satisfies both ``Phase1TouchInterface`` and ``Phase1CaptureInterface``.
    In paper mode (``paper=True``), ``tap`` and ``swipe`` are hard-blocked from
    dispatching real ADB commands.
    """

    def __init__(
        self,
        adapter: Phase1DeviceAdapter,
        serial: str,
        *,
        paper: bool = True,
    ) -> None:
        self._adapter = adapter
        self._serial = serial
        self._paper = bool(paper)
        self.executed_taps: List[Tuple[int, int, int]] = []
        self.executed_swipes: List[Tuple[int, int, int, int, int]] = []

    def tap(self, x: int, y: int, duration_ms: int = 100) -> None:
        if self._paper:
            raise RuntimeError("DeviceTouchCaptureBridge refused tap() in paper mode")
        ok = self._adapter.tap(self._serial, x, y, duration_ms=duration_ms)
        if not ok:
            raise RuntimeError(f"ADB tap failed on serial={self._serial}")
        self.executed_taps.append((int(x), int(y), int(duration_ms)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        if self._paper:
            raise RuntimeError("DeviceTouchCaptureBridge refused swipe() in paper mode")
        ok = self._adapter.swipe(self._serial, x1, y1, x2, y2, duration_ms=duration_ms)
        if not ok:
            raise RuntimeError(f"ADB swipe failed on serial={self._serial}")
        self.executed_swipes.append((int(x1), int(y1), int(x2), int(y2), int(duration_ms)))

    def screenshot(self) -> bytes:
        return self._adapter.screenshot(self._serial)

    def dump_ui(self) -> str:
        return self._adapter.dump_ui(self._serial)
