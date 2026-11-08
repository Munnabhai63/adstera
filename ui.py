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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("web_ui")

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = BASE_DIR / "config.yaml"
PROXIES_PATH = BASE_DIR / "proxies.txt"

# ── Process Manager ─────────────────────────────────────────────────────────────

class RunnerManager:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
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
                mode_desc = "⚡ Headless (Background)" if is_headless else "👁️ Head-On (Visible Window)"
                self._logs.append(f"[{time.strftime('%X')}] Runner launched with PID {self._proc.pid} [{mode_desc}]")

                # Background thread to capture stdout
                def stream_reader(p: subprocess.Popen, log_queue: collections.deque):
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
      <div class="stat-title">Current CTR (Last 100)</div>
      <div class="stat-val" id="statCTR">0.0%</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Active Proxies</div>
      <div class="stat-val" id="statProxies">0</div>
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
        <label>Target URL (Your Article / Webpage)</label>
        <input type="text" id="targetUrl" placeholder="https://example.com/article">
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
          <button id="btnTabProxy" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="switchNetworkMode('proxy')">🌐 Proxies</button>
          <button id="btnTabMobile" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="switchNetworkMode('mobile_tether')">📱 Mobile ADB IP</button>
        </div>
      </div>

      <!-- Mode 1: Proxy Pool -->
      <div id="sectionProxy" style="display: flex; flex-direction: column; gap: 14px;">
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
          <tr><td colspan="9" style="text-align: center; color: var(--muted);">No sessions recorded yet</td></tr>
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
      document.getElementById('statProxies').innerText = data.proxies_count;

      // Update sessions table
      const tbody = document.getElementById('sessionsTbody');
      if (data.recent_sessions && data.recent_sessions.length > 0) {
        tbody.innerHTML = data.recent_sessions.map(s => `
          <tr>
            <td>#${s.id}</td>
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

  function switchNetworkMode(mode) {
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
      checkAdbStatus();
    } else {
      btnProxy.className = 'btn btn-primary';
      btnMobile.className = 'btn btn-secondary';
      secProxy.style.display = 'flex';
      secMobile.style.display = 'none';
    }
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

  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      const data = await res.json();
      const cfg = data.config;
      
      document.getElementById('targetUrl').value = cfg.target.url || '';
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
    } catch (e) {
      console.error("loadConfig failed:", e);
    }
  }

  async function saveConfig(showNotification = true) {
    const payload = {
      url: document.getElementById('targetUrl').value.trim(),
      headless: document.getElementById('modeHeadless').checked,
      network_mode: currentNetworkMode,
      airplane_mode_wait: parseInt(document.getElementById('airplaneWait').value) || 4,
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
            self._send_html(HTML_PAGE)
            return

        if path == "/api/status":
            db.init()
            status_data = {
                "is_running": RUNNER.is_running(),
                "pid": RUNNER.get_pid(),
                "today": db.today(),
                "ctr": db.ctr(100),
                "proxies_count": count_valid_proxies(),
                "recent_sessions": db.last_sessions(20),
                "logs": RUNNER.get_logs(),
            }
            self._send_json(status_data)
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

        if path == "/api/config":
            try:
                cfg = read_config()
                if "url" in payload:
                    cfg["target"]["url"] = payload["url"]
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

                write_config(cfg)
                self._send_json({"ok": True, "msg": "Config saved"})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/adb/rotate":
            import mobile_adb
            try:
                wait_sec = int(payload.get("airplane_wait", 4))
                res = mobile_adb.rotate_ip(wait_seconds=wait_sec)
                old_ip = res.get("old_ip", {}).get("ip", "unknown")
                new_ip = res.get("new_ip", {}).get("ip", "unknown")
                msg = f"Flight mode rotated successfully! IP changed: {old_ip} -> {new_ip}"
                self._send_json({"ok": True, "msg": msg, "data": res})
            except Exception as exc:
                self._send_json({"ok": False, "msg": f"Rotation failed: {exc}"})
            return

        if path == "/api/proxies":
            proxies_str = payload.get("proxies", "")
            write_proxies(proxies_str)
            self._send_json({"ok": True, "count": count_valid_proxies()})
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
    print(f"🚀 QA Control Dashboard running at: http://{host}:{port}")
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

