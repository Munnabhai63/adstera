"""
android_cdp_bridge.py — Real Android Chrome ADB DevTools Bridge (B3).

Discovers listening DevTools Unix abstract sockets on USB-connected Android
devices via `/proc/net/unix`, maintains crash-safe port-forward ownership in
`state/adb_forwards.json`, probes `/json/version` & `/json/list` without host
proxy interference, attaches via Playwright `connect_over_cdp()`, reads real
device telemetry via an IsolatedWorld (without enabling CDP `Runtime.enable`),
and closes only automation-owned tabs cleanly (preserving personal tabs/FTUE).
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import Browser, BrowserContext, Page, Playwright

import mobile_adb

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.resolve()
STATE_DIR = BASE_DIR / "state"
FORWARD_STATE_FILE = STATE_DIR / "adb_forwards.json"
OWNED_TARGETS_FILE = STATE_DIR / "adb_owned_targets.json"

DEFAULT_PORT_MIN = 9222
DEFAULT_PORT_MAX = 9299
ADB_DAEMON_PORT = 5037
SO_ACCEPTCON = 0x00010000
SOCK_STREAM = 1
SS_UNCONNECTED = 1


@dataclass
class UnixSocketEntry:
    """Parsed entry from Android `/proc/net/unix`."""

    num: str
    ref_count: int
    protocol: int
    flags: int
    sock_type: int
    state: int
    inode: int
    path: str

    @property
    def socket_name(self) -> str:
        return self.path.lstrip("@")

    @property
    def is_listening(self) -> bool:
        return (
            self.sock_type == SOCK_STREAM
            and self.state == SS_UNCONNECTED
            and bool(self.flags & SO_ACCEPTCON)
        )


@dataclass
class AndroidCdpSession:
    """Live Playwright CDP connection to real Android Chrome."""

    serial: str
    host_port: int
    remote_socket: str
    ws_url: str
    browser_version: str
    user_agent: str
    browser: Browser
    context: BrowserContext
    owned_target_ids: list[str] = field(default_factory=list)
    visited_origins: set[str] = field(default_factory=set)
    adb_path: str = ""
    _dedicated_device: bool = False


def parse_proc_net_unix(
    raw: str,
    preferred_prefix: str = "chrome_devtools_remote",
) -> list[UnixSocketEntry]:
    """
    Parse `/proc/net/unix` output cleanly and return listening `@` abstract
    DevTools sockets prioritized by exact match to `preferred_prefix`.
    """
    entries: list[UnixSocketEntry] = []
    seen_paths: set[str] = set()
    pref = (preferred_prefix or "chrome_devtools_remote").strip().lstrip("@")

    for raw_line in (raw or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Num "):
            continue
        parts = line.split(maxsplit=7)
        if len(parts) < 8:
            continue
        num, ref_s, proto_s, flags_s, type_s, state_s, inode_s, path_s = parts
        path = path_s.strip()
        if not path.startswith("@") or path in seen_paths:
            continue
        try:
            entry = UnixSocketEntry(
                num=num,
                ref_count=int(ref_s, 16),
                protocol=int(proto_s, 16),
                flags=int(flags_s, 16),
                sock_type=int(type_s, 16),
                state=int(state_s, 16),
                inode=int(inode_s, 10),
                path=path,
            )
        except ValueError:
            continue

        if not entry.is_listening:
            continue
        sock_name = entry.socket_name
        if pref == sock_name or pref in sock_name or "chrome_devtools_remote" in sock_name:
            seen_paths.add(path)
            entries.append(entry)

    def _priority(item: UnixSocketEntry) -> tuple[int, int, str]:
        name = item.socket_name
        if name == pref:
            return (0, len(name), name)
        if name.startswith(pref):
            return (1, len(name), name)
        if name == "chrome_devtools_remote":
            return (2, len(name), name)
        return (3, len(name), name)

    entries.sort(key=_priority)
    return entries


def _is_pid_alive(pid: int) -> bool:
    """Check cross-platform whether an OS PID still exists."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            err = ctypes.GetLastError()
            return err == 5  # ACCESS_DENIED implies process exists
        try:
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok and exit_code.value == STILL_ACTIVE)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _load_json_dict(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_json_dict(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _record_owned_target(
    serial: str,
    target_id: str,
    url: str = "about:blank",
    state_file: Path = OWNED_TARGETS_FILE,
) -> None:
    if not target_id:
        return
    data = _load_json_dict(state_file)
    data[target_id] = {
        "serial": serial,
        "target_id": target_id,
        "url": url,
        "owner_pid": os.getpid(),
        "created_at": time.time(),
    }
    _save_json_dict(state_file, data)


def _forget_owned_target(target_id: str, state_file: Path = OWNED_TARGETS_FILE) -> None:
    if not target_id or not state_file.exists():
        return
    data = _load_json_dict(state_file)
    if target_id in data:
        data.pop(target_id, None)
        _save_json_dict(state_file, data)


def _parse_forward_list(raw: str) -> list[dict[str, str]]:
    """Parse lines from `adb forward --list`."""
    items: list[dict[str, str]] = []
    for line in (raw or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 3:
            items.append({"serial": parts[0], "local": parts[1], "remote": parts[2]})
    return items


def _port_from_forward_spec(local_spec: str) -> Optional[int]:
    m = re.match(r"^tcp:(\d+)$", (local_spec or "").strip())
    return int(m.group(1)) if m else None


def _is_localhost_port_free(port: int) -> bool:
    if port == ADB_DAEMON_PORT:
        return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.2)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return False
    except OSError:
        pass
    finally:
        probe.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


async def probe_cdp_endpoint(host_port: int, timeout: float = 3.0) -> Optional[dict[str, Any]]:
    """
    Verify DevTools HTTP server responsiveness on `127.0.0.1:<host_port>`.
    Requires both `/json/version` (with `webSocketDebuggerUrl`) and `/json/list`.
    """
    base = f"http://127.0.0.1:{host_port}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
            r_ver = await client.get(f"{base}/json/version")
            if r_ver.status_code != 200:
                return None
            ver_data = r_ver.json()
            if not isinstance(ver_data, dict):
                return None
            ws_url = str(ver_data.get("webSocketDebuggerUrl") or "").strip()
            if not (ws_url.startswith("ws://") or ws_url.startswith("wss://")):
                return None

            r_list = await client.get(f"{base}/json/list")
            if r_list.status_code != 200 or not isinstance(r_list.json(), list):
                return None
            return ver_data
    except Exception as exc:
        logger.debug("CDP HTTP probe failed on %s: %s", base, exc)
        return None


class AndroidCdpBridge:
    """Orchestrates safe ADB DevTools forwarding and Playwright CDP connections."""

    def __init__(
        self,
        cfg: Optional[dict] = None,
        forward_state_file: Path = FORWARD_STATE_FILE,
        owned_targets_file: Path = OWNED_TARGETS_FILE,
    ) -> None:
        self.cfg = cfg or {}
        android_cfg = self.cfg.get("android_cdp") or {}
        net_cfg = self.cfg.get("network") or {}

        self.adb_path: str = str(
            android_cfg.get("adb_path") or net_cfg.get("adb_path") or ""
        ).strip()
        self.preferred_serial: str = str(
            android_cfg.get("device_id") or net_cfg.get("device_id") or ""
        ).strip()
        self.preferred_socket: str = str(
            android_cfg.get("preferred_socket") or "chrome_devtools_remote"
        ).strip()
        self.port_min: int = max(1024, int(android_cfg.get("port_min", DEFAULT_PORT_MIN)))
        self.port_max: int = min(65535, int(android_cfg.get("port_max", DEFAULT_PORT_MAX)))
        self.dedicated_device: bool = bool(android_cfg.get("dedicated_device", False))
        self.forward_state_file = forward_state_file
        self.owned_targets_file = owned_targets_file

    def resolve_device_serial(self, requested_serial: str = "") -> str:
        """
        Verify connected ADB device early so offline/unauthorized states abort
        immediately without cycling through all candidate host ports.
        """
        target = (requested_serial or self.preferred_serial).strip()
        devices = mobile_adb.list_devices(custom_path=self.adb_path)
        if not devices:
            raise RuntimeError("No Android devices attached over ADB")

        if target:
            matches = [d for d in devices if d["id"] == target]
            if not matches:
                raise RuntimeError(f"Requested ADB device {target!r} is not attached")
            status = matches[0]["status"]
            if status != "device":
                raise RuntimeError(f"ADB device {target} is {status!r} — unlock & authorize USB debugging")
            return target

        authorized = [d for d in devices if d["status"] == "device"]
        if not authorized:
            raise RuntimeError(
                f"Attached ADB device is {devices[0]['status']!r} — authorize USB debugging on device"
            )
        return authorized[0]["id"]

    def cleanup_orphaned_forwards(self, serial: str = "") -> int:
        """
        Remove only stale `adb forward` bindings previously created by dead
        bridge owner PIDs recorded in `forward_state_file`.
        """
        state = _load_json_dict(self.forward_state_file)
        if not state:
            return 0

        code, raw = mobile_adb.run_adb(["forward", "--list"], custom_path=self.adb_path)
        active_forwards = _parse_forward_list(raw) if code == 0 else []
        active_set = {(f["serial"], f["local"]) for f in active_forwards}

        removed = 0
        updated_state = dict(state)
        for key, rec in state.items():
            if not isinstance(rec, dict):
                updated_state.pop(key, None)
                continue
            rec_serial = str(rec.get("serial") or "")
            rec_port = rec.get("host_port")
            owner_pid = int(rec.get("owner_pid") or 0)
            if serial and rec_serial != serial:
                continue
            if _is_pid_alive(owner_pid):
                continue
            local_spec = f"tcp:{rec_port}"
            if (rec_serial, local_spec) in active_set:
                rm_code, _ = mobile_adb.run_adb(
                    ["-s", rec_serial, "forward", "--remove", local_spec],
                    custom_path=self.adb_path,
                )
                if rm_code == 0:
                    removed += 1
                    logger.info("Removed orphaned ADB forward %s on %s (dead PID %s)", local_spec, rec_serial, owner_pid)
            updated_state.pop(key, None)

        if len(updated_state) != len(state):
            _save_json_dict(self.forward_state_file, updated_state)
        return removed

    def ensure_chrome_foreground(self, serial: str) -> None:
        """
        Bring `com.android.chrome` cleanly to the foreground (without creating an
        extra blank tab via VIEW intent) so Android 13–17 stops freezing background
        DevTools IPC sockets (`ReadTimeout` on `/json/version`).
        """
        mobile_adb.run_adb(
            [
                "-s", serial, "shell", "am", "start",
                "-a", "android.intent.action.MAIN",
                "-c", "android.intent.category.LAUNCHER",
                "-p", "com.android.chrome",
            ],
            custom_path=self.adb_path,
            timeout=8.0,
        )

    def discover_devtools_socket(
        self,
        serial: str,
        auto_launch_chrome: bool = True,
        launch_timeout_s: float = 4.0,
    ) -> UnixSocketEntry:
        """Read `/proc/net/unix` over ADB; optionally launch Chrome if absent."""
        code, raw = mobile_adb.run_adb(
            ["-s", serial, "shell", "cat", "/proc/net/unix"],
            custom_path=self.adb_path,
            timeout=8.0,
        )
        if code != 0:
            raise RuntimeError(f"Failed reading /proc/net/unix on {serial}: {raw}")

        entries = parse_proc_net_unix(raw, preferred_prefix=self.preferred_socket)
        if entries:
            return entries[0]

        if not auto_launch_chrome:
            raise RuntimeError(f"No listening Chrome DevTools socket found on {serial}")

        logger.info("No active Chrome DevTools socket on %s — waking Chrome cleanly…", serial)
        self.ensure_chrome_foreground(serial)
        deadline = time.monotonic() + launch_timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.5)
            code2, raw2 = mobile_adb.run_adb(
                ["-s", serial, "shell", "cat", "/proc/net/unix"],
                custom_path=self.adb_path,
                timeout=8.0,
            )
            if code2 == 0:
                entries = parse_proc_net_unix(raw2, preferred_prefix=self.preferred_socket)
                if entries:
                    return entries[0]

        raise RuntimeError(f"Timed out waiting for Chrome DevTools socket on {serial}")

    def setup_forward(self, serial: str, socket_entry: UnixSocketEntry) -> int:
        """Allocate a safe localhost port (9222–9299) and bind via `--no-rebind`."""
        code, raw = mobile_adb.run_adb(["forward", "--list"], custom_path=self.adb_path)
        used_ports: set[int] = set()
        if code == 0:
            for item in _parse_forward_list(raw):
                p = _port_from_forward_spec(item["local"])
                if p is not None:
                    used_ports.add(p)

        remote_spec = f"localabstract:{socket_entry.socket_name}"
        state = _load_json_dict(self.forward_state_file)

        for port in range(self.port_min, self.port_max + 1):
            if port == ADB_DAEMON_PORT or port in used_ports:
                continue
            if not _is_localhost_port_free(port):
                continue

            fwd_code, fwd_out = mobile_adb.run_adb(
                ["-s", serial, "forward", "--no-rebind", f"tcp:{port}", remote_spec],
                custom_path=self.adb_path,
            )
            if fwd_code == 0:
                state[f"{serial}:{port}"] = {
                    "serial": serial,
                    "host_port": port,
                    "remote_socket": socket_entry.socket_name,
                    "owner_pid": os.getpid(),
                    "created_at": time.time(),
                }
                _save_json_dict(self.forward_state_file, state)
                logger.info("ADB forward ready: 127.0.0.1:%d -> %s (%s)", port, remote_spec, serial)
                return port

            # Re-verify early in case device detached between check and bind
            if "not found" in fwd_out.lower() or "offline" in fwd_out.lower() or "unauthorized" in fwd_out.lower():
                raise RuntimeError(f"ADB device {serial} disconnected during forward: {fwd_out}")

        raise RuntimeError(f"No free localhost port in {self.port_min}-{self.port_max} for ADB forward")

    def remove_forward(self, serial: str, host_port: int) -> None:
        if not host_port:
            return
        mobile_adb.run_adb(
            ["-s", serial, "forward", "--remove", f"tcp:{host_port}"],
            custom_path=self.adb_path,
        )
        state = _load_json_dict(self.forward_state_file)
        key = f"{serial}:{host_port}"
        if key in state:
            state.pop(key, None)
            _save_json_dict(self.forward_state_file, state)

    async def connect(self, pw: Playwright, serial: str = "") -> AndroidCdpSession:
        """Establish a verified Playwright CDP connection to real Android Chrome."""
        dev_serial = await asyncio.to_thread(self.resolve_device_serial, serial)
        await asyncio.to_thread(self.cleanup_orphaned_forwards, dev_serial)
        sock_entry = await asyncio.to_thread(self.discover_devtools_socket, dev_serial, True)
        host_port = await asyncio.to_thread(self.setup_forward, dev_serial, sock_entry)

        ver_data: Optional[dict[str, Any]] = None
        try:
            for attempt in range(3):
                ver_data = await probe_cdp_endpoint(host_port, timeout=3.0)
                if ver_data is not None:
                    break
                if attempt == 0:
                    # Chrome may be frozen in background on Android 13–17 even with open socket
                    await asyncio.to_thread(self.ensure_chrome_foreground, dev_serial)
                    await asyncio.sleep(0.8)
                elif attempt < 2:
                    await asyncio.sleep(0.6)

            if ver_data is None:
                raise RuntimeError(
                    f"Chrome DevTools HTTP endpoint on 127.0.0.1:{host_port} failed /json/version probe"
                )

            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{host_port}")
            if not browser.contexts:
                await browser.close()
                raise RuntimeError("Android Chrome CDP exposed 0 browser contexts")

            context = browser.contexts[0]
            browser_ver = str(ver_data.get("Browser") or "")
            ua = str(ver_data.get("User-Agent") or "")
            try:
                b_cdp = await browser.new_browser_cdp_session()
                cdp_ver = await b_cdp.send("Browser.getVersion")
                browser_ver = str(cdp_ver.get("product") or browser_ver)
                ua = str(cdp_ver.get("userAgent") or ua)
                await b_cdp.detach()
            except Exception as exc:
                logger.debug("Browser.getVersion fallback notice: %s", exc)

            # Cleanup orphaned automation tabs from prior crashed runs
            try:
                await self.cleanup_orphaned_targets(browser, dev_serial)
            except Exception as clean_exc:
                logger.debug("Startup orphaned targets cleanup notice: %s", clean_exc)

            return AndroidCdpSession(
                serial=dev_serial,
                host_port=host_port,
                remote_socket=sock_entry.socket_name,
                ws_url=str(ver_data.get("webSocketDebuggerUrl") or ""),
                browser_version=browser_ver,
                user_agent=ua,
                browser=browser,
                context=context,
                adb_path=self.adb_path,
                _dedicated_device=self.dedicated_device,
            )
        except Exception:
            await asyncio.to_thread(self.remove_forward, dev_serial, host_port)
            raise

    async def reverify_after_ip_rotation(
        self, pw: Playwright, session: Optional[AndroidCdpSession], serial: str = ""
    ) -> AndroidCdpSession:
        """
        Re-verify DevTools socket and Playwright connection after Airplane Mode
        IP rotation (USB forward survives, though Chrome sockets may cycle).
        """
        if session is not None and await probe_cdp_endpoint(session.host_port, timeout=2.0):
            try:
                if session.browser.contexts:
                    return session
            except Exception:
                pass
        if session is not None:
            await self.disconnect(session, remove_forward=True)
        return await self.connect(pw, serial=serial or (session.serial if session else ""))

    async def open_owned_tab(self, session: AndroidCdpSession) -> tuple[Page, str]:
        """
        Open a fresh automation-owned tab and record its `targetId` so personal
        tabs are never touched.

        Fast path: Playwright ``context.new_page()`` → ``Target.createTarget``.
        Fallback (Android 17 Chrome 156 foreground race): fire
        ``am start -a android.intent.action.VIEW -d <sentinel_url>`` and await
        ``context.expect_page()``, falling back to ``/json/list`` diff if needed.
        """
        import uuid as _uuid

        sentinel = f"https://example.com/?_adt_init={_uuid.uuid4().hex[:12]}"
        page: Optional[Page] = None
        target_id = ""

        # ── Fast path ────────────────────────────────────────────────────────
        try:
            page = await session.context.new_page()
        except Exception as exc:
            logger.warning("new_page() failed (%s); using am-start VIEW fallback", exc)

        # ── Fallback: am start with expect_page ────────────────────────────────
        if page is None:
            # Snapshot target IDs before launch so we can diff if expect_page times out
            ids_before: set[str] = set()
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=4.0) as cl:
                    resp = await cl.get(f"http://127.0.0.1:{session.host_port}/json/list")
                    for t in resp.json():
                        ids_before.add(str(t.get("id") or ""))
            except Exception:
                pass

            am_fired = False
            try:
                async with session.context.expect_page(timeout=5000) as page_info:
                    await asyncio.to_thread(
                        mobile_adb.run_adb,
                        [
                            "-s", session.serial,
                            "shell", "am", "start",
                            "-a", "android.intent.action.VIEW",
                            "-d", sentinel,
                            "-p", "com.android.chrome",
                        ],
                        self.adb_path,
                        10.0,
                    )
                    am_fired = True
                page = await page_info.value
            except Exception as am_exc:
                logger.warning("expect_page am-start notice (%s); checking /json/list diff", am_exc)

            # Secondary fallback: tab was already launched with am start above!
            # Do NOT fire a second am start intent (avoids spawning duplicate orphaned tabs)
            if page is None:
                if not am_fired:
                    await asyncio.to_thread(
                        mobile_adb.run_adb,
                        [
                            "-s", session.serial,
                            "shell", "am", "start",
                            "-a", "android.intent.action.VIEW",
                            "-d", sentinel,
                            "-p", "com.android.chrome",
                        ],
                        self.adb_path,
                        10.0,
                    )

                # Wait up to 4 s for the tab to appear in /json/list
                new_tid = ""
                deadline = asyncio.get_running_loop().time() + 4.0
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.3)
                    try:
                        async with httpx.AsyncClient(trust_env=False, timeout=4.0) as cl:
                            resp = await cl.get(f"http://127.0.0.1:{session.host_port}/json/list")
                            for t in resp.json():
                                tid = str(t.get("id") or "")
                                if tid and tid not in ids_before:
                                    new_tid = tid
                                    break
                    except Exception:
                        pass
                    if new_tid:
                        break

                if not new_tid:
                    raise RuntimeError(
                        "open_owned_tab: am-start fallback produced no new target within deadline"
                    )

            # Match new_tid in context.pages
            for p in session.context.pages:
                try:
                    p_cdp = await session.context.new_cdp_session(p)
                    info = await p_cdp.send("Target.getTargetInfo")
                    tid = str((info.get("targetInfo") or {}).get("targetId") or "")
                    await p_cdp.detach()
                    if tid == new_tid:
                        page = p
                        target_id = tid
                        break
                except Exception:
                    pass

        # ── Retrieve targetId from page if not already populated ───────────────
        if not target_id and page is not None:
            try:
                p_cdp = await session.context.new_cdp_session(page)
                info = await p_cdp.send("Target.getTargetInfo")
                target_id = str((info.get("targetInfo") or {}).get("targetId") or "")
                await p_cdp.detach()
            except Exception as exc:
                logger.debug("Target.getTargetInfo notice: %s", exc)

        # ── Record ownership ─────────────────────────────────────────────────
        if target_id:
            session.owned_target_ids.append(target_id)
            await asyncio.to_thread(
                _record_owned_target,
                session.serial,
                target_id,
                page.url or sentinel,
                self.owned_targets_file,
            )

        if page is None:
            raise RuntimeError("open_owned_tab failed to create or attach a Page")

        return page, target_id

    async def cleanup_orphaned_targets(self, browser: Browser, serial: str) -> int:
        """
        Close previous automation tabs whose owner PID is dead.
        Protects personal tabs by ONLY closing targets recorded in state/adb_owned_targets.json.
        """
        state = _load_json_dict(self.owned_targets_file)
        if not state:
            return 0

        my_pid = os.getpid()
        dead_targets = []
        for tid, info in list(state.items()):
            if info.get("serial") != serial:
                continue
            owner_pid = int(info.get("owner_pid") or 0)
            if owner_pid != my_pid and not _is_pid_alive(owner_pid):
                dead_targets.append(tid)

        if not dead_targets:
            return 0

        closed = 0
        try:
            b_cdp = await browser.new_browser_cdp_session()
            for tid in dead_targets:
                try:
                    await b_cdp.send("Target.closeTarget", {"targetId": tid})
                    closed += 1
                except Exception:
                    pass
                state.pop(tid, None)
            await b_cdp.detach()
            _save_json_dict(self.owned_targets_file, state)
            logger.info("Pruned %d orphaned automation tab(s) on %s", closed, serial)
        except Exception as exc:
            logger.debug("cleanup_orphaned_targets notice: %s", exc)
        return closed

    async def track_page_if_new(self, session: AndroidCdpSession, page: Page) -> None:
        """Register automation-spawned popunder/advertiser tabs for guaranteed cleanup."""
        try:
            p_cdp = await session.context.new_cdp_session(page)
            info = await p_cdp.send("Target.getTargetInfo")
            tid = str((info.get("targetInfo") or {}).get("targetId") or "")
            await p_cdp.detach()
            if tid and tid not in session.owned_target_ids:
                session.owned_target_ids.append(tid)
                await asyncio.to_thread(
                    _record_owned_target,
                    session.serial,
                    tid,
                    page.url or "",
                    self.owned_targets_file,
                )
        except Exception:
            pass

    @staticmethod
    def _origin_from_url(url: str) -> str:
        parsed = urlparse(url or "")
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return ""

    async def read_isolated_telemetry(self, session: AndroidCdpSession, page: Page) -> dict[str, Any]:
        """
        Read genuine device/page telemetry inside an IsolatedWorld without
        calling `Runtime.enable` on the main world (C1-safe).
        """
        p_cdp = await session.context.new_cdp_session(page)
        try:
            ft = await p_cdp.send("Page.getFrameTree")
            frame_id = ft["frameTree"]["frame"]["id"]
            iw = await p_cdp.send(
                "Page.createIsolatedWorld",
                {"frameId": frame_id, "worldName": "", "grantUniveralAccess": True},
            )
            expr = """(() => {
                let renderer = '';
                try {
                    const c = document.createElement('canvas');
                    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
                    if (gl) {
                        const ext = gl.getExtension('WEBGL_debug_renderer_info');
                        renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : String(gl.getParameter(37446) || '');
                    }
                } catch (e) {}
                return {
                    webdriver: navigator.webdriver,
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: Array.from(navigator.languages || []),
                    devicePixelRatio: window.devicePixelRatio,
                    innerWidth: window.innerWidth,
                    innerHeight: window.innerHeight,
                    maxTouchPoints: navigator.maxTouchPoints,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    webglRenderer: renderer
                };
            })()"""
            eval_res = await p_cdp.send(
                "Runtime.evaluate",
                {
                    "expression": expr,
                    "contextId": iw["executionContextId"],
                    "returnByValue": True,
                },
            )
            data = (eval_res.get("result") or {}).get("value") or {}
            try:
                metrics = await p_cdp.send("Page.getLayoutMetrics")
                data["cssLayoutViewport"] = metrics.get("cssLayoutViewport") or {}
                data["cssVisualViewport"] = metrics.get("cssVisualViewport") or {}
            except Exception:
                pass
            return data if isinstance(data, dict) else {}
        finally:
            try:
                await p_cdp.detach()
            except Exception:
                pass

    async def cleanup_owned_targets(
        self,
        session: AndroidCdpSession,
        keep_cookies: bool = True,
        extra_origins: Optional[list[str]] = None,
    ) -> None:
        """
        Close ONLY automation-owned tabs (never touching personal tabs or calling
        `pm clear`) and clear storage only for automation-visited origins unless
        explicitly configured as a dedicated burner device.
        """
        origins = set(session.visited_origins)
        for u in extra_origins or []:
            org = self._origin_from_url(u)
            if org:
                origins.add(org)

        storage_types = (
            "local_storage,indexeddb,cache_storage,service_workers"
            if keep_cookies
            else "cookies,local_storage,indexeddb,cache_storage,service_workers"
        )

        # Clear per-origin site storage on an attached target or browser CDP session
        b_cdp = None
        try:
            b_cdp = await session.browser.new_browser_cdp_session()
        except Exception:
            b_cdp = None

        try:
            if session._dedicated_device and not keep_cookies and b_cdp is not None:
                try:
                    await b_cdp.send("Storage.clearDataForOrigin", {"origin": "*", "storageTypes": "all"})
                except Exception:
                    pass
                try:
                    await b_cdp.send("Network.clearBrowserCookies")
                    await b_cdp.send("Network.clearBrowserCache")
                except Exception:
                    pass
            elif b_cdp is not None:
                for origin in sorted(origins):
                    try:
                        await b_cdp.send(
                            "Storage.clearDataForOrigin",
                            {"origin": origin, "storageTypes": storage_types},
                        )
                    except Exception:
                        pass

            # Close owned Playwright pages and clear any emulation overrides first
            owned_set = set(session.owned_target_ids)
            for page in list(session.context.pages):
                try:
                    pc = await session.context.new_cdp_session(page)
                    info = await pc.send("Target.getTargetInfo")
                    tid = str((info.get("targetInfo") or {}).get("targetId") or "")
                    if tid in owned_set:
                        try:
                            await pc.send("Emulation.clearDeviceMetricsOverride")
                        except Exception:
                            pass
                        await pc.detach()
                        await page.close()
                        owned_set.discard(tid)
                        await asyncio.to_thread(_forget_owned_target, tid, self.owned_targets_file)
                    else:
                        await pc.detach()
                except Exception:
                    pass

            # Close any remaining owned targetIds directly at browser CDP level
            if b_cdp is not None:
                for tid in list(owned_set):
                    try:
                        await b_cdp.send("Target.closeTarget", {"targetId": tid})
                        await asyncio.to_thread(_forget_owned_target, tid, self.owned_targets_file)
                    except Exception:
                        pass
            session.owned_target_ids.clear()
        finally:
            if b_cdp is not None:
                try:
                    await b_cdp.detach()
                except Exception:
                    pass

    async def disconnect(
        self,
        session: Optional[AndroidCdpSession],
        remove_forward: bool = True,
        keep_cookies: bool = True,
    ) -> None:
        """Gracefully close owned targets, detach CDP, and remove forward."""
        if session is None:
            return
        try:
            await self.cleanup_owned_targets(session, keep_cookies=keep_cookies)
        except Exception as exc:
            logger.debug("Owned target cleanup notice: %s", exc)
        try:
            await session.browser.close()
        except Exception:
            pass
        if remove_forward:
            await asyncio.to_thread(self.remove_forward, session.serial, session.host_port)
