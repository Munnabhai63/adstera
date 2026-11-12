"""Vuexy v3.1.0 Live Workflow Visualizer View — n8n & Swarm Multi-Agent Architecture Graph.

Renders full A-to-Z 4-Layer system architecture with live wiring:
- LAYER 1: Content Generation & Publishing (Trends -> FreeLLM -> A5 Gate -> Cloudflare Pages -> GSC)
- LAYER 2: Hardware Farm & Scheduler (A6 Scheduler -> CGNAT Tracker -> Airplane IP Rotator -> Phone Farm)
- LAYER 3: AI Vision & Safety (Screen Capture -> A4 Visual -> A2 Anomaly -> Safe Mode Diamond -> CTR Guard Diamond -> LinTS Bandit -> Biometric Touch)
- LAYER 4: Central HQ & Telemetry (ui.py Controller -> phase3.db WAL -> A3 Forecaster -> Adsterra Sync -> Telegram Alert Bot)
"""
from __future__ import annotations
from typing import Optional

_WORKFLOW_STYLES = """
<style>
/* Clean Monochrome n8n / Swarm Canvas */
#wfCanvasViewport {
  background-color: #0b0f19;
  background-image: radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px);
  background-size: 20px 20px;
  cursor: grab;
  user-select: none;
  min-height: 820px;
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
#wfCanvasViewport.grabbing {
  cursor: grabbing;
}
#wfCanvasTransform {
  transform-origin: 0 0;
  transition: transform 0.05s ease-out;
  position: absolute;
  top: 0;
  left: 0;
  width: 2200px;
  height: 1200px;
}
.wf-layer-subgraph {
  background: rgba(15, 23, 42, 0.65);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  padding: 16px;
  backdrop-filter: blur(8px);
}
.wf-layer-header {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
  font-weight: 700;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  padding-bottom: 6px;
}
.wf-box-node {
  background: #111827;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  padding: 8px 12px;
  min-width: 175px;
  max-width: 205px;
  position: relative;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.15s ease;
  z-index: 5;
}
.wf-box-node:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.4);
}
.wf-box-node.processing {
  border-color: #38bdf8 !important;
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.45) !important;
  animation: wfNodeGlow 1.2s infinite alternate;
}
.wf-box-node.success {
  border-color: #10b981 !important;
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.3) !important;
}
.wf-box-node.failed {
  border-color: #ef4444 !important;
  box-shadow: 0 0 14px rgba(239, 68, 68, 0.4) !important;
}
.wf-diamond-node {
  background: #1e293b;
  border: 1.5px solid #94a3b8;
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 170px;
  text-align: center;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5);
  transition: all 0.25s ease;
  z-index: 5;
}
.wf-diamond-node.processing {
  border-color: #f59e0b !important;
  box-shadow: 0 0 16px rgba(245, 158, 11, 0.45) !important;
}
.wf-diamond-node.success {
  border-color: #10b981 !important;
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.3) !important;
}
.wf-box-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: #f8fafc;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.wf-box-subtitle {
  font-size: 0.68rem;
  color: #94a3b8;
  margin-bottom: 4px;
}
.wf-box-metric {
  font-size: 0.65rem;
  font-family: monospace;
  padding: 3px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.35);
  color: #cbd5e1;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wf-svg-wire {
  fill: none;
  stroke: rgba(148, 163, 184, 0.35);
  stroke-width: 1.8;
  stroke-dasharray: 4 4;
  transition: stroke 0.25s ease, stroke-width 0.25s ease;
}
.wf-svg-wire.active {
  stroke: #38bdf8;
  stroke-width: 2.8;
  stroke-dasharray: 6 4;
  animation: wfWireFlow 0.65s linear infinite;
  filter: drop-shadow(0 0 3px rgba(56, 189, 248, 0.8));
}
.wf-svg-wire.success {
  stroke: #10b981;
  stroke-width: 2.2;
  stroke-dasharray: none;
}
.wf-svg-wire.failed {
  stroke: #ef4444;
  stroke-width: 2.2;
}
@keyframes wfWireFlow {
  to { stroke-dashoffset: -20; }
}
@keyframes wfNodeGlow {
  0% { transform: scale(1); }
  100% { transform: scale(1.02); }
}
</style>
"""


def render_live_workflow_view(*, active: bool = False) -> str:
    """Render the complete 4-Layer A-to-Z visual wiring workspace (#view-workflow-live)."""
    view_cls = "crm-view active" if active else "crm-view"
    return f"""
<section id="view-workflow-live" class="{view_cls}">
  <!-- Top Navigation & Execution Toolbar -->
  <div class="card mb-3 border-0 shadow-sm">
    <div class="card-body py-2 px-3">
      <div class="d-flex flex-column flex-xl-row align-items-xl-center justify-content-between gap-2">
        <div class="d-flex align-items-center gap-2">
          <div class="rounded p-2 bg-label-primary">
            <i class="icon-base ti tabler-git-branch icon-20px"></i>
          </div>
          <div>
            <div class="d-flex align-items-center gap-2">
              <h5 class="mb-0 fw-bold">Autonomous System Architecture Wiring</h5>
              <span class="badge bg-label-success d-inline-flex align-items-center gap-1" id="wfStreamStatusBadge">
                <span class="spinner-grow spinner-grow-sm text-success" role="status" style="width: 7px; height: 7px;" id="wfStreamPulse"></span>
                <span id="wfStreamStatusText">SSE STREAMING</span>
              </span>
              <span class="badge bg-label-info tabular-nums" id="wfActiveStageReadout">IDLE</span>
            </div>
            <small class="text-body-secondary">Full Loop: Trends &rarr; FreeLLM &rarr; A5 Gate &rarr; Pages &rarr; Scheduler &rarr; CGNAT &rarr; Phone Farm &rarr; AI Vision &rarr; Touch &rarr; DB</small>
          </div>
        </div>

        <!-- Controls Group -->
        <div class="d-flex flex-wrap align-items-center gap-2">
          <div class="btn-group btn-group-sm" role="group">
            <input type="radio" class="btn-check" name="wfExecMode" id="wfModePaper" value="paper" checked>
            <label class="btn btn-outline-secondary" for="wfModePaper" title="Simulated decisions and safe touches">Paper Mode</label>
            <input type="radio" class="btn-check" name="wfExecMode" id="wfModeLive" value="live">
            <label class="btn btn-outline-warning" for="wfModeLive" title="Live hardware taps on physical phones">Live Touch</label>
          </div>

          <div class="input-group input-group-sm" style="width: 105px;">
            <span class="input-group-text">Steps</span>
            <select class="form-select form-select-sm" id="wfStepsSelect">
              <option value="1" selected>1</option>
              <option value="3">3</option>
              <option value="5">5</option>
              <option value="10">10</option>
            </select>
          </div>

          <button type="button" class="btn btn-sm btn-primary d-inline-flex align-items-center gap-1 px-3 shadow-sm" id="wfTriggerRunBtn">
            <i class="icon-base ti tabler-player-play icon-16px" id="wfTriggerIcon"></i>
            <span id="wfTriggerBtnText">Start Pipeline Run</span>
          </button>

          <!-- Canvas Zoom / Pan Controls -->
          <div class="btn-group btn-group-sm">
            <button type="button" class="btn btn-outline-secondary" id="wfZoomInBtn" title="Zoom In"><i class="icon-base ti tabler-zoom-in icon-16px"></i></button>
            <button type="button" class="btn btn-outline-secondary" id="wfZoomOutBtn" title="Zoom Out"><i class="icon-base ti tabler-zoom-out icon-16px"></i></button>
            <button type="button" class="btn btn-outline-secondary" id="wfZoomResetBtn" title="Reset View (100%)">1:1</button>
          </div>

          <button type="button" class="btn btn-sm btn-outline-secondary" id="wfResetBtn" title="Reset All Nodes"><i class="icon-base ti tabler-refresh icon-16px"></i></button>
        </div>
      </div>
    </div>
  </div>

  <!-- Interactive Pan & Zoom Architectural Canvas -->
  <div id="wfCanvasViewport">
    <!-- Inner Scaled / Translated World -->
    <div id="wfCanvasTransform">
      <!-- SVG Dynamic Wiring Overlay -->
      <svg class="w-100 h-100 position-absolute top-0 start-0 pointer-events-none" id="wfMainSvg" style="z-index: 2;">
        <defs>
          <marker id="wfArrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#64748b" />
          </marker>
          <marker id="wfArrowActive" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#38bdf8" />
          </marker>
          <marker id="wfArrowSuccess" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#10b981" />
          </marker>
        </defs>
        <g id="wfWirePathGroup"></g>
      </svg>

      <!-- 4 Architectural Functional Clusters -->
      <div class="position-absolute d-flex flex-column gap-4" style="top: 24px; left: 24px; width: 440px;">
        <!-- CLUSTER 1: CONTENT & SEO PIPELINE -->
        <div class="wf-layer-subgraph" id="clusterContent">
          <div class="wf-layer-header">
            <span>Layer 1: Content &amp; Publishing Engine</span>
            <span class="badge bg-label-secondary">10 Sites Live</span>
          </div>
          <div class="d-flex flex-column gap-3">
            <div class="wf-box-node" id="node-TRENDS_HARVESTER" data-node="TRENDS_HARVESTER">
              <div class="wf-box-title"><i class="icon-base ti tabler-trending-up text-primary"></i> 01. Trends Harvester</div>
              <div class="wf-box-subtitle">Google Trends RSS (IN/US)</div>
              <div class="wf-box-metric" id="metric-TRENDS_HARVESTER">Keywords: 14 Today</div>
            </div>

            <div class="wf-box-node" id="node-FREELMM_GATEWAY" data-node="FREELMM_GATEWAY">
              <div class="wf-box-title"><i class="icon-base ti tabler-cloud-computing text-info"></i> 02. FreeLLMAPI Gateway</div>
              <div class="wf-box-subtitle">Multi-provider Hybrid LLM</div>
              <div class="wf-box-metric" id="metric-FREELMM_GATEWAY">Cost: $0.00 &bull; 1,420 words</div>
            </div>

            <div class="wf-box-node" id="node-A5_SEO_GATE" data-node="A5_SEO_GATE">
              <div class="wf-box-title"><i class="icon-base ti tabler-shield-check text-success"></i> 03. A5 Anti-AI Gate</div>
              <div class="wf-box-subtitle">Perplexity &amp; Burstiness Check</div>
              <div class="wf-box-metric" id="metric-A5_SEO_GATE">Score: 84.2 &bull; No Gibberish</div>
            </div>

            <div class="wf-box-node" id="node-CF_PAGES" data-node="CF_PAGES">
              <div class="wf-box-title"><i class="icon-base ti tabler-world-www text-warning"></i> 04. Cloudflare Pages</div>
              <div class="wf-box-subtitle">Hugo Static Build &amp; Deploy</div>
              <div class="wf-box-metric" id="metric-CF_PAGES">10 Domains &bull; Banners 50/50</div>
            </div>

            <div class="d-flex gap-2">
              <div class="wf-box-node flex-grow-1" id="node-GSC_INDEX" data-node="GSC_INDEX">
                <div class="wf-box-title"><i class="icon-base ti tabler-brand-google text-danger"></i> 05. GSC IndexNow</div>
                <div class="wf-box-subtitle">Instant Search Ping</div>
                <div class="wf-box-metric" id="metric-GSC_INDEX">10 URLs Pushed</div>
              </div>
              <div class="wf-box-node flex-grow-1" id="node-PUSH_NOTIF" data-node="PUSH_NOTIF">
                <div class="wf-box-title"><i class="icon-base ti tabler-bell-ringing text-info"></i> 06. Web Push</div>
                <div class="wf-box-subtitle">OneSignal / VAPID</div>
                <div class="wf-box-metric" id="metric-PUSH_NOTIF">Broadcast Active</div>
              </div>
            </div>
          </div>
        </div>

        <!-- CLUSTER 2: HARDWARE FARM & SCHEDULER -->
        <div class="wf-layer-subgraph" id="clusterHardware">
          <div class="wf-layer-header">
            <span>Layer 2: Mobile Farm &amp; Hardware</span>
            <span class="badge bg-label-secondary">USB 3.0 Connected</span>
          </div>
          <div class="d-flex flex-column gap-3">
            <div class="wf-box-node" id="node-A6_SCHEDULER" data-node="A6_SCHEDULER">
              <div class="wf-box-title"><i class="icon-base ti tabler-calendar-time text-primary"></i> 07. A6 Diurnal Scheduler</div>
              <div class="wf-box-subtitle">NHPP Poisson Peak Hour Curve</div>
              <div class="wf-box-metric" id="metric-A6_SCHEDULER">Intensity: 0.94 &bull; 150/hr</div>
            </div>

            <div class="wf-box-node" id="node-CGNAT_TRACKER" data-node="CGNAT_TRACKER">
              <div class="wf-box-title"><i class="icon-base ti tabler-network text-info"></i> 08. CGNAT IP Tracker</div>
              <div class="wf-box-subtitle">/24 &amp; /20 Subnet Collision Lock</div>
              <div class="wf-box-metric" id="metric-CGNAT_TRACKER">Subnet: 100.64.55.0/24</div>
            </div>

            <div class="d-flex gap-2">
              <div class="wf-box-node flex-grow-1" id="node-AIRPLANE_ROTATOR" data-node="AIRPLANE_ROTATOR">
                <div class="wf-box-title"><i class="icon-base ti tabler-plane-tilt text-warning"></i> 09. Airplane Rotate</div>
                <div class="wf-box-subtitle">Carrier IP Renewal</div>
                <div class="wf-box-metric" id="metric-AIRPLANE_ROTATOR">IP: 100.64.55.10</div>
              </div>
              <div class="wf-box-node flex-grow-1" id="node-PHONE_FARM" data-node="PHONE_FARM">
                <div class="wf-box-title"><i class="icon-base ti tabler-device-mobile text-success"></i> 10. Phone Cluster</div>
                <div class="wf-box-subtitle">Physical Android Device</div>
                <div class="wf-box-metric" id="metric-PHONE_FARM">Battery: 88% &bull; 32°C</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- CLUSTER 3: AI VISION, SAFETY & DECISION ENGINE -->
      <div class="position-absolute wf-layer-subgraph" id="clusterAI" style="top: 24px; left: 520px; width: 490px;">
        <div class="wf-layer-header">
          <span>Layer 3: AI Decision &amp; Safety Engine</span>
          <span class="badge bg-label-primary">LinTS + SafeMode</span>
        </div>
        <div class="d-flex flex-column gap-3">
          <div class="wf-box-node" id="node-CAPTURE" data-node="CAPTURE">
            <div class="wf-box-title"><i class="icon-base ti tabler-camera text-primary"></i> 11. Android Screen Capture</div>
            <div class="wf-box-subtitle">ADB Screencap &amp; UI Dump (1080x2400)</div>
            <div class="wf-box-metric" id="metric-CAPTURE">Frame: 418 KB &bull; PNG</div>
          </div>

          <div class="wf-box-node" id="node-A4_VISION" data-node="A4_VISION">
            <div class="wf-box-title"><i class="icon-base ti tabler-scan-eye text-info"></i> 12. A4 Visual Ad Detector</div>
            <div class="wf-box-subtitle">XML Parse + RuleFallback BBox</div>
            <div class="wf-box-metric" id="metric-A4_VISION">bbox: [80, 1218, 920, 250] conf: 0.94</div>
          </div>

          <div class="wf-box-node" id="node-A2_ANOMALY" data-node="A2_ANOMALY">
            <div class="wf-box-title"><i class="icon-base ti tabler-filter text-warning"></i> 13. A2 Anomaly Filter</div>
            <div class="wf-box-subtitle">EWMA + Isolation Forest Telemetry</div>
            <div class="wf-box-metric" id="metric-A2_ANOMALY">Severity: NORMAL &bull; Clean</div>
          </div>

          <!-- Decision Diamond 1: Safe Mode Active? -->
          <div class="d-flex align-items-center justify-content-between gap-2">
            <div class="wf-diamond-node flex-grow-1" id="node-SAFE_MODE_GATE" data-node="SAFE_MODE_GATE">
              <div class="fw-bold small text-light"><i class="icon-base ti tabler-diamond text-warning"></i> 14. Safe Mode Active?</div>
              <div class="text-body-secondary" style="font-size: 0.65rem;">Fail-Closed Sentinel Check</div>
              <div class="wf-box-metric mt-1" id="metric-SAFE_MODE_GATE">Verdict: NO (Clean)</div>
            </div>
            <div class="wf-box-node" id="node-SKIP_ACTION" data-node="SKIP_ACTION" style="max-width: 150px; opacity: 0.7;">
              <div class="wf-box-title text-danger" style="font-size: 0.75rem;"><i class="icon-base ti tabler-player-skip-forward"></i> Skip Action</div>
              <div class="wf-box-subtitle">Clicks Suppressed</div>
            </div>
          </div>

          <!-- Decision Diamond 2: CTR Guard Hard Cap? -->
          <div class="d-flex align-items-center justify-content-between gap-2">
            <div class="wf-diamond-node flex-grow-1" id="node-CTR_GUARD_GATE" data-node="CTR_GUARD_GATE">
              <div class="fw-bold small text-light"><i class="icon-base ti tabler-diamond text-info"></i> 15. CTR Guard &lt;= 4.5%?</div>
              <div class="text-body-secondary" style="font-size: 0.65rem;">Atomic Cap Lock</div>
              <div class="wf-box-metric mt-1" id="metric-CTR_GUARD_GATE">Current: 2.40% &lt; 4.50%</div>
            </div>
            <div class="wf-box-node" id="node-DEFER_ACTION" data-node="DEFER_ACTION" style="max-width: 150px; opacity: 0.7;">
              <div class="wf-box-title text-warning" style="font-size: 0.75rem;"><i class="icon-base ti tabler-clock-pause"></i> Defer Action</div>
              <div class="wf-box-subtitle">Cooldown Throttled</div>
            </div>
          </div>

          <div class="wf-box-node" id="node-A1_DECISION" data-node="A1_DECISION">
            <div class="wf-box-title"><i class="icon-base ti tabler-brain text-danger"></i> 16. A1 LinTS Contextual Bandit</div>
            <div class="wf-box-subtitle">Upper Confidence Bound Sampling</div>
            <div class="wf-box-metric" id="metric-A1_DECISION">Action: CLICK &bull; Reward: 0.00145</div>
          </div>

          <div class="wf-box-node" id="node-ADB_TAP" data-node="ADB_TAP">
            <div class="wf-box-title"><i class="icon-base ti tabler-fingerprint text-success"></i> 17. Biometric Touch Bridge</div>
            <div class="wf-box-subtitle">Bézier Capacitive Tap inside BBox</div>
            <div class="wf-box-metric" id="metric-ADB_TAP">Tap at (540, 1343) &bull; Jitter 12ms</div>
          </div>
        </div>
      </div>

      <!-- CLUSTER 4: CENTRAL HQ, PERSISTENCE & TELEMETRY -->
      <div class="position-absolute wf-layer-subgraph" id="clusterHQ" style="top: 24px; left: 1060px; width: 440px;">
        <div class="wf-layer-header">
          <span>Central HQ, DB &amp; Telemetry</span>
          <span class="badge bg-label-success">SQLite WAL Atomic</span>
        </div>
        <div class="d-flex flex-column gap-3">
          <div class="wf-box-node" id="node-CENTRAL_HQ" data-node="CENTRAL_HQ">
            <div class="wf-box-title"><i class="icon-base ti tabler-building-broadcast-tower text-primary"></i> Central Controller</div>
            <div class="wf-box-subtitle">ui.py :5050 &bull; rechargekar.com</div>
            <div class="wf-box-metric" id="metric-CENTRAL_HQ">Cloudflare Tunnel: Active</div>
          </div>

          <div class="wf-box-node" id="node-DB_SAVE" data-node="DB_SAVE">
            <div class="wf-box-title"><i class="icon-base ti tabler-database text-warning"></i> phase3.db Persistence</div>
            <div class="wf-box-subtitle">SQLite WAL + BEGIN IMMEDIATE</div>
            <div class="wf-box-metric" id="metric-DB_SAVE">Session Committed &bull; Dwell: 32s</div>
          </div>

          <div class="wf-box-node" id="node-A3_FORECAST" data-node="A3_FORECAST">
            <div class="wf-box-title"><i class="icon-base ti tabler-chart-line text-info"></i> 18. A3 Quantile Forecaster</div>
            <div class="wf-box-subtitle">IRLS P10 / P50 / P90 Projection</div>
            <div class="wf-box-metric" id="metric-A3_FORECAST">P50: $14.20 &bull; Trend: Bullish</div>
          </div>

          <div class="wf-box-node" id="node-ADSTERRA_SYNC" data-node="ADSTERRA_SYNC">
            <div class="wf-box-title"><i class="icon-base ti tabler-refresh text-success"></i> 19. Adsterra Official API</div>
            <div class="wf-box-subtitle">15-min Revenue &amp; CPM Pull</div>
            <div class="wf-box-metric" id="metric-ADSTERRA_SYNC">Delta: 0.0% &bull; Matched 100%</div>
          </div>

          <div class="wf-box-node" id="node-TELEGRAM_BOT" data-node="TELEGRAM_BOT">
            <div class="wf-box-title"><i class="icon-base ti tabler-brand-telegram text-primary"></i> 20. Telegram Alert Bot</div>
            <div class="wf-box-subtitle">Daily Report &amp; Safety Sentinel</div>
            <div class="wf-box-metric" id="metric-TELEGRAM_BOT">Status: Green &bull; Zero Alerts</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Real-time Event Stream Log & Terminal Drawer -->
  <div class="card border-0 shadow-sm mt-3">
    <div class="card-header border-bottom py-2 d-flex align-items-center justify-content-between bg-body-tertiary">
      <div class="d-flex align-items-center gap-2">
        <i class="icon-base ti tabler-terminal text-primary icon-18px"></i>
        <span class="fw-semibold small">Live Pipeline Event Stream (SSE)</span>
        <span class="badge bg-label-primary tabular-nums" id="wfLogCountBadge">0 Events</span>
      </div>
      <div class="d-flex align-items-center gap-2">
        <div class="form-check form-switch form-check-sm mb-0">
          <input class="form-check-input" type="checkbox" id="wfAutoScrollSwitch" checked>
          <label class="form-check-label small" for="wfAutoScrollSwitch">Auto-scroll</label>
        </div>
        <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-2" id="wfClearLogBtn">Clear</button>
      </div>
    </div>
    <div class="card-body p-0">
      <div class="p-2 bg-dark text-light font-monospace small overflow-auto" id="wfTerminalBox" style="height: 180px; line-height: 1.5; font-size: 0.78rem;">
        <div class="text-secondary">[SYSTEM] Connected to Live Workflow event stream. Awaiting pipeline triggers...</div>
      </div>
    </div>
  </div>
</section>
{_WORKFLOW_STYLES}
"""


def render_workflow_dashboard_page(initial_title: Optional[str] = None) -> str:
    """Render standalone HTML document for the Live Workflow Visualizer (served at /workflow on port 5054)."""
    title = initial_title or "AdsterraFleet | Live Workflow Visualizer"
    body = render_live_workflow_view(active=True)

    return f"""<!doctype html>
<html
  lang="en"
  class="layout-navbar-fixed layout-compact"
  dir="ltr"
  data-skin="default"
  data-bs-theme="dark"
  data-assets-path="/crm-assets/"
  data-template="adstera-crm">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, minimum-scale=1.0, maximum-scale=1.0" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="color-scheme" content="dark light" />
    <title>{title}</title>
    <link rel="icon" type="image/x-icon" href="/crm-assets/img/favicon/favicon.ico" />
    <link rel="stylesheet" href="/crm-assets/vendor/fonts/iconify-icons.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/core.css" />
    <link rel="stylesheet" href="/crm-assets/css/demo.css" />
    <link rel="stylesheet" href="/crm-assets/css/cms-shell.css" />
  </head>
  <body>
    <div class="layout-wrapper layout-content-navbar layout-without-menu">
      <div class="layout-container">
        <div class="layout-page">
          <nav class="layout-navbar container-xxl navbar-detached navbar navbar-expand-xl align-items-center bg-navbar-theme" id="layout-navbar">
            <div class="navbar-nav-right d-flex align-items-center justify-content-between w-100">
              <div class="d-flex align-items-center gap-2">
                <span class="fw-bold text-primary">AdsterraFleet</span>
                <span class="text-body-secondary small">/ Pipeline Live Execution Visualizer</span>
              </div>
              <div class="d-flex align-items-center gap-2">
                <a href="/" class="btn btn-sm btn-outline-secondary">
                  <i class="icon-base ti tabler-arrow-left icon-14px me-1"></i>Farm Dashboard
                </a>
              </div>
            </div>
          </nav>

          <div class="content-wrapper">
            <div class="container-xxl flex-grow-1 container-p-y">
              {body}
            </div>

            <footer class="content-footer footer bg-footer-theme">
              <div class="container-xxl">
                <div class="footer-container d-flex align-items-center justify-content-between py-4 flex-md-row flex-column">
                  <div class="text-body">
                    AdsterraFleet Real-time AI Pipeline &bull; n8n/Make.com Style Visualizer
                  </div>
                  <div class="d-flex gap-3">
                    <a href="/api/phase4/live-workflow-stream" class="footer-link">SSE Stream Endpoint</a>
                    <a href="/api/phase4/workflow/history" class="footer-link">History JSON</a>
                  </div>
                </div>
              </div>
            </footer>
            <div class="content-backdrop fade"></div>
          </div>
        </div>
      </div>
    </div>

    <script src="/crm-assets/vendor/libs/popper/popper.js"></script>
    <script src="/crm-assets/vendor/js/bootstrap.js"></script>
    <script src="/crm-assets/js/crm-workflow.js"></script>
  </body>
</html>
"""
