/**
 * AdsterraFleet Vuexy CRM — Live Workflow Controller
 * Connects to /api/phase4/live-workflow-stream via Server-Sent Events (SSE).
 * Renders n8n / Make.com style visual pipeline animations across:
 * CAPTURE -> A4_VISION -> A2_ANOMALY -> A1_DECISION -> ADB_TAP -> DB_SAVE.
 */
(function () {
  "use strict";

  const PIPELINE_NODES = [
    "CAPTURE",
    "A4_VISION",
    "A2_ANOMALY",
    "A1_DECISION",
    "ADB_TAP",
    "DB_SAVE",
  ];

  let eventSource = null;
  let logCount = 0;
  let activeRunId = null;

  function initWorkflow() {
    const viewEl = document.getElementById("view-workflow-live");
    if (!viewEl) return;

    setupControls();
    connectSSE();
    drawConnectors();

    window.addEventListener("resize", debounce(drawConnectors, 150));
    window.addEventListener("crm:view-activated", function (e) {
      if (e.detail && e.detail.view === "workflow-live") {
        setTimeout(drawConnectors, 100);
      }
    });
  }

  function setupControls() {
    const triggerBtn = document.getElementById("wfTriggerRunBtn");
    const resetBtn = document.getElementById("wfResetBtn");
    const clearLogBtn = document.getElementById("wfClearLogBtn");
    const modeRadios = document.querySelectorAll('input[name="wfExecMode"]');

    if (triggerBtn) {
      triggerBtn.addEventListener("click", triggerRun);
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", resetAllNodes);
    }

    if (clearLogBtn) {
      clearLogBtn.addEventListener("click", function () {
        const box = document.getElementById("wfTerminalBox");
        if (box) {
          box.innerHTML = '<div class="text-secondary">[SYSTEM] Terminal log cleared.</div>';
          logCount = 0;
          updateLogCount();
        }
      });
    }

    modeRadios.forEach((radio) => {
      radio.addEventListener("change", function () {
        const badge = document.getElementById("wfRunModeBadge");
        if (badge) {
          const val = this.value.toUpperCase();
          badge.textContent = val + " MODE";
          badge.className = val === "LIVE" ? "badge bg-label-warning tabular-nums" : "badge bg-label-primary tabular-nums";
        }
      });
    });
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
        logToTerminal("SYSTEM", "Connected to Live Workflow SSE stream.", "info");
      };

      eventSource.addEventListener("connected", function (e) {
        try {
          const payload = JSON.parse(e.data);
          logToTerminal("INIT", payload.message || "Connected", "info");
          if (Array.isArray(payload.history) && payload.history.length > 0) {
            payload.history.forEach((ev) => handlePipelineEvent(ev, true));
          }
        } catch (err) {
          console.warn("[WorkflowSSE] JSON parse error on connected:", err);
        }
      });

      eventSource.addEventListener("pipeline", function (e) {
        try {
          const ev = JSON.parse(e.data);
          handlePipelineEvent(ev);
        } catch (err) {
          console.warn("[WorkflowSSE] JSON parse error on pipeline:", err);
        }
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
      console.error("[WorkflowSSE] Failed to initialize EventSource:", err);
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
      const runDisplay = document.getElementById("wfRunIdDisplay");
      if (runDisplay) runDisplay.textContent = "Run: " + runId;
    }

    if (!isHistory) {
      logToTerminal(nodeId, message, status, data);
    }

    // Top status pill update
    const activeBadge = document.getElementById("wfActiveNodeBadge");
    if (activeBadge) {
      activeBadge.textContent = nodeId + ": " + status.toUpperCase();
      activeBadge.className = status === "processing"
        ? "badge bg-label-warning rounded-pill ms-2"
        : status === "success"
        ? "badge bg-label-success rounded-pill ms-2"
        : status === "failed"
        ? "badge bg-label-danger rounded-pill ms-2"
        : "badge bg-label-info rounded-pill ms-2";
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

    // Pipeline Stage Node Update
    if (PIPELINE_NODES.includes(nodeId)) {
      updateNodeState(nodeId, status, message, data);
      updateConnectorState(nodeId, status);
    }
  }

  function updateNodeState(nodeId, status, message, data) {
    const nodeEl = document.getElementById("wfNode-" + nodeId);
    const statusPill = document.getElementById("wfStatus-" + nodeId);
    const dataBox = document.getElementById("wfData-" + nodeId);
    const checkIcon = document.getElementById("wfCheck-" + nodeId);

    if (!nodeEl) return;

    nodeEl.classList.remove("processing", "success", "failed");

    if (status === "processing") {
      nodeEl.classList.add("processing");
      if (statusPill) {
        statusPill.className = "badge bg-label-warning wf-status-pill";
        statusPill.innerHTML = '<span class="spinner-border spinner-border-sm me-1" style="width: 10px; height: 10px;"></span>RUNNING';
      }
      if (checkIcon) {
        checkIcon.className = "icon-base ti tabler-loader text-warning animate-spin wf-node-check";
      }
      if (dataBox) {
        dataBox.innerHTML = '<div class="text-warning">' + escapeHtml(message) + '</div>';
      }
    } else if (status === "success") {
      nodeEl.classList.add("success");
      if (statusPill) {
        statusPill.className = "badge bg-label-success wf-status-pill";
        statusPill.textContent = "SUCCESS";
      }
      if (checkIcon) {
        checkIcon.className = "icon-base ti tabler-circle-check-filled text-success wf-node-check";
      }
      if (dataBox) {
        dataBox.innerHTML = renderPayloadPreview(data, message);
      }
    } else if (status === "failed") {
      nodeEl.classList.add("failed");
      if (statusPill) {
        statusPill.className = "badge bg-label-danger wf-status-pill";
        statusPill.textContent = "FAILED";
      }
      if (checkIcon) {
        checkIcon.className = "icon-base ti tabler-alert-circle-filled text-danger wf-node-check";
      }
      if (dataBox) {
        dataBox.innerHTML = '<div class="text-danger fw-bold">' + escapeHtml(message) + '</div>';
      }
    }
  }

  function renderPayloadPreview(data, fallbackMsg) {
    if (!data || Object.keys(data).length === 0) {
      return '<div class="text-success text-truncate">' + escapeHtml(fallbackMsg) + '</div>';
    }
    const parts = [];
    if (data.bbox) parts.push('bbox: [' + data.bbox.join(', ') + ']');
    if (data.confidence !== undefined) parts.push('conf: ' + Number(data.confidence).toFixed(2));
    if (data.action) parts.push('action: <b class="text-primary">' + data.action.toUpperCase() + '</b>');
    if (data.reward !== undefined) parts.push('reward: ' + Number(data.reward).toFixed(5));
    if (data.current_ctr !== undefined) parts.push('ctr: ' + (Number(data.current_ctr) * 100).toFixed(2) + '%');
    if (data.executed !== undefined) parts.push('tap: ' + (data.executed ? 'YES' : 'SIMULATED'));
    if (data.session_id) parts.push('sid: ' + data.session_id.substring(0, 14) + '...');

    if (parts.length > 0) {
      return '<div class="text-body-secondary">' + parts.join(' &bull; ') + '</div>';
    }
    return '<div class="text-truncate text-body-secondary">' + escapeHtml(JSON.stringify(data)) + '</div>';
  }

  function updateConnectorState(nodeId, status) {
    const idx = PIPELINE_NODES.indexOf(nodeId);
    if (idx < 0) return;

    const path = document.getElementById("wfPath-" + idx);
    if (!path) return;

    path.classList.remove("active", "success", "failed");
    if (status === "processing") {
      path.classList.add("active");
    } else if (status === "success") {
      path.classList.add("success");
    } else if (status === "failed") {
      path.classList.add("failed");
    }
  }

  function drawConnectors() {
    const group = document.getElementById("wfSvgPathGroup");
    const container = document.getElementById("wfCanvasContainer");
    if (!group || !container) return;

    group.innerHTML = "";
    const containerRect = container.getBoundingClientRect();

    for (let i = 0; i < PIPELINE_NODES.length - 1; i++) {
      const fromEl = document.getElementById("wfNode-" + PIPELINE_NODES[i]);
      const toEl = document.getElementById("wfNode-" + PIPELINE_NODES[i + 1]);
      if (!fromEl || !toEl) continue;

      const r1 = fromEl.getBoundingClientRect();
      const r2 = toEl.getBoundingClientRect();

      // Start: right middle of fromEl
      const x1 = r1.right - containerRect.left;
      const y1 = r1.top + r1.height / 2 - containerRect.top;

      // End: left middle of toEl
      const x2 = r2.left - containerRect.left;
      const y2 = r2.top + r2.height / 2 - containerRect.top;

      let d;
      if (Math.abs(y1 - y2) < 40 && x2 > x1) {
        // Same row: smooth horizontal cubic bezier
        const dx = (x2 - x1) * 0.5;
        d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
      } else {
        // Wrap to next row: S-curve path
        const mx = (x1 + x2) / 2;
        d = `M ${x1} ${y1} C ${x1 + 60} ${y1}, ${mx} ${y1}, ${mx} ${(y1 + y2) / 2} S ${x2 - 60} ${y2}, ${x2} ${y2}`;
      }

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("id", "wfPath-" + i);
      path.setAttribute("class", "wf-svg-path");
      path.setAttribute("d", d);
      group.appendChild(path);
    }
  }

  function resetAllNodes() {
    PIPELINE_NODES.forEach((nodeId) => {
      const nodeEl = document.getElementById("wfNode-" + nodeId);
      const statusPill = document.getElementById("wfStatus-" + nodeId);
      const dataBox = document.getElementById("wfData-" + nodeId);
      const checkIcon = document.getElementById("wfCheck-" + nodeId);

      if (nodeEl) nodeEl.classList.remove("processing", "success", "failed");
      if (statusPill) {
        statusPill.className = "badge bg-label-secondary wf-status-pill";
        statusPill.textContent = "IDLE";
      }
      if (checkIcon) {
        checkIcon.className = "icon-base ti tabler-circle-check text-body-tertiary wf-node-check";
      }
      if (dataBox) {
        dataBox.innerHTML = '<div class="text-body-secondary fst-italic">Waiting for pipeline trigger...</div>';
      }
    });

    document.querySelectorAll(".wf-svg-path").forEach((p) => {
      p.classList.remove("active", "success", "failed");
    });

    const activeBadge = document.getElementById("wfActiveNodeBadge");
    if (activeBadge) {
      activeBadge.textContent = "PIPELINE IDLE";
      activeBadge.className = "badge bg-label-info rounded-pill ms-2";
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
        device_id: "dev-01",
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.ok) {
          showNotification(`Triggered ${mode.toUpperCase()} run (${steps} steps)`, "success");
        } else {
          showNotification(`Run trigger failed: ${data.error || "Unknown error"}`, "error");
          setTriggerLoading(false);
        }
      })
      .catch((err) => {
        showNotification(`API Error: ${err.message}`, "error");
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
      if (text) text.textContent = "Start Live Run";
    }
  }

  function logToTerminal(tag, message, status, data) {
    const box = document.getElementById("wfTerminalBox");
    if (!box) return;

    logCount++;
    updateLogCount();

    const timeStr = new Date().toLocaleTimeString();
    let colorClass = "text-light";
    if (status === "processing") colorClass = "text-warning";
    if (status === "success") colorClass = "text-success";
    if (status === "failed") colorClass = "text-danger";

    const div = document.createElement("div");
    div.className = "mb-1 text-break";
    div.innerHTML = `<span class="text-secondary">[${timeStr}]</span> <span class="badge bg-label-primary px-1">${escapeHtml(tag)}</span> <span class="${colorClass}">${escapeHtml(message)}</span>`;

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

  function showNotification(msg, type) {
    if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
      window.AdsterraShell.toast(msg, type);
    } else {
      console.log(`[WorkflowToast:${type}]`, msg);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function debounce(fn, delay) {
    let timer = null;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, delay);
    };
  }

  // Auto-init on DOMContentLoaded or immediate if DOM already loaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWorkflow);
  } else {
    initWorkflow();
  }

  window.CRMWorkflow = {
    trigger: triggerRun,
    reset: resetAllNodes,
    redraw: drawConnectors,
  };
})();
