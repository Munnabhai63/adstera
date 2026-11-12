"""Host client adapter for the Phase 3 B1 Android PhoneAgent APK.

Manages ``adb -s <serial> forward tcp:<host_port> tcp:<device_listen_port>``
and communicates over a pure-stdlib RFC 6455 WebSocket channel on localhost.
Enforces A4 bbox and A2 health safety guardrails before dispatching gestures
and gracefully falls back to ``mobile_adb.run_adb`` shell input when enabled.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import socket
import struct
import threading
from typing import Any, Callable, Dict, Optional, Tuple

import mobile_adb
from phase3.config_loader import (
    B1AndroidConfig,
    Phase3Config,
    SafetyConfig,
    load_phase3_config,
)
from phase3.logging_utils import get_correlation_id, log_event

logger = logging.getLogger("phase3.b1_android")

_WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_LOOPBACK_HOST = "127.0.0.1"


class GestureGuardError(PermissionError):
    """Raised when a safety guardrail blocks a gesture dispatch."""


def _extract_configs(
    cfg: Optional[Phase3Config | B1AndroidConfig | Dict[str, Any]]
) -> Tuple[B1AndroidConfig, SafetyConfig]:
    """Normalize config argument into (B1AndroidConfig, SafetyConfig)."""
    if cfg is None:
        loaded = load_phase3_config()
        return loaded.b1_android, loaded.safety

    if isinstance(cfg, Phase3Config):
        return cfg.b1_android, cfg.safety

    if isinstance(cfg, B1AndroidConfig):
        return cfg, load_phase3_config().safety

    if isinstance(cfg, dict):
        base = load_phase3_config()
        b1_raw = cfg.get("b1_android", cfg)
        if isinstance(b1_raw, dict):
            for k, v in b1_raw.items():
                if hasattr(base.b1_android, k):
                    setattr(base.b1_android, k, v)
        safety_raw = cfg.get("safety")
        if isinstance(safety_raw, dict):
            for k, v in safety_raw.items():
                if hasattr(base.safety, k):
                    setattr(base.safety, k, v)
        return base.b1_android, base.safety

    loaded = load_phase3_config()
    return loaded.b1_android, loaded.safety


def _clamp_int(value: Optional[int], low: int, high: int) -> int:
    if value is None:
        return (int(low) + int(high)) // 2
    v = int(value)
    if v < int(low):
        return int(low)
    if v > int(high):
        return int(high)
    return v


class PhoneAgentClient:
    """Client for driving the B1 Android PhoneAgent APK over ADB-forwarded WebSocket."""

    def __init__(
        self,
        serial: str = "",
        host_port: Optional[int] = None,
        cfg: Optional[Phase3Config | B1AndroidConfig | Dict[str, Any]] = None,
        adb_fallback: Optional[bool] = None,
        adb_runner: Optional[Callable[..., Tuple[int, str]]] = None,
    ) -> None:
        self.b1_cfg, self.safety_cfg = _extract_configs(cfg)
        self.serial = (serial or "").strip()
        self.host_port = (
            int(host_port) if host_port is not None else int(self.b1_cfg.host_port_base)
        )
        self.adb_fallback = (
            bool(adb_fallback)
            if adb_fallback is not None
            else bool(self.b1_cfg.fallback_to_adb)
        )
        self._adb_runner = adb_runner
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._forward_active = False
        self._transport = "disconnected"

    @property
    def transport(self) -> str:
        return self._transport

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def __enter__(self) -> "PhoneAgentClient":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _run_adb(self, args: list[str], timeout: Optional[float] = None) -> Tuple[int, str]:
        runner = self._adb_runner if self._adb_runner is not None else mobile_adb.run_adb
        adb_args = (["-s", self.serial] + args) if self.serial else list(args)
        eff_timeout = (
            float(timeout)
            if timeout is not None
            else float(self.b1_cfg.command_timeout_seconds)
        )
        try:
            return runner(adb_args, timeout=eff_timeout)
        except TypeError:
            return runner(adb_args)

    def _close_socket(self) -> None:
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                self._send_ws_frame(sock, 0x8, b"")
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

    def connect(self, correlation_id: Optional[str] = None) -> bool:
        """Set up ``adb forward`` and establish RFC 6455 WebSocket connection."""
        cid = correlation_id or get_correlation_id()
        if not self.b1_cfg.enabled:
            self._transport = "adb_fallback" if self.adb_fallback else "disabled"
            log_event(
                logger,
                logging.INFO,
                "b1_client_disabled",
                correlation_id=cid,
                serial=self.serial,
                transport=self._transport,
            )
            return False

        with self._lock:
            self._close_socket()
            rc, out = self._run_adb(
                [
                    "forward",
                    f"tcp:{self.host_port}",
                    f"tcp:{int(self.b1_cfg.device_listen_port)}",
                ],
                timeout=float(self.b1_cfg.connect_timeout_seconds),
            )
            if rc != 0:
                self._forward_active = False
                self._transport = "adb_fallback" if self.adb_fallback else "disconnected"
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_adb_forward_failed",
                    correlation_id=cid,
                    serial=self.serial,
                    host_port=self.host_port,
                    rc=rc,
                    output=out,
                    fallback=self.adb_fallback,
                )
                return False

            self._forward_active = True
            try:
                sock = socket.create_connection(
                    (_LOOPBACK_HOST, self.host_port),
                    timeout=float(self.b1_cfg.connect_timeout_seconds),
                )
                sock.settimeout(float(self.b1_cfg.command_timeout_seconds))
                self._ws_handshake(sock)
                self._sock = sock
                self._transport = "websocket"
                log_event(
                    logger,
                    logging.INFO,
                    "b1_ws_connected",
                    correlation_id=cid,
                    serial=self.serial,
                    host_port=self.host_port,
                    device_port=int(self.b1_cfg.device_listen_port),
                )
                return True
            except Exception as exc:
                self._close_socket()
                self._transport = "adb_fallback" if self.adb_fallback else "disconnected"
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_ws_connect_failed",
                    correlation_id=cid,
                    serial=self.serial,
                    host_port=self.host_port,
                    error=str(exc),
                    fallback=self.adb_fallback,
                )
                return False

    def close(self) -> None:
        """Close WebSocket connection and remove ADB forward rule best-effort."""
        with self._lock:
            self._close_socket()
            if self._forward_active:
                self._forward_active = False
                try:
                    self._run_adb(
                        ["forward", "--remove", f"tcp:{self.host_port}"],
                        timeout=float(self.b1_cfg.connect_timeout_seconds),
                    )
                except Exception:
                    pass
            self._transport = "disconnected"

    def _ws_handshake(self, sock: socket.socket) -> None:
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {_LOOPBACK_HOST}:{self.host_port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))

        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("EOF during WebSocket handshake")
            buf.extend(chunk)
            if len(buf) > 16384:
                raise ValueError("Handshake response headers exceeded 16KB")

        header_end = buf.index(b"\r\n\r\n")
        raw_headers = bytes(buf[:header_end]).decode("latin-1")
        lines = raw_headers.split("\r\n")
        if not lines or "101" not in lines[0]:
            raise ConnectionError(f"Unexpected WebSocket handshake status: {lines[0] if lines else ''}")

        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        expected_accept = base64.b64encode(
            hashlib.sha1((sec_key + _WS_MAGIC_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if headers.get("sec-websocket-accept") != expected_accept:
            raise ConnectionError("Invalid Sec-WebSocket-Accept header")

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < n:
            part = sock.recv(n - len(chunks))
            if not part:
                raise ConnectionError("Unexpected EOF on WebSocket stream")
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    def _send_ws_frame(sock: socket.socket, opcode: int, payload: bytes) -> None:
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        length = len(payload)
        mask_bit = 0x80  # Client-to-server frames MUST be masked per RFC 6455.
        if length <= 125:
            header.append(mask_bit | length)
        elif length <= 65535:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", length))

        mask_key = os.urandom(4)
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        sock.sendall(bytes(header) + masked)

    def _recv_ws_frame(self, sock: socket.socket) -> Tuple[int, bytes]:
        while True:
            b0, b1 = self._recv_exact(sock, 2)
            opcode = b0 & 0x0F
            masked = (b1 & 0x80) != 0
            length = b1 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._recv_exact(sock, 2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._recv_exact(sock, 8))

            mask_key = self._recv_exact(sock, 4) if masked else None
            payload = self._recv_exact(sock, length)
            if mask_key is not None:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == 0x9:  # Ping -> Pong
                self._send_ws_frame(sock, 0xA, payload)
                continue
            if opcode == 0xA:  # Pong
                continue
            if opcode == 0x8:  # Close
                raise ConnectionError("WebSocket closed by peer")
            return opcode, payload

    def _ws_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            sock = self._sock
            if sock is None:
                raise ConnectionError("WebSocket is not connected")
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self._send_ws_frame(sock, 0x1, encoded)
            opcode, resp_bytes = self._recv_ws_frame(sock)
            if opcode != 0x1:
                raise ValueError(f"Expected text frame, got opcode={opcode}")
            data = json.loads(resp_bytes.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("WebSocket response must be a JSON object")
            return data

    def _check_guardrails(
        self,
        a4_verified_bbox: Optional[bool],
        a2_ok: Optional[bool],
        *,
        require_explicit: bool,
        correlation_id: str,
        gesture_type: str,
    ) -> Optional[Dict[str, Any]]:
        if self.safety_cfg.require_a4_bbox_for_gesture:
            blocked_a4 = (not bool(a4_verified_bbox)) if require_explicit else (a4_verified_bbox is False)
            if blocked_a4:
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_gesture_refused_guardrail",
                    correlation_id=correlation_id,
                    serial=self.serial,
                    gesture=gesture_type,
                    reason="a4_verified_bbox_false",
                )
                return {
                    "ok": False,
                    "executed": False,
                    "refused": True,
                    "transport": "guard",
                    "reason": "a4_verified_bbox_required",
                }

        if self.safety_cfg.require_a2_ok_for_gesture:
            blocked_a2 = (not bool(a2_ok)) if require_explicit else (a2_ok is False)
            if blocked_a2:
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_gesture_refused_guardrail",
                    correlation_id=correlation_id,
                    serial=self.serial,
                    gesture=gesture_type,
                    reason="a2_ok_false",
                )
                return {
                    "ok": False,
                    "executed": False,
                    "refused": True,
                    "transport": "guard",
                    "reason": "a2_ok_required",
                }

        return None

    def ping(self) -> Dict[str, Any]:
        """Ping the local PhoneAgent WebSocket server."""
        if self._sock is None and not self.connect():
            return {"ok": False, "transport": self._transport, "error": "not_connected"}
        try:
            resp = self._ws_request({"cmd": "ping"})
            resp.setdefault("transport", "websocket")
            return resp
        except Exception as exc:
            self._close_socket()
            return {"ok": False, "transport": "websocket", "error": str(exc)}

    def status(self) -> Dict[str, Any]:
        """Return WebSocket server + accessibility service status, or ADB package probe."""
        if self._sock is not None:
            try:
                resp = self._ws_request({"cmd": "status"})
                resp["transport"] = "websocket"
                resp["serial"] = self.serial
                resp["host_port"] = self.host_port
                return resp
            except Exception as exc:
                self._close_socket()
                self._transport = "adb_fallback" if self.adb_fallback else "disconnected"
                return {
                    "ok": False,
                    "transport": self._transport,
                    "serial": self.serial,
                    "error": str(exc),
                }

        pkg_installed = False
        if self.adb_fallback:
            rc, out = self._run_adb(["shell", "pm", "path", self.b1_cfg.package_name])
            pkg_installed = (rc == 0) and bool(out.strip())
        return {
            "ok": False,
            "connected": False,
            "transport": self._transport,
            "serial": self.serial,
            "host_port": self.host_port,
            "apk_installed": pkg_installed,
            "adb_fallback": self.adb_fallback,
        }

    def tap(
        self,
        x: float,
        y: float,
        duration_ms: Optional[int] = None,
        *,
        a4_verified_bbox: Optional[bool] = None,
        a2_ok: Optional[bool] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a tap gesture via WebSocket, falling back to ADB ``input tap``."""
        cid = correlation_id or get_correlation_id()
        refused = self._check_guardrails(
            a4_verified_bbox,
            a2_ok,
            require_explicit=False,
            correlation_id=cid,
            gesture_type="tap",
        )
        if refused is not None:
            return refused

        dur = _clamp_int(
            duration_ms,
            self.b1_cfg.gesture_min_duration_ms,
            self.b1_cfg.gesture_max_duration_ms,
        )
        px = int(round(float(x)))
        py = int(round(float(y)))

        if self._sock is not None:
            try:
                resp = self._ws_request(
                    {"cmd": "tap", "x": px, "y": py, "duration_ms": dur}
                )
                ok = bool(resp.get("ok", False))
                if ok:
                    resp["executed"] = True
                    resp["transport"] = "websocket"
                    return resp
                # If AccessibilityService is unbound on device, optionally fall back to ADB.
                if not self.adb_fallback:
                    resp["executed"] = False
                    resp["transport"] = "websocket"
                    return resp
            except Exception as exc:
                self._close_socket()
                self._transport = "adb_fallback" if self.adb_fallback else "disconnected"
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_ws_tap_failed",
                    correlation_id=cid,
                    serial=self.serial,
                    error=str(exc),
                )
                if not self.adb_fallback:
                    return {
                        "ok": False,
                        "executed": False,
                        "transport": "websocket",
                        "error": str(exc),
                    }

        if not self.adb_fallback:
            return {
                "ok": False,
                "executed": False,
                "transport": self._transport,
                "error": "websocket_unavailable_and_fallback_disabled",
            }

        rc, out = self._run_adb(["shell", "input", "tap", str(px), str(py)])
        log_event(
            logger,
            logging.INFO if rc == 0 else logging.WARNING,
            "b1_adb_fallback_tap",
            correlation_id=cid,
            serial=self.serial,
            x=px,
            y=py,
            rc=rc,
        )
        return {
            "ok": rc == 0,
            "executed": rc == 0,
            "transport": "adb_fallback",
            "cmd": "tap",
            "x": px,
            "y": py,
            "duration_ms": dur,
            "output": out,
        }

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration_ms: Optional[int] = None,
        *,
        a4_verified_bbox: Optional[bool] = None,
        a2_ok: Optional[bool] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a swipe/scroll gesture via WebSocket, falling back to ADB ``input swipe``."""
        cid = correlation_id or get_correlation_id()
        refused = self._check_guardrails(
            a4_verified_bbox,
            a2_ok,
            require_explicit=False,
            correlation_id=cid,
            gesture_type="swipe",
        )
        if refused is not None:
            return refused

        dur = _clamp_int(
            duration_ms,
            self.b1_cfg.scroll_min_duration_ms,
            self.b1_cfg.scroll_max_duration_ms,
        )
        px1, py1, px2, py2 = (
            int(round(float(x1))),
            int(round(float(y1))),
            int(round(float(x2))),
            int(round(float(y2))),
        )

        if self._sock is not None:
            try:
                resp = self._ws_request(
                    {
                        "cmd": "scroll",
                        "x1": px1,
                        "y1": py1,
                        "x2": px2,
                        "y2": py2,
                        "duration_ms": dur,
                    }
                )
                ok = bool(resp.get("ok", False))
                if ok:
                    resp["executed"] = True
                    resp["transport"] = "websocket"
                    return resp
                if not self.adb_fallback:
                    resp["executed"] = False
                    resp["transport"] = "websocket"
                    return resp
            except Exception as exc:
                self._close_socket()
                self._transport = "adb_fallback" if self.adb_fallback else "disconnected"
                log_event(
                    logger,
                    logging.WARNING,
                    "b1_ws_swipe_failed",
                    correlation_id=cid,
                    serial=self.serial,
                    error=str(exc),
                )
                if not self.adb_fallback:
                    return {
                        "ok": False,
                        "executed": False,
                        "transport": "websocket",
                        "error": str(exc),
                    }

        if not self.adb_fallback:
            return {
                "ok": False,
                "executed": False,
                "transport": self._transport,
                "error": "websocket_unavailable_and_fallback_disabled",
            }

        rc, out = self._run_adb(
            ["shell", "input", "swipe", str(px1), str(py1), str(px2), str(py2), str(dur)]
        )
        log_event(
            logger,
            logging.INFO if rc == 0 else logging.WARNING,
            "b1_adb_fallback_swipe",
            correlation_id=cid,
            serial=self.serial,
            x1=px1,
            y1=py1,
            x2=px2,
            y2=py2,
            duration_ms=dur,
            rc=rc,
        )
        return {
            "ok": rc == 0,
            "executed": rc == 0,
            "transport": "adb_fallback",
            "cmd": "scroll",
            "x1": px1,
            "y1": py1,
            "x2": px2,
            "y2": py2,
            "duration_ms": dur,
            "output": out,
        }

    def scroll(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration_ms: Optional[int] = None,
        *,
        a4_verified_bbox: Optional[bool] = None,
        a2_ok: Optional[bool] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for ``swipe``."""
        return self.swipe(
            x1,
            y1,
            x2,
            y2,
            duration_ms=duration_ms,
            a4_verified_bbox=a4_verified_bbox,
            a2_ok=a2_ok,
            correlation_id=correlation_id,
        )

    def dispatch_gesture(
        self,
        gesture_type: str,
        *,
        x: Optional[float] = None,
        y: Optional[float] = None,
        x1: Optional[float] = None,
        y1: Optional[float] = None,
        x2: Optional[float] = None,
        y2: Optional[float] = None,
        duration_ms: Optional[int] = None,
        a4_verified_bbox: bool = False,
        a2_ok: bool = False,
        correlation_id: Optional[str] = None,
        raise_on_refusal: bool = False,
    ) -> Dict[str, Any]:
        """Gated gesture dispatcher requiring explicit A4 bbox and A2 OK flags."""
        cid = correlation_id or get_correlation_id()
        kind = (gesture_type or "").strip().lower()
        refused = self._check_guardrails(
            a4_verified_bbox,
            a2_ok,
            require_explicit=True,
            correlation_id=cid,
            gesture_type=kind or "unknown",
        )
        if refused is not None:
            if raise_on_refusal:
                raise GestureGuardError(refused["reason"])
            return refused

        if kind == "tap":
            if x is None or y is None:
                return {"ok": False, "executed": False, "error": "missing_tap_coordinates"}
            return self.tap(
                x,
                y,
                duration_ms=duration_ms,
                a4_verified_bbox=a4_verified_bbox,
                a2_ok=a2_ok,
                correlation_id=cid,
            )

        if kind in ("swipe", "scroll"):
            if None in (x1, y1, x2, y2):
                return {"ok": False, "executed": False, "error": "missing_swipe_coordinates"}
            return self.swipe(
                float(x1),  # type: ignore[arg-type]
                float(y1),  # type: ignore[arg-type]
                float(x2),  # type: ignore[arg-type]
                float(y2),  # type: ignore[arg-type]
                duration_ms=duration_ms,
                a4_verified_bbox=a4_verified_bbox,
                a2_ok=a2_ok,
                correlation_id=cid,
            )

        return {"ok": False, "executed": False, "error": f"unsupported_gesture:{kind}"}

    # Async convenience wrappers for async orchestrators
    async def aconnect(self, correlation_id: Optional[str] = None) -> bool:
        return await asyncio.to_thread(self.connect, correlation_id)

    async def astatus(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.status)

    async def atap(
        self,
        x: float,
        y: float,
        duration_ms: Optional[int] = None,
        *,
        a4_verified_bbox: Optional[bool] = None,
        a2_ok: Optional[bool] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.tap,
            x,
            y,
            duration_ms,
            a4_verified_bbox=a4_verified_bbox,
            a2_ok=a2_ok,
            correlation_id=correlation_id,
        )

    async def aswipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration_ms: Optional[int] = None,
        *,
        a4_verified_bbox: Optional[bool] = None,
        a2_ok: Optional[bool] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.swipe,
            x1,
            y1,
            x2,
            y2,
            duration_ms,
            a4_verified_bbox=a4_verified_bbox,
            a2_ok=a2_ok,
            correlation_id=correlation_id,
        )

    async def adispatch_gesture(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(self.dispatch_gesture, *args, **kwargs)

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)
