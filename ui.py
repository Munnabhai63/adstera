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
                if os.name == "nt":
                    try:
                        self._proc = InteractiveProcess(cmd, cwd=str(BASE_DIR), env=dict(os.environ))
                    except Exception as ex:
                        logger.warning("InteractiveProcess fallback to subprocess.Popen: %s", ex)
                        self._proc = subprocess.Popen(
                            cmd,
                            cwd=str(BASE_DIR),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"},
                        )
                else:
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
                    return True, f"Force killed: {exc}"
                except Exception as k_exc:
                    return False, f"Error stopping: {k_exc}"

    def get_logs(self) -> list[str]:
        return list(self._logs)


RUNNER = RunnerManager()

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
  <title>QA Traffic Harness — Control Center</title>
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
      <div class="brand-logo">QA</div>
      <div>
        <h1>Traffic Generator Dashboard</h1>
        <div class="subtitle">Chromium Anti-Detect Traffic &amp; Impression Simulator</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 14px;">
      <div id="statusBadge" class="status-badge stopped">
        <span class="status-dot"></span>
        <span id="statusText">STOPPED</span>
      </div>
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
      <div class="card-title">
        <span>Target Configuration</span>
        <button class="btn btn-primary" onclick="saveConfig()">Save Config</button>
      </div>

      <div class="form-group">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <label style="margin: 0; font-weight: 700; color: #f1f5f9;">🎯 Target URLs Pool (One per line for rotation)</label>
          <span id="targetUrlsCount" style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(16,185,129,0.15); color: #10b981; font-weight: 600; border: 1px solid rgba(16,185,129,0.3);">1 URL Active</span>
        </div>
        <textarea id="targetUrls" rows="3" placeholder="https://example.com/article-1&#10;https://example.com/article-2&#10;https://example.com/article-3" style="width: 100%; font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.4; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: #0f172a; color: #e2e8f0; resize: vertical;" oninput="updateTargetUrlsCount()"></textarea>
        <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">
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

      <div class="control-bar" style="margin-top: 10px;">
        <button id="btnStart" class="btn btn-success" style="flex: 1;" onclick="startRunner()">▶ Start Live Run</button>
        <button id="btnStop" class="btn btn-danger" style="flex: 1;" onclick="stopRunner()" disabled>■ Stop Run</button>
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
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span>🌐 Multi-Domain Fleet Governance & Independent CTR Circuit Breakers</span>
      <span style="font-size: 11px; background: rgba(52, 211, 153, 0.15); color: #34d399; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">Safe CTR Limit: &le; 5.0%</span>
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

  <!-- Pillar 1: Adsterra Real-Time Stats API Sync & Reconciliation Card -->
  <div class="card">
    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
      <span><span>📡</span> Pillar 1: Adsterra Real-Time Stats API Sync & Audit</span>
      <div>
        <button id="btnSyncAdsterra" class="btn btn-secondary" onclick="syncAdsterraApi()" style="padding: 4px 12px; font-size: 0.85rem;">🔄 Sync Adsterra API</button>
      </div>
    </div>
    <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 12px;">
      Direct integration with Adsterra Publisher Stats API (<code>https://api3.adsterratools.com/v1/statistic.json</code>) reconciling live API impressions &amp; clicks against local database counts.
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
            <th>US Location</th>
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
            <th>Time</th>
          </tr>
        </thead>
        <tbody id="sessionsTbody">
          <tr><td colspan="10" style="text-align: center; color: var(--muted);">No sessions recorded yet</td></tr>
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
          } else if (d.status === 'PAUSED') {
            badgeColor = '#f87171';
            badgeBg = 'rgba(248, 113, 113, 0.15)';
            badgeBorder = 'rgba(248, 113, 113, 0.3)';
          }
          return `
            <tr>
              <td><strong style="color: #f8fafc;">${d.domain}</strong></td>
              <td>${d.sessions}</td>
              <td>${d.impressions}</td>
              <td><strong style="color: ${d.clicks > 0 ? '#34d399' : 'inherit'}">${d.clicks}</strong></td>
              <td><span style="font-weight: 600; color: ${badgeColor}">${d.ctr.toFixed(2)}%</span></td>
              <td><span style="font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; color: ${badgeColor}; background: ${badgeBg}; border: 1px solid ${badgeBorder};">${d.status}</span></td>
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
              <td>${p.city ? p.city + ', ' + p.state : 'US Domestic'}</td>
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
    const lines = el.value.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    const countEl = document.getElementById('targetUrlsCount');
    if (countEl) {
      countEl.innerText = lines.length === 1 ? '1 URL Active' : (lines.length > 1 ? lines.length + ' URLs in Pool' : '0 URLs');
      countEl.style.color = lines.length > 0 ? '#10b981' : '#f59e0b';
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      const data = await res.json();
      const cfg = data.config;
      
      let urls = [];
      if (cfg.target && cfg.target.urls && Array.isArray(cfg.target.urls) && cfg.target.urls.length > 0) {
        urls = cfg.target.urls;
      } else if (cfg.target && cfg.target.url) {
        urls = [cfg.target.url];
      }
      const targetUrlsEl = document.getElementById('targetUrls');
      if (targetUrlsEl) targetUrlsEl.value = urls.join('\n');
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
    const urlsList = rawUrls.split('\n').map(l => l.trim()).filter(l => l.length > 0);

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
    if (currentNetworkMode === 'proxy') {
      const pText = document.getElementById('proxiesText').value.trim();
      if (!pText) {
        alert("⚠️ You are in '🌐 Proxies' mode, but no proxies are configured!\n\nEither paste your proxies into 'One proxy per line', or switch to the '📱 Mobile ADB IP' tab to run directly via your connected phone's mobile data.");
        return;
      }
    } else if (currentNetworkMode === 'mobile_tether') {
      try {
        const adbRes = await fetch('/api/adb/status');
        const adbData = await adbRes.json();
        if (!adbData.ok || !adbData.devices || adbData.devices.length === 0) {
          alert("⚠️ No Android phone detected via USB debugging!\n\nPlease check:\n1. Mobile phone is plugged in via USB\n2. USB Tethering is turned ON in phone Settings\n3. USB Debugging is turned ON in Developer Options\n4. Check phone screen to allow USB debugging prompt");
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
    fetchStatus();
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

  // Initial load & Polling
  loadConfig();
  fetchStatus();
  setInterval(fetchStatus, 3000);
</script>

</body>
</html>
"""

# ── HTTP Request Handler ────────────────────────────────────────────────────────

class UIRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine access logs
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("", "/"):
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
            from autopilot_watchdog import AutopilotWatchdog
            acc_mgr = AccountsManager()
            accs = acc_mgr.get_all_accounts()
            warmed_c = sum(1 for a in accs if a.warmed or a.cookies_count > 0)

            status_data = {
                "is_running": RUNNER.is_running(),
                "pid": RUNNER.get_pid(),
                "today": db.today(),
                "ctr": db.ctr(100),
                "metrics": metrics,
                "domains": db.all_domains_summary(
                    cpm_rate,
                    configured_domains=cfg.get("target", {}).get("domains", []),
                ),
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
                "adsterra_sync": db.get_latest_adsterra_sync(limit=10),
                "logs": RUNNER.get_logs(),
            }
            self._send_json(status_data)
            return

        if path == "/api/adsterra/sync":
            from adsterra_api import AdsterraApiClient
            client = AdsterraApiClient()
            records = client.sync_now()
            self._send_json({"status": "ok", "synced_count": len(records), "records": records})
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

        if path == "/api/config":
            cfg = read_config()
            proxies_txt = read_proxies()
            self._send_json({"config": cfg, "proxies": proxies_txt})
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
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if path == "/api/accounts/generate":
            try:
                from accounts_manager import AccountsManager
                mgr = AccountsManager()
                acc = mgr.generate_synthetic_account()
                self._send_json({"success": True, "account": acc.to_dict()})
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

        if path == "/api/config":
            try:
                cfg = read_config()
                if "urls" in payload and isinstance(payload["urls"], list):
                    clean_urls = [str(u).strip() for u in payload["urls"] if str(u).strip()]
                    cfg["target"]["urls"] = clean_urls
                    if clean_urls:
                        cfg["target"]["url"] = clean_urls[0]
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

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


# ── Entrypoint ──────────────────────────────────────────────────────────────────

def run_server(port: int = 5050, host: str = "127.0.0.1") -> None:
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, UIRequestHandler)
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

