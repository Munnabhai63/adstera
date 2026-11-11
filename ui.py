"""
ui.py — Localhost Web UI for managing target URL, proxies, and monitoring live sessions.
Runs on http://localhost:5050 (or custom port). Zero extra pip dependencies needed.
"""
from __future__ import annotations

import collections
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

import db

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("web_ui")

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = BASE_DIR / "config.yaml"
PROXIES_PATH = BASE_DIR / "proxies.txt"

# ── Interactive Process Launcher ───────────────────────────────────────────────

class InteractiveProcess:
    """Spawns process on WinSta0\\Default so visible GUI windows appear on user's primary monitor."""
    def __init__(self, cmd: list[str], cwd: str, env: dict):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.pid: int | None = None
        self._hProcess: int | None = None
        self._pipe_r: int | None = None
        self._returncode: int | None = None
        self._spawn()

    def _spawn(self) -> None:
        import ctypes
        import ctypes.wintypes
        import msvcrt

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ('cb', ctypes.wintypes.DWORD),
                ('lpReserved', ctypes.wintypes.LPWSTR),
                ('lpDesktop', ctypes.wintypes.LPWSTR),
                ('lpTitle', ctypes.wintypes.LPWSTR),
                ('dwX', ctypes.wintypes.DWORD),
                ('dwY', ctypes.wintypes.DWORD),
                ('dwXSize', ctypes.wintypes.DWORD),
                ('dwYSize', ctypes.wintypes.DWORD),
                ('dwXCountChars', ctypes.wintypes.DWORD),
                ('dwYCountChars', ctypes.wintypes.DWORD),
                ('dwFillAttribute', ctypes.wintypes.DWORD),
                ('dwFlags', ctypes.wintypes.DWORD),
                ('wShowWindow', ctypes.wintypes.WORD),
                ('cbReserved2', ctypes.wintypes.WORD),
                ('lpReserved2', ctypes.c_void_p),
                ('hStdInput', ctypes.wintypes.HANDLE),
                ('hStdOutput', ctypes.wintypes.HANDLE),
                ('hStdError', ctypes.wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('hProcess', ctypes.wintypes.HANDLE),
                ('hThread', ctypes.wintypes.HANDLE),
                ('dwProcessId', ctypes.wintypes.DWORD),
                ('dwThreadId', ctypes.wintypes.DWORD),
            ]

        r_fd, w_fd = os.pipe()
        w_handle = msvcrt.get_osfhandle(w_fd)
        ctypes.windll.kernel32.SetHandleInformation(w_handle, 1, 1)

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.lpDesktop = "WinSta0\\Default"
        si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
        si.hStdOutput = w_handle
        si.hStdError = w_handle
        si.hStdInput = msvcrt.get_osfhandle(0)

        pi = PROCESS_INFORMATION()
        cmd_str = subprocess.list2cmdline(self.cmd)

        res = ctypes.windll.kernel32.CreateProcessW(
            None, cmd_str, None, None, True, 0, None, str(self.cwd),
            ctypes.byref(si), ctypes.byref(pi),
        )
        os.close(w_fd)
        if not res:
            os.close(r_fd)
            raise OSError(f"CreateProcess failed (error {ctypes.windll.kernel32.GetLastError()})")

        ctypes.windll.kernel32.CloseHandle(pi.hThread)
        self._hProcess = pi.hProcess
        self.pid = pi.dwProcessId
        self._pipe_r = r_fd

    def poll(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        if not self._hProcess:
            return -1
        import ctypes
        import ctypes.wintypes
        code = ctypes.wintypes.DWORD()
        res = ctypes.windll.kernel32.GetExitCodeProcess(self._hProcess, ctypes.byref(code))
        if res and code.value != 259:
            self._returncode = code.value
            return self._returncode
        return None

    def terminate(self) -> None:
        if self._hProcess and self.poll() is None:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(self._hProcess, 1)
            self._returncode = 1

    def kill(self) -> None:
        self.terminate()

    def readline(self) -> str:
        if self._pipe_r is None:
            return ""
        chars = []
        while True:
            try:
                b = os.read(self._pipe_r, 1)
                if not b:
                    break
                chars.append(b)
                if b == b"\n":
                    break
            except Exception:
                break
        return b"".join(chars).decode("utf-8", errors="replace")

    def close_pipe(self) -> None:
        if self._pipe_r is not None:
            try:
                os.close(self._pipe_r)
            except Exception:
                pass
            self._pipe_r = None

    def wait(self) -> int:
        while self.poll() is None:
            time.sleep(0.1)
        return self._returncode or 0


# ── Process Manager ─────────────────────────────────────────────────────────────

class RunnerManager:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._logs = collections.deque(maxlen=300)
        self._reader_thread: threading.Thread | None = None

    def is_running(self) -> bool:
        with self._lock:
            if self._proc is None:
                return False
            return self._proc.poll() is None

    def get_pid(self) -> int | None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return self._proc.pid
            return None

    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return False, f"Runner already active (PID {self._proc.pid})"

            # Ensure DB is ready
            db.init()

            python_exe = sys.executable
            main_script = str(BASE_DIR / "main.py")
            cmd = [python_exe, "-u", main_script]

            try:
                # Always clean up terminated process reference
                if self._proc and self._proc.poll() is not None:
                    self._proc = None

                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )

                cfg = read_config()
                is_headless = cfg.get("browser", {}).get("headless", False)
                mode_desc = "⚡ Headless (Background)" if is_headless else "👁️ Head-On (Visible Window on Screen)"
                self._logs.append(f"[{time.strftime('%X')}] Runner launched with PID {self._proc.pid} [{mode_desc}]")

                # Background thread to capture stdout
                def stream_reader(p, log_queue: collections.deque):
                    if hasattr(p, "readline") and not hasattr(p, "stdout"):
                        while True:
                            line = p.readline()
                            if not line:
                                break
                            clean = line.rstrip()
                            if clean:
                                log_queue.append(clean)
                        if hasattr(p, "close_pipe"):
                            p.close_pipe()
                        p.wait()
                        log_queue.append(f"[{time.strftime('%X')}] Runner process ended (code {p.poll()})")
                    else:
                        for line in iter(p.stdout.readline, ""):
                            clean = line.rstrip()
                            if clean:
                                log_queue.append(clean)
                        p.stdout.close()
                        p.wait()
                        log_queue.append(f"[{time.strftime('%X')}] Runner process ended (code {p.returncode})")

                self._reader_thread = threading.Thread(
                    target=stream_reader, args=(self._proc, self._logs), daemon=True
                )
                self._reader_thread.start()
                return True, f"Started with PID {self._proc.pid}"
            except Exception as exc:
                return False, f"Failed to start: {exc}"

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                return False, "Runner is not currently running"

            try:
                self._proc.terminate()
                self._logs.append(f"[{time.strftime('%X')}] Termination signal sent to PID {self._proc.pid}")
                return True, "Stop signal sent"
            except Exception as exc:
                try:
                    self._proc.kill()
                    return True, f"Force killed: {exc}"
                except Exception as k_exc:
                    return False, f"Error stopping: {k_exc}"

    def force_stop(self) -> tuple[bool, str]:
        """Instantly and forcefully terminate runner process tree and all open Chromium browsers."""
        with self._lock:
            pid = self._proc.pid if self._proc else None
            # 1. Kill the runner process tree on Windows via taskkill
            if pid:
                try:
                    import subprocess
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
                except Exception:
                    pass

            # 2. Terminate any lingering Chromium instances launched by this automation
            try:
                import subprocess
                for p_name in ["chrome.exe", "headless_shell.exe"]:
                    subprocess.run(["taskkill", "/F", "/IM", p_name], capture_output=True, timeout=5)
            except Exception:
                pass

            # 3. Clean up internal process reference
            if self._proc:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc = None

            self._logs.append(f"[{time.strftime('%X')}] 🛑 FORCE STOP EXECUTED: All runner processes and browsers terminated immediately.")
            return True, "Force stop complete. All processes and browsers killed."

    def get_logs(self) -> list[str]:
        return list(self._logs)


RUNNER = RunnerManager()
GLOBAL_FAILOVER_MGR = None

def get_failover_mgr():
    global GLOBAL_FAILOVER_MGR
    cfg = read_config()
    if GLOBAL_FAILOVER_MGR is None:
        from failover_manager import DualTransportManager
        GLOBAL_FAILOVER_MGR = DualTransportManager(cfg)
    else:
        failover_cfg = cfg.get("failover", {})
        GLOBAL_FAILOVER_MGR.enabled = bool(failover_cfg.get("enabled", True))
        GLOBAL_FAILOVER_MGR.latency_threshold_ms = float(failover_cfg.get("latency_threshold_ms", 1500.0))
    return GLOBAL_FAILOVER_MGR

# ── Config & Proxy Helpers ──────────────────────────────────────────────────────

def read_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def read_proxies() -> str:
    if PROXIES_PATH.exists():
        return PROXIES_PATH.read_text(encoding="utf-8")
    return ""


def write_proxies(content: str) -> None:
    PROXIES_PATH.write_text(content.strip() + "\n", encoding="utf-8")


def count_valid_proxies() -> int:
    txt = read_proxies()
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return len(lines)


def read_active_ua() -> dict:
    active_file = BASE_DIR / "state" / "active_ua.json"
    if active_file.exists():
        try:
            return json.loads(active_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "active": False,
        "proxy_id": "—",
        "user_agent": "Ready — Click Start Live Run to rotate",
        "device_label": "⚪ Waiting for session start…",
        "is_mobile": False,
        "platform": "—",
        "updated_at": "—",
    }


_last_mobile_check_ts = 0.0
_cached_mobile_info = {"device": "RZCX21WTS9E", "carrier": "Cellular Dynamic IP"}
_mobile_check_in_progress = False


def get_cached_mobile_info() -> dict:
    global _last_mobile_check_ts, _cached_mobile_info, _mobile_check_in_progress
    now = time.time()
    if now - _last_mobile_check_ts > 20.0 and not _mobile_check_in_progress:
        _mobile_check_in_progress = True

        def _bg_check():
            global _last_mobile_check_ts, _cached_mobile_info, _mobile_check_in_progress
            try:
                import mobile_adb
                devs = mobile_adb.list_devices()
                dev_name = devs[0]["id"] if devs else "No phone"
                _cached_mobile_info = {"device": dev_name, "carrier": "Cellular Dynamic IP"}
            except Exception:
                pass
            finally:
                _last_mobile_check_ts = time.time()
                _mobile_check_in_progress = False

        threading.Thread(target=_bg_check, daemon=True).start()
    return _cached_mobile_info


# ── Web UI HTML Template ────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>rechargekar.com — Adsterra Enterprise Fleet Controller</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f293d;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', sans-serif;
      padding: 24px;
      line-height: 1.5;
    }
    .container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
    
    /* Header */
    header {
      display: flex; justify-content: space-between; align-items: center;
      padding-bottom: 16px; border-bottom: 1px solid var(--border);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
      width: 40px; height: 40px; background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      border-radius: 10px; display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 20px; color: #fff;
    }
    h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
    .subtitle { font-size: 13px; color: var(--muted); }
    
    .status-badge {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 14px; border-radius: 999px; font-size: 13px; font-weight: 600;
      background: #1f293d; color: var(--muted);
    }
    .status-badge.running { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .status-badge.stopped { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }

    /* Top stats */
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .stat-card {
      background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
      padding: 18px 20px; display: flex; flex-direction: column; gap: 6px;
    }
    .stat-title { font-size: 13px; color: var(--muted); font-weight: 500; }
    .stat-val { font-size: 26px; font-weight: 700; letter-spacing: -0.03em; font-family: 'JetBrains Mono', monospace; }

    /* Main Grid */
    .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }

    .card {
      background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
      padding: 24px; display: flex; flex-direction: column; gap: 16px;
    }
    .card-title {
      font-size: 16px; font-weight: 700; display: flex; justify-content: space-between; align-items: center;
      padding-bottom: 12px; border-bottom: 1px solid var(--border);
    }

    /* Forms */
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    label { font-size: 13px; font-weight: 600; color: var(--muted); }
    input[type="text"], input[type="number"], textarea {
      background: #0d131f; border: 1px solid var(--border); border-radius: 8px;
      padding: 10px 14px; color: var(--text); font-family: inherit; font-size: 14px;
      transition: border-color 0.15s;
    }
    input[type="text"]:focus, input[type="number"]:focus, textarea:focus {
      outline: none; border-color: var(--accent);
    }
    textarea { font-family: 'JetBrains Mono', monospace; font-size: 13px; resize: vertical; min-height: 130px; }
    .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

    /* Buttons */
    .btn {
      padding: 10px 18px; border-radius: 8px; font-weight: 600; font-size: 14px;
      cursor: pointer; border: none; display: inline-flex; align-items: center; justify-content: center;
      gap: 8px; transition: all 0.15s;
    }
    .btn-primary { background: var(--accent); color: white; }
    .btn-primary:hover { background: var(--accent-hover); }
    .btn-success { background: var(--success); color: white; }
    .btn-success:hover { background: #059669; }
    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { background: #dc2626; }
    .btn-secondary { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { background: #334155; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .control-bar { display: flex; gap: 12px; }

    /* Tables */
    .table-container { overflow-x: auto; max-height: 380px; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
    th { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--card-bg); }
    td { padding: 10px 12px; border-bottom: 1px solid #162032; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }

    /* Console logs */
    .console-box {
      background: #070a10; border: 1px solid var(--border); border-radius: 8px;
      padding: 12px 16px; font-family: 'JetBrains Mono', monospace; font-size: 12px;
      height: 220px; overflow-y: auto; color: #cbd5e1; line-height: 1.6;
    }
    .console-line { white-space: pre-wrap; word-break: break-all; }
    .toast {
      position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 8px;
      background: #1f293d; color: #fff; font-size: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      border: 1px solid var(--border); opacity: 0; transform: translateY(10px); transition: all 0.2s; pointer-events: none; z-index: 1000;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
  </style>
</head>
<body>

<div class="container">
  <!-- Header -->
  <header>
    <div class="brand">
      <div class="brand-logo" style="background: linear-gradient(135deg, #10b981, #06b6d4); font-weight: 800; font-size: 16px;">⚡ RK</div>
      <div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <h1 style="margin: 0; font-size: 22px;">rechargekar.com</h1>
          <span style="background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 700; letter-spacing: 0.5px;">🌐 LIVE CLOUD HUB</span>
        </div>
        <div class="subtitle">Master Fleet Controller &bull; Adsterra 10-Domain Monetization Engine</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 10px;">
      <a href="/" class="btn" style="text-decoration: none; background: linear-gradient(135deg, #7367f0, #5e50ee); color: #fff; font-weight: 700; padding: 7px 14px; font-size: 13px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); display: inline-flex; align-items: center; gap: 6px;">✨ Vuexy CRM UI</a>
      <a href="/autopublish" class="btn" style="text-decoration: none; background: linear-gradient(135deg, #f59e0b, #ef4444); color: #fff; font-weight: 700; padding: 7px 16px; font-size: 13px; border-radius: 8px; box-shadow: 0 0 15px rgba(245, 158, 11, 0.4); border: 1px solid rgba(255,255,255,0.2); display: inline-flex; align-items: center; gap: 6px;">⚡ AutoPublish & Indexing Pipeline</a>
      <div id="statusBadge" class="status-badge stopped">
        <span class="status-dot"></span>
        <span id="statusText">STOPPED</span>
      </div>
      <button class="btn" onclick="forceStopRunner()" style="background: #b91c1c; color: #fff; border: 1px solid #ef4444; font-weight: 700; padding: 6px 14px; font-size: 12px; cursor: pointer;" title="Kill all running processes and browsers instantly">🛑 Force Stop All</button>
      <a href="/api/stats/csv" download="stats.csv" class="btn btn-secondary" style="text-decoration: none;">📥 Export CSV</a>
      <button class="btn btn-secondary" onclick="fetchStatus()">↻ Refresh</button>
    </div>
  </header>

  <!-- Metrics -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-title">Sessions Today</div>
      <div class="stat-val" id="statSessionsToday">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Impressions / Clicks</div>
      <div class="stat-val" id="statImpsClicks" style="color: #60a5fa; font-size: 22px;">0 / 0</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Current CTR (Last 100)</div>
      <div class="stat-val" id="statCTR">0.0%</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Est. Revenue / CPM</div>
      <div class="stat-val" id="statRevenue" style="color: #34d399; font-size: 22px;">$0.00</div>
    </div>
    <div class="stat-card">
      <div class="stat-title" id="statProxyTitle">Active Proxies</div>
      <div class="stat-val" id="statProxies" style="color: #60a5fa;">0</div>
      <div id="statProxySub" style="font-size: 11px; color: var(--muted); margin-top: 2px;">Proxy Pool Mode</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">User-Agents (useragent.in)</div>
      <div class="stat-val" id="statUserAgents" style="color: #38bdf8;">27,103</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Runner Process PID</div>
      <div class="stat-val" id="statPID">—</div>
    </div>
  </div>

  <!-- Main Section -->
  <div class="main-grid">
    <!-- Config Column -->
    <div class="card">
      <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
        <span>Target Configuration</span>
        <div style="display: flex; gap: 8px;">
          <button class="btn" onclick="clearAllUrls()" style="padding: 5px 10px; font-size: 11px; background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);">🗑️ Clear All</button>
          <button class="btn btn-primary" onclick="saveConfig()" style="padding: 5px 12px; font-size: 12px;">💾 Save Config</button>
        </div>
      </div>

      <div class="form-group">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <label style="margin: 0; font-weight: 700; color: #f1f5f9;">🎯 Target URLs Pool (One per line for rotation)</label>
          <span id="targetUrlsCount" style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(16,185,129,0.15); color: #10b981; font-weight: 600; border: 1px solid rgba(16,185,129,0.3);">1 URL Active</span>
        </div>
        <textarea id="targetUrls" rows="3" placeholder="https://example.com/article-1&#10;https://example.com/article-2&#10;https://example.com/article-3" style="width: 100%; font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.4; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: #0f172a; color: #e2e8f0; resize: vertical;" oninput="updateTargetUrlsCount()"></textarea>

        <!-- Quick Add Single URL -->
        <div style="display: flex; gap: 6px; margin-top: 6px;">
          <input type="text" id="newUrlInput" placeholder="Add custom URL (e.g. https://loanraaj.com) and click Add" style="flex: 1; font-size: 12px; padding: 6px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: #fff;">
          <button class="btn btn-secondary" onclick="addSingleUrl()" style="padding: 6px 12px; font-size: 12px; white-space: nowrap;">+ Add URL</button>
        </div>

        <!-- Interactive URL Pills List with individual ❌ Remove buttons -->
        <div style="margin-top: 8px;">
          <div style="font-size: 11px; color: var(--muted); margin-bottom: 4px; display: flex; justify-content: space-between;">
            <span>Active URLs in Pool (Click ❌ to remove):</span>
          </div>
          <div id="targetUrlsPills" style="display: flex; flex-direction: column; gap: 4px; max-height: 140px; overflow-y: auto; padding-right: 2px;">
            <!-- Rendered dynamically -->
          </div>
        </div>

        <div style="font-size: 11px; color: var(--muted); margin-top: 6px;">
          💡 प्रत्येक नया सेशन रैंडमली इस पूल में से एक अलग URL चुनेगा, जिससे ट्रैफ़िक पूरे डोमेन में प्राकृतिक रूप से फैलेगा।
        </div>
      </div>

      <!-- Execution Mode Switcher -->
      <div class="form-group" style="background: #0d131f; border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin: 4px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <label style="color: var(--text); font-weight: 700; font-size: 13px;">🖥️ Browser Execution Mode</label>
          <span id="modeBadge" style="font-size: 11px; padding: 3px 8px; border-radius: 4px; background: #2563eb; color: #fff; font-weight: 700;">👁️ VISIBLE (HEAD-ON)</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <label id="cardHeaded" style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer; padding: 10px 12px; border-radius: 8px; border: 1px solid #3b82f6; background: rgba(59, 130, 246, 0.1);">
            <input type="radio" name="browserMode" id="modeHeaded" value="headed" checked onchange="onModeChange()" style="margin-top: 3px;">
            <div>
              <div style="font-size: 13px; font-weight: 700; color: #60a5fa;">👁️ Head-On (Visible)</div>
              <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">ब्राउज़र सामने स्क्रीन पर खुलेगा (Watch live)</div>
            </div>
          </label>
          <label id="cardHeadless" style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); background: #111827;">
            <input type="radio" name="browserMode" id="modeHeadless" value="headless" onchange="onModeChange()" style="margin-top: 3px;">
            <div>
              <div style="font-size: 13px; font-weight: 700; color: #e2e8f0;">⚡ Headless (Silent)</div>
              <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">बिना विंडो बैकग्राउंड में चलेगा (Silent runner)</div>
            </div>
          </label>
        </div>
      </div>

      <div class="row-2">
        <div class="form-group">
          <label>Min Dwell Time (sec)</label>
          <input type="number" id="minDwell" value="25" min="20">
        </div>
        <div class="form-group">
          <label>Max Dwell Time (sec)</label>
          <input type="number" id="maxDwell" value="110">
        </div>
      </div>

      <div class="row-2">
        <div class="form-group">
          <label>Ad Click Probability (0.01 - 0.20)</label>
          <input type="number" id="clickProb" step="0.01" value="0.06">
        </div>
        <div class="form-group">
          <label>Max Ad Clicks per Session</label>
          <input type="number" id="adClicksMax" value="2">
        </div>
      </div>

      <div class="row-2">
        <div class="form-group">
          <label>Daily Sessions Cap</label>
          <input type="number" id="dailyCap" value="2000">
        </div>
        <div class="form-group">
          <label>Concurrency (Parallel Browsers)</label>
          <input type="number" id="concurrency" value="6" min="1" max="20">
        </div>
      </div>

      <!-- useragent.in Database Info -->
      <div style="display: flex; justify-content: space-between; align-items: center; background: #0d131f; border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; margin-top: 2px;">
        <div>
          <div style="font-size: 13px; font-weight: 700; color: #38bdf8;">🌐 useragent.in Database</div>
          <div style="font-size: 11px; color: var(--muted); margin-top: 2px;" id="uaSubText">27,103 Real UAs (8,989 Desktop, 18,114 Mobile/Tablet)</div>
        </div>
        <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="syncUserAgents()" id="btnSyncUA">🔄 Sync from useragent.in</button>
      </div>

      <!-- Real-Time Live Active User-Agent Box (Requested by User) -->
      <div id="liveUACard" style="background: #090e17; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 14px; margin-top: 8px; display: flex; flex-direction: column; gap: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 13px; font-weight: 700; color: #f1f5f9;">⚡ Live Session User-Agent</span>
            <span id="uaLiveBadge" style="font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(148,163,184,0.15); color: #94a3b8; font-weight: 600;">⚪ IDLE / READY</span>
          </div>
          <span id="uaDeviceBadge" style="font-size: 11px; font-weight: 600; color: #38bdf8; background: rgba(56,189,248,0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.2);">⚪ Waiting…</span>
        </div>
        <div style="background: #04070d; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 10px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #e2e8f0; word-break: break-all; line-height: 1.4; max-height: 60px; overflow-y: auto;" id="uaLiveText">
          Ready — Session will pick a fresh UA from 27,103 pool upon launch
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); padding-top: 2px;">
          <span>Connected IP: <strong id="uaLiveIP" style="color: #cbd5e1;">—</strong></span>
          <span>Rotated At: <strong id="uaLiveTime" style="color: #cbd5e1;">—</strong></span>
        </div>
        <div style="font-size: 11px; color: var(--muted); border-top: 1px dashed rgba(255,255,255,0.08); padding-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <span>Active Target: <strong id="uaLiveTarget" style="color: #38bdf8; font-family: 'JetBrains Mono', monospace;">—</strong></span>
        </div>
      </div>

      <div class="control-bar" style="margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 8px;">
        <button id="btnStart" class="btn btn-success" onclick="startRunner()">▶ Start Live Run</button>
        <button id="btnStop" class="btn btn-danger" onclick="stopRunner()" disabled style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4);">■ Stop Run</button>
        <button id="btnForceStop" class="btn" onclick="forceStopRunner()" style="background: #b91c1c; color: #ffffff; border: 1px solid #ef4444; font-weight: 700;">🛑 Force Stop</button>
      </div>
    </div>

    <!-- Network Provider Column -->
    <div class="card">
      <div class="card-title">
        <span>Network &amp; IP Source</span>
        <div style="display: flex; gap: 8px;">
          <button id="btnTabProxy" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="switchNetworkMode('proxy', true)">🌐 Proxies</button>
          <button id="btnTabMobile" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="switchNetworkMode('mobile_tether', true)">📱 Mobile ADB IP</button>
        </div>
      </div>

      <!-- Mode 1: Proxy Pool -->
      <div id="sectionProxy" style="display: flex; flex-direction: column; gap: 14px;">
        <div class="form-group" style="background: #0d131f; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 2px;">
          <label style="color: #60a5fa; font-weight: 700;">📥 Auto-Fetch from Proxy API URL (Optional)</label>
          <div style="display: flex; gap: 8px; margin-top: 6px;">
            <input type="text" id="proxyApiUrl" placeholder="https://api.yourproxyprovider.com/getproxies" style="flex: 1;">
            <button class="btn btn-secondary" onclick="fetchProxiesFromApi()">Fetch Now</button>
          </div>
          <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">Supports Bright Data, Smartproxy, Oxylabs, Webshare, ProxyScrape (JSON or Text list)</div>
        </div>

        <div class="form-group">
          <label>One proxy per line (Format: <code>host:port:user:pass</code> or <code>user:pass@host:port</code>)</label>
          <textarea id="proxiesText" placeholder="global.provider.com:10000:username:password&#10;1.2.3.4:8080"></textarea>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="font-size: 12px; color: var(--muted);">
            Datacenter IPs are auto-rejected by pool.py.
          </div>
          <button class="btn btn-primary" onclick="saveProxies()">Save Proxies</button>
        </div>
      </div>

      <!-- Mode 2: Mobile ADB IP Rotation -->
      <div id="sectionMobile" style="display: none; flex-direction: column; gap: 16px;">
        <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 12px 14px; font-size: 13px;">
          <div style="font-weight: 700; color: #34d399; display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span>⚡ Direct Mobile Cellular IP with Flight Mode Rotation</span>
          </div>
          <div style="color: var(--muted); font-size: 12px;">
            Phone is connected via USB. Browser connects directly through tethered mobile data. After each session, Airplane Mode toggles to renew dynamic cellular IP.
          </div>
        </div>

        <div class="form-group">
          <label>Current Public IP &amp; Carrier</label>
          <div id="mobileIpInfo" style="background: #090e18; border: 1px solid var(--border); padding: 10px 14px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #60a5fa;">
            Loading IP info…
          </div>
        </div>

        <div class="form-group">
          <label>Connected USB Debugging Devices</label>
          <div id="mobileDeviceList" style="background: #090e18; border: 1px solid var(--border); padding: 10px 14px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 13px;">
            Checking ADB devices…
          </div>
        </div>

        <div class="row-2">
          <div class="form-group">
            <label>Airplane Mode Off/On Wait (sec)</label>
            <input type="number" id="airplaneWait" value="4" min="2" max="15">
          </div>
          <div class="form-group" style="justify-content: flex-end;">
            <button class="btn btn-primary" onclick="saveMobileSettings()" style="height: 42px;">Save Mobile Mode</button>
          </div>
        </div>

        <div style="display: flex; gap: 10px; margin-top: 4px;">
          <button class="btn btn-secondary" style="flex: 1;" onclick="checkAdbStatus()">🔄 Refresh ADB &amp; IP</button>
          <button class="btn btn-success" style="flex: 1;" onclick="testAdbRotate()">✈️ Test Flight Mode Rotate</button>
        </div>
      </div>
    </div>
  </div>


  <!-- Live Console Logs -->
  <div class="card">
    <div class="card-title">
      <span>Live Process Logs</span>
      <span style="font-size: 12px; color: var(--muted); font-weight: normal;">Auto-updates every 3s</span>
    </div>
    <div class="console-box" id="consoleBox">
      <div class="console-line" style="color: var(--muted);">Waiting for logs…</div>
    </div>
  </div>

  <!-- Multi-Domain Fleet Governance Table (MD Spec 1) -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
      <span>🌐 Multi-Domain Fleet Governance &amp; Independent CTR Circuit Breakers</span>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span id="breakerStatusBadge" style="font-size: 11px; background: rgba(52, 211, 153, 0.15); color: #34d399; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">🟢 0 Breakers Tripped</span>
        <span style="font-size: 11px; background: rgba(52, 211, 153, 0.15); color: #34d399; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">Safe CTR Limit: &le; 5.0%</span>
        <button id="btnResetBreaker" class="btn btn-secondary" onclick="resetCircuitBreakers()" style="padding: 4px 10px; font-size: 11px;">🔓 Reset Breakers</button>
      </div>
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Sessions</th>
            <th>Impressions</th>
            <th>Clicks</th>
            <th>Live CTR</th>
            <th>Circuit Status</th>
            <th>Target CPM</th>
            <th>Est. Revenue</th>
          </tr>
        </thead>
        <tbody id="domainsTbody">
          <tr><td colspan="8" style="text-align: center; color: var(--muted);">Loading domain fleet status…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Pillar 1: Adsterra Real-Time Verification Funnel & Live Handshake Console -->
  <div class="card" style="border: 1px solid rgba(245, 158, 11, 0.4); box-shadow: 0 0 25px rgba(245, 158, 11, 0.08);">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 1.2rem;">⚡</span>
        <span style="font-weight: 800; color: #fff;">Real-Time Adsterra Funnel & Live Handshake Verification Console</span>
        <span style="background: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700;">● ZERO-WASTE GUARD ACTIVE</span>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <select id="funnelTestDomain" style="background: #090D16; color: #F8FAFC; border: 1px solid #334155; padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;">
          <option value="loanraaj.com">loanraaj.com (Personal &amp; Business Loans)</option>
          <option value="rechargetak.com">rechargetak.com (5G Telecom)</option>
          <option value="rechargepur.com">rechargepur.com (Smart Meter)</option>
          <option value="tazaloan.com">tazaloan.com (Instant Credit)</option>
          <option value="loankiseva.com">loankiseva.com (MSME Schemes)</option>
          <option value="karzseva.com">karzseva.com (Debt Relief)</option>
          <option value="loantau.com">loantau.com (KCC Tractor)</option>
          <option value="tazabhav.com">tazabhav.com (24K Gold Rates)</option>
          <option value="tazarokda.com">tazarokda.com (SIP Mutual Funds)</option>
          <option value="rechargekar.com">rechargekar.com (DTH Subsidy)</option>
        </select>
        <button id="btnRunFunnelTest" class="btn" onclick="runLiveFunnelTest()" style="background: linear-gradient(135deg, #F59E0B, #EF4444); color: #fff; font-weight: 700; padding: 5px 14px; font-size: 12px; border-radius: 6px;">⚡ Run 1-Click Verification Test</button>
        <button id="btnSyncAdsterra" class="btn btn-secondary" onclick="syncAdsterraApi()" style="padding: 5px 12px; font-size: 12px;">🔄 Sync Official API</button>
      </div>
    </div>

    <!-- Funnel Metrics Strip -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0;">
      <div style="background: #090D16; border: 1px solid #1E293B; border-radius: 8px; padding: 12px;">
        <div style="font-size: 11px; color: var(--muted); font-weight: 700;">BOT SESSIONS DISPATCHED</div>
        <div style="font-size: 20px; font-weight: 800; color: #60A5FA; font-family: monospace;" id="fnlSessions">0</div>
        <div style="font-size: 11px; color: var(--muted);">Real Chromium Visits</div>
      </div>
      <div style="background: #090D16; border: 1px solid #1E293B; border-radius: 8px; padding: 12px;">
        <div style="font-size: 11px; color: var(--muted); font-weight: 700;">ADSTERRA HANDSHAKES</div>
        <div style="font-size: 20px; font-weight: 800; color: #10B981; font-family: monospace;" id="fnlHandshakes">0</div>
        <div style="font-size: 11px; color: #10B981;">HTTP 200/302 Confirmed</div>
      </div>
      <div style="background: #090D16; border: 1px solid #1E293B; border-radius: 8px; padding: 12px;">
        <div style="font-size: 11px; color: var(--muted); font-weight: 700;">ADSTERRA OFFICIAL REVENUE</div>
        <div style="font-size: 20px; font-weight: 800; color: #F59E0B; font-family: monospace;" id="fnlRevenue">$0.000</div>
        <div style="font-size: 11px; color: var(--muted);" id="fnlApiImps">Official API Synced</div>
      </div>
      <div style="background: #090D16; border: 1px solid #1E293B; border-radius: 8px; padding: 12px;">
        <div style="font-size: 11px; color: var(--muted); font-weight: 700;">FUNNEL ACCEPTANCE RATE</div>
        <div style="font-size: 20px; font-weight: 800; color: #A855F7; font-family: monospace;" id="fnlRate">100.0%</div>
        <div style="font-size: 11px; color: #10B981;">● Zero Traffic Wasted</div>
      </div>
    </div>

    <!-- Visual 5-Stage Stepper -->
    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 16px;">
      <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3B82F6; border-radius: 6px; padding: 8px 10px; font-size: 11px;">
        <div style="font-weight: 800; color: #60A5FA;">1. Session Dispatched</div>
        <div style="color: var(--muted); font-size: 10px;">Anti-detect IP &amp; FP</div>
      </div>
      <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3B82F6; border-radius: 6px; padding: 8px 10px; font-size: 11px;">
        <div style="font-weight: 800; color: #60A5FA;">2. Ad Unit In-View</div>
        <div style="color: var(--muted); font-size: 10px;">Human Scroll &amp; Dwell</div>
      </div>
      <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10B981; border-radius: 6px; padding: 8px 10px; font-size: 11px;">
        <div style="font-weight: 800; color: #10B981;">3. Bézier Click Triggered</div>
        <div style="color: var(--muted); font-size: 10px;">Target Smartlink Hit</div>
      </div>
      <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10B981; border-radius: 6px; padding: 8px 10px; font-size: 11px;">
        <div style="font-weight: 800; color: #10B981;">4. Gateway 200/302 OK</div>
        <div style="color: var(--muted); font-size: 10px;">araplhn.org / bauval.org Beacon</div>
      </div>
      <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid #F59E0B; border-radius: 6px; padding: 8px 10px; font-size: 11px;">
        <div style="font-weight: 800; color: #F59E0B;">5. Adsterra Reconciled</div>
        <div style="color: var(--muted); font-size: 10px;">Official API Verified</div>
      </div>
    </div>

    <!-- Live Test Status Alert Box -->
    <div id="funnelTestStatusBox" style="display: none; background: #0A101D; border: 1px solid #3B82F6; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <strong id="funnelTestTitle" style="color: #60A5FA; font-size: 13px;">● Running Live Verification Test...</strong>
        <span id="funnelTestTime" style="font-size: 11px; color: var(--muted);"></span>
      </div>
      <div id="funnelTestLogs" style="font-family: monospace; font-size: 11px; color: #E2E8F0; line-height: 1.6; max-height: 150px; overflow-y: auto;"></div>
    </div>

    <!-- Live Network Handshakes Table -->
    <div style="margin-bottom: 16px;">
      <div style="font-size: 12px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px; display: flex; justify-content: space-between;">
        <span>📡 Live Adsterra Outbound Network Handshakes Stream (Real-Time Proof)</span>
        <span style="color: #10B981; font-size: 11px;">● Zero Mock Data (Real Chromium HTTP Traffic)</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th style="width: 140px;">Website</th>
              <th style="width: 150px;">Timestamp</th>
              <th>Adsterra Gateway URL (araplhn.org / bauval.org)</th>
              <th style="width: 130px;">HTTP Status</th>
              <th style="width: 110px;">Latency</th>
              <th style="width: 150px; text-align: right;">Handshake Verdict</th>
            </tr>
          </thead>
          <tbody id="handshakesTbody">
            <tr><td colspan="6" style="text-align: center; color: var(--muted);">Loading live handshakes stream...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Official Adsterra Stats API Reconciliation Table -->
    <div style="border-top: 1px solid #1E293B; padding-top: 14px;">
      <div style="font-size: 12px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;">
        📊 Official Adsterra API Reconciled Records (api3.adsterratools.com)
      </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Date</th>
            <th>API Imps</th>
            <th>API Clicks</th>
            <th>API CTR</th>
            <th>API eCPM</th>
            <th>API Revenue</th>
            <th>Local Imps</th>
            <th>Discrepancy</th>
          </tr>
        </thead>
        <tbody id="adsterraSyncTbody">
          <tr><td colspan="9" style="text-align: center; color: var(--muted);">Click "Sync Adsterra API" to fetch latest reconciliation data...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Layer 1: Adsterra Display Banner Vault Card -->
  <div class="card" id="bannerVaultCard" style="margin-bottom: 24px; border: 1px solid rgba(56, 189, 248, 0.25);">
    <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px;">
      <div>
        <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.9px; color: #38bdf8; text-transform: uppercase;">Layer 1 · Display Banner Vault</div>
        <h3 style="margin: 4px 0 0 0; font-size: 17px; color: #f8fafc;">Adsterra 300×250 · 728×90 · NativeBanner Manager</h3>
        <div id="bannerVaultSummary" style="font-size: 12px; color: var(--muted); margin-top: 4px;">Loading banner inventory...</div>
      </div>
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        <button type="button" onclick="syncBannerPlacements()" style="background: rgba(56, 189, 248, 0.14); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;">Sync API Placements</button>
        <button type="button" onclick="deployBannerSlots(false)" style="background: rgba(148, 163, 184, 0.14); color: #e2e8f0; border: 1px solid rgba(148, 163, 184, 0.3); padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;">Inject Local HTML</button>
        <button type="button" onclick="deployBannerSlots(true)" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; border: none; padding: 8px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">Inject &amp; Deploy Cloudflare</button>
      </div>
    </div>

    <div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 14px; margin-bottom: 16px;">
      <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; align-items: center;">
        <select id="bvDomainSelect" style="background: #0f172a; color: #f8fafc; border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 6px; padding: 7px 10px; font-size: 12px;">
          <option value="loanraaj.com">loanraaj.com</option>
          <option value="rechargetak.com">rechargetak.com</option>
          <option value="rechargepur.com">rechargepur.com</option>
          <option value="tazaloan.com">tazaloan.com</option>
          <option value="loankiseva.com">loankiseva.com</option>
          <option value="karzseva.com">karzseva.com</option>
          <option value="loantau.com">loantau.com</option>
          <option value="tazabhav.com">tazabhav.com</option>
          <option value="tazarokda.com">tazarokda.com</option>
          <option value="rechargekar.com">rechargekar.com</option>
        </select>
        <select id="bvSlotSelect" style="background: #0f172a; color: #f8fafc; border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 6px; padding: 7px 10px; font-size: 12px;">
          <option value="auto">Auto-Detect Slot (Single or Bulk All 3)</option>
          <option value="728x90">728×90 Leaderboard</option>
          <option value="300x250">300×250 Medium Rectangle</option>
          <option value="native">NativeBanner</option>
        </select>
        <button type="button" onclick="saveBannerSnippet()" style="background: #38bdf8; color: #0f172a; border: none; padding: 7px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">Validate &amp; Save Snippet</button>
        <span id="bvSaveFeedback" style="font-size: 12px; color: var(--muted);"></span>
      </div>
      <textarea id="bvSnippetInput" rows="3" placeholder="Paste official Adsterra 'Get Code' JS snippet(s) here (supports atOptions + invoke.js or NativeBanner container + invoke.js; single or multiple formats together)." style="width: 100%; background: #090d16; color: #e2e8f0; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 6px; padding: 9px 11px; font-family: monospace; font-size: 12px; box-sizing: border-box;"></textarea>
    </div>

    <div style="overflow-x: auto;">
      <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
        <thead>
          <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.2); text-align: left; color: var(--muted);">
            <th style="padding: 8px 6px;">Domain</th>
            <th style="padding: 8px 6px;">Domain ID</th>
            <th style="padding: 8px 6px;">728×90 Leaderboard</th>
            <th style="padding: 8px 6px;">300×250 Sidebar</th>
            <th style="padding: 8px 6px;">NativeBanner</th>
            <th style="padding: 8px 6px; text-align: right;">Ready</th>
          </tr>
        </thead>
        <tbody id="bannerVaultTbody">
          <tr><td colspan="6" style="padding: 12px; text-align: center; color: var(--muted);">Loading Display Banner inventory...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Pillar 2: High-Payout CPL/CPA Lead Engine Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>💰 Pillar 2: High-Payout CPL/CPA Post-Click Lead Engine</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="leadsCountBadge" style="font-size: 11px; background: rgba(34, 197, 94, 0.15); color: #22c55e; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">0 Leads ($0.00 Bounty)</span>
        <button id="btnSimulateLead" class="btn btn-secondary" onclick="simulateLeadConversion()" style="padding: 4px 10px; font-size: 11px;">⚡ +1 CPL Lead Submission</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Autonomous human form filler submitting geo-coherent IN/US persona + real Sonjj email details on advertiser landing pages ($1.50–$4.50 CPL conversion bounty).
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Persona Name</th>
            <th>Email</th>
            <th>Fields Filled</th>
            <th>Dwell Time</th>
            <th>Bounty</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="leadsTbody">
          <tr><td colspan="7" style="text-align: center; color: var(--muted);">No lead conversions recorded today...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Pillar 3: Dynamic SERP Organic Search Referrer Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>🔍 Pillar 3: Dynamic SERP Organic Search Referrer</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">40% Organic Google/Bing Traffic</span>
        <button id="btnPreviewSerp" class="btn btn-secondary" onclick="previewSerpQueries()" style="padding: 4px 10px; font-size: 11px;">⚡ Refresh Organic Queries</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Dynamic search intent generator interpolating proxy geo (City, State) to produce 100% verified Google Search referrers, eliminating invalid traffic (IVT) flags.
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Geo Location</th>
            <th>Synthesized Organic Search Query</th>
            <th>Search Engine</th>
            <th>Referrer Type</th>
          </tr>
        </thead>
        <tbody id="serpTbody">
          <tr><td colspan="5" style="text-align: center; color: var(--muted);">Click "Refresh Organic Queries" to view live query matrix...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Pillar 4: 24/7 Telegram Live Revenue & Circuit Breaker Bot Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>📱 Pillar 4: 24/7 Telegram Revenue & Circuit Breaker Bot</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="telegramBadge" style="font-size: 11px; background: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">@Liveadsterabot</span>
        <button id="btnTgTest" class="btn btn-secondary" onclick="sendTelegramTestAlert()" style="padding: 4px 10px; font-size: 11px;">⚡ Send Test Ping</button>
        <button id="btnTgHeartbeat" class="btn btn-secondary" onclick="sendTelegramHeartbeat()" style="padding: 4px 10px; font-size: 11px;">📊 Push Heartbeat</button>
        <button id="btnTgDailyReport" class="btn btn-secondary" onclick="sendTelegramDailyReport()" style="padding: 4px 10px; font-size: 11px;">📰 Send Daily Report</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Autonomous push notification agent delivering 2-hour multi-domain yield heartbeats, instant CTR circuit breaker trips (4.4% warning / 5.0% emergency), and CPL lead bounties straight to your Telegram phone.
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 14px;">
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Alerts Today</div>
        <div id="tgTotalAlerts" style="font-size: 1.1rem; font-weight: 700; color: #38bdf8;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Heartbeats</div>
        <div id="tgInfoAlerts" style="font-size: 1.1rem; font-weight: 700; color: #4ade80;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">CTR Warnings (≥4.4%)</div>
        <div id="tgWarnAlerts" style="font-size: 1.1rem; font-weight: 700; color: #facc15;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Emergencies (≥5.0%)</div>
        <div id="tgCritAlerts" style="font-size: 1.1rem; font-weight: 700; color: #f87171;">0</div>
      </div>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Type</th>
            <th>Level</th>
            <th>Domain</th>
            <th>Notification Message Preview</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="telegramTbody">
          <tr><td colspan="6" style="text-align: center; color: var(--muted);">No alerts dispatched yet today...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Layer 5: Google Search Console Real OAuth2 & Weekly Report Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>🔎 Layer 5: Google Search Console (OAuth2 / Service Account &amp; Weekly Report)</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="gscAuthBadge" style="font-size: 11px; background: rgba(248, 113, 113, 0.15); color: #f87171; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(248, 113, 113, 0.3);">🔴 Credentials Pending</span>
        <button id="btnGscSetup" class="btn btn-secondary" onclick="toggleGscSetupBox()" style="padding: 4px 10px; font-size: 11px;">🔑 Setup JSON</button>
        <button id="btnGscSync" class="btn btn-secondary" onclick="syncGscNow()" style="padding: 4px 10px; font-size: 11px;">🔄 Sync GSC</button>
        <button id="btnGscWeekly" class="btn btn-secondary" onclick="sendGscWeeklyReport()" style="padding: 4px 10px; font-size: 11px;">📈 Weekly Report</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Real Search Console API v3/v1 integration (Search Analytics, Sitemaps, URL Inspection, Indexing API v3) plus automated weekly Telegram digests. Clearly distinguishes live Google API data from fallback estimates.
    </div>

    <div id="gscCredsBox" style="display: none; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 12px; margin-bottom: 14px;">
      <div style="font-size: 12px; font-weight: 600; color: #38bdf8; margin-bottom: 6px;">Connect Real Google Search Console Credentials (Stored locally in gitignored state/)</div>
      <div style="font-size: 11px; color: var(--muted); margin-bottom: 8px; line-height: 1.5;">
        1. Google Cloud Console &rarr; Enable <b>Google Search Console API</b> &amp; <b>Web Search Indexing API</b>.<br>
        2. Create a <b>Service Account</b> &rarr; Keys &rarr; Download <b>JSON</b> (or paste OAuth2 refresh_token JSON).<br>
        3. Add the Service Account <code>client_email</code> as <b>Owner / Full user</b> inside Google Search Console for each domain.
      </div>
      <textarea id="gscCredsInput" rows="5" placeholder='Paste Google Service Account JSON ({"type": "service_account", "client_email": "...", "private_key": "..."})' style="width: 100%; background: rgba(2, 6, 23, 0.9); color: #e2e8f0; border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-family: monospace; font-size: 11px; box-sizing: border-box;"></textarea>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
        <span id="gscCredsMsg" style="font-size: 11px; color: var(--muted);">Saved safely to state/gsc_service_account.json (never committed to Git).</span>
        <button id="btnGscSaveCreds" class="btn btn-primary" onclick="saveGscCredentials()" style="padding: 5px 12px; font-size: 11px;">💾 Save Credentials</button>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px;">
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Live Properties</div>
        <div id="gscLiveCount" style="font-size: 1.05rem; font-weight: 700; color: #facc15;">0 / 10</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">7d Organic Imps</div>
        <div id="gscTotalImps" style="font-size: 1.05rem; font-weight: 700; color: #38bdf8;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">7d Organic Clicks</div>
        <div id="gscTotalClicks" style="font-size: 1.05rem; font-weight: 700; color: #4ade80;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Service Identity</div>
        <div id="gscClientEmail" style="font-size: 0.78rem; font-weight: 600; color: #cbd5e1; word-break: break-all;">Not Configured</div>
      </div>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Source</th>
            <th>GSC Property</th>
            <th>7d Imps</th>
            <th>7d Clicks</th>
            <th>CTR</th>
            <th>Avg Pos</th>
            <th>Top Query</th>
          </tr>
        </thead>
        <tbody id="gscTbody">
          <tr><td colspan="8" style="text-align: center; color: var(--muted);">Loading GSC status…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Layer 6: Push Notification Foundation Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
      <span>🔔 Layer 6: Push Notification Foundation (VAPID P-256 + OneSignal Collect-Only)</span>
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <span id="pushModeBadge" style="font-size: 11px; background: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">🔒 COLLECT ONLY (DELIVERY LOCKED)</span>
        <button id="btnPushSetup" class="btn btn-secondary" onclick="toggleOneSignalBox()" style="padding: 4px 10px; font-size: 11px;">🔑 Setup OneSignal</button>
        <button id="btnPushVapid" class="btn btn-secondary" onclick="rotateVapidKeys()" style="padding: 4px 10px; font-size: 11px;">🔐 Rotate VAPID</button>
        <button id="btnPushInject" class="btn btn-secondary" onclick="syncPushSitesHtml()" style="padding: 4px 10px; font-size: 11px;">💉 Sync Sites HTML</button>
        <button id="btnPushLockTest" class="btn btn-secondary" onclick="testPushDeliveryLock()" style="padding: 4px 10px; font-size: 11px;">🚫 Test Delivery Lock</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Collects Web Push subscribers via local RFC 8292 P-256 VAPID keys &amp; optional OneSignal Web SDK v16 without dispatching campaigns during testing phase. Keeps Monetag <code>/sw.js</code> untouched alongside dedicated <code>/push-sw.js</code> and <code>/OneSignalSDKWorker.js</code>.
    </div>

    <div id="pushSetupBox" style="display: none; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 12px; margin-bottom: 14px;">
      <div style="font-size: 12px; font-weight: 600; color: #38bdf8; margin-bottom: 6px;">Optional OneSignal Free-Tier App ID Setup (Saved locally in gitignored state/push_network.json)</div>
      <div style="font-size: 11px; color: var(--muted); margin-bottom: 8px; line-height: 1.5;">
        1. Create a free OneSignal account (10,000 subscribers free) &rarr; Web Push setup.<br>
        2. <code>/OneSignalSDKWorker.js</code> is already deployed across all 10 sites.<br>
        3. Paste your UUID App ID below (plus optional REST API Key for audience sync), then click <b>Sync Sites HTML</b>.
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr 160px; gap: 8px; margin-bottom: 8px;">
        <input id="pushOsAppId" type="text" placeholder="OneSignal App ID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)" style="background: rgba(2, 6, 23, 0.9); color: #e2e8f0; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-family: monospace; font-size: 11px;">
        <input id="pushOsRestKey" type="password" placeholder="Optional OneSignal REST API Key (kept secret)" style="background: rgba(2, 6, 23, 0.9); color: #e2e8f0; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-family: monospace; font-size: 11px;">
        <input id="pushOsDomain" type="text" placeholder="Global (blank) or domain.com" style="background: rgba(2, 6, 23, 0.9); color: #e2e8f0; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-family: monospace; font-size: 11px;">
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span id="pushSetupMsg" style="font-size: 11px; color: var(--muted);">VAPID collection works standalone even before OneSignal is linked.</span>
        <button id="btnPushSaveOs" class="btn btn-primary" onclick="saveOneSignalConfig()" style="padding: 5px 12px; font-size: 11px;">💾 Save OneSignal</button>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px;">
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">VAPID P-256 Key</div>
        <div id="pushVapidFp" style="font-size: 0.9rem; font-weight: 700; color: #38bdf8; font-family: monospace;">Loading…</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Active Provider</div>
        <div id="pushProviderLabel" style="font-size: 0.95rem; font-weight: 700; color: #facc15;">VAPID Local</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Collected Subscribers</div>
        <div id="pushSubTotal" style="font-size: 1.05rem; font-weight: 700; color: #4ade80;">0 <span id="pushAllowRate" style="font-size: 11px; color: var(--muted);">(0% allow)</span></div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">10-Site Injection</div>
        <div id="pushSitesReady" style="font-size: 1.05rem; font-weight: 700; color: #4ade80;">0 / 10</div>
      </div>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Collector Script</th>
            <th>push-sw.js</th>
            <th>OneSignal SW</th>
            <th>Subscribers</th>
            <th>Provider</th>
            <th>Delivery Mode</th>
          </tr>
        </thead>
        <tbody id="pushTbody">
          <tr><td colspan="7" style="text-align: center; color: var(--muted);">Loading Layer 6 Push status…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Pillar 5: Dual-ISP Carrier Hot-Failover Engine Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>⚡ Pillar 5: Dual-ISP Carrier Hot-Failover Engine</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="failoverModeBadge" style="font-size: 11px; background: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">PRIMARY: Mobile 4G/5G</span>
        <button id="btnProbeFailover" class="btn btn-secondary" onclick="probeFailoverHealth()" style="padding: 4px 10px; font-size: 11px;">⚡ Probe Health</button>
        <button id="btnSwapFailover" class="btn btn-secondary" onclick="toggleFailoverTransport()" style="padding: 4px 10px; font-size: 11px;">🔄 Force Hot-Swap</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Zero-drop carrier resilience switching dynamically between Primary Mobile 4G/5G (unlimited dynamic carrier IPs via ADB) and Fallback Residential Proxy Pool whenever high latency (>1500ms) or network timeout occurs.
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px;">
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Active Transport</div>
        <div id="foActiveTransport" style="font-size: 1.0rem; font-weight: 700; color: #4ade80;">PRIMARY MOBILE</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Carrier Latency</div>
        <div id="foLatency" style="font-size: 1.0rem; font-weight: 700; color: #38bdf8;">-- ms</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Primary Health</div>
        <div id="foHealth" style="font-size: 1.0rem; font-weight: 700; color: #4ade80;">ONLINE</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Failover Trips</div>
        <div id="foTotalTrips" style="font-size: 1.0rem; font-weight: 700; color: #facc15;">0</div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);">
        <div style="font-size: 11px; color: var(--muted);">Auto Recoveries</div>
        <div id="foRecoveries" style="font-size: 1.0rem; font-weight: 700; color: #38bdf8;">0</div>
      </div>
    </div>
  </div>

  <!-- Step 7.2: Real-Time Revenue Analytics & 7-Day Forecast Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>📈 Real-Time Revenue Analytics & 7-Day Forecast</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="forecastMonthlyBadge" style="font-size: 11px; background: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">Projected 30d: Loading…</span>
        <button class="btn btn-secondary" onclick="refreshAnalyticsCharts()" style="padding: 4px 10px; font-size: 11px;">🔄 Refresh Charts</button>
      </div>
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px;">
      <!-- Hourly Impression & Traffic Bars -->
      <div style="background: rgba(15, 23, 42, 0.6); padding: 14px; border-radius: 8px; border: 1px solid var(--border);">
        <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">📊 Hourly Session & Impression Pace (Today)</div>
        <div id="hourlyChartContainer" style="display: flex; align-items: flex-end; gap: 6px; height: 110px; padding: 8px 0; border-bottom: 1px solid var(--border);">
          <div style="color: var(--muted); font-size: 11px; margin: auto;">Loading hourly pacing…</div>
        </div>
      </div>
      <!-- 7-Day Projected Revenue -->
      <div style="background: rgba(15, 23, 42, 0.6); padding: 14px; border-radius: 8px; border: 1px solid var(--border);">
        <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">🔮 Predictive Revenue Model (Next 7 Days)</div>
        <div id="forecastContainer" style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; text-align: center;">
          <div style="color: var(--muted); font-size: 11px; grid-column: span 7; padding: 20px 0;">Loading forecasts…</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Unlimited Accounts & Warmed Cookie Pool Card (MD Spec 3 & 4) -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>👤 Unlimited Persona Accounts & Warmed Cookie Pool</span>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span id="accountsCountBadge" style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">Loading accounts…</span>
        <button class="btn btn-secondary" onclick="generateSyntheticAccount()" style="padding: 4px 10px; font-size: 11px;">⚡ +1 Synthetic Persona</button>
      </div>
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Email / Identity</th>
            <th>Persona Name</th>
            <th>Geo Location</th>
            <th>Credit Score</th>
            <th>Commercial Intent</th>
            <th>Warmed Status</th>
            <th>Cookies Cached</th>
          </tr>
        </thead>
        <tbody id="accountsTbody">
          <tr><td colspan="7" style="text-align: center; color: var(--muted);">Loading accounts pool…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Session Log Table -->
  <div class="card">
    <div class="card-title">
      <span>Recent Sessions Log (from sessions.db)</span>
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Domain</th>
            <th>Proxy</th>
            <th>Referrer</th>
            <th>Dwell</th>
            <th>Pages</th>
            <th>Clicks</th>
            <th>Imps</th>
            <th>Status</th>
            <th>Notes / Error</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody id="sessionsTbody">
          <tr><td colspan="11" style="text-align: center; color: var(--muted);">No sessions recorded yet</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<div id="toast" class="toast">Settings Saved</div>

<script>
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerText = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      
      // Update badge
      const badge = document.getElementById('statusBadge');
      const text = document.getElementById('statusText');
      const btnStart = document.getElementById('btnStart');
      const btnStop = document.getElementById('btnStop');

      if (data.is_running) {
        badge.className = 'status-badge running';
        text.innerText = 'RUNNING (PID ' + data.pid + ')';
        btnStart.disabled = true;
        btnStop.disabled = false;
        document.getElementById('statPID').innerText = data.pid;
      } else {
        badge.className = 'status-badge stopped';
        text.innerText = 'STOPPED';
        btnStart.disabled = false;
        btnStop.disabled = true;
        document.getElementById('statPID').innerText = '—';
      }

      document.getElementById('statSessionsToday').innerText = data.today;
      document.getElementById('statCTR').innerText = (data.ctr * 100).toFixed(1) + '%';

      const statTitle = document.getElementById('statProxyTitle');
      const statVal = document.getElementById('statProxies');
      const statSub = document.getElementById('statProxySub');

      if (currentNetworkMode === 'mobile_tether') {
        if (statTitle) statTitle.innerText = 'Network Source';
        if (statVal) {
          statVal.innerHTML = '<span style="color: #34d399; font-size: 20px;">📱 Mobile ADB</span>';
        }
        if (statSub) {
          statSub.innerText = data.mobile_info ? `${data.mobile_info.device} • ${data.mobile_info.carrier}` : 'Direct Cellular USB Tether';
        }
      } else {
        if (statTitle) statTitle.innerText = 'Active Proxies';
        if (statVal) {
          statVal.innerText = data.proxies_count;
          statVal.style.color = '#60a5fa';
        }
        if (statSub) statSub.innerText = 'Proxy Pool Mode';
      }

      if (data.metrics) {
        const impsClicksElem = document.getElementById('statImpsClicks');
        if (impsClicksElem) impsClicksElem.innerText = `${data.metrics.impressions} / ${data.metrics.clicks}`;
        const revElem = document.getElementById('statRevenue');
        if (revElem) revElem.innerText = `$${data.metrics.revenue.toFixed(2)} ($${data.metrics.cpm.toFixed(2)})`;
      }

      if (data.ua_stats) {
        const uaElem = document.getElementById('statUserAgents');
        if (uaElem) uaElem.innerText = (data.ua_stats.total || 27103).toLocaleString();
        const sub = document.getElementById('uaSubText');
        if (sub) {
          sub.innerText = `${(data.ua_stats.total || 27103).toLocaleString()} Real UAs (${(data.ua_stats.desktop_count || 8989).toLocaleString()} Desktop, ${(data.ua_stats.mobile_count || 18114).toLocaleString()} Mobile/Tablet)`;
        }
      }

      if (data.active_ua) {
        const uBadge = document.getElementById('uaLiveBadge');
        const dBadge = document.getElementById('uaDeviceBadge');
        const uText = document.getElementById('uaLiveText');
        const uIp = document.getElementById('uaLiveIP');
        const uTime = document.getElementById('uaLiveTime');
        const uTarget = document.getElementById('uaLiveTarget');

        if (uBadge) {
          if (data.active_ua.active) {
            uBadge.innerText = '🟢 LIVE CONNECTED';
            uBadge.style.background = 'rgba(34, 197, 94, 0.15)';
            uBadge.style.color = '#22c55e';
            uBadge.style.border = '1px solid rgba(34, 197, 94, 0.3)';
          } else if (data.is_running) {
            uBadge.innerText = '🔄 ROTATING NEXT';
            uBadge.style.background = 'rgba(234, 179, 8, 0.15)';
            uBadge.style.color = '#eab308';
            uBadge.style.border = '1px solid rgba(234, 179, 8, 0.3)';
          } else {
            uBadge.innerText = '⏸️ IDLE / STOPPED';
            uBadge.style.background = 'rgba(148,163,184,0.15)';
            uBadge.style.color = '#94a3b8';
            uBadge.style.border = 'none';
          }
        }
        if (dBadge) dBadge.innerText = data.active_ua.device_label || '⚪ Ready';
        if (uText) uText.innerText = data.active_ua.user_agent || 'Waiting for session…';
        if (uIp) uIp.innerText = data.active_ua.proxy_id || '—';
        if (uTime) uTime.innerText = data.active_ua.updated_at || '—';
        if (uTarget) uTarget.innerText = data.active_ua.target_url || '—';
      }

      // Update circuit breaker summary badge
      const cbBadge = document.getElementById('breakerStatusBadge');
      if (cbBadge && data.circuit_breaker) {
        const pCount = (data.circuit_breaker.paused_domains || []).length;
        if (pCount > 0 || data.circuit_breaker.global_pause) {
          cbBadge.innerText = data.circuit_breaker.global_pause && pCount === 0
            ? '⚠️ Global Pause'
            : `⚠️ ${pCount} Paused`;
          cbBadge.style.color = '#f87171';
          cbBadge.style.background = 'rgba(248, 113, 113, 0.15)';
          cbBadge.style.borderColor = 'rgba(248, 113, 113, 0.3)';
        } else {
          cbBadge.innerText = '🟢 0 Breakers Tripped';
          cbBadge.style.color = '#34d399';
          cbBadge.style.background = 'rgba(52, 211, 153, 0.15)';
          cbBadge.style.borderColor = 'rgba(52, 211, 153, 0.3)';
        }
      }

      // Update domain fleet table
      const domTbody = document.getElementById('domainsTbody');
      if (domTbody && data.domains && data.domains.length > 0) {
        domTbody.innerHTML = data.domains.map(d => {
          let badgeColor = '#34d399';
          let badgeBg = 'rgba(52, 211, 153, 0.15)';
          let badgeBorder = 'rgba(52, 211, 153, 0.3)';
          if (d.status === 'GUARD_ACTIVE') {
            badgeColor = '#fbbf24';
            badgeBg = 'rgba(251, 191, 36, 0.15)';
            badgeBorder = 'rgba(251, 191, 36, 0.3)';
          } else if (d.status === 'PAUSED' || d.status === 'CIRCUIT_PAUSED') {
            badgeColor = '#f87171';
            badgeBg = 'rgba(248, 113, 113, 0.15)';
            badgeBorder = 'rgba(248, 113, 113, 0.3)';
          }
          const titleAttr = d.breaker_reason ? ` title="${String(d.breaker_reason).replace(/"/g, '&quot;')}"` : '';
          return `
            <tr>
              <td><strong style="color: #f8fafc;">${d.domain}</strong></td>
              <td>${d.sessions}</td>
              <td>${d.impressions}</td>
              <td><strong style="color: ${d.clicks > 0 ? '#34d399' : 'inherit'}">${d.clicks}</strong></td>
              <td><span style="font-weight: 600; color: ${badgeColor}">${d.ctr.toFixed(2)}%</span></td>
              <td><span${titleAttr} style="font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; color: ${badgeColor}; background: ${badgeBg}; border: 1px solid ${badgeBorder};">${d.status}</span></td>
              <td>$${d.cpm ? d.cpm.toFixed(2) : '4.50'}</td>
              <td><strong style="color: #38bdf8;">$${d.estimated_revenue ? d.estimated_revenue.toFixed(2) : '0.00'}</strong></td>
            </tr>
          `;
        }).join('');
      } else if (domTbody) {
        domTbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--muted);">No domain sessions recorded today yet</td></tr>';
      }

      // Update accounts pool table
      const accBadge = document.getElementById('accountsCountBadge');
      if (accBadge && data.accounts_total !== undefined) {
        accBadge.innerText = `${data.accounts_total} Accounts (${data.accounts_warmed || 0} Warmed)`;
      }
      const accTbody = document.getElementById('accountsTbody');
      if (accTbody && data.accounts_sample && data.accounts_sample.length > 0) {
        accTbody.innerHTML = data.accounts_sample.map(a => {
          const p = a.persona || {};
          const isW = a.warmed || (a.cookies_count > 0);
          return `
            <tr>
              <td><strong style="color: #f8fafc;">${a.email}</strong></td>
              <td>${p.full_name || a.name || '—'}</td>
              <td>${p.city ? p.city + ', ' + p.state : 'India (IN)'}</td>
              <td><span style="color: #34d399; font-weight: 600;">${p.credit_score || 740}</span></td>
              <td><span style="font-size: 11px; color: #94a3b8;">${p.commercial_intent || 'Finance & Loans'}</span></td>
              <td><span style="font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; color: ${isW ? '#34d399' : '#fbbf24'}; background: ${isW ? 'rgba(52,211,153,0.15)' : 'rgba(251,191,36,0.15)'}; border: 1px solid ${isW ? 'rgba(52,211,153,0.3)' : 'rgba(251,191,36,0.3)'};">${isW ? '🔥 WARMED' : '⏳ FRESH'}</span></td>
              <td><strong>${a.cookies_count || (isW ? 18 : 0)}</strong></td>
            </tr>
          `;
        }).join('');
      } else if (accTbody) {
        accTbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted);">No accounts loaded yet</td></tr>';
      }

      // Update Adsterra API sync table
      if (data.adsterra_sync && data.adsterra_sync.length > 0) {
        renderAdsterraSync(data.adsterra_sync);
      }

      // Update Pillar 2 Leads table
      if (data.recent_leads && data.recent_leads.length > 0) {
        renderLeads(data.recent_leads, data.today_leads);
      }

      // Update sessions table
      const tbody = document.getElementById('sessionsTbody');
      if (data.recent_sessions && data.recent_sessions.length > 0) {
        tbody.innerHTML = data.recent_sessions.map(s => `
          <tr>
            <td>#${s.id}</td>
            <td><span style="color: #38bdf8; font-weight: 500;">${s.domain || 'loanraaj.com'}</span></td>
            <td title="${s.proxy_id}">${s.proxy_id}</td>
            <td title="${s.referrer}">${s.referrer ? s.referrer.substring(0, 32) + '…' : '(direct)'}</td>
            <td>${s.dwell}s</td>
            <td>${s.pages}</td>
            <td><strong style="color: ${s.ad_clicks > 0 ? '#34d399' : 'inherit'}">${s.ad_clicks}</strong></td>
            <td>${s.impressions}</td>
            <td><span style="color: ${s.status === 'ok' ? '#34d399' : '#f87171'}">${s.status}</span></td>
            <td style="color: ${s.error_reason ? '#fca5a5' : 'var(--muted)'}; font-size: 11px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(s.error_reason || '')}">${s.error_reason ? escapeHtml(s.error_reason) : '—'}</td>
            <td>${s.ts}</td>
          </tr>
        `).join('');
      }

      // Update console
      const cBox = document.getElementById('consoleBox');
      if (data.logs && data.logs.length > 0) {
        const atBottom = cBox.scrollHeight - cBox.scrollTop <= cBox.clientHeight + 50;
        cBox.innerHTML = data.logs.map(l => `<div class="console-line">${escapeHtml(l)}</div>`).join('');
        if (atBottom) { cBox.scrollTop = cBox.scrollHeight; }
      }
    } catch (e) {
      console.error("fetchStatus failed:", e);
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function onModeChange() {
    const isHeadless = document.getElementById('modeHeadless').checked;
    const badge = document.getElementById('modeBadge');
    const cardHeaded = document.getElementById('cardHeaded');
    const cardHeadless = document.getElementById('cardHeadless');

    if (isHeadless) {
      badge.innerText = '⚡ SILENT (HEADLESS)';
      badge.style.background = '#8b5cf6';
      cardHeadless.style.border = '1px solid #8b5cf6';
      cardHeadless.style.background = 'rgba(139, 92, 246, 0.12)';
      cardHeaded.style.border = '1px solid var(--border)';
      cardHeaded.style.background = '#111827';
    } else {
      badge.innerText = '👁️ VISIBLE (HEAD-ON)';
      badge.style.background = '#2563eb';
      cardHeaded.style.border = '1px solid #3b82f6';
      cardHeaded.style.background = 'rgba(59, 130, 246, 0.12)';
      cardHeadless.style.border = '1px solid var(--border)';
      cardHeadless.style.background = '#111827';
    }
  }

  let currentNetworkMode = 'proxy';

  function switchNetworkMode(mode, autoSave = false) {
    currentNetworkMode = mode;
    const btnProxy = document.getElementById('btnTabProxy');
    const btnMobile = document.getElementById('btnTabMobile');
    const secProxy = document.getElementById('sectionProxy');
    const secMobile = document.getElementById('sectionMobile');

    if (mode === 'mobile_tether') {
      btnMobile.className = 'btn btn-primary';
      btnProxy.className = 'btn btn-secondary';
      secMobile.style.display = 'flex';
      secProxy.style.display = 'none';
      document.getElementById('concurrency').value = 1;
      document.getElementById('concurrency').disabled = true;
      checkAdbStatus();
    } else {
      btnProxy.className = 'btn btn-primary';
      btnMobile.className = 'btn btn-secondary';
      secProxy.style.display = 'flex';
      secMobile.style.display = 'none';
      document.getElementById('concurrency').disabled = false;
    }
    if (autoSave) {
      saveConfig(false);
    }
    fetchStatus();
  }

  async function checkAdbStatus() {
    const devBox = document.getElementById('mobileDeviceList');
    const ipBox = document.getElementById('mobileIpInfo');
    devBox.innerText = 'Checking ADB devices…';
    ipBox.innerText = 'Checking public IP…';

    try {
      const res = await fetch('/api/adb/status');
      const data = await res.json();
      if (!data.ok) {
        devBox.innerHTML = `<span style="color: #f87171;">Error: ${escapeHtml(data.error || 'ADB not available')}</span>`;
        ipBox.innerText = 'Unable to check IP';
        return;
      }

      if (data.ip_info && data.ip_info.ip) {
        ipBox.innerHTML = `<strong>${data.ip_info.ip}</strong> (${data.ip_info.org} • ${data.ip_info.city}, ${data.ip_info.country})`;
      } else {
        ipBox.innerHTML = '<span style="color: #f59e0b;">No internet connection detected</span>';
      }

      if (data.devices && data.devices.length > 0) {
        devBox.innerHTML = data.devices.map(d => `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span>📱 <strong>${d.id}</strong></span>
            <span style="color: ${d.status === 'device' ? '#34d399' : '#f59e0b'}; font-weight: 700;">${d.status.toUpperCase()}</span>
          </div>
        `).join('');
      } else {
        devBox.innerHTML = '<span style="color: #f59e0b;">⚠️ No Android phone detected via USB. Connect phone with USB Tethering & USB Debugging enabled.</span>';
      }
    } catch (e) {
      devBox.innerText = 'Failed to query ADB status';
      ipBox.innerText = 'Error';
    }
  }

  async function testAdbRotate() {
    showToast('Toggling Airplane Mode on phone…');
    try {
      const res = await fetch('/api/adb/rotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ airplane_wait: parseInt(document.getElementById('airplaneWait').value) })
      });
      const data = await res.json();
      if (data.ok) {
        showToast(data.msg);
      } else {
        alert(data.msg);
      }
      checkAdbStatus();
    } catch (e) {
      alert('Error triggering IP rotation: ' + e);
    }
  }

  async function saveMobileSettings() {
    await saveConfig(true);
  }

  function updateTargetUrlsCount() {
    const el = document.getElementById('targetUrls');
    if (!el) return;
    const lines = el.value.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
    const countEl = document.getElementById('targetUrlsCount');
    if (countEl) {
      countEl.innerText = lines.length === 1 ? '1 URL Active' : (lines.length > 1 ? lines.length + ' URLs in Pool' : '0 URLs');
      countEl.style.color = lines.length > 0 ? '#10b981' : '#f59e0b';
    }
    renderTargetUrlPills(lines);
  }

  function renderTargetUrlPills(lines) {
    const pillsContainer = document.getElementById('targetUrlsPills');
    if (!pillsContainer) return;
    if (!lines || lines.length === 0) {
      pillsContainer.innerHTML = '<div style="font-size: 11px; color: var(--muted); font-style: italic; padding: 4px 0;">No URLs currently in pool. Paste above or use + Add URL.</div>';
      return;
    }
    pillsContainer.innerHTML = lines.map((url, idx) => `
      <div style="display: flex; align-items: center; justify-content: space-between; background: #0f172a; border: 1px solid #1e293b; border-radius: 4px; padding: 4px 8px; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
        <span style="color: #38bdf8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px;" title="${escapeHtml(url)}">${escapeHtml(url)}</span>
        <button onclick="removeUrlAt(${idx})" style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 3px; padding: 2px 6px; font-size: 10px; cursor: pointer; font-weight: 700; white-space: nowrap;" title="Remove this URL">❌ Remove</button>
      </div>
    `).join('');
  }

  function removeUrlAt(index) {
    const el = document.getElementById('targetUrls');
    if (!el) return;
    let lines = el.value.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
    if (index >= 0 && index < lines.length) {
      const removed = lines.splice(index, 1)[0];
      el.value = lines.join('\\n');
      updateTargetUrlsCount();
      saveConfig(false);
      showToast('Removed: ' + (removed.length > 30 ? removed.substring(0, 30) + '…' : removed));
    }
  }

  async function clearAllUrls() {
    const el = document.getElementById('targetUrls');
    if (el) el.value = '';
    updateTargetUrlsCount();
    await saveConfig(true);
    showToast('All URLs cleared from pool!');
  }

  async function addSingleUrl() {
    const input = document.getElementById('newUrlInput');
    if (!input) return;
    const val = input.value.trim();
    if (!val) {
      alert('Please enter a valid URL (e.g. https://loanraaj.com)');
      return;
    }
    const el = document.getElementById('targetUrls');
    if (!el) return;
    let lines = el.value.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
    if (lines.includes(val)) {
      alert('This URL is already in the pool!');
      return;
    }
    lines.push(val);
    el.value = lines.join('\\n');
    input.value = '';
    updateTargetUrlsCount();
    await saveConfig(true);
    showToast('Added: ' + val);
  }

  async function forceStopRunner() {
    const btn = document.getElementById('btnForceStop');
    if (btn) {
      btn.innerText = '🛑 Killing...';
      btn.disabled = true;
    }
    try {
      const res = await fetch('/api/force-stop', { method: 'POST' });
      const data = await res.json();
      showToast(data.msg || 'Force stopped!');
    } catch (e) {
      alert('Error during force stop: ' + e);
    } finally {
      if (btn) {
        btn.innerText = '🛑 Force Stop';
        btn.disabled = false;
      }
      fetchStatus();
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      const data = await res.json();
      const cfg = data.config;
      
      let urls = [];
      if (cfg.target && cfg.target.urls !== undefined && Array.isArray(cfg.target.urls)) {
        urls = cfg.target.urls;
      } else if (cfg.target && cfg.target.url) {
        urls = [cfg.target.url];
      }
      const targetUrlsEl = document.getElementById('targetUrls');
      if (targetUrlsEl) targetUrlsEl.value = urls.join('\\n');
      updateTargetUrlsCount();

      document.getElementById('minDwell').value = cfg.target.min_dwell || 25;
      document.getElementById('maxDwell').value = cfg.target.max_dwell || 110;
      document.getElementById('clickProb').value = cfg.target.click_prob || 0.06;
      document.getElementById('adClicksMax').value = cfg.target.ad_clicks_max || 2;
      document.getElementById('dailyCap').value = cfg.scheduler.daily_cap || 2000;
      document.getElementById('concurrency').value = cfg.scheduler.concurrency || 6;

      const isHeadless = !!(cfg.browser && cfg.browser.headless);
      if (isHeadless) {
        document.getElementById('modeHeadless').checked = true;
      } else {
        document.getElementById('modeHeaded').checked = true;
      }
      onModeChange();

      const netMode = (cfg.network && cfg.network.mode) || 'proxy';
      document.getElementById('airplaneWait').value = (cfg.network && cfg.network.airplane_mode_wait) || 4;
      switchNetworkMode(netMode);
      
      document.getElementById('proxiesText').value = data.proxies || '';
      document.getElementById('proxyApiUrl').value = (cfg.proxy && cfg.proxy.api_url) || '';
    } catch (e) {
      console.error("loadConfig failed:", e);
    }
  }

  async function saveConfig(showNotification = true) {
    const rawUrls = (document.getElementById('targetUrls') ? document.getElementById('targetUrls').value : '') || '';
    const urlsList = rawUrls.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

    const payload = {
      url: urlsList.length > 0 ? urlsList[0] : '',
      urls: urlsList,
      headless: document.getElementById('modeHeadless').checked,
      network_mode: currentNetworkMode,
      airplane_mode_wait: parseInt(document.getElementById('airplaneWait').value) || 4,
      proxy_api_url: document.getElementById('proxyApiUrl').value.trim(),
      min_dwell: parseInt(document.getElementById('minDwell').value),
      max_dwell: parseInt(document.getElementById('maxDwell').value),
      click_prob: parseFloat(document.getElementById('clickProb').value),
      ad_clicks_max: parseInt(document.getElementById('adClicksMax').value),
      daily_cap: parseInt(document.getElementById('dailyCap').value),
      concurrency: parseInt(document.getElementById('concurrency').value)
    };

    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      if (showNotification) {
        showToast('Configuration successfully saved!');
      }
    } else {
      alert('Error saving config: ' + data.error);
    }
  }

  async function fetchProxiesFromApi() {
    const url = document.getElementById('proxyApiUrl').value.trim();
    if (!url) {
      alert('Please enter a valid Proxy Provider API URL');
      return;
    }
    showToast('Fetching proxies from provider API…');
    try {
      const res = await fetch('/api/proxies/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_url: url })
      });
      const data = await res.json();
      if (data.ok) {
        document.getElementById('proxiesText').value = data.proxies;
        showToast('Successfully fetched ' + data.count + ' proxies!');
        fetchStatus();
      } else {
        alert('Failed to fetch proxies: ' + (data.error || data.msg));
      }
    } catch (e) {
      alert('Error fetching from API: ' + e);
    }
  }

  async function saveProxies() {
    const text = document.getElementById('proxiesText').value;
    const res = await fetch('/api/proxies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxies: text })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Proxies updated (' + data.count + ' active)');
      fetchStatus();
    } else {
      alert('Error saving proxies');
    }
  }

  async function startRunner() {
    const btn = document.getElementById('btnStart');
    if (btn) {
      btn.disabled = true;
      btn.innerText = '⏳ Starting…';
    }

    try {
      if (currentNetworkMode === 'proxy') {
        const pText = document.getElementById('proxiesText').value.trim();
        if (!pText) {
          alert("⚠️ You are in '🌐 Proxies' mode, but no proxies are configured!\\n\\nEither paste your proxies into 'One proxy per line', or switch to the '📱 Mobile ADB IP' tab to run directly via your connected phone's mobile data.");
          if (btn) { btn.disabled = false; btn.innerText = '▶ Start Live Run'; }
          return;
        }
      } else if (currentNetworkMode === 'mobile_tether') {
        try {
          const adbRes = await fetch('/api/adb/status');
          const adbData = await adbRes.json();
          if (!adbData.ok || !adbData.devices || adbData.devices.length === 0) {
            alert("⚠️ No Android phone detected via USB debugging!\\n\\nPlease check:\\n1. Mobile phone is plugged in via USB\\n2. USB Tethering is turned ON in phone Settings\\n3. USB Debugging is turned ON in Developer Options\\n4. Check phone screen to allow USB debugging prompt");
            if (btn) { btn.disabled = false; btn.innerText = '▶ Start Live Run'; }
            return;
          }
        } catch (err) {
          console.warn("Pre-flight ADB check error:", err);
        }
      }

      await saveConfig(false);
      const res = await fetch('/api/start', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showToast(data.msg);
      } else {
        alert(data.msg);
      }
    } catch (e) {
      alert("Error starting runner: " + e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = '▶ Start Live Run';
      }
      fetchStatus();
    }
  }

  async function stopRunner() {
    const res = await fetch('/api/stop', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      showToast('Runner stopping…');
    } else {
      alert(data.msg);
    }
    fetchStatus();
  }

  async function syncUserAgents() {
    const btn = document.getElementById('btnSyncUA');
    if (btn) {
      btn.disabled = true;
      btn.innerText = '⏳ Syncing…';
    }
    showToast('Fetching latest 27,000+ UAs from useragent.in…');
    try {
      const res = await fetch('/api/useragents/sync', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showToast('Successfully synced ' + data.total.toLocaleString() + ' UAs from useragent.in!');
      } else {
        alert('Sync error: ' + (data.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error syncing UAs: ' + e);
    }
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔄 Sync from useragent.in';
    }
    fetchStatus();
  }

  async function generateSyntheticAccount() {
    showToast('Generating synthetic high-intent persona…');
    try {
      const res = await fetch('/api/accounts/generate', { method: 'POST' });
      const data = await res.json();
      if (data.success && data.account) {
        showToast('Generated: ' + data.account.email + ' (' + (data.account.persona?.full_name || 'Persona') + ')');
        fetchStatus();
      } else {
        alert('Failed: ' + (data.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error generating account: ' + e);
    }
  }

  async function syncAdsterraApi() {
    const btn = document.getElementById('btnSyncAdsterra');
    if (btn) btn.innerText = '⏳ Syncing...';
    try {
      const res = await fetch('/api/adsterra/sync', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ok') {
        renderAdsterraSync(data.records);
        showToast('Adsterra API Synced: ' + data.synced_count + ' domains reconciled!');
      } else {
        alert('Adsterra Sync error: ' + (data.error || 'Unknown'));
      }
    } catch (e) {
      alert('Network error syncing Adsterra API: ' + e);
    } finally {
      if (btn) btn.innerText = '🔄 Sync Adsterra API';
    }
  }

  function renderAdsterraSync(records) {
    const tbody = document.getElementById('adsterraSyncTbody');
    if (!tbody || !records || records.length === 0) return;
    tbody.innerHTML = records.map(r => {
      const disc = r.discrepancy_pct || 0;
      const isOk = Math.abs(disc) < 15.0;
      const discColor = isOk ? '#34d399' : '#fbbf24';
      return `
        <tr>
          <td><strong style="color: #f8fafc;">${r.domain}</strong></td>
          <td>${r.date}</td>
          <td>${r.api_impressions}</td>
          <td><strong>${r.api_clicks}</strong></td>
          <td><span style="color: #38bdf8;">${r.api_ctr.toFixed(2)}%</span></td>
          <td>$${r.api_cpm.toFixed(2)}</td>
          <td><strong style="color: #34d399;">$${r.api_revenue.toFixed(3)}</strong></td>
          <td>${r.local_impressions}</td>
          <td><span style="font-weight: 600; color: ${discColor};">${disc > 0 ? '+' : ''}${disc.toFixed(1)}%</span></td>
        </tr>
      `;
    }).join('');
  }

  function _renderSlotCell(slotData) {
    if (!slotData) return '<span style="color: var(--muted);">—</span>';
    const pid = slotData.placement_id ? '#' + escapeHtml(String(slotData.placement_id)) : 'No ID';
    if (slotData.configured) {
      const preview = escapeHtml(String(slotData.zone_key_preview || ''));
      return `<span style="color: #34d399; font-weight: 700;">LIVE</span> <span style="font-family: monospace; color: #94a3b8;">(${pid} · ${preview})</span>`;
    }
    return `<span style="color: #fbbf24; font-weight: 600;">Awaiting Code</span> <span style="font-family: monospace; color: var(--muted);">(${pid})</span>`;
  }

  function renderBannerVault(payload) {
    const tbody = document.getElementById('bannerVaultTbody');
    const summaryEl = document.getElementById('bannerVaultSummary');
    if (!tbody || !payload) return;
    const domains = payload.domains || [];
    const cfg = payload.configured_slots ?? 0;
    const tot = payload.total_slots ?? 30;
    if (summaryEl) {
      summaryEl.innerText = `${cfg}/${tot} Live Display Snippets Configured · ${domains.length} Publisher Domains`;
    }
    if (domains.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="padding: 12px; text-align: center; color: var(--muted);">No domain placement data synced yet. Click Sync API Placements.</td></tr>';
      return;
    }
    tbody.innerHTML = domains.map(d => {
      const slots = d.slots || {};
      const readyColor = d.configured_count === d.total_slots ? '#34d399' : (d.configured_count > 0 ? '#38bdf8' : '#fbbf24');
      return `
        <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.12);">
          <td style="padding: 8px 6px;"><strong style="color: #f8fafc;">${escapeHtml(String(d.domain || ''))}</strong></td>
          <td style="padding: 8px 6px; font-family: monospace; color: var(--muted);">${d.adsterra_domain_id ? escapeHtml(String(d.adsterra_domain_id)) : '—'}</td>
          <td style="padding: 8px 6px;">${_renderSlotCell(slots.banner_728x90)}</td>
          <td style="padding: 8px 6px;">${_renderSlotCell(slots.banner_300x250)}</td>
          <td style="padding: 8px 6px;">${_renderSlotCell(slots.native_banner)}</td>
          <td style="padding: 8px 6px; text-align: right; font-weight: 700; color: ${readyColor};">${d.configured_count}/${d.total_slots}</td>
        </tr>
      `;
    }).join('');
  }

  async function loadBannerVault() {
    try {
      const res = await fetch('/api/adsterra/banners');
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === 'ok') renderBannerVault(data);
    } catch (err) {
      console.error('Banner vault load error:', err);
    }
  }

  async function syncBannerPlacements() {
    const fb = document.getElementById('bvSaveFeedback');
    if (fb) fb.innerText = 'Syncing Adsterra API placements...';
    try {
      const res = await fetch('/api/adsterra/banners/sync', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ok') {
        renderBannerVault(data.inventory);
        const synced = data.sync ? data.sync.placements_synced : 0;
        if (fb) fb.innerHTML = `<span style="color: #34d399;">Synced ${synced} official placements.</span>`;
        showToast('Placements synced');
      } else if (fb) {
        fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(data.error || 'Sync failed'))}</span>`;
      }
    } catch (err) {
      if (fb) fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(err))}</span>`;
    }
  }

  async function saveBannerSnippet() {
    const domain = (document.getElementById('bvDomainSelect') || {}).value;
    const slot = (document.getElementById('bvSlotSelect') || {}).value || 'auto';
    const rawEl = document.getElementById('bvSnippetInput');
    const snippet = rawEl ? rawEl.value.trim() : '';
    const fb = document.getElementById('bvSaveFeedback');
    if (!snippet) {
      if (fb) fb.innerHTML = '<span style="color: #fbbf24;">Paste an Adsterra Get Code snippet first.</span>';
      return;
    }
    if (fb) fb.innerText = 'Validating & saving...';
    try {
      const res = await fetch('/api/adsterra/banners/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, slot, snippet })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        if (rawEl) rawEl.value = '';
        renderBannerVault(data.inventory);
        const savedList = (data.saved || []).map(x => x.slot).join(', ');
        if (fb) fb.innerHTML = `<span style="color: #34d399;">Saved ${escapeHtml(savedList)} for ${escapeHtml(domain)}. Click Inject/Deploy to update HTML.</span>`;
        showToast('Banner snippet saved');
      } else if (fb) {
        fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(data.error || 'Invalid snippet'))}</span>`;
      }
    } catch (err) {
      if (fb) fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(err))}</span>`;
    }
  }

  async function deployBannerSlots(deployCf) {
    const fb = document.getElementById('bvSaveFeedback');
    if (fb) fb.innerText = deployCf ? 'Injecting HTML slots & deploying to Cloudflare Pages...' : 'Injecting HTML slots across local sites/...';
    try {
      const res = await fetch('/api/adsterra/banners/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deploy: Boolean(deployCf) })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        const inj = data.inject || {};
        const cfCount = Array.isArray(inj.deploy_results) ? inj.deploy_results.filter(r => r.ok).length : 0;
        const msg = deployCf
          ? `Scanned ${inj.files_scanned || 0} pages, updated ${inj.files_updated || 0}, Cloudflare OK: ${cfCount}`
          : `Scanned ${inj.files_scanned || 0} pages, updated ${inj.files_updated || 0} locally`;
        if (fb) fb.innerHTML = `<span style="color: #34d399;">${escapeHtml(msg)}</span>`;
        showToast('Banner injection complete');
      } else if (fb) {
        fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(data.error || 'Deploy failed'))}</span>`;
      }
    } catch (err) {
      if (fb) fb.innerHTML = `<span style="color: #f87171;">${escapeHtml(String(err))}</span>`;
    }
  }

  async function simulateLeadConversion() {
    showToast('Simulating post-click CPL lead form conversion…');
    try {
      const res = await fetch('/api/leads/simulate', { method: 'POST' });
      const data = await res.json();
      if (data.success && data.lead) {
        showToast('CPL Lead Submitted! Bounty: +$' + data.lead.bounty_est.toFixed(2));
        fetchStatus();
      } else {
        alert('Failed: ' + (data.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error simulating lead: ' + e);
    }
  }

  function renderLeads(leads, summary) {
    const badge = document.getElementById('leadsCountBadge');
    if (badge && summary) {
      badge.innerText = `${summary.today_leads || 0} Leads (+$${(summary.estimated_bounty || 0).toFixed(2)} Bounty)`;
    }
    const tbody = document.getElementById('leadsTbody');
    if (!tbody || !leads || leads.length === 0) return;
    tbody.innerHTML = leads.map(l => `
      <tr>
        <td><strong style="color: #38bdf8;">${l.domain}</strong></td>
        <td>${l.persona_name}</td>
        <td>${l.email}</td>
        <td>${l.fields_filled} fields</td>
        <td>${l.dwell_sec}s</td>
        <td><strong style="color: #34d399;">+$${l.bounty_est.toFixed(2)}</strong></td>
        <td><span class="status-badge status-ok">${l.status.toUpperCase()}</span></td>
      </tr>
    `).join('');
  }

  async function previewSerpQueries() {
    const btn = document.getElementById('btnPreviewSerp');
    if (btn) btn.innerText = '⏳ Generating…';
    try {
      const res = await fetch('/api/serp/preview');
      const data = await res.json();
      if (data.success && data.queries) {
        renderSerp(data.queries);
      }
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '⚡ Refresh Organic Queries';
    }
  }

  function renderSerp(queries) {
    const tbody = document.getElementById('serpTbody');
    if (!tbody || !queries || queries.length === 0) return;
    tbody.innerHTML = queries.map(q => `
      <tr>
        <td><strong style="color: #38bdf8;">${q.domain}</strong></td>
        <td>${q.city}, ${q.state}</td>
        <td><span style="color: #f8fafc; font-style: italic;">"${q.query}"</span></td>
        <td><span style="font-weight: 600; color: #4ade80;">Google</span></td>
        <td><span class="status-badge status-ok">ORGANIC SEARCH</span></td>
      </tr>
    `).join('');
  }

  async function fetchTelegramStatus() {
    try {
      const res = await fetch('/api/telegram/status');
      const data = await res.json();
      if (data.success) {
        const badge = document.getElementById('telegramBadge');
        if (badge) {
          if (data.configured) {
            badge.style.background = 'rgba(34, 197, 94, 0.2)';
            badge.style.color = '#4ade80';
            badge.style.borderColor = 'rgba(34, 197, 94, 0.4)';
            badge.innerText = `🟢 Live: @${data.bot_username}`;
          } else {
            badge.style.background = 'rgba(250, 204, 21, 0.15)';
            badge.style.color = '#facc15';
            badge.style.borderColor = 'rgba(250, 204, 21, 0.3)';
            badge.innerText = `🟡 Standby Mode: @${data.bot_username}`;
          }
        }
        if (data.summary) {
          const totEl = document.getElementById('tgTotalAlerts');
          const infEl = document.getElementById('tgInfoAlerts');
          const wrnEl = document.getElementById('tgWarnAlerts');
          const crtEl = document.getElementById('tgCritAlerts');
          if (totEl) totEl.innerText = data.summary.total || 0;
          if (infEl) infEl.innerText = (data.summary.INFO || 0) + (data.summary.SUCCESS || 0);
          if (wrnEl) wrnEl.innerText = data.summary.WARNING || 0;
          if (crtEl) crtEl.innerText = data.summary.CRITICAL || 0;
        }
        renderTelegramAlerts(data.recent_alerts || []);
      }
    } catch (e) {
      console.error(e);
    }
  }

  function renderTelegramAlerts(alerts) {
    const tbody = document.getElementById('telegramTbody');
    if (!tbody) return;
    if (alerts.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted);">No alerts dispatched yet today...</td></tr>';
      return;
    }
    tbody.innerHTML = alerts.map(a => {
      let levelColor = '#4ade80';
      if (a.level === 'WARNING') levelColor = '#facc15';
      if (a.level === 'CRITICAL') levelColor = '#f87171';
      const cleanMsg = (a.message || '').replace(/<[^>]*>?/gm, '').substring(0, 75) + '…';
      const statusBadge = a.sent_live ? '<span class="status-badge status-ok">LIVE SENT</span>' : '<span class="status-badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3);">STANDBY LOG</span>';
      return `
        <tr>
          <td style="font-size: 11px; color: var(--muted);">${a.ts}</td>
          <td><strong style="color: #38bdf8;">${a.alert_type}</strong></td>
          <td><span style="font-weight: 700; color: ${levelColor};">${a.level}</span></td>
          <td><code>${a.domain || 'ALL FLEET'}</code></td>
          <td style="font-size: 11px; color: #f1f5f9;">${cleanMsg}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    }).join('');
  }

  async function sendTelegramTestAlert() {
    const btn = document.getElementById('btnTgTest');
    if (btn) btn.innerText = '⏳ Sending…';
    try {
      const res = await fetch('/api/telegram/test', { method: 'POST' });
      const data = await res.json();
      await fetchTelegramStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '⚡ Send Test Ping';
    }
  }

  async function sendTelegramHeartbeat() {
    const btn = document.getElementById('btnTgHeartbeat');
    if (btn) btn.innerText = '⏳ Pushing…';
    try {
      const res = await fetch('/api/telegram/heartbeat', { method: 'POST' });
      const data = await res.json();
      await fetchTelegramStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '📊 Push Heartbeat';
    }
  }

  async function sendTelegramDailyReport() {
    const btn = document.getElementById('btnTgDailyReport');
    if (btn) btn.innerText = '⏳ Sending…';
    try {
      const res = await fetch('/api/telegram/daily-report', { method: 'POST' });
      await res.json();
      await fetchTelegramStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '📰 Send Daily Report';
    }
  }

  async function resetCircuitBreakers() {
    const btn = document.getElementById('btnResetBreaker');
    if (btn) btn.innerText = '⏳ Resetting…';
    try {
      const res = await fetch('/api/circuit-breaker/reset', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('Circuit breakers & active UA state reset cleanly.');
        await fetchStatus();
      }
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '🔓 Reset Breakers';
    }
  }

  function escGsc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toggleGscSetupBox() {
    const box = document.getElementById('gscCredsBox');
    if (box) box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }

  async function fetchGscStatus() {
    try {
      const res = await fetch('/api/gsc/status');
      const data = await res.json();
      if (!data.success) return;
      const auth = data.auth || {};
      const sum = data.summary || {};
      const badge = document.getElementById('gscAuthBadge');
      if (badge) {
        if (auth.configured && (sum.live_domains_count || 0) > 0) {
          badge.style.background = 'rgba(34, 197, 94, 0.2)';
          badge.style.color = '#4ade80';
          badge.style.borderColor = 'rgba(34, 197, 94, 0.4)';
          badge.innerText = `🟢 Connected (${auth.auth_type})`;
        } else if (auth.configured) {
          badge.style.background = 'rgba(56, 189, 248, 0.15)';
          badge.style.color = '#38bdf8';
          badge.style.borderColor = 'rgba(56, 189, 248, 0.35)';
          badge.innerText = `🔵 Auth Ready — Click Sync GSC`;
        } else {
          badge.style.background = 'rgba(250, 204, 21, 0.15)';
          badge.style.color = '#facc15';
          badge.style.borderColor = 'rgba(250, 204, 21, 0.35)';
          badge.innerText = '🟡 Estimate Mode (OAuth Pending)';
        }
      }
      const liveEl = document.getElementById('gscLiveCount');
      const impEl = document.getElementById('gscTotalImps');
      const clkEl = document.getElementById('gscTotalClicks');
      const emailEl = document.getElementById('gscClientEmail');
      if (liveEl) liveEl.innerText = `${sum.live_domains_count || 0} / ${sum.total_domains || 10}`;
      if (impEl) impEl.innerText = (sum.total_impressions_7d || 0).toLocaleString();
      if (clkEl) clkEl.innerText = (sum.total_clicks_7d || 0).toLocaleString();
      if (emailEl) emailEl.innerText = auth.client_email || (auth.configured ? auth.auth_type : 'Not Configured');

      const tbody = document.getElementById('gscTbody');
      if (tbody) {
        const rows = data.domains || [];
        if (rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--muted);">Click "Sync GSC" to populate domain metrics.</td></tr>';
        } else {
          tbody.innerHTML = rows.map(d => {
            const isLive = d.data_source === 'google_search_console_api' && !d.is_mock;
            const srcBadge = isLive
              ? '<span class="status-badge status-ok">LIVE GSC</span>'
              : '<span class="status-badge" style="background: rgba(250, 204, 21, 0.15); color: #facc15; border: 1px solid rgba(250, 204, 21, 0.35);">ESTIMATE</span>';
            const topQ = d.top_queries && d.top_queries.length > 0 ? escGsc(d.top_queries[0].query) : '—';
            const ctrPct = ((d.ctr || 0) * 100).toFixed(2) + '%';
            return `
              <tr>
                <td><strong>${escGsc(d.domain)}</strong></td>
                <td>${srcBadge}</td>
                <td style="font-size: 11px; color: var(--muted);">${escGsc(d.property_url || 'pending')}</td>
                <td>${Number(d.impressions || 0).toLocaleString()}</td>
                <td>${Number(d.clicks || 0).toLocaleString()}</td>
                <td>${ctrPct}</td>
                <td>#${Number(d.avg_position || 0).toFixed(1)}</td>
                <td style="font-size: 11px; color: #cbd5e1;">${topQ}</td>
              </tr>
            `;
          }).join('');
        }
      }
    } catch (e) {
      console.error('GSC status error:', e);
    }
  }

  async function syncGscNow() {
    const btn = document.getElementById('btnGscSync');
    if (btn) btn.innerText = '⏳ Syncing…';
    try {
      const res = await fetch('/api/gsc/sync', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('GSC sync completed (' + ((data.report && data.report.live_domains_count) || 0) + ' live properties).');
      }
      await fetchGscStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '🔄 Sync GSC';
    }
  }

  async function sendGscWeeklyReport() {
    const btn = document.getElementById('btnGscWeekly');
    if (btn) btn.innerText = '⏳ Generating…';
    try {
      const res = await fetch('/api/gsc/weekly-report', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('Weekly GSC report saved (' + data.date + ') & Telegram dispatched: ' + Boolean(data.telegram_sent));
      }
      await fetchGscStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '📈 Weekly Report';
    }
  }

  async function saveGscCredentials() {
    const inp = document.getElementById('gscCredsInput');
    const msg = document.getElementById('gscCredsMsg');
    const raw = inp ? inp.value.trim() : '';
    if (!raw) {
      if (msg) { msg.style.color = '#f87171'; msg.innerText = 'Paste valid JSON before saving.'; }
      return;
    }
    try {
      const res = await fetch('/api/gsc/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credentials_json: raw })
      });
      const data = await res.json();
      if (data.success) {
        if (msg) {
          msg.style.color = '#4ade80';
          msg.innerText = 'Saved ' + data.saved.auth_type + (data.saved.client_email ? ' (' + data.saved.client_email + ')' : '');
        }
        if (inp) inp.value = '';
        await fetchGscStatus();
      } else {
        if (msg) { msg.style.color = '#f87171'; msg.innerText = data.error || 'Invalid credentials payload'; }
      }
    } catch (e) {
      if (msg) { msg.style.color = '#f87171'; msg.innerText = 'Failed to save credentials'; }
    }
  }

  function escPush(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toggleOneSignalBox() {
    const box = document.getElementById('pushSetupBox');
    if (box) box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }

  async function fetchPushStatus() {
    try {
      const res = await fetch('/api/push/status');
      const data = await res.json();
      if (!data.success) return;
      const vapid = data.vapid || {};
      const os = data.onesignal || {};
      const stats = data.subscribers || {};
      const sites = data.sites_coverage || {};

      const badge = document.getElementById('pushModeBadge');
      if (badge) {
        if (os.delivery_locked !== false) {
          badge.style.background = 'rgba(34, 197, 94, 0.15)';
          badge.style.color = '#4ade80';
          badge.style.borderColor = 'rgba(34, 197, 94, 0.35)';
          badge.innerText = '🔒 COLLECT ONLY (DELIVERY LOCKED)';
        } else {
          badge.style.background = 'rgba(248, 113, 113, 0.18)';
          badge.style.color = '#f87171';
          badge.style.borderColor = 'rgba(248, 113, 113, 0.4)';
          badge.innerText = '📡 DELIVERY UNLOCKED';
        }
      }

      const fpEl = document.getElementById('pushVapidFp');
      const provEl = document.getElementById('pushProviderLabel');
      const subEl = document.getElementById('pushSubTotal');
      const readyEl = document.getElementById('pushSitesReady');

      if (fpEl) fpEl.innerText = vapid.fingerprint ? (vapid.fingerprint + ' (' + String(vapid.public_key || '').slice(0, 10) + '…)') : 'Pending';
      if (provEl) provEl.innerText = os.configured ? 'OneSignal + VAPID' : 'VAPID P-256 Local';
      const allowPct = Math.round((stats.allow_rate || 0) * 100);
      if (subEl) subEl.innerHTML = `${Number(stats.total_subscribers || 0).toLocaleString()} <span style="font-size:11px; color:var(--muted);">(${allowPct}% allow)</span>`;
      if (readyEl) readyEl.innerText = `${sites.ready_domains || 0} / ${sites.total_domains || 10}`;

      const tbody = document.getElementById('pushTbody');
      if (tbody) {
        const rows = sites.domains || [];
        const byDom = stats.by_domain || {};
        if (rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted);">No domain coverage data yet.</td></tr>';
        } else {
          tbody.innerHTML = rows.map(r => {
            const subCnt = byDom[r.domain] || 0;
            const okBadge = '<span class="status-badge status-ok">READY</span>';
            const missBadge = '<span class="status-badge status-warn">MISSING</span>';
            const lockBadge = os.delivery_locked !== false ? '<span class="status-badge status-ok">COLLECT ONLY</span>' : '<span class="status-badge status-warn">LIVE</span>';
            const provName = (os.domain_app_ids && os.domain_app_ids[r.domain]) || os.app_id ? 'OneSignal+VAPID' : 'VAPID P-256';
            return `
              <tr>
                <td><strong>${escPush(r.domain)}</strong></td>
                <td>${r.has_collector ? okBadge : missBadge}</td>
                <td>${r.has_push_sw ? okBadge : missBadge}</td>
                <td>${r.has_onesignal_sw ? okBadge : missBadge}</td>
                <td>${Number(subCnt).toLocaleString()}</td>
                <td style="font-size: 11px; color: #cbd5e1;">${escPush(provName)}</td>
                <td>${lockBadge}</td>
              </tr>
            `;
          }).join('');
        }
      }
    } catch (e) {
      console.error('Push status error:', e);
    }
  }

  async function saveOneSignalConfig() {
    const appId = (document.getElementById('pushOsAppId')?.value || '').trim();
    const restKey = (document.getElementById('pushOsRestKey')?.value || '').trim();
    const domain = (document.getElementById('pushOsDomain')?.value || '').trim();
    const msg = document.getElementById('pushSetupMsg');
    try {
      const res = await fetch('/api/push/onesignal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: appId, rest_api_key: restKey, domain })
      });
      const data = await res.json();
      if (data.success) {
        if (msg) { msg.style.color = '#4ade80'; msg.innerText = 'OneSignal config saved safely. Click Sync Sites HTML to inject.'; }
        const rkEl = document.getElementById('pushOsRestKey');
        if (rkEl) rkEl.value = '';
        await fetchPushStatus();
      } else {
        if (msg) { msg.style.color = '#f87171'; msg.innerText = data.error || 'Invalid OneSignal config'; }
      }
    } catch (e) {
      if (msg) { msg.style.color = '#f87171'; msg.innerText = 'Failed to save OneSignal config'; }
    }
  }

  async function rotateVapidKeys() {
    const btn = document.getElementById('btnPushVapid');
    if (btn) btn.innerText = '⏳ Rotating…';
    try {
      const res = await fetch('/api/push/vapid/generate', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('Rotated P-256 VAPID keypair (fp: ' + (data.vapid && data.vapid.fingerprint) + '). Sync Sites HTML to update.');
      }
      await fetchPushStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '🔐 Rotate VAPID';
    }
  }

  async function syncPushSitesHtml() {
    const btn = document.getElementById('btnPushInject');
    if (btn) btn.innerText = '⏳ Injecting…';
    try {
      const res = await fetch('/api/push/inject', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('Synced Layer 6 Push Foundation across ' + ((data.summary && data.summary.sites_processed) || 10) + ' domains.');
      }
      await fetchPushStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '💉 Sync Sites HTML';
    }
  }

  async function testPushDeliveryLock() {
    const btn = document.getElementById('btnPushLockTest');
    if (btn) btn.innerText = '⏳ Checking…';
    try {
      const res = await fetch('/api/push/deliver-test', { method: 'POST' });
      const data = await res.json();
      if (data.success && data.result && data.result.status === 'blocked_testing_phase') {
        showToast('Delivery Lock Verified: ' + data.result.reason);
      } else {
        showToast('Push delivery check status: ' + (data.result && data.result.status));
      }
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '🚫 Test Delivery Lock';
    }
  }

  async function fetchFailoverStatus() {
    try {
      const res = await fetch('/api/failover/status');
      const data = await res.json();
      if (data.success && data.status) {
        const s = data.status;
        const badge = document.getElementById('failoverModeBadge');
        const activeEl = document.getElementById('foActiveTransport');
        const latEl = document.getElementById('foLatency');
        const hlthEl = document.getElementById('foHealth');
        const tripsEl = document.getElementById('foTotalTrips');
        const recovEl = document.getElementById('foRecoveries');

        if (activeEl) activeEl.innerText = s.active_mode.replace('_', ' ');
        if (latEl) latEl.innerText = (s.last_latency_ms > 0 ? `${s.last_latency_ms} ms` : 'Active');
        if (tripsEl) tripsEl.innerText = s.total_failovers || 0;
        if (recovEl) recovEl.innerText = s.total_recoveries || 0;

        if (s.active_mode === 'PRIMARY_MOBILE') {
          if (badge) {
            badge.style.background = 'rgba(34, 197, 94, 0.2)';
            badge.style.color = '#4ade80';
            badge.innerText = 'PRIMARY: Mobile 4G/5G';
          }
          if (activeEl) activeEl.style.color = '#4ade80';
        } else {
          if (badge) {
            badge.style.background = 'rgba(56, 189, 248, 0.2)';
            badge.style.color = '#38bdf8';
            badge.innerText = 'FALLBACK: Residential Proxy';
          }
          if (activeEl) activeEl.style.color = '#38bdf8';
        }

        if (hlthEl) {
          if (s.primary_healthy) {
            hlthEl.innerText = 'ONLINE';
            hlthEl.style.color = '#4ade80';
          } else {
            hlthEl.innerText = 'DEGRADED';
            hlthEl.style.color = '#f87171';
          }
        }
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function probeFailoverHealth() {
    const btn = document.getElementById('btnProbeFailover');
    if (btn) btn.innerText = '⏳ Probing…';
    try {
      const res = await fetch('/api/failover/test', { method: 'POST' });
      const data = await res.json();
      await fetchFailoverStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '⚡ Probe Health';
    }
  }

  async function toggleFailoverTransport() {
    const btn = document.getElementById('btnSwapFailover');
    if (btn) btn.innerText = '⏳ Swapping…';
    try {
      const res = await fetch('/api/failover/switch', { method: 'POST' });
      const data = await res.json();
      await fetchFailoverStatus();
    } catch (e) {
      console.error(e);
    } finally {
      if (btn) btn.innerText = '🔄 Force Hot-Swap';
    }
  }

  async function refreshAnalyticsCharts() {
    try {
      const res = await fetch('/api/analytics/charts');
      const data = await res.json();
      if (!data) return;

      const monthlyBadge = document.getElementById('forecastMonthlyBadge');
      if (monthlyBadge) monthlyBadge.textContent = 'Projected 30d: $' + (data.monthly_estimate_usd || 0).toFixed(2);

      const hBox = document.getElementById('hourlyChartContainer');
      if (hBox && data.hourly) {
        if (data.hourly.length === 0) {
          hBox.innerHTML = '<div style="color: var(--muted); font-size: 11px; margin: auto;">No sessions recorded today yet</div>';
        } else {
          const maxImps = Math.max(...data.hourly.map(h => h.impressions), 10);
          hBox.innerHTML = data.hourly.map(h => {
            const hPct = Math.max(12, Math.round((h.impressions / maxImps) * 85));
            return `<div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">
              <div style="font-size: 9px; color: #38bdf8;">${h.impressions}</div>
              <div style="width: 100%; max-width: 20px; height: ${hPct}px; background: linear-gradient(180deg, #38bdf8 0%, #1e3a8a 100%); border-radius: 3px 3px 0 0;" title="${h.hour}: ${h.sessions} sessions, ${h.impressions} imps, ${h.clicks} clicks"></div>
              <div style="font-size: 9px; color: var(--muted);">${h.hour.split(':')[0]}h</div>
            </div>`;
          }).join('');
        }
      }

      const fBox = document.getElementById('forecastContainer');
      if (fBox && data.forecast_7d) {
        fBox.innerHTML = data.forecast_7d.map(f => `
          <div style="background: rgba(30, 41, 59, 0.7); padding: 8px 4px; border-radius: 6px; border: 1px solid var(--border);">
            <div style="font-size: 10px; color: var(--muted);">${f.day_name.substring(0, 3)}</div>
            <div style="font-size: 12px; font-weight: 700; color: #4ade80; margin: 4px 0;">$${f.projected_usd.toFixed(2)}</div>
            <div style="font-size: 9px; color: #94a3b8;">$${f.confidence_low.toFixed(1)}-$${f.confidence_high.toFixed(1)}</div>
          </div>
        `).join('');
      }
    } catch (e) {
      console.debug('Analytics chart fetch error:', e);
    }
  }

  // Initial load & Polling
  loadConfig();
  fetchStatus();
  previewSerpQueries();
  fetchTelegramStatus();
  fetchGscStatus();
  fetchPushStatus();
  fetchFailoverStatus();
  refreshAnalyticsCharts();
  setInterval(() => {
    fetchStatus();
    fetchTelegramStatus();
    fetchFailoverStatus();
  }, 3000);
  setInterval(() => {
    refreshAnalyticsCharts();
  }, 10000);

  // Adsterra Real-Time Funnel Handshake Polling & Test Runner
  async function fetchAdsterraFunnelData() {
    try {
      const res = await fetch('/api/adsterra/funnel');
      if (!res.ok) return;
      const json = await res.json();
      if (!json || !json.data) return;
      const f = json.data.funnel || {};
      
      const elSess = document.getElementById('fnlSessions');
      if (elSess) elSess.innerText = f.sessions_dispatched || '0';
      
      const elHs = document.getElementById('fnlHandshakes');
      if (elHs) elHs.innerText = f.confirmed_handshakes || '0';
      
      const elRev = document.getElementById('fnlRevenue');
      if (elRev) elRev.innerText = f.api_revenue || '$0.000';
      
      const elImps = document.getElementById('fnlApiImps');
      if (elImps) elImps.innerText = `${f.api_impressions || 0} Imps / ${f.api_clicks || 0} Clicks Counted`;
      
      const elRate = document.getElementById('fnlRate');
      if (elRate) elRate.innerText = f.handshake_success_rate || '100.0%';

      const hsTbody = document.getElementById('handshakesTbody');
      if (hsTbody && json.data.recent_handshakes && json.data.recent_handshakes.length > 0) {
        let rows = '';
        json.data.recent_handshakes.forEach(h => {
          const isOk = [200, 301, 302, 307].includes(h.status_code);
          const statusBadge = isOk 
            ? `<span style="background: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 700;">HTTP ${h.status_code} OK</span>`
            : `<span style="background: rgba(239, 68, 68, 0.15); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 700;">HTTP ${h.status_code}</span>`;
          
          const verdictBadge = isOk
            ? `<span style="color: #10B981; font-weight: 800; font-size: 11px;">● COUNTED &amp; VERIFIED</span>`
            : `<span style="color: #EF4444; font-weight: 800; font-size: 11px;">● PENDING / RETRY</span>`;

          rows += `
            <tr>
              <td><strong style="color: #F8FAFC;">${h.domain}</strong></td>
              <td style="font-family: monospace; font-size: 11px; color: var(--muted);">${h.ts || ''}</td>
              <td><code style="font-family: monospace; font-size: 11px; color: #60A5FA; background: rgba(59, 130, 246, 0.1); padding: 2px 6px; border-radius: 4px; word-break: break-all;">${h.ad_url}</code></td>
              <td>${statusBadge}</td>
              <td style="font-family: monospace; font-size: 11px;">${h.latency_ms || 150}ms</td>
              <td style="text-align: right;">${verdictBadge}</td>
            </tr>
          `;
        });
        hsTbody.innerHTML = rows;
      }
    } catch (err) {
      console.error('Funnel data fetch notice:', err);
    }
  }

  async function runLiveFunnelTest() {
    const domSelect = document.getElementById('funnelTestDomain');
    const targetDomain = domSelect ? domSelect.value : 'loanraaj.com';
    const btn = document.getElementById('btnRunFunnelTest');
    const statusBox = document.getElementById('funnelTestStatusBox');
    const titleEl = document.getElementById('funnelTestTitle');
    const logsEl = document.getElementById('funnelTestLogs');
    
    if (btn) {
      btn.disabled = true;
      btn.innerText = 'Testing Funnel...';
    }
    if (statusBox) statusBox.style.display = 'block';
    if (titleEl) titleEl.innerText = `● Launching Chromium Session on ${targetDomain} (Tracking Network Handshake)...`;
    if (logsEl) logsEl.innerHTML = `<div>[${new Date().toLocaleTimeString()}] Initializing headless Chromium with anti-detect fingerprint...</div>`;

    try {
      const res = await fetch('/api/adsterra/test-handshake', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({domain: targetDomain})
      });
      const data = await res.json();
      
      if (data.success) {
        if (titleEl) titleEl.innerHTML = `<span style="color: #10B981;">✔ VERIFIED 100%! Adsterra Gateway Received Impression &amp; Click Handshake (${data.duration_sec}s)</span>`;
        let logsHtml = '';
        (data.steps || []).forEach(s => {
          logsHtml += `<div>✔ ${s}</div>`;
        });
        if (data.handshakes && data.handshakes.length > 0) {
          data.handshakes.forEach(h => {
            logsHtml += `<div style="color: #10B981; font-weight: 700;">★ Network Handshake Confirmed: ${h.url} -> Status ${h.status}</div>`;
          });
        }
        if (logsEl) logsEl.innerHTML = logsHtml;
        await fetchAdsterraFunnelData();
      } else {
        if (titleEl) titleEl.innerHTML = `<span style="color: #EF4444;">✖ Test Notice: ${data.error || 'Check logs'}</span>`;
      }
    } catch (err) {
      if (titleEl) titleEl.innerHTML = `<span style="color: #EF4444;">✖ Error: ${err}</span>`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = '⚡ Run 1-Click Verification Test';
      }
    }
  }

  fetchAdsterraFunnelData();
  setInterval(fetchAdsterraFunnelData, 5000);
  loadBannerVault();
</script>

</body>
</html>
"""

# ── HTTP Request Handler ────────────────────────────────────────────────────────

class UIRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine access logs
        pass

    def _send_json(
        self,
        data: dict,
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for h_k, h_v in (extra_headers or []):
            self.send_header(h_k, h_v)
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(
        self,
        html: str,
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for h_k, h_v in (extra_headers or []):
            self.send_header(h_k, h_v)
        self.end_headers()
        self.wfile.write(raw)

    def _send_redirect(
        self,
        location: str,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        for h_k, h_v in (extra_headers or []):
            self.send_header(h_k, h_v)
        self.end_headers()

    def _require_crm_unlocked(self) -> bool:
        from admin_ui import profile_auth
        if profile_auth.is_crm_locked(self.headers.get("Cookie")):
            self._send_json({"ok": False, "locked": True, "error": "CRM session is locked."}, status=401)
            return False
        return True

    def _redirect_if_crm_locked(self) -> bool:
        from admin_ui import profile_auth
        if profile_auth.is_crm_locked(self.headers.get("Cookie")):
            self._send_redirect("/crm/login")
            return True
        return False

    def _banner_inventory_payload(self) -> dict:
        import adsterra_links
        domains = adsterra_links.get_banner_inventory()
        return {
            "status": "ok",
            "configured_slots": sum(d["configured_count"] for d in domains),
            "total_slots": sum(d["total_slots"] for d in domains),
            "domains": domains,
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Domain Virtual Host router
        host_header = (self.headers.get("Host") or "").split(":")[0].lower()
        if host_header.startswith("www."):
            host_header = host_header[4:]

        if path.startswith("/crm-assets/"):
            rel_asset = path[len("/crm-assets/"):].lstrip("/")
            assets_root = Path("admin_ui/assets").resolve()
            asset_file = (assets_root / rel_asset).resolve()
            if asset_file.is_relative_to(assets_root) and asset_file.is_file():
                ext = asset_file.suffix.lower()
                mime_map = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".ico": "image/x-icon",
                    ".woff2": "font/woff2",
                    ".woff": "font/woff",
                    ".ttf": "font/ttf",
                }
                ctype = mime_map.get(ext, "application/octet-stream")
                raw_bytes = asset_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(raw_bytes)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Asset Not Found")
            return

        if path in ("/crm/login", "/crm/login/"):
            from admin_ui import profile_auth
            from admin_ui.views import render_login_view
            q = parse_qs(parsed.query)
            err = "Invalid operator credentials. Please try again." if q.get("error") else ""
            prof = profile_auth.load_profile()
            self._send_html(render_login_view(prof, error_msg=err), extra_headers=[("Cache-Control", "no-store")])
            return

        if path in ("/crm", "/crm/"):
            if self._redirect_if_crm_locked():
                return
            from admin_ui.shell import render_crm_shell
            self._send_html(render_crm_shell(), extra_headers=[("Cache-Control", "no-store")])
            return

        if path in ("/autopublish", "/autopublish/"):
            if self._redirect_if_crm_locked():
                return
            from autopublish_dashboard_html import AUTOPUBLISH_DASHBOARD_HTML
            self._send_html(AUTOPUBLISH_DASHBOARD_HTML)
            return

        if path == "/api/autopublish/stats":
            if not self._require_crm_unlocked():
                return
            try:
                import autopublish_service
                query = parse_qs(parsed.query)
                dom = query.get("domain", ["tazaloan"])[0]
                stats = autopublish_service.get_autopublish_stats(dom)
                self._send_json(stats)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)
            return

        if path == "/api/autopublish/preview":
            try:
                import html as _html
                import autopublish_service
                query = parse_qs(parsed.query)
                dom = query.get("domain", ["loanraaj"])[0]
                slug = query.get("slug", [""])[0]
                safe_mode = query.get("safe", ["0"])[0] == "1"
                html_content = autopublish_service.get_preview_html(dom, slug, safe=safe_mode)
                if html_content:
                    self._send_html(html_content)
                else:
                    self._send_html(
                        f"<div style='font-family:sans-serif;padding:40px;text-align:center;'><h2>Preview Loading...</h2><p>Preview file for {_html.escape(dom)}/{_html.escape(slug)} not found or being generated.</p></div>"
                    )
            except Exception as e:
                import html as _html
                self._send_html(f"<h3>Preview Error: {_html.escape(str(e))}</h3>")
            return

        DOMAIN_FOLDERS = {
            "loanraaj.com": "loanraaj",
            "rechargetak.com": "rechargetak",
            "rechargepur.com": "rechargepur",
            "tazaloan.com": "tazaloan",
            "loankiseva.com": "loankiseva",
            "karzseva.com": "karzseva",
            "loantau.com": "loantau",
            "tazabhav.com": "tazabhav",
            "tazarokda.com": "tazarokda",
            "rechargekar.com": "rechargekar",
        }

        sites_root = Path("sites").resolve()

        # 1. Direct static route: /sites/<folder>
        if path.startswith("/sites/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                folder_name = parts[1]
                if ".." not in folder_name and "/" not in folder_name and "\\" not in folder_name:
                    canonical_folder = folder_name if folder_name.endswith(".com") else f"{folder_name}.com"
                    site_file = (sites_root / canonical_folder / "index.html").resolve()
                    if site_file.is_relative_to(sites_root) and site_file.is_file():
                        content = site_file.read_text(encoding="utf-8")
                        self._send_html(content)
                        return

        # 2. Virtual Host route for live domains
        if host_header in DOMAIN_FOLDERS:
            # If accessing admin dashboard on rechargekar.com/admin or /dashboard
            if host_header == "rechargekar.com" and path in ("/admin", "/dashboard"):
                pass  # Fall through to render dashboard
            else:
                folder_name = DOMAIN_FOLDERS[host_header]
                clean_p = path.lstrip("/") or "index.html"
                canonical_dir = folder_name if folder_name.endswith(".com") else f"{folder_name}.com"
                candidate = (sites_root / canonical_dir / clean_p).resolve()
                candidates = [candidate] if candidate.is_relative_to(sites_root) else []
                for target_file in candidates:
                    if target_file.is_file():
                        ctype = "text/html; charset=utf-8"
                        if clean_p.endswith(".js"):
                            ctype = "application/javascript; charset=utf-8"
                        elif clean_p.endswith(".css"):
                            ctype = "text/css; charset=utf-8"
                        elif clean_p.endswith(".txt"):
                            ctype = "text/plain; charset=utf-8"
                        elif clean_p.endswith(".xml"):
                            ctype = "application/xml; charset=utf-8"
                        elif clean_p.endswith(".png"):
                            ctype = "image/png"
                        elif clean_p.endswith((".jpg", ".jpeg")):
                            ctype = "image/jpeg"

                        raw_bytes = target_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(len(raw_bytes)))
                        self.send_header("Access-Control-Allow-Origin", "*")
                        if clean_p.endswith("sw.js"):
                            self.send_header("Service-Worker-Allowed", "/")
                        self.end_headers()
                        self.wfile.write(raw_bytes)
                        return

        if path in ("", "/", "/admin", "/dashboard"):
            if self._redirect_if_crm_locked():
                return
            from admin_ui.shell import render_crm_shell
            self._send_html(render_crm_shell(), extra_headers=[("Cache-Control", "no-store")])
            return

        if path in ("/classic", "/classic/"):
            if self._redirect_if_crm_locked():
                return
            cfg = read_config()
            net_mode = cfg.get("network", {}).get("mode", "proxy")
            raw_urls = cfg.get("target", {}).get("urls") or ([cfg.get("target", {}).get("url")] if cfg.get("target", {}).get("url") else [])
            urls_text = "\n".join(raw_urls)
            proxies_text = read_proxies()

            rendered = HTML_PAGE
            if net_mode == "mobile_tether":
                rendered = rendered.replace('id="btnTabProxy" class="btn btn-primary"', 'id="btnTabProxy" class="btn btn-secondary"')
                rendered = rendered.replace('id="btnTabMobile" class="btn btn-secondary"', 'id="btnTabMobile" class="btn btn-primary"')
                rendered = rendered.replace('id="sectionProxy" style="display: flex;', 'id="sectionProxy" style="display: none;')
                rendered = rendered.replace('id="sectionMobile" style="display: none;', 'id="sectionMobile" style="display: flex;')
                rendered = rendered.replace("let currentNetworkMode = 'proxy';", "let currentNetworkMode = 'mobile_tether';")

            if urls_text:
                rendered = rendered.replace('id="targetUrls" rows="3" placeholder="https://example.com/article-1&#10;https://example.com/article-2&#10;https://example.com/article-3" style="width: 100%; font-family: \'JetBrains Mono\', monospace; font-size: 12px; line-height: 1.4; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: #0f172a; color: #e2e8f0; resize: vertical;" oninput="updateTargetUrlsCount()"></textarea>', f'id="targetUrls" rows="3" placeholder="https://example.com/article-1&#10;https://example.com/article-2&#10;https://example.com/article-3" style="width: 100%; font-family: \'JetBrains Mono\', monospace; font-size: 12px; line-height: 1.4; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: #0f172a; color: #e2e8f0; resize: vertical;" oninput="updateTargetUrlsCount()">{urls_text}</textarea>')
                count_lbl = f"{len(raw_urls)} URLs in Pool" if len(raw_urls) > 1 else "1 URL Active"
                rendered = rendered.replace('>1 URL Active</span>', f'>{count_lbl}</span>')

            if proxies_text:
                rendered = rendered.replace('id="proxiesText" placeholder="global.provider.com:10000:username:password&#10;1.2.3.4:8080"></textarea>', f'id="proxiesText" placeholder="global.provider.com:10000:username:password&#10;1.2.3.4:8080">{proxies_text}</textarea>')

            self._send_html(rendered)
            return

        if path.startswith("/api/"):
            if not self._require_crm_unlocked():
                return

        if path == "/api/status":
            db.init()
            import ua_provider
            cfg = read_config()
            net_mode = cfg.get("network", {}).get("mode", "proxy")
            cpm_rate = float(cfg.get("target", {}).get("cpm_rate", 2.50))
            metrics = db.get_metrics(cpm_rate)

            mobile_info = None
            if net_mode == "mobile_tether":
                mobile_info = get_cached_mobile_info()

            from accounts_manager import AccountsManager
            from anomaly_detector import AnomalyDetector
            from autopilot_watchdog import AutopilotWatchdog
            acc_mgr = AccountsManager()
            accs = acc_mgr.get_all_accounts()
            warmed_c = sum(1 for a in accs if a.warmed or a.cookies_count > 0)

            detector = AnomalyDetector()
            cb_state = detector._load_state()
            paused_map = cb_state.get("paused_domains", {}) or {}
            domains_list = db.all_domains_summary(
                cpm_rate,
                configured_domains=cfg.get("target", {}).get("domains", []),
            )
            latest_sync = db.get_latest_adsterra_sync(limit=20)
            sync_by_dom = {}
            for srow in latest_sync:
                d_key = str(srow.get("domain") or "").lower().strip()
                if d_key and d_key not in sync_by_dom:
                    sync_by_dom[d_key] = srow

            for dom_item in domains_list:
                is_cb_paused, cb_action, cb_reason = detector.is_domain_paused(dom_item["domain"])
                if is_cb_paused:
                    dom_item["status"] = "PAUSED"
                    dom_item["allow_click"] = False
                    dom_item["breaker_action"] = cb_action
                    dom_item["breaker_reason"] = cb_reason
                s_match = sync_by_dom.get(str(dom_item["domain"]).lower().strip())
                if s_match is not None:
                    dom_item["cpm"] = round(float(s_match.get("api_cpm") or 0.0), 3)
                    dom_item["estimated_revenue"] = round(float(s_match.get("api_revenue") or 0.0), 4)
                    dom_item["api_impressions"] = int(s_match.get("api_impressions") or 0)
                    dom_item["api_clicks"] = int(s_match.get("api_clicks") or 0)

            if sync_by_dom:
                tot_api_imps = sum(int(r.get("api_impressions") or 0) for r in sync_by_dom.values())
                tot_api_rev = round(sum(float(r.get("api_revenue") or 0.0) for r in sync_by_dom.values()), 4)
                metrics["revenue"] = tot_api_rev
                metrics["cpm"] = round((tot_api_rev / tot_api_imps * 1000.0), 3) if tot_api_imps > 0 else 0.0

            status_data = {
                "is_running": RUNNER.is_running(),
                "pid": RUNNER.get_pid(),
                "today": db.today(),
                "ctr": db.ctr(100),
                "metrics": metrics,
                "domains": domains_list,
                "circuit_breaker": {
                    "paused_domains": sorted(paused_map.keys()),
                    "global_pause": bool(cb_state.get("global_pause", False)),
                },
                "accounts_total": len(accs),
                "accounts_warmed": warmed_c,
                "accounts_sample": [a.to_dict() for a in accs[:8]],
                "hourly_target": AutopilotWatchdog.calculate_diurnal_pace(
                    base_hourly_rate=cfg.get("scheduler", {}).get("sessions_per_hour", 150),
                    diurnal=cfg.get("scheduler", {}).get("diurnal"),
                    weekday_scale=cfg.get("scheduler", {}).get("weekday_scale")
                ),
                "network_mode": net_mode,
                "mobile_info": mobile_info,
                "proxies_count": count_valid_proxies(),
                "ua_stats": ua_provider.get_stats(),
                "active_ua": read_active_ua(),
                "recent_sessions": db.last_sessions(20),
                "adsterra_sync": latest_sync[:10],
                "today_leads": db.today_leads_summary(),
                "recent_leads": db.get_lead_conversions(limit=8),
                "logs": RUNNER.get_logs(),
            }
            self._send_json(status_data)
            return

        if path == "/api/analytics/charts":
            db.init()
            with db._conn() as con:
                hourly_rows = con.execute(
                    """
                    SELECT strftime('%H:00', ts, 'localtime') AS hour_slot,
                           COUNT(*) AS sessions,
                           SUM(impressions) AS imps,
                           SUM(ad_clicks) AS clicks
                    FROM sessions
                    WHERE DATE(ts, 'localtime') = DATE('now', 'localtime')
                    GROUP BY hour_slot
                    ORDER BY hour_slot ASC
                    """
                ).fetchall()
                domain_rows = con.execute(
                    """
                    SELECT domain, COUNT(*) AS sessions, SUM(impressions) AS imps, SUM(ad_clicks) AS clicks
                    FROM sessions
                    WHERE DATE(ts, 'localtime') = DATE('now', 'localtime')
                    GROUP BY domain
                    ORDER BY imps DESC
                    """
                ).fetchall()

            from revenue_forecast import RevenueForecaster
            try:
                forecaster = RevenueForecaster().fit()
                forecast_7d = forecaster.forecast_next_7_days()
                monthly_est = forecaster.forecast_monthly_estimate()
            except Exception as fe:
                forecast_7d = []
                monthly_est = 0.0

            payload = {
                "hourly": [
                    {"hour": r["hour_slot"], "sessions": int(r["sessions"] or 0), "impressions": int(r["imps"] or 0), "clicks": int(r["clicks"] or 0)}
                    for r in hourly_rows
                ],
                "domains": [
                    {"domain": r["domain"], "sessions": int(r["sessions"] or 0), "impressions": int(r["imps"] or 0), "clicks": int(r["clicks"] or 0)}
                    for r in domain_rows
                ],
                "forecast_7d": forecast_7d,
                "monthly_estimate_usd": monthly_est,
            }
            self._send_json(payload)
            return

        if path == "/api/adsterra/funnel":
            try:
                import adsterra_funnel
                data = adsterra_funnel.get_live_funnel_dashboard_data()
                self._send_json({"status": "ok", "data": data})
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/adsterra/live-audit":
            try:
                import asyncio
                from adsterra_api import AdsterraApiClient
                q = parse_qs(parsed.query)
                start_d = q.get("start_date", [None])[0]
                finish_d = q.get("finish_date", [None])[0]
                client = AdsterraApiClient()
                audit_payload = asyncio.run(client.fetch_full_live_audit(start_date=start_d, finish_date=finish_d))
                self._send_json(audit_payload)
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/adsterra/sync":
            from adsterra_api import AdsterraApiClient
            client = AdsterraApiClient()
            records = client.sync_now()
            self._send_json({"status": "ok", "synced_count": len(records), "records": records})
            return

        if path == "/api/adsterra/banners":
            try:
                self._send_json(self._banner_inventory_payload())
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/leads":
            leads = db.get_lead_conversions(limit=20)
            summary = db.today_leads_summary()
            self._send_json({"success": True, "summary": summary, "leads": leads})
            return

        if path == "/api/serp/preview":
            from serp_synthesizer import SerpSynthesizer, DOMAIN_QUERY_MATRIX, DEFAULT_US_GEOS, DEFAULT_IN_GEOS
            cfg = read_config()
            is_mobile = cfg.get("network", {}).get("mode") == "mobile_tether"
            geo_pool = DEFAULT_IN_GEOS if is_mobile else DEFAULT_US_GEOS
            synth = SerpSynthesizer()
            queries = []
            for idx, dom in enumerate(DOMAIN_QUERY_MATRIX.keys()):
                geo = geo_pool[idx % len(geo_pool)]
                q = synth.generate_query(dom, city=geo["city"], state=geo["state"])
                queries.append({
                    "domain": dom,
                    "city": geo["city"],
                    "state": geo["state"],
                    "query": q,
                })
            self._send_json({"success": True, "queries": queries})
            return

        if path == "/api/telegram/status":
            from alert_bot import TelegramAlertBot
            bot = TelegramAlertBot()
            alerts = db.get_recent_alerts(limit=15)
            summary = db.get_alert_summary_today()
            self._send_json({
                "success": True,
                "configured": bot.is_live_configured(),
                "bot_username": bot.bot_username,
                "summary": summary,
                "recent_alerts": alerts,
            })
            return

        if path == "/api/failover/status":
            mgr = get_failover_mgr()
            status = mgr.get_status()
            self._send_json({"success": True, "status": status})
            return

        if path == "/api/accounts":
            from accounts_manager import AccountsManager
            mgr = AccountsManager()
            accs = [a.to_dict() for a in mgr.get_all_accounts()]
            self._send_json({"success": True, "accounts": accs})
            return

        if path == "/api/stats/csv":
            cfg = read_config()
            cpm_rate = float(cfg.get("target", {}).get("cpm_rate", 2.50))
            csv_path = db.export_stats_csv("stats.csv", cpm_rate)
            raw = Path(csv_path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="stats.csv"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if path == "/api/gsc/status":
            try:
                from gsc_monitor import GSCMonitor
                mon = GSCMonitor()
                auth_status = mon.auth.get_status()
                cached = mon._cached_metrics or {}
                if not cached:
                    mon.audit_all_domains()
                    cached = mon._cached_metrics or {}
                dom_rows = []
                for dom in mon.domains:
                    clean_dom = str(dom.get("domain", dom) if isinstance(dom, dict) else dom).lower().replace("https://", "").replace("http://", "").rstrip("/")
                    entry = cached.get(clean_dom) or mon._mock_estimate(clean_dom, 7, auth_status["configured"], "mock_estimate")
                    dom_rows.append(entry)
                live_cnt = sum(1 for r in dom_rows if r.get("data_source") == "google_search_console_api" and not r.get("is_mock"))
                tot_imps = sum(int(r.get("impressions", 0) or 0) for r in dom_rows)
                tot_clks = sum(int(r.get("clicks", 0) or 0) for r in dom_rows)
                avg_pos = round(sum(float(r.get("avg_position", 0) or 0) for r in dom_rows) / max(1, len(dom_rows)), 1)
                weekly_state = {}
                if mon.weekly_state_path.is_file():
                    try:
                        weekly_state = json.loads(mon.weekly_state_path.read_text(encoding="utf-8"))
                    except Exception:
                        weekly_state = {}
                self._send_json({
                    "success": True,
                    "auth": auth_status,
                    "summary": {
                        "total_domains": len(dom_rows),
                        "live_domains_count": live_cnt,
                        "mock_domains_count": len(dom_rows) - live_cnt,
                        "total_impressions_7d": tot_imps,
                        "total_clicks_7d": tot_clks,
                        "fleet_ctr": round(tot_clks / tot_imps, 4) if tot_imps > 0 else 0.0,
                        "avg_position": avg_pos,
                    },
                    "domains": dom_rows,
                    "weekly_report": weekly_state,
                })
            except Exception as exc:
                self._send_json({"success": False, "error": str(exc)}, 500)
            return

        if path == "/api/push/status":
            try:
                import vapid_keys
                import push_manager
                import push_foundation
                cfg = read_config()
                pn_cfg = cfg.get("push_notifications", {}) or {}
                vapid_pub = vapid_keys.get_public_vapid_status(
                    state_path=pn_cfg.get("vapid_keys_path") or vapid_keys.DEFAULT_VAPID_STATE_PATH
                )
                os_status = push_manager.OneSignalPushClient(cfg=cfg).get_status()
                sub_stats = db.get_push_subscriber_stats()
                cov = push_foundation.audit_sites_push_coverage()
                self._send_json({
                    "success": True,
                    "vapid": vapid_pub,
                    "onesignal": os_status,
                    "subscribers": sub_stats,
                    "sites_coverage": cov,
                })
            except Exception as exc:
                self._send_json({"success": False, "error": str(exc)}, 500)
            return

        if path == "/api/config":
            cfg = read_config()
            proxies_txt = read_proxies()
            self._send_json({"config": cfg, "proxies": proxies_txt})
            return

        if path == "/api/profile":
            from admin_ui import profile_auth
            cfg = read_config()
            cookie_hdr = self.headers.get("Cookie")
            self._send_json({
                "ok": True,
                "profile": profile_auth.load_profile(),
                "connections": profile_auth.get_connections_summary(cfg=cfg),
                "sessions": profile_auth.list_active_sessions(cookie_hdr),
            })
            return

        if path == "/api/notifications":
            from admin_ui import profile_auth
            self._send_json({"ok": True, **profile_auth.get_notifications()})
            return

        if path == "/api/adb/status":
            import mobile_adb
            try:
                adb_bin = mobile_adb.get_adb_path()
                devs = mobile_adb.list_devices()
                ip_info = mobile_adb.get_public_ip()
                self._send_json({
                    "ok": True,
                    "adb_path": adb_bin,
                    "devices": devs,
                    "ip_info": ip_info,
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc), "devices": [], "ip_info": {}})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        ctype = (self.headers.get("Content-Type") or "").lower()
        is_form_post = "application/x-www-form-urlencoded" in ctype
        if is_form_post:
            form_qs = parse_qs(body.decode("utf-8", errors="ignore"))
            payload = {k: v[0] for k, v in form_qs.items() if v}
        else:
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                payload = {}

        if path == "/api/auth/login":
            from admin_ui import profile_auth
            mode = str(payload.get("mode") or "login").strip().lower()
            ident = str(payload.get("identifier") or "")
            pw = str(payload.get("password") or "")
            remember = str(payload.get("remember", True)).lower() not in ("0", "false", "no", "")
            prof = profile_auth.load_profile()

            if mode == "setup" and not prof.get("has_password"):
                ok, msg, _ = profile_auth.set_password(pw, confirm_password=pw)
                if not ok:
                    if is_form_post:
                        self._send_redirect("/crm/login?error=invalid")
                    else:
                        self._send_json({"ok": False, "error": msg}, status=400)
                    return
            elif not profile_auth.verify_credentials(ident, pw):
                if is_form_post:
                    self._send_redirect("/crm/login?error=invalid")
                else:
                    self._send_json({"ok": False, "error": "Invalid operator credentials."}, status=401)
                return

            tok = profile_auth.create_session_token(self.headers.get("User-Agent", ""), remember=remember)
            max_age_part = "; Max-Age=2592000" if remember else ""
            cookie_hdr = f"{profile_auth.COOKIE_NAME}={tok}; Path=/; HttpOnly; SameSite=Lax{max_age_part}"
            if is_form_post:
                self._send_redirect("/", extra_headers=[("Set-Cookie", cookie_hdr)])
            else:
                self._send_json({"ok": True, "redirect": "/"}, extra_headers=[("Set-Cookie", cookie_hdr)])
            return

        if path == "/api/auth/logout":
            from admin_ui import profile_auth
            profile_auth.revoke_session_and_lock(self.headers.get("Cookie"))
            clear_hdr = f"{profile_auth.COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            self._send_json({"ok": True, "redirect": "/crm/login"}, extra_headers=[("Set-Cookie", clear_hdr)])
            return

        if path == "/api/auth/unlock-dev":
            from admin_ui import profile_auth
            ok, msg = profile_auth.unlock_without_password()
            self._send_json({"ok": ok, "msg": msg, "redirect": "/" if ok else ""}, status=200 if ok else 403)
            return

        # Enforce CRM lock uniformly across all sensitive/mutating POST endpoints beyond /api/auth/*
        if not self._require_crm_unlocked():
            return

        if path == "/api/profile":
            from admin_ui import profile_auth
            ok, msg, prof = profile_auth.save_profile(payload)
            self._send_json({"ok": ok, "msg": msg if ok else "", "error": "" if ok else msg, "profile": prof}, status=200 if ok else 400)
            return

        if path == "/api/profile/password":
            from admin_ui import profile_auth
            action = str(payload.get("action") or "set_password").strip().lower()
            if action == "toggle_gate":
                ok, msg, prof = profile_auth.set_require_login(bool(payload.get("require_login")))
            elif action == "clear_password":
                ok, msg, prof = profile_auth.clear_password(str(payload.get("current_password") or ""))
            else:
                ok, msg, prof = profile_auth.set_password(
                    new_password=str(payload.get("new_password") or ""),
                    confirm_password=str(payload.get("confirm_password") or ""),
                    current_password=str(payload.get("current_password") or ""),
                )
            extra_hdrs: list[tuple[str, str]] = []
            if ok and action in ("set_password", "toggle_gate") and prof.get("has_password"):
                if not profile_auth.validate_session_cookie(self.headers.get("Cookie")):
                    tok = profile_auth.create_session_token(self.headers.get("User-Agent", ""), remember=True)
                    extra_hdrs.append((
                        "Set-Cookie",
                        f"{profile_auth.COOKIE_NAME}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000",
                    ))
            self._send_json(
                {"ok": ok, "msg": msg if ok else "", "error": "" if ok else msg, "profile": prof},
                status=200 if ok else 400,
                extra_headers=extra_hdrs,
            )
            return

        if path == "/api/notifications/read":
            from admin_ui import profile_auth
            notif_state = profile_auth.mark_notifications_read(
                notif_ids=payload.get("ids"),
                mark_all=bool(payload.get("all")),
            )
            self._send_json({"ok": True, **notif_state})
            return

        if path == "/api/notifications/test":
            from admin_ui import profile_auth
            db.record_alert_log("OPERATOR_TEST", "INFO", "Live Notification Bell check passed.", domain="system", sent_live=False)
            self._send_json({"ok": True, **profile_auth.get_notifications()})
            return

        if path == "/api/autopublish/trigger":
            try:
                domain = payload.get("domain", "rechargetak")
                import autopublish_service
                res = autopublish_service.trigger_instant_publish(domain)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/autopublish/refresh-candidates":
            try:
                domain = payload.get("domain", "tazaloan")
                import autopublish_service
                candidates = autopublish_service.refresh_20_candidates(domain)
                self._send_json({"success": True, "domain": domain, "candidates": candidates})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/autopublish/kick":
            try:
                import autopublish_service
                raw_doms = payload.get("domains") if isinstance(payload, dict) else None
                target_list = [str(d).strip() for d in raw_doms if str(d).strip()] if isinstance(raw_doms, list) else None
                res = autopublish_service.kick_stuck_domains(domains=target_list)
                self._send_json({"success": True, **res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/autopublish/trigger-batch":
            try:
                import autopublish_service
                raw_n = (payload.get("parallel_domains", 2) if isinstance(payload, dict) else 2)
                try:
                    n = int(raw_n)
                except (TypeError, ValueError):
                    self._send_json({"success": False, "error": "parallel_domains must be an integer between 1 and 4"}, 400)
                    return
                res = autopublish_service.trigger_parallel_batch(parallel_domains=max(1, min(4, n)))
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/accounts/generate":
            try:
                from accounts_manager import AccountsManager
                cfg = read_config()
                default_country = "IN" if cfg.get("network", {}).get("mode") == "mobile_tether" else "US"
                req_country = payload.get("country", default_country) if isinstance(payload, dict) else default_country
                mgr = AccountsManager()
                acc = mgr.generate_synthetic_account(country=req_country)
                self._send_json({"success": True, "account": acc.to_dict()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/adsterra/test-handshake":
            try:
                import subprocess
                target_dom = payload.get("domain", "loanraaj.com")
                script_path = str(BASE_DIR / "adsterra_funnel.py")
                cmd = [sys.executable, script_path, "--domain", target_dom, "--json"]
                proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60, encoding="utf-8")
                if proc.returncode == 0 and proc.stdout.strip():
                    res = json.loads(proc.stdout.strip())
                else:
                    res = {"success": False, "error": proc.stderr or "Verification process exited unexpectedly"}
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/adsterra/sync":
            try:
                from adsterra_api import AdsterraApiClient
                client = AdsterraApiClient()
                records = client.sync_now()
                self._send_json({"status": "ok", "synced_count": len(records), "records": records})
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/adsterra/banners/sync":
            try:
                import adsterra_links
                sync_res = adsterra_links.sync_placements_from_api()
                inv = self._banner_inventory_payload()
                inv["sync"] = sync_res
                self._send_json({"status": "ok", "sync": sync_res, "inventory": inv})
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/adsterra/banners/save":
            try:
                import adsterra_links
                body = payload if isinstance(payload, dict) else {}
                domain = (body.get("domain") or "").strip()
                slot = (body.get("slot") or "auto").strip()
                snippet = (body.get("snippet") or "").strip()
                if not domain or not snippet:
                    self._send_json({"status": "error", "error": "Both 'domain' and 'snippet' are required."}, 400)
                    return
                if not slot or slot == "auto":
                    saved = adsterra_links.register_bulk_snippets(domain, snippet)
                else:
                    saved = [adsterra_links.register_banner_snippet(domain, snippet, slot=slot)]
                self._send_json({"status": "ok", "saved": saved, "inventory": self._banner_inventory_payload()})
            except (ValueError, json.JSONDecodeError) as e:
                self._send_json({"status": "error", "error": str(e)}, 400)
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/adsterra/banners/deploy":
            try:
                import inject_display_banners
                body = payload if isinstance(payload, dict) else {}
                domain_filter = (body.get("domain") or "").strip() or None
                deploy_cf = bool(body.get("deploy", False))
                res = inject_display_banners.inject_all_sites(domain_filter=domain_filter, dry_run=False)
                if deploy_cf and not res.get("errors"):
                    deploy_ids = None
                    if domain_filter:
                        norm = inject_display_banners._normalize_domain_key(domain_filter)
                        deploy_ids = [norm]
                    elif res.get("affected_site_ids"):
                        deploy_ids = list(res["affected_site_ids"])
                    res["deploy_results"] = inject_display_banners.deploy_cloudflare_sites(deploy_ids)
                self._send_json({"status": "ok", "inject": res})
            except ValueError as e:
                self._send_json({"status": "error", "error": str(e)}, 400)
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)
            return

        if path == "/api/leads/simulate":
            try:
                from lead_engine import LeadConversionEngine
                engine = LeadConversionEngine()
                lead = engine.simulate_offline_conversion(domain="loanraaj.com")
                self._send_json({"success": True, "lead": lead})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/telegram/test":
            try:
                from alert_bot import TelegramAlertBot
                bot = TelegramAlertBot()
                res = bot.send_test_alert()
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/telegram/heartbeat":
            try:
                from alert_bot import TelegramAlertBot
                bot = TelegramAlertBot()
                res = bot.send_heartbeat()
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/telegram/daily-report":
            try:
                import daily_report
                ok = daily_report.send_daily_report_telegram()
                stats = daily_report.get_daily_fleet_stats()
                self._send_json({"success": ok, "stats": stats})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/circuit-breaker/reset":
            try:
                import state_cleanup
                cb_res = state_cleanup.reset_circuit_breaker(apply=True)
                ua_res = state_cleanup.reset_active_ua_file(apply=True)
                self._send_json({"success": True, "circuit_breaker": cb_res, "active_ua": ua_res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/gsc/sync":
            try:
                from gsc_monitor import GSCMonitor
                mon = GSCMonitor()
                raw_days = (payload or {}).get("days", 7) if isinstance(payload, dict) else 7
                try:
                    days = max(1, min(90, int(raw_days)))
                except (TypeError, ValueError):
                    self._send_json({"success": False, "error": "Invalid days parameter"}, 400)
                    return
                report = mon.audit_all_domains(days=days)
                self._send_json({"success": True, "report": report})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/gsc/weekly-report":
            try:
                from gsc_monitor import GSCMonitor
                mon = GSCMonitor()
                res = mon.generate_weekly_report(send_telegram=True)
                self._send_json({
                    "success": True,
                    "date": res["date"],
                    "txt_path": res["txt_path"],
                    "json_path": res["json_path"],
                    "telegram_sent": res["telegram_sent"],
                    "audit": res["audit"],
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/gsc/credentials":
            try:
                from gsc_auth import GSCAuthManager
                if length > 262144:
                    self._send_json({"success": False, "error": "Payload exceeds 256KB limit."}, 413)
                    return
                raw_cred = payload.get("credentials_json", payload) if isinstance(payload, dict) and "credentials_json" in payload else payload
                mgr = GSCAuthManager()
                saved = mgr.save_credentials_payload(raw_cred)
                self._send_json({"success": True, "saved": saved, "auth": mgr.get_status()})
            except ValueError as ve:
                self._send_json({"success": False, "error": str(ve)}, 400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/push/onesignal":
            try:
                import push_manager
                data_in = payload if isinstance(payload, dict) else {}
                client = push_manager.OneSignalPushClient(cfg=read_config())
                saved = client.save_credentials(
                    app_id=str(data_in.get("app_id", "")),
                    rest_api_key=str(data_in.get("rest_api_key", "")),
                    domain=str(data_in.get("domain", "")),
                    domain_app_ids=data_in.get("domain_app_ids") if isinstance(data_in.get("domain_app_ids"), dict) else None,
                )
                self._send_json({"success": True, "onesignal": saved})
            except ValueError as ve:
                self._send_json({"success": False, "error": str(ve)}, 400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/push/vapid/generate":
            try:
                import vapid_keys
                cfg = read_config()
                pn_cfg = cfg.get("push_notifications", {}) or {}
                vapid_path = pn_cfg.get("vapid_keys_path") or vapid_keys.DEFAULT_VAPID_STATE_PATH
                subject = pn_cfg.get("vapid_subject") or vapid_keys.DEFAULT_VAPID_SUBJECT
                vapid_keys.load_or_create_vapid_keys(state_path=vapid_path, subject=subject, force_rotate=True)
                self._send_json({"success": True, "vapid": vapid_keys.get_public_vapid_status(state_path=vapid_path)})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/push/inject":
            try:
                import push_foundation
                cfg = read_config()
                summary = push_foundation.inject_push_all_sites(dry_run=False, cfg=cfg)
                cov = push_foundation.audit_sites_push_coverage()
                self._send_json({"success": True, "summary": summary, "sites_coverage": cov})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/push/deliver-test":
            try:
                import push_manager
                cfg = read_config()
                mgr = push_manager.build_from_config(cfg)
                data_in = payload if isinstance(payload, dict) else {}
                res = mgr.dispatch_campaign_guarded(
                    title=str(data_in.get("title", "Test Push Alert")),
                    message=str(data_in.get("message", "Testing-phase collect-only verification")),
                    url=str(data_in.get("url", "https://loanraaj.com/")),
                    domain=str(data_in.get("domain", "loanraaj.com")),
                )
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/failover/test":
            try:
                mgr = get_failover_mgr()
                health = mgr.check_primary_health()
                self._send_json({"success": True, "health": health})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/failover/switch":
            try:
                mgr = get_failover_mgr()
                if mgr.active_mode == "PRIMARY_MOBILE":
                    mgr.trigger_failover(reason="User manual hot-swap trigger from Web Dashboard")
                else:
                    mgr.active_mode = "PRIMARY_MOBILE"
                    mgr.primary_healthy = True
                    mgr.consecutive_primary_failures = 0
                self._send_json({"success": True, "active_mode": mgr.active_mode})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return

        if path == "/api/config":
            try:
                cfg = read_config()
                if "urls" in payload and isinstance(payload["urls"], list):
                    clean_urls = [str(u).strip() for u in payload["urls"] if str(u).strip()]
                    cfg["target"]["urls"] = clean_urls
                    cfg["target"]["url"] = clean_urls[0] if clean_urls else ""
                elif "url" in payload:
                    u = str(payload["url"]).strip()
                    cfg["target"]["url"] = u
                    cfg["target"]["urls"] = [u] if u else []
                if "headless" in payload:
                    if "browser" not in cfg:
                        cfg["browser"] = {}
                    cfg["browser"]["headless"] = bool(payload["headless"])
                if "min_dwell" in payload:
                    cfg["target"]["min_dwell"] = int(payload["min_dwell"])
                if "max_dwell" in payload:
                    cfg["target"]["max_dwell"] = int(payload["max_dwell"])
                if "click_prob" in payload:
                    cfg["target"]["click_prob"] = float(payload["click_prob"])
                if "ad_clicks_max" in payload:
                    cfg["target"]["ad_clicks_max"] = int(payload["ad_clicks_max"])
                if "daily_cap" in payload:
                    cfg["scheduler"]["daily_cap"] = int(payload["daily_cap"])
                if "concurrency" in payload:
                    cfg["scheduler"]["concurrency"] = int(payload["concurrency"])
                if "network_mode" in payload:
                    if "network" not in cfg:
                        cfg["network"] = {}
                    cfg["network"]["mode"] = str(payload["network_mode"])
                if "airplane_mode_wait" in payload:
                    if "network" not in cfg:
                        cfg["network"] = {}
                    cfg["network"]["airplane_mode_wait"] = int(payload["airplane_mode_wait"])
                if "proxy_api_url" in payload:
                    if "proxy" not in cfg:
                        cfg["proxy"] = {}
                    cfg["proxy"]["api_url"] = str(payload["proxy_api_url"]).strip()

                write_config(cfg)
                self._send_json({"ok": True, "msg": "Config saved"})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/proxies/fetch":
            import pool
            api_url = payload.get("api_url", "").strip()
            if not api_url:
                self._send_json({"ok": False, "error": "API URL is required"}, status=400)
                return
            try:
                lines = pool.fetch_proxies_from_api(api_url)
                if not lines:
                    self._send_json({"ok": False, "error": "No proxies returned by API"})
                    return
                proxies_str = "\n".join(lines)
                write_proxies(proxies_str)
                cfg = read_config()
                if "proxy" not in cfg:
                    cfg["proxy"] = {}
                cfg["proxy"]["api_url"] = api_url
                write_config(cfg)
                self._send_json({
                    "ok": True,
                    "count": count_valid_proxies(),
                    "proxies": proxies_str,
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/adb/rotate":
            import mobile_adb
            try:
                wait_sec = int(payload.get("airplane_wait", 4))
                ok, old_ip, new_ip, msg_text = mobile_adb.rotate_ip(wait_seconds=wait_sec)
                if ok:
                    self._send_json({
                        "ok": True,
                        "msg": msg_text,
                        "data": {"old_ip": old_ip, "new_ip": new_ip},
                    })
                else:
                    self._send_json({"ok": False, "msg": f"Rotation failed: {msg_text}"})
            except Exception as exc:
                self._send_json({"ok": False, "msg": f"Rotation failed: {exc}"})
            return

        if path == "/api/proxies":
            proxies_str = payload.get("proxies", "")
            write_proxies(proxies_str)
            self._send_json({"ok": True, "count": count_valid_proxies()})
            return

        if path == "/api/useragents/sync":
            try:
                import ua_provider
                res = ua_provider.sync_from_useragent_in()
                self._send_json({"ok": True, **res})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/start":
            ok, msg = RUNNER.start()
            self._send_json({"ok": ok, "msg": msg})
            return

        if path == "/api/stop":
            ok, msg = RUNNER.stop()
            self._send_json({"ok": ok, "msg": msg})
            return

        if path == "/api/force-stop":
            ok, msg = RUNNER.force_stop()
            self._send_json({"ok": ok, "msg": msg})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


# ── Entrypoint ──────────────────────────────────────────────────────────────────

def _start_background_sync_worker() -> None:
    """Daemon thread that auto-syncs official Adsterra Stats API every 15 minutes."""
    import threading
    def _loop():
        while True:
            time.sleep(900)  # 15 minutes
            try:
                from adsterra_api import AdsterraApiClient
                client = AdsterraApiClient()
                if not client.is_mock_mode():
                    client.sync_now()
            except Exception:
                pass
    t = threading.Thread(target=_loop, daemon=True, name="AdsterraApiAutoSync")
    t.start()


def run_server(port: int = 5050, host: str = "127.0.0.1") -> None:
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, UIRequestHandler)
    _start_background_sync_worker()
    print("\n" + "="*60)
    print(f">> QA Control Dashboard running at: http://{host}:{port}")
    print("="*60 + "\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web dashboard…")
        RUNNER.stop()
        httpd.server_close()


if __name__ == "__main__":
    port = 5050
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)

