"""Vuexy v3.1.0 Live Workflow Visualizer View — n8n / Make.com Style Pipeline Stream.

Visualizes real-time execution flow:
CAPTURE -> A4_VISION -> A2_ANOMALY -> A1_DECISION -> ADB_TAP -> DB_SAVE
"""
from __future__ import annotations


_WORKFLOW_STYLES = """
<style>
.wf-node {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  position: relative;
  z-index: 3;
}
.wf-node:hover {
  transform: translateY(-2px);
}
.wf-node.processing {
  border-color: #3b82f6 !important;
  box-shadow: 0 0 20px rgba(59, 130, 246, 0.4) !important;
  animation: wfPulse 1.5s infinite alternate;
}
.wf-node.success {
  border-color: #10b981 !important;
  box-shadow: 0 0 15px rgba(16, 185, 129, 0.25) !important;
}
.wf-node.failed {
  border-color: #ef4444 !important;
  box-shadow: 0 0 18px rgba(239, 68, 68, 0.35) !important;
}
.wf-node-data {
  min-height: 52px;
  max-height: 80px;
  overflow-y: auto;
  font-size: 0.78rem;
  border: 1px dashed rgba(128, 128, 128, 0.25);
}
@keyframes wfPulse {
  0% { transform: scale(1); }
  100% { transform: scale(1.015); }
}
.wf-svg-path {
  fill: none;
  stroke: var(--bs-border-color);
  stroke-width: 2.5;
  stroke-dasharray: 6 6;
  transition: stroke 0.3s ease, stroke-width 0.3s ease;
}
.wf-svg-path.active {
  stroke: url(#gradFlow);
  stroke-width: 3.5;
  stroke-dasharray: 8 6;
  animation: wfFlow 0.8s linear infinite;
  filter: drop-shadow(0 0 4px rgba(6, 182, 212, 0.6));
}
.wf-svg-path.success {
  stroke: #10b981;
  stroke-width: 3;
  stroke-dasharray: none;
}
.wf-svg-path.failed {
  stroke: #ef4444;
  stroke-width: 3;
}
@keyframes wfFlow {
  to {
    stroke-dashoffset: -28;
  }
}
</style>
"""


def render_live_workflow_view(*, active: bool = False) -> str:
    """Render the Live Workflow Visualizer view (#view-workflow-live)."""
    view_cls = "crm-view active" if active else "crm-view"
    return f"""
<section id="view-workflow-live" class="{view_cls}">
  <!-- Top Banner / Control Panel -->
  <div class="card mb-4 border-0 shadow-sm">
    <div class="card-body py-3">
      <div class="d-flex flex-column flex-lg-row align-items-lg-center justify-content-between gap-3">
        <div>
          <div class="d-flex align-items-center gap-2 mb-1">
            <h4 class="mb-0 fw-bold">Live Workflow Visualizer</h4>
            <span class="badge bg-label-success d-inline-flex align-items-center gap-1" id="wfStreamStatusBadge">
              <span class="spinner-grow spinner-grow-sm text-success" role="status" style="width: 8px; height: 8px;" id="wfStreamPulse"></span>
              <span id="wfStreamStatusText">SSE CONNECTED</span>
            </span>
            <span class="badge bg-label-primary tabular-nums" id="wfRunModeBadge">PAPER MODE</span>
          </div>
          <small class="text-body-secondary">Real-time pipeline orchestration: Capture &rarr; A4 Vision &rarr; A2 Safety &rarr; A1 LinTS &rarr; Touch &rarr; DB Save</small>
        </div>

        <!-- Controls Toolbar -->
        <div class="d-flex flex-wrap align-items-center gap-2">
          <div class="btn-group btn-group-sm" role="group" aria-label="Execution Mode">
            <input type="radio" class="btn-check" name="wfExecMode" id="wfModePaper" value="paper" checked>
            <label class="btn btn-outline-primary" for="wfModePaper" title="Simulated decisions and safe touches">Paper (Safe)</label>
            <input type="radio" class="btn-check" name="wfExecMode" id="wfModeLive" value="live">
            <label class="btn btn-outline-warning" for="wfModeLive" title="Live hardware taps on attached Android devices">Live Touch</label>
          </div>

          <div class="input-group input-group-sm" style="width: 110px;">
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
            <span id="wfTriggerBtnText">Start Live Run</span>
          </button>

          <button type="button" class="btn btn-sm btn-outline-secondary" id="wfResetBtn" title="Reset all node visual states">
            <i class="icon-base ti tabler-refresh icon-16px"></i>
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Main Workflow Canvas (n8n / Make.com Style) -->
  <div class="card mb-4 border-0 shadow-sm overflow-hidden" id="workflowCanvasCard">
    <div class="card-header border-bottom py-3 d-flex align-items-center justify-content-between bg-body-tertiary">
      <div class="d-flex align-items-center gap-2">
        <i class="icon-base ti tabler-git-branch text-primary icon-20px"></i>
        <span class="fw-semibold">Autonomous Decision Graph</span>
        <span class="badge bg-label-info rounded-pill ms-2" id="wfActiveNodeBadge">PIPELINE IDLE</span>
      </div>
      <div class="d-flex align-items-center gap-3">
        <small class="text-body-secondary tabular-nums" id="wfRunIdDisplay">Run ID: --</small>
        <span class="badge bg-label-secondary" id="wfStepCounter">Step 0/0</span>
      </div>
    </div>

    <div class="card-body p-4 position-relative" id="wfCanvasContainer" style="min-height: 440px; background-color: var(--bs-body-bg); background-image: radial-gradient(var(--bs-border-color) 1px, transparent 1px); background-size: 24px 24px;">
      <!-- SVG Connecting Lines Overlay -->
      <svg class="w-100 h-100 position-absolute top-0 start-0 pointer-events-none" id="wfConnectorSvg" style="z-index: 1;">
        <defs>
          <linearGradient id="gradFlow" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#3b82f6" />
            <stop offset="50%" stop-color="#06b6d4" />
            <stop offset="100%" stop-color="#10b981" />
          </linearGradient>
          <filter id="glowFlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        <!-- Dynamic paths injected by crm-workflow.js -->
        <g id="wfSvgPathGroup"></g>
      </svg>

      <!-- 6 Pipeline Nodes Grid -->
      <div class="row g-4 position-relative" style="z-index: 2;" id="wfNodesRow">
        <!-- Node 1: CAPTURE -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-CAPTURE" data-node="CAPTURE">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-primary">
                    <i class="icon-base ti tabler-device-mobile icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-primary px-1 py-0 small mb-1">STAGE 01</span>
                    <h6 class="mb-0 fw-bold">Screen Capture</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-CAPTURE">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">Capture physical Android frame via ADB &amp; UI dump.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-CAPTURE">
                <div class="text-body-secondary fst-italic">Awaiting capture trigger...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>Bridge: ADB / CDP</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-CAPTURE"></i>
            </div>
          </div>
        </div>

        <!-- Node 2: A4_VISION -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-A4_VISION" data-node="A4_VISION">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-info">
                    <i class="icon-base ti tabler-scan-eye icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-info px-1 py-0 small mb-1">STAGE 02</span>
                    <h6 class="mb-0 fw-bold">A4 Ad Detector</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-A4_VISION">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">XML hierarchy parse + RuleFallback bounding box.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-A4_VISION">
                <div class="text-body-secondary fst-italic">Awaiting visual frame...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>Threshold: &gt;= 0.55 conf</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-A4_VISION"></i>
            </div>
          </div>
        </div>

        <!-- Node 3: A2_ANOMALY -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-A2_ANOMALY" data-node="A2_ANOMALY">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-warning">
                    <i class="icon-base ti tabler-shield-check icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-warning px-1 py-0 small mb-1">STAGE 03</span>
                    <h6 class="mb-0 fw-bold">A2 Safety &amp; EWMA</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-A2_ANOMALY">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">Isolation Forest telemetry check &amp; SafeMode lock.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-A2_ANOMALY">
                <div class="text-body-secondary fst-italic">Awaiting metrics telemetry...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>SafeMode: FAIL-CLOSED</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-A2_ANOMALY"></i>
            </div>
          </div>
        </div>

        <!-- Node 4: A1_DECISION -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-A1_DECISION" data-node="A1_DECISION">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-danger">
                    <i class="icon-base ti tabler-brain icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-danger px-1 py-0 small mb-1">STAGE 04</span>
                    <h6 class="mb-0 fw-bold">A1 LinTS Bandit</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-A1_DECISION">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">Contextual Thompson Sampling &amp; CTR hard cap 4.5%.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-A1_DECISION">
                <div class="text-body-secondary fst-italic">Awaiting state vector...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>Hard Cap: 4.5% CTR</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-A1_DECISION"></i>
            </div>
          </div>
        </div>

        <!-- Node 5: ADB_TAP -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-ADB_TAP" data-node="ADB_TAP">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-success">
                    <i class="icon-base ti tabler-fingerprint icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-success px-1 py-0 small mb-1">STAGE 05</span>
                    <h6 class="mb-0 fw-bold">Biometric Touch</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-ADB_TAP">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">Human-like Bézier gesture dispatch with jitter.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-ADB_TAP">
                <div class="text-body-secondary fst-italic">Awaiting decision execution...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>Capacitive Touch Bridge</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-ADB_TAP"></i>
            </div>
          </div>
        </div>

        <!-- Node 6: DB_SAVE -->
        <div class="col-12 col-md-6 col-xl-4">
          <div class="wf-node card border h-100 shadow-sm transition-all" id="wfNode-DB_SAVE" data-node="DB_SAVE">
            <div class="card-body p-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  <div class="wf-node-icon-box rounded p-2 bg-label-secondary">
                    <i class="icon-base ti tabler-database icon-22px"></i>
                  </div>
                  <div>
                    <span class="badge bg-label-secondary px-1 py-0 small mb-1">STAGE 06</span>
                    <h6 class="mb-0 fw-bold">SQLite Persistence</h6>
                  </div>
                </div>
                <span class="badge bg-label-secondary wf-status-pill" id="wfStatus-DB_SAVE">IDLE</span>
              </div>
              <p class="text-body-secondary small mb-2">Atomic WAL commit with BEGIN IMMEDIATE lock.</p>
              <div class="wf-node-data p-2 rounded bg-body-tertiary small font-monospace" id="wfData-DB_SAVE">
                <div class="text-body-secondary fst-italic">Awaiting session record...</div>
              </div>
            </div>
            <div class="wf-node-footer px-3 py-1 bg-body-secondary border-top d-flex align-items-center justify-content-between small text-body-secondary">
              <span>WAL Atomic Rollup</span>
              <i class="icon-base ti tabler-circle-check text-body-tertiary wf-node-check" id="wfCheck-DB_SAVE"></i>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Real-time Event Stream Log & Terminal Drawer -->
  <div class="card border-0 shadow-sm">
    <div class="card-header border-bottom py-3 d-flex align-items-center justify-content-between">
      <div class="d-flex align-items-center gap-2">
        <i class="icon-base ti tabler-terminal text-primary icon-20px"></i>
        <h6 class="mb-0 fw-semibold">Live Event Stream Log (SSE)</h6>
        <span class="badge bg-label-primary tabular-nums" id="wfLogCountBadge">0 Events</span>
      </div>
      <div class="d-flex align-items-center gap-2">
        <div class="form-check form-switch form-check-sm mb-0">
          <input class="form-check-input" type="checkbox" id="wfAutoScrollSwitch" checked>
          <label class="form-check-label small" for="wfAutoScrollSwitch">Auto-scroll</label>
        </div>
        <button type="button" class="btn btn-sm btn-outline-secondary" id="wfClearLogBtn">Clear Log</button>
      </div>
    </div>
    <div class="card-body p-0">
      <div class="p-3 bg-dark text-light font-monospace small overflow-auto" id="wfTerminalBox" style="height: 240px; line-height: 1.6;">
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
