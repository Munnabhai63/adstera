/**
 * AdsterraFleet Vuexy CRM — Complete A-to-Z Multi-Agent Architectural Wiring Controller
 * Connects to /api/phase4/live-workflow-stream via Server-Sent Events (SSE).
 * Handles pan/zoom, dynamic SVG wire routing, and stage telemetry for all 4 layers:
 * Content -> Hardware Farm -> AI Vision & Decision Core -> HQ & Telemetry.
 */
(function () {
  "use strict";

  const WIRE_CONNECTIONS = [
    // Layer 1 Content
    { from: "TRENDS_HARVESTER", to: "FREELMM_GATEWAY", id: "w-trends-llm" },
    { from: "FREELMM_GATEWAY", to: "A5_SEO_GATE", id: "w-llm-gate" },
    { from: "A5_SEO_GATE", to: "CF_PAGES", id: "w-gate-cf" },
    { from: "CF_PAGES", to: "GSC_INDEX", id: "w-cf-gsc" },
    { from: "CF_PAGES", to: "PUSH_NOTIF", id: "w-cf-push" },

    // Layer 2 Hardware
    { from: "A6_SCHEDULER", to: "CGNAT_TRACKER", id: "w-sched-cgnat" },
    { from: "CGNAT_TRACKER", to: "AIRPLANE_ROTATOR", id: "w-cgnat-air" },
    { from: "AIRPLANE_ROTATOR", to: "PHONE_FARM", id: "w-air-farm" },

    // Cross-layer: Phone Farm to Capture
    { from: "PHONE_FARM", to: "CAPTURE", id: "w-farm-capture" },

    // Layer 3 AI Decision & Safety
    { from: "CAPTURE", to: "A4_VISION", id: "w-cap-a4" },
    { from: "A4_VISION", to: "A2_ANOMALY", id: "w-a4-a2" },
    { from: "A2_ANOMALY", to: "SAFE_MODE_GATE", id: "w-a2-safe" },
    { from: "SAFE_MODE_GATE", to: "SKIP_ACTION", id: "w-safe-skip" },
    { from: "SAFE_MODE_GATE", to: "CTR_GUARD_GATE", id: "w-safe-ctr" },
    { from: "CTR_GUARD_GATE", to: "DEFER_ACTION", id: "w-ctr-defer" },
    { from: "CTR_GUARD_GATE", to: "A1_DECISION", id: "w-ctr-bandit" },
    { from: "A1_DECISION", to: "ADB_TAP", id: "w-bandit-tap" },

    // Layer 3 to Layer 4 HQ & Telemetry
    { from: "ADB_TAP", to: "DB_SAVE", id: "w-tap-db" },
    { from: "DB_SAVE", to: "CENTRAL_HQ", id: "w-db-hq" },
    { from: "DB_SAVE", to: "A3_FORECAST", id: "w-db-a3" },
    { from: "DB_SAVE", to: "ADSTERRA_SYNC", id: "w-db-adsterra" },
    { from: "DB_SAVE", to: "TELEGRAM_BOT", id: "w-db-tg" },
  ];

  let eventSource = null;
  let logCount = 0;
  let activeRunId = null;

  // Pan & Zoom state
  let scale = 0.9;
  let panX = 10;
  let panY = 10;
  let isPanning = false;
  let startX = 0;
  let startY = 0;

  function initWorkflow() {
    const viewEl = document.getElementById("view-workflow-live");
    if (!viewEl) return;

    setupPanZoom();
    setupControls();
    connectSSE();

    // Initial draw and redraw on layout settle
    setTimeout(() => {
      drawAllWires();
      updateTransform();
    }, 200);

    window.addEventListener("resize", debounce(drawAllWires, 200));
    window.addEventListener("crm:view-activated", function (e) {
      if (e.detail && e.detail.view === "workflow-live") {
        setTimeout(drawAllWires, 150);
      }
    });
  }

  function setupPanZoom() {
    const viewport = document.getElementById("wfCanvasViewport");
    const transformEl = document.getElementById("wfCanvasTransform");
    if (!viewport || !transformEl) return;

    viewport.addEventListener("mousedown", (e) => {
      if (e.target.closest(".wf-box-node, .wf-diamond-node, button, select, input")) return;
      isPanning = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
      viewport.classList.add("grabbing");
    });

    window.addEventListener("mousemove", (e) => {
      if (!isPanning) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      updateTransform();
    });

    window.addEventListener("mouseup", () => {
      if (isPanning) {
        isPanning = false;
        viewport.classList.remove("grabbing");
      }
    });

    viewport.addEventListener("wheel", (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      const newScale = Math.min(Math.max(scale * zoomFactor, 0.4), 1.8);

      const rect = viewport.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      panX = mouseX - (mouseX - panX) * (newScale / scale);
      panY = mouseY - (mouseY - panY) * (newScale / scale);
      scale = newScale;

      updateTransform();
    }, { passive: false });

    // Toolbar Zoom Buttons
    const inBtn = document.getElementById("wfZoomInBtn");
    const outBtn = document.getElementById("wfZoomOutBtn");
    const resetBtn = document.getElementById("wfZoomResetBtn");

    if (inBtn) inBtn.addEventListener("click", () => { scale = Math.min(scale + 0.15, 1.8); updateTransform(); });
    if (outBtn) outBtn.addEventListener("click", () => { scale = Math.max(scale - 0.15, 0.4); updateTransform(); });
    if (resetBtn) resetBtn.addEventListener("click", () => { scale = 0.9; panX = 10; panY = 10; updateTransform(); });
  }

  function updateTransform() {
    const transformEl = document.getElementById("wfCanvasTransform");
    if (transformEl) {
      transformEl.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    }
  }

  function setupControls() {
    const triggerBtn = document.getElementById("wfTriggerRunBtn");
    const resetBtn = document.getElementById("wfResetBtn");
    const clearLogBtn = document.getElementById("wfClearLogBtn");

    if (triggerBtn) triggerBtn.addEventListener("click", triggerRun);
    if (resetBtn) resetBtn.addEventListener("click", resetAllNodes);

    if (clearLogBtn) {
      clearLogBtn.addEventListener("click", () => {
        const box = document.getElementById("wfTerminalBox");
        if (box) {
          box.innerHTML = '<div class="text-secondary">[SYSTEM] Terminal log cleared.</div>';
          logCount = 0;
          updateLogCount();
        }
      });
    }
  }

  function connectSSE() {
    if (eventSource) {
      try { eventSource.close(); } catch (_) {}
    }

    const badge = document.getElementById("wfStreamStatusBadge");
    const text = document.getElementById("wfStreamStatusText");
    const pulse = document.getElementById("wfStreamPulse");

    const sseUrl = "/api/phase4/live-workflow-stream";
    try {
      eventSource = new EventSource(sseUrl);

      eventSource.onopen = function () {
        if (badge) badge.className = "badge bg-label-success d-inline-flex align-items-center gap-1";
        if (text) text.textContent = "SSE STREAMING";
        if (pulse) pulse.className = "spinner-grow spinner-grow-sm text-success";
        logToTerminal("SYSTEM", "Connected to Live Architecture SSE Stream.", "info");
      };

      eventSource.addEventListener("connected", function (e) {
        try {
          const payload = JSON.parse(e.data);
          logToTerminal("INIT", payload.message || "Connected", "info");
          if (Array.isArray(payload.history) && payload.history.length > 0) {
            payload.history.forEach((ev) => handlePipelineEvent(ev, true));
          }
        } catch (_) {}
      });

      eventSource.addEventListener("pipeline", function (e) {
        try {
          const ev = JSON.parse(e.data);
          handlePipelineEvent(ev);
        } catch (_) {}
      });

      eventSource.onmessage = function (e) {
        try {
          const ev = JSON.parse(e.data);
          handlePipelineEvent(ev);
        } catch (_) {}
      };

      eventSource.onerror = function () {
        if (badge) badge.className = "badge bg-label-danger d-inline-flex align-items-center gap-1";
        if (text) text.textContent = "SSE RECONNECTING";
        if (pulse) pulse.className = "spinner-grow spinner-grow-sm text-danger";
      };
    } catch (err) {
      console.error("[WorkflowSSE] Error initializing EventSource:", err);
    }
  }

  function handlePipelineEvent(ev, isHistory = false) {
    if (!ev || !ev.node_id) return;

    const nodeId = ev.node_id.toUpperCase();
    const status = (ev.status || "info").toLowerCase();
    const message = ev.message || "";
    const data = ev.data || {};
    const runId = ev.run_id || "";

    if (runId && runId !== activeRunId) {
      activeRunId = runId;
    }

    if (!isHistory) {
      logToTerminal(nodeId, message, status, data);
    }

    const readout = document.getElementById("wfActiveStageReadout");
    if (readout) {
      readout.textContent = nodeId.replace(/_/g, " ") + " [" + status.toUpperCase() + "]";
      readout.className = status === "processing" ? "badge bg-label-warning tabular-nums" : "badge bg-label-info tabular-nums";
    }

    if (nodeId === "WORKFLOW_START") {
      resetAllNodes();
      setTriggerLoading(true);
      return;
    }

    if (nodeId === "WORKFLOW_FINISH" || nodeId === "WORKFLOW_ERROR") {
      setTriggerLoading(false);
      return;
    }

    updateNodeState(nodeId, status, message, data);
    updateWireState(nodeId, status);
  }

  function updateNodeState(nodeId, status, message, data) {
    const nodeEl = document.getElementById("node-" + nodeId);
    const metricEl = document.getElementById("metric-" + nodeId);

    if (nodeEl) {
      nodeEl.classList.remove("processing", "success", "failed");
      if (status === "processing") nodeEl.classList.add("processing");
      else if (status === "success") nodeEl.classList.add("success");
      else if (status === "failed") nodeEl.classList.add("failed");
    }

    if (metricEl) {
      if (status === "processing") {
        metricEl.textContent = "... processing ...";
      } else if (message) {
        metricEl.textContent = formatMetricText(nodeId, message, data);
      }
    }
  }

  function formatMetricText(nodeId, msg, data) {
    if (data.bbox) return `bbox: [${data.bbox.join(", ")}]`;
    if (data.action) return `Action: ${data.action.toUpperCase()} (${Number(data.reward || 0).toFixed(4)})`;
    if (data.intensity) return `Intensity: ${data.intensity} (${data.sessions_today} today)`;
    if (data.subnet_24) return `Subnet: ${data.subnet_24}`;
    if (data.perplexity) return `Perplexity: ${data.perplexity} (Approved)`;
    if (data.p50) return `P50: $${Number(data.p50).toFixed(2)}`;
    if (data.session_id) return `Committed: ${data.session_id.substring(0, 12)}...`;
    return msg.length > 36 ? msg.substring(0, 34) + "..." : msg;
  }

  function updateWireState(nodeId, status) {
    WIRE_CONNECTIONS.forEach((w) => {
      if (w.from === nodeId) {
        const path = document.getElementById(w.id);
        if (path) {
          path.classList.remove("active", "success", "failed");
          if (status === "processing") {
            path.classList.add("active");
            path.setAttribute("marker-end", "url(#wfArrowActive)");
          } else if (status === "success") {
            path.classList.add("success");
            path.setAttribute("marker-end", "url(#wfArrowSuccess)");
          } else if (status === "failed") {
            path.classList.add("failed");
          }
        }
      }
    });
  }

  function drawAllWires() {
    const group = document.getElementById("wfWirePathGroup");
    const transformEl = document.getElementById("wfCanvasTransform");
    if (!group || !transformEl) return;

    group.innerHTML = "";
    const parentRect = transformEl.getBoundingClientRect();

    WIRE_CONNECTIONS.forEach((conn) => {
      const fromEl = document.getElementById("node-" + conn.from);
      const toEl = document.getElementById("node-" + conn.to);
      if (!fromEl || !toEl) return;

      const r1 = fromEl.getBoundingClientRect();
      const r2 = toEl.getBoundingClientRect();

      // Normalize coordinates within unscaled coordinate space
      const x1 = (r1.right - parentRect.left) / scale;
      const y1 = (r1.top + r1.height / 2 - parentRect.top) / scale;

      const x2 = (r2.left - parentRect.left) / scale;
      const y2 = (r2.top + r2.height / 2 - parentRect.top) / scale;

      let d;
      // If target is to the right
      if (x2 > x1 + 15) {
        const dx = Math.max((x2 - x1) * 0.45, 30);
        d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2 - 4} ${y2}`;
      } else {
        // Vertical or looped connection (same column or flowing backwards)
        const cy1 = (r1.bottom - parentRect.top) / scale;
        const cx1 = (r1.left + r1.width / 2 - parentRect.top) / scale;
        const cy2 = (r2.top - parentRect.top) / scale;
        const cx2 = (r2.left + r2.width / 2 - parentRect.top) / scale;
        d = `M ${cx1} ${cy1} C ${cx1} ${cy1 + 25}, ${cx2} ${cy2 - 25}, ${cx2} ${cy2 - 4}`;
      }

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("id", conn.id);
      path.setAttribute("class", "wf-svg-wire");
      path.setAttribute("d", d);
      path.setAttribute("marker-end", "url(#wfArrow)");
      group.appendChild(path);
    });
  }

  function resetAllNodes() {
    document.querySelectorAll(".wf-box-node, .wf-diamond-node").forEach((el) => {
      el.classList.remove("processing", "success", "failed");
    });
    document.querySelectorAll(".wf-svg-wire").forEach((p) => {
      p.classList.remove("active", "success", "failed");
      p.setAttribute("marker-end", "url(#wfArrow)");
    });
    const readout = document.getElementById("wfActiveStageReadout");
    if (readout) {
      readout.textContent = "IDLE";
      readout.className = "badge bg-label-info tabular-nums";
    }
  }

  function triggerRun() {
    const modeEl = document.querySelector('input[name="wfExecMode"]:checked');
    const stepsEl = document.getElementById("wfStepsSelect");
    const mode = modeEl ? modeEl.value : "paper";
    const steps = stepsEl ? parseInt(stepsEl.value, 10) || 1 : 1;

    setTriggerLoading(true);

    fetch("/api/phase4/workflow/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: mode,
        steps: steps,
        domain: "rechargekar.com",
        device_id: "RZCX21WT59E",
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.ok) {
          setTriggerLoading(false);
        }
      })
      .catch(() => {
        setTriggerLoading(false);
      });
  }

  function setTriggerLoading(isLoading) {
    const btn = document.getElementById("wfTriggerRunBtn");
    const icon = document.getElementById("wfTriggerIcon");
    const text = document.getElementById("wfTriggerBtnText");
    if (!btn) return;

    if (isLoading) {
      btn.disabled = true;
      if (icon) icon.className = "spinner-border spinner-border-sm me-1";
      if (text) text.textContent = "Running Pipeline...";
    } else {
      btn.disabled = false;
      if (icon) icon.className = "icon-base ti tabler-player-play icon-16px";
      if (text) text.textContent = "Start Pipeline Run";
    }
  }

  function logToTerminal(tag, message, status, data) {
    const box = document.getElementById("wfTerminalBox");
    if (!box) return;

    logCount++;
    updateLogCount();

    const timeStr = new Date().toLocaleTimeString();
    let colorClass = "text-light";
    if (status === "processing") colorClass = "text-info";
    if (status === "success") colorClass = "text-success";
    if (status === "failed") colorClass = "text-danger";

    const div = document.createElement("div");
    div.className = "mb-1 text-break";
    div.innerHTML = `<span class="text-secondary">[${timeStr}]</span> <span class="badge bg-label-secondary px-1">${escapeHtml(tag)}</span> <span class="${colorClass}">${escapeHtml(message)}</span>`;

    box.appendChild(div);

    const autoScroll = document.getElementById("wfAutoScrollSwitch");
    if (autoScroll && autoScroll.checked) {
      box.scrollTop = box.scrollHeight;
    }
  }

  function updateLogCount() {
    const badge = document.getElementById("wfLogCountBadge");
    if (badge) badge.textContent = `${logCount} Events`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function debounce(fn, delay) {
    let timer = null;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, delay);
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWorkflow);
  } else {
    initWorkflow();
  }

  window.CRMWorkflow = {
    trigger: triggerRun,
    reset: resetAllNodes,
    redraw: drawAllWires,
  };
})();
