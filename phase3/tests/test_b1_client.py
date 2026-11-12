"""Unit tests for Phase 3 B1 PhoneAgentClient and Java LocalControlServer."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import socket
import struct
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

import mobile_adb
from phase3.b1_android import GestureGuardError, PhoneAgentClient
from phase3.config_loader import load_phase3_config

_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _MockWebSocketServer:
    """Minimal pure-stdlib RFC 6455 server on 127.0.0.1 for host unit tests."""

    def __init__(
        self,
        accessibility_connected: bool = True,
        auth_token: Optional[str] = None,
    ) -> None:
        self.accessibility_connected = accessibility_connected
        self.auth_token = auth_token
        self.commands: List[Dict[str, Any]] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port: int = int(self._sock.getsockname()[1])
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
            t.start()

    def _handle_conn(self, conn: socket.socket) -> None:
        with conn:
            buf = bytearray()
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf.extend(chunk)
            header_text = bytes(buf[: buf.index(b"\r\n\r\n")]).decode("latin-1")
            headers: Dict[str, str] = {}
            for line in header_text.split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            sec_key = headers.get("sec-websocket-key", "")
            if self.auth_token:
                client_token = headers.get("x-auth-token")
                if not client_token:
                    auth_hdr = headers.get("authorization", "")
                    if auth_hdr.lower().startswith("bearer "):
                        client_token = auth_hdr[7:].strip()
                if client_token != self.auth_token:
                    conn.sendall(b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n")
                    return

            accept = base64.b64encode(
                hashlib.sha1((sec_key + _WS_MAGIC).encode("ascii")).digest()
            ).decode("ascii")
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode("ascii")
            )

            while not self._stop.is_set():
                try:
                    b0, b1 = self._recv_exact(conn, 2)
                except OSError:
                    break
                opcode = b0 & 0x0F
                masked = (b1 & 0x80) != 0
                length = b1 & 0x7F
                if length == 126:
                    (length,) = struct.unpack("!H", self._recv_exact(conn, 2))
                elif length == 127:
                    (length,) = struct.unpack("!Q", self._recv_exact(conn, 8))
                mask = self._recv_exact(conn, 4) if masked else None
                payload = self._recv_exact(conn, length)
                if mask is not None:
                    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

                if opcode == 0x8:
                    self._send_text_or_ctrl(conn, 0x8, b"")
                    break
                if opcode == 0x9:
                    self._send_text_or_ctrl(conn, 0xA, payload)
                    continue
                if opcode != 0x1:
                    continue

                req = json.loads(payload.decode("utf-8"))
                self.commands.append(req)
                cmd = req.get("cmd")
                if cmd == "ping":
                    resp = {"ok": True, "cmd": "ping", "pong": True}
                elif cmd == "status":
                    resp = {
                        "ok": True,
                        "cmd": "status",
                        "server_running": True,
                        "port": self.port,
                        "accessibility_connected": self.accessibility_connected,
                        "details": "accessibility_ready"
                        if self.accessibility_connected
                        else "accessibility_not_enabled",
                    }
                elif cmd == "tap":
                    resp = {
                        "ok": self.accessibility_connected,
                        "cmd": "tap",
                        "x": req["x"],
                        "y": req["y"],
                        "duration_ms": req["duration_ms"],
                        "message": "completed"
                        if self.accessibility_connected
                        else "accessibility_service_not_connected",
                    }
                elif cmd == "scroll":
                    resp = {
                        "ok": self.accessibility_connected,
                        "cmd": "scroll",
                        "x1": req["x1"],
                        "y1": req["y1"],
                        "x2": req["x2"],
                        "y2": req["y2"],
                        "duration_ms": req["duration_ms"],
                        "message": "completed"
                        if self.accessibility_connected
                        else "accessibility_service_not_connected",
                    }
                else:
                    resp = {"ok": False, "error": f"unknown_cmd:{cmd}"}

                self._send_text_or_ctrl(
                    conn, 0x1, json.dumps(resp).encode("utf-8")
                )

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            chunk = conn.recv(n - len(out))
            if not chunk:
                raise EOFError("closed")
            out.extend(chunk)
        return bytes(out)

    @staticmethod
    def _send_text_or_ctrl(conn: socket.socket, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | (opcode & 0x0F)])
        length = len(payload)
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        conn.sendall(bytes(header) + payload)


def test_websocket_handshake_status_tap_scroll_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    srv = _MockWebSocketServer(accessibility_connected=True)
    adb_calls: List[List[str]] = []

    def fake_run_adb(args: list[str], custom_path: str = "", timeout: float = 12.0) -> Tuple[int, str]:
        adb_calls.append(list(args))
        return 0, ""

    monkeypatch.setattr(mobile_adb, "run_adb", fake_run_adb)
    cfg = load_phase3_config()

    client = PhoneAgentClient(serial="TESTDEV01", host_port=srv.port, cfg=cfg)
    try:
        assert client.connect() is True
        assert client.transport == "websocket"
        assert adb_calls[0][:2] == ["-s", "TESTDEV01"]
        assert adb_calls[0][2:] == ["forward", f"tcp:{srv.port}", f"tcp:{cfg.b1_android.device_listen_port}"]

        st = client.status()
        assert st["ok"] is True
        assert st["accessibility_connected"] is True
        assert st["transport"] == "websocket"

        tap_res = client.tap(420, 810, duration_ms=90)
        assert tap_res["ok"] is True
        assert tap_res["executed"] is True
        assert tap_res["transport"] == "websocket"

        swipe_res = client.swipe(300, 1200, 300, 350, duration_ms=420)
        assert swipe_res["ok"] is True
        assert swipe_res["executed"] is True
        assert swipe_res["transport"] == "websocket"

        assert [c["cmd"] for c in srv.commands] == ["status", "tap", "scroll"]
        assert srv.commands[1] == {"cmd": "tap", "x": 420, "y": 810, "duration_ms": 90}
        assert srv.commands[2] == {
            "cmd": "scroll",
            "x1": 300,
            "y1": 1200,
            "x2": 300,
            "y2": 350,
            "duration_ms": 420,
        }
    finally:
        client.close()
        srv.close()

    assert any(
        c == ["-s", "TESTDEV01", "forward", "--remove", f"tcp:{srv.port}"]
        for c in adb_calls
    )


def test_adb_fallback_when_apk_absent_or_ws_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bind and close an ephemeral socket so connection is guaranteed refused.
    tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tmp_sock.bind(("127.0.0.1", 0))
    closed_port = int(tmp_sock.getsockname()[1])
    tmp_sock.close()

    adb_calls: List[List[str]] = []

    def fake_run_adb(args: list[str], custom_path: str = "", timeout: float = 12.0) -> Tuple[int, str]:
        adb_calls.append(list(args))
        if "pm" in args and "path" in args:
            return 1, ""
        return 0, ""

    monkeypatch.setattr(mobile_adb, "run_adb", fake_run_adb)
    cfg = load_phase3_config()

    client = PhoneAgentClient(
        serial="TESTDEV02",
        host_port=closed_port,
        cfg=cfg,
        adb_fallback=True,
    )
    assert client.connect() is False
    assert client.transport == "adb_fallback"

    st = client.status()
    assert st["ok"] is False
    assert st["apk_installed"] is False

    tap_res = client.tap(210, 650)
    assert tap_res["ok"] is True
    assert tap_res["executed"] is True
    assert tap_res["transport"] == "adb_fallback"

    swipe_res = client.swipe(350, 1100, 350, 300, duration_ms=500)
    assert swipe_res["ok"] is True
    assert swipe_res["executed"] is True
    assert swipe_res["transport"] == "adb_fallback"

    assert ["-s", "TESTDEV02", "shell", "input", "tap", "210", "650"] in adb_calls
    assert [
        "-s",
        "TESTDEV02",
        "shell",
        "input",
        "swipe",
        "350",
        "1100",
        "350",
        "300",
        "500",
    ] in adb_calls

    # With fallback disabled, unreachable WS must refuse/fail cleanly without ADB input calls.
    adb_calls.clear()
    strict_client = PhoneAgentClient(
        serial="TESTDEV02",
        host_port=closed_port,
        cfg=cfg,
        adb_fallback=False,
    )
    assert strict_client.connect() is False
    fail_tap = strict_client.tap(100, 200)
    assert fail_tap["ok"] is False
    assert fail_tap["executed"] is False
    assert not any("input" in c for c in adb_calls)


def test_safety_guardrails_block_unverified_gestures(monkeypatch: pytest.MonkeyPatch) -> None:
    srv = _MockWebSocketServer(accessibility_connected=True)
    adb_calls: List[List[str]] = []

    def fake_run_adb(args: list[str], custom_path: str = "", timeout: float = 12.0) -> Tuple[int, str]:
        adb_calls.append(list(args))
        return 0, ""

    monkeypatch.setattr(mobile_adb, "run_adb", fake_run_adb)
    client = PhoneAgentClient(serial="TESTDEV03", host_port=srv.port)
    try:
        assert client.connect() is True

        # Gated helper requires BOTH a4_verified_bbox=True and a2_ok=True.
        r1 = client.dispatch_gesture("tap", x=120, y=340)
        assert r1["ok"] is False
        assert r1["refused"] is True
        assert r1["executed"] is False

        r2 = client.dispatch_gesture("tap", x=120, y=340, a4_verified_bbox=True, a2_ok=False)
        assert r2["ok"] is False
        assert r2["refused"] is True
        assert r2["reason"] == "a2_ok_required"

        r3 = client.dispatch_gesture("tap", x=120, y=340, a4_verified_bbox=False, a2_ok=True)
        assert r3["ok"] is False
        assert r3["refused"] is True
        assert r3["reason"] == "a4_verified_bbox_required"

        # Direct tap/swipe also enforce explicit False guard params.
        r4 = client.tap(120, 340, a4_verified_bbox=False, a2_ok=True)
        assert r4["ok"] is False
        assert r4["refused"] is True

        r5 = client.swipe(100, 800, 100, 200, a4_verified_bbox=True, a2_ok=False)
        assert r5["ok"] is False
        assert r5["refused"] is True

        with pytest.raises(GestureGuardError):
            client.dispatch_gesture(
                "tap", x=120, y=340, a4_verified_bbox=False, a2_ok=True, raise_on_refusal=True
            )

        # Confirm zero commands were sent to the server while blocked.
        assert srv.commands == []

        # Verified call passes through cleanly.
        r_ok = client.dispatch_gesture(
            "tap", x=120, y=340, duration_ms=75, a4_verified_bbox=True, a2_ok=True
        )
        assert r_ok["ok"] is True
        assert r_ok["executed"] is True
        assert len(srv.commands) == 1
        assert srv.commands[0] == {"cmd": "tap", "x": 120, "y": 340, "duration_ms": 75}
    finally:
        client.close()
        srv.close()


def test_java_local_control_server_interop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compile and boot the real Java LocalControlServer and drive it via PhoneAgentClient."""
    if not shutil.which("javac") or not shutil.which("java"):
        pytest.skip("javac/java not available on PATH")

    java_src = (
        Path(__file__).resolve().parents[1]
        / "b1_android"
        / "apk"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "adsterra"
        / "phoneagent"
        / "LocalControlServer.java"
    )
    assert java_src.is_file()

    harness = tmp_path / "Harness.java"
    harness.write_text(
        """
import com.adsterra.phoneagent.LocalControlServer;

public class Harness {
    public static void main(String[] args) throws Exception {
        LocalControlServer server = new LocalControlServer(0, new LocalControlServer.CommandHandler() {
            @Override
            public LocalControlServer.StatusResult onStatus() {
                return new LocalControlServer.StatusResult(true, "harness_ready");
            }
            @Override
            public LocalControlServer.GestureResult onTap(float x, float y, long durationMs) {
                return new LocalControlServer.GestureResult(true, "tap_ok");
            }
            @Override
            public LocalControlServer.GestureResult onScroll(
                    float x1, float y1, float x2, float y2, long durationMs) {
                return new LocalControlServer.GestureResult(true, "scroll_ok");
            }
        });
        server.start();
        System.out.println("PORT=" + server.getPort());
        System.out.flush();
        Thread.sleep(15000);
        server.stop();
    }
}
""".strip(),
        encoding="utf-8",
    )

    subprocess.run(
        ["javac", "-d", str(tmp_path), str(java_src), str(harness)],
        check=True,
        capture_output=True,
        text=True,
    )

    proc = subprocess.Popen(
        ["java", "-cp", str(tmp_path), "Harness"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line.startswith("PORT="), f"Unexpected Java harness output: {line}"
        port = int(line.split("=", 1)[1])

        monkeypatch.setattr(mobile_adb, "run_adb", lambda args, **kw: (0, ""))
        client = PhoneAgentClient(serial="JAVA_HARNESS", host_port=port)
        try:
            assert client.connect() is True
            assert client.ping()["pong"] is True
            st = client.status()
            assert st["ok"] is True
            assert st["accessibility_connected"] is True
            tap = client.dispatch_gesture(
                "tap", x=500, y=900, duration_ms=80, a4_verified_bbox=True, a2_ok=True
            )
            assert tap["ok"] is True
            assert tap["message"] == "tap_ok"
            scroll = client.dispatch_gesture(
                "scroll",
                x1=300,
                y1=1000,
                x2=300,
                y2=300,
                duration_ms=400,
                a4_verified_bbox=True,
                a2_ok=True,
            )
            assert scroll["ok"] is True
            assert scroll["message"] == "scroll_ok"
        finally:
            client.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_android_websocket_authentication_token_security(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure unauthorized apps without a matching auth token cannot control the phone."""
    secret_token = "secure_android_phone_token_xyz123"
    srv = _MockWebSocketServer(accessibility_connected=True, auth_token=secret_token)
    try:
        monkeypatch.setattr(mobile_adb, "run_adb", lambda args, **kw: (0, ""))

        # 1. Unauthorized client with missing or wrong token -> connection refused / fails
        unauthorized = PhoneAgentClient(serial="DEV_UNAUTH", host_port=srv.port, adb_fallback=False)
        unauthorized.auth_token = "wrong_token"
        assert unauthorized.connect() is False
        assert unauthorized.connected is False

        # 2. Authorized client with correct token -> connects cleanly and executes
        authorized = PhoneAgentClient(serial="DEV_AUTH", host_port=srv.port, adb_fallback=False)
        authorized.auth_token = secret_token
        assert authorized.connect() is True
        assert authorized.connected is True
        ping = authorized.ping()
        assert ping["ok"] is True
        assert ping["pong"] is True

        tap = authorized.dispatch_gesture("tap", x=100, y=200, duration_ms=60, a4_verified_bbox=True, a2_ok=True)
        assert tap["ok"] is True
        assert tap["executed"] is True
    finally:
        srv.close()
