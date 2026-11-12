/**
 * AdsterraFleet Vuexy Phase 4 Autonomous Farm & AI Ops Controller
 * Strict DOM construction using createElement and textContent only.
 */
(function () {
  "use strict";

  const state = {
    payload: null,
    charts: {
      forecast: null,
      activity: null,
    },
    pollTimer: null,
    isFetching: false,
  };

  function clearChildren(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function createEl(tag, className, textValue) {
    const el = document.createElement(tag);
    if (className) {
      el.className = className;
    }
    if (textValue !== undefined && textValue !== null) {
      el.textContent = String(textValue);
    }
    return el;
  }

  function createBadge(text, variant) {
    return createEl("span", "badge bg-label-" + (variant || "secondary"), text);
  }

  function createCell(content, className) {
    const td = document.createElement("td");
    if (className) {
      td.className = className;
    }
    if (content instanceof Node) {
      td.appendChild(content);
    } else {
      td.textContent = content == null ? "" : String(content);
    }
    return td;
  }

  function renderEmptyRow(tbody, colSpan, message) {
    clearChildren(tbody);
    const tr = document.createElement("tr");
    const td = createEl("td", "text-center text-body-secondary py-4", message);
    td.setAttribute("colspan", String(colSpan));
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function formatTs(epochSec) {
    const n = Number(epochSec || 0);
    if (!Number.isFinite(n) || n <= 0) {
      return "--";
    }
    try {
      return new Date(n * 1000).toISOString().replace("T", " ").slice(0, 19) + "Z";
    } catch (_) {
      return String(epochSec);
    }
  }

  function formatUsd(val, decimals) {
    const n = Number(val || 0);
    if (!Number.isFinite(n) || n === 0) return "$0.00";
    if (decimals != null) {
      if (Math.abs(n) > 0 && Math.abs(n) < 0.01 && decimals < 4) {
        return "$" + n.toFixed(4);
      }
      return "$" + n.toFixed(decimals);
    }
    if (Math.abs(n) > 0 && Math.abs(n) < 0.01) {
      return "$" + n.toFixed(4);
    }
    return "$" + n.toFixed(2);
  }

  function statusVariant(status) {
    const s = String(status || "").toLowerCase();
    if (s === "healthy" || s === "active" || s === "completed" || s === "ok") {
      return "success";
    }
    if (s === "started" || s === "paper" || s === "irls_quantile") {
      return "primary";
    }
    if (s === "quarantined" || s === "degraded" || s === "median_fallback" || s === "insufficient_data") {
      return "warning";
    }
    if (s.includes("fail") || s.includes("error") || s.includes("offline") || s.includes("collision") || s.includes("blocked")) {
      return "danger";
    }
    return "secondary";
  }

  function getChartPalette() {
    const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    const styles = getComputedStyle(document.documentElement);
    const cssVar = (name, fb) => styles.getPropertyValue(name).trim() || fb;
    return {
      isDark,
      primary: cssVar("--bs-primary", "#7367f0"),
      success: cssVar("--bs-success", "#28c76f"),
      info: cssVar("--bs-info", "#00bad1"),
      warning: cssVar("--bs-warning", "#ff9f43"),
      danger: cssVar("--bs-danger", "#ff4c51"),
      textMuted: isDark ? "#a3a7c4" : "#6d6b77",
      heading: isDark ? "#e0e3f5" : "#444050",
      border: isDark ? "#434968" : "#e6e6f1",
    };
  }

  function isEmbeddedShell() {
    return Boolean(document.getElementById("view-overview"));
  }

  function isPhase4Visible() {
    const view = document.getElementById("view-phase4-farm");
    if (!view) return false;
    return !isEmbeddedShell() || view.classList.contains("active");
  }

  function upsertChart(key, selector, options) {
    if (typeof ApexCharts === "undefined") {
      return;
    }
    const container = document.querySelector(selector);
    if (!container) {
      return;
    }
    if (isEmbeddedShell() && container.offsetParent === null) {
      return;
    }
    if (state.charts[key]) {
      try {
        state.charts[key].updateOptions(options, false, false);
        return;
      } catch (_) {
        try {
          state.charts[key].destroy();
        } catch (__) {}
        state.charts[key] = null;
      }
    }
    const chart = new ApexCharts(container, options);
    chart.render();
    state.charts[key] = chart;
  }

  function renderErrorBanner(payload) {
    const banner = document.getElementById("p4DbErrorBanner");
    const titleEl = document.getElementById("p4DbErrorTitle");
    const msgEl = document.getElementById("p4DbErrorMessage");
    const codeEl = document.getElementById("p4DbErrorCode");
    const badgeEl = document.getElementById("p4DbStatusBadge");
    if (!banner) return;

    const ok = Boolean(payload && payload.ok);
    const dbStatus = String((payload && payload.db_status) || "error").toUpperCase();

    if (ok) {
      banner.classList.add("d-none");
      if (badgeEl) {
        badgeEl.className = "badge bg-label-success";
        badgeEl.textContent = "LIVE SQLITE OK";
      }
    } else {
      banner.classList.remove("d-none");
      if (titleEl) {
        titleEl.textContent = dbStatus === "LOCKED"
          ? "Database Temporarily Locked"
          : dbStatus === "MISSING"
            ? "Phase 3 Database Not Found"
            : "Dashboard Telemetry Error";
      }
      if (msgEl) {
        msgEl.textContent = (payload && payload.error) || "Unable to read Phase 3 SQLite state.";
      }
      if (codeEl) {
        codeEl.textContent = dbStatus;
      }
      if (badgeEl) {
        badgeEl.className = dbStatus === "LOCKED" ? "badge bg-label-warning" : "badge bg-label-danger";
        badgeEl.textContent = "DB " + dbStatus;
      }
    }
  }

  function renderKpis(payload) {
    const kpis = (payload && payload.kpis) || {};
    const fva = kpis.p50_forecast_vs_actual || {};
    const safeMode = kpis.safe_mode || {};

    const elSess = document.getElementById("p4KpiSessions");
    const elSessSub = document.getElementById("p4KpiSessionsSub");
    if (elSess) elSess.textContent = String(Number(kpis.total_sessions || 0));
    if (elSessSub) {
      elSessSub.textContent =
        Number(kpis.completed_sessions || 0) +
        " completed · " +
        Number(kpis.failed_sessions || 0) +
        " failed";
    }

    const elDev = document.getElementById("p4KpiDevices");
    const elDevSub = document.getElementById("p4KpiDevicesSub");
    if (elDev) elDev.textContent = String(Number(kpis.active_devices || 0));
    if (elDevSub) {
      elDevSub.textContent =
        Number(kpis.healthy_farm_devices || 0) +
        " healthy · " +
        Number(kpis.active_cgnat_slots || 0) +
        " active CGNAT";
    }

    const elCol = document.getElementById("p4KpiCollisions");
    const elColSub = document.getElementById("p4KpiCollisionsSub");
    if (elCol) elCol.textContent = String(Number(kpis.ip_collisions_prevented || 0));
    if (elColSub) {
      elColSub.textContent =
        Number(kpis.session_collision_blocks || 0) +
        " blocks · " +
        Number(kpis.subnet_cooldown_hits || 0) +
        " subnet hits";
    }

    const elFc = document.getElementById("p4KpiForecast");
    const elFcSub = document.getElementById("p4KpiForecastSub");
    if (elFc) {
      elFc.textContent =
        formatUsd(fva.p50_revenue, 2) + " / " + formatUsd(fva.actual_revenue, 2);
    }
    if (elFcSub) {
      elFcSub.textContent =
        "P10 " +
        formatUsd(fva.p10_revenue, 2) +
        " – P90 " +
        formatUsd(fva.p90_revenue, 2) +
        " (" +
        Number(fva.pct_of_p50 || 0).toFixed(1) +
        "%)";
    }

    const elSm = document.getElementById("p4KpiSafeMode");
    const elSmSub = document.getElementById("p4KpiSafeModeSub");
    const elSmIcon = document.getElementById("p4KpiSafeIconBox");
    const isSafeActive = Boolean(safeMode.active);
    if (elSm) {
      elSm.className = isSafeActive ? "badge bg-label-danger" : "badge bg-label-success";
      elSm.textContent = isSafeActive ? "SAFE MODE ACTIVE" : "NORMAL";
    }
    if (elSmIcon) {
      elSmIcon.className = isSafeActive
        ? "avatar-initial rounded bg-label-danger"
        : "avatar-initial rounded bg-label-success";
    }
    if (elSmSub) {
      if (isSafeActive && safeMode.reason) {
        elSmSub.textContent = safeMode.reason + " (" + Number(safeMode.clean_windows || 0) + " clean)";
      } else {
        elSmSub.textContent = Number(safeMode.clean_windows || 0) + " clean windows · clicks enabled";
      }
    }

    const updatedEl = document.getElementById("p4LastUpdatedText");
    if (updatedEl && payload && payload.generated_at) {
      updatedEl.textContent =
        "Last synced: " +
        String(payload.generated_at).replace("T", " ").slice(0, 19) +
        "Z · DB: " +
        String((payload.config && payload.config.phase3_db_path) || "state/phase3/phase3.db");
    }
  }

  function renderCharts(payload) {
    const p = getChartPalette();
    const chartsData = (payload && payload.charts) || {};
    const forecastSeries = Array.isArray(chartsData.forecast_series) ? chartsData.forecast_series : [];
    const deviceActivity = Array.isArray(chartsData.device_activity) ? chartsData.device_activity : [];

    const fcMeta = document.getElementById("p4ForecastChartMeta");
    if (fcMeta) {
      fcMeta.textContent = forecastSeries.length + " forecast points";
    }

    const fcLabels = forecastSeries.length ? forecastSeries.map((x) => String(x.label || "")) : ["No Data"];
    const p10 = forecastSeries.length ? forecastSeries.map((x) => Number(x.p10_revenue || 0)) : [0];
    const p50 = forecastSeries.length ? forecastSeries.map((x) => Number(x.p50_revenue || 0)) : [0];
    const p90 = forecastSeries.length ? forecastSeries.map((x) => Number(x.p90_revenue || 0)) : [0];
    const actual = forecastSeries.length ? forecastSeries.map((x) => Number(x.actual_revenue || 0)) : [0];

    upsertChart("forecast", "#p4ChartForecast", {
      chart: { height: 290, type: "line", toolbar: { show: false } },
      colors: [p.info, p.primary, p.warning, p.success],
      stroke: { width: [2, 3, 2, 3], curve: "smooth", dashArray: [4, 0, 4, 0] },
      dataLabels: { enabled: false },
      grid: { borderColor: p.border, strokeDashArray: 4 },
      series: [
        { name: "P10 Forecast", data: p10 },
        { name: "P50 Forecast", data: p50 },
        { name: "P90 Forecast", data: p90 },
        { name: "Actual Revenue", data: actual },
      ],
      xaxis: { categories: fcLabels, labels: { style: { colors: p.textMuted, fontSize: "12px" } } },
      yaxis: {
        labels: {
          style: { colors: p.textMuted, fontSize: "12px" },
          formatter: (v) => "$" + Number(v || 0).toFixed(2),
        },
      },
      legend: { position: "top", labels: { colors: p.heading } },
      tooltip: { theme: p.isDark ? "dark" : "light" },
    });

    const actMeta = document.getElementById("p4ActivityChartMeta");
    if (actMeta) {
      actMeta.textContent = deviceActivity.length + " devices";
    }

    const devLabels = deviceActivity.length ? deviceActivity.map((d) => String(d.device_id || "")) : ["No Devices"];
    const devSessions = deviceActivity.length ? deviceActivity.map((d) => Number(d.total_sessions || 0)) : [0];
    const devClicks = deviceActivity.length ? deviceActivity.map((d) => Number(d.total_clicks || 0)) : [0];

    upsertChart("activity", "#p4ChartActivity", {
      chart: { height: 290, type: "bar", toolbar: { show: false } },
      colors: [p.primary, p.success],
      plotOptions: { bar: { columnWidth: "48%", borderRadius: 5 } },
      dataLabels: { enabled: false },
      grid: { borderColor: p.border, strokeDashArray: 4 },
      series: [
        { name: "Sessions", data: devSessions },
        { name: "Clicks", data: devClicks },
      ],
      xaxis: { categories: devLabels, labels: { style: { colors: p.textMuted, fontSize: "12px" } } },
      yaxis: { labels: { style: { colors: p.textMuted, fontSize: "12px" } } },
      legend: { position: "top", labels: { colors: p.heading } },
      tooltip: { theme: p.isDark ? "dark" : "light" },
    });
  }

  function renderDevicesTable() {
    const tbody = document.getElementById("p4BodyDevices");
    if (!tbody) return;
    const rows = Array.isArray(state.payload && state.payload.farm_devices)
      ? state.payload.farm_devices
      : [];
    const q = ((document.getElementById("p4SearchDevices") || {}).value || "").trim().toLowerCase();
    const statusFilter = ((document.getElementById("p4FilterDeviceStatus") || {}).value || "all").toLowerCase();

    const filtered = rows.filter((row) => {
      const status = String(row.status || "").toLowerCase();
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (!q) return true;
      const hay = [row.device_id, row.usb_port, row.cdp_port, row.b1_port, row.status]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });

    if (!filtered.length) {
      renderEmptyRow(tbody, 7, rows.length ? "No farm devices match filter." : "No farm devices recorded.");
      return;
    }

    clearChildren(tbody);
    filtered.forEach((row) => {
      const tr = document.createElement("tr");
      tr.appendChild(createCell(createEl("code", "small", row.device_id || "")));
      tr.appendChild(createCell(row.usb_port || "--"));
      tr.appendChild(createCell((row.cdp_port || 0) + " / " + (row.b1_port || 0), "tabular-nums"));
      tr.appendChild(createCell(createBadge(String(row.status || "unknown").toUpperCase(), statusVariant(row.status))));
      tr.appendChild(createCell(String(Number(row.consecutive_failures || 0)), "tabular-nums"));
      tr.appendChild(createCell(Number(row.total_sessions || 0) + " / " + Number(row.total_clicks || 0), "tabular-nums"));
      tr.appendChild(createCell(formatTs(row.last_seen_at), "small text-body-secondary tabular-nums"));
      tbody.appendChild(tr);
    });
  }

  function renderSessionsTable() {
    const tbody = document.getElementById("p4BodySessions");
    if (!tbody) return;
    const rows = Array.isArray(state.payload && state.payload.sessions) ? state.payload.sessions : [];
    const q = ((document.getElementById("p4SearchSessions") || {}).value || "").trim().toLowerCase();
    const statusFilter = ((document.getElementById("p4FilterSessionStatus") || {}).value || "all").toLowerCase();

    const filtered = rows.filter((row) => {
      const st = String(row.status || "").toLowerCase();
      if (statusFilter !== "all") {
        if (statusFilter === "failed" && !(st.includes("fail") || st.includes("error") || st.includes("degraded"))) {
          return false;
        } else if (statusFilter === "blocked" && !(st.includes("block") || st.includes("collision") || st.includes("cooldown"))) {
          return false;
        } else if (statusFilter !== "failed" && statusFilter !== "blocked" && st !== statusFilter) {
          return false;
        }
      }
      if (!q) return true;
      const hay = [row.session_id, row.device_id, row.domain, row.ip_address, row.subnet_24, row.status, row.error]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });

    if (!filtered.length) {
      renderEmptyRow(tbody, 8, rows.length ? "No sessions match filter." : "No sessions recorded.");
      return;
    }

    clearChildren(tbody);
    filtered.forEach((row) => {
      const tr = document.createElement("tr");
      tr.appendChild(createCell(createEl("code", "small", row.session_id || "")));
      tr.appendChild(createCell(row.device_id || ""));
      tr.appendChild(createCell(createBadge(String(row.mode || "paper").toUpperCase(), row.mode === "live" ? "danger" : "info")));
      tr.appendChild(createCell(row.domain || ""));
      tr.appendChild(createCell((row.ip_address || "--") + " (" + (row.subnet_24 || "--") + ")", "small tabular-nums"));
      tr.appendChild(createCell(createBadge(String(row.status || "unknown").toUpperCase(), statusVariant(row.status))));
      tr.appendChild(createCell(Number(row.dwell_seconds || 0).toFixed(1), "tabular-nums"));
      tr.appendChild(createCell(formatTs(row.started_at), "small text-body-secondary tabular-nums"));
      tbody.appendChild(tr);
    });
  }

  function renderCgnatTable() {
    const tbody = document.getElementById("p4BodyCgnat");
    if (!tbody) return;
    const rows = Array.isArray(state.payload && state.payload.cgnat_slots) ? state.payload.cgnat_slots : [];
    const q = ((document.getElementById("p4SearchCgnat") || {}).value || "").trim().toLowerCase();
    const activeFilter = (document.getElementById("p4FilterCgnatActive") || {}).value || "all";

    const filtered = rows.filter((row) => {
      if (activeFilter !== "all" && String(Number(row.active || 0)) !== activeFilter) {
        return false;
      }
      if (!q) return true;
      const hay = [row.device_id, row.ip_address, row.subnet_24, row.subnet_20].join(" ").toLowerCase();
      return hay.includes(q);
    });

    if (!filtered.length) {
      renderEmptyRow(tbody, 5, rows.length ? "No CGNAT slots match filter." : "No CGNAT slots recorded.");
      return;
    }

    clearChildren(tbody);
    filtered.forEach((row) => {
      const tr = document.createElement("tr");
      const isActive = Number(row.active || 0) === 1;
      tr.appendChild(createCell(row.device_id || ""));
      tr.appendChild(createCell(row.ip_address || "", "tabular-nums"));
      tr.appendChild(createCell((row.subnet_24 || "--") + " · " + (row.subnet_20 || "--"), "small tabular-nums"));
      tr.appendChild(createCell(createBadge(isActive ? "ACTIVE" : "RELEASED", isActive ? "success" : "secondary")));
      tr.appendChild(createCell(formatTs(row.acquired_at), "small text-body-secondary tabular-nums"));
      tbody.appendChild(tr);
    });
  }

  function renderForecastsTable() {
    const tbody = document.getElementById("p4BodyForecasts");
    if (!tbody) return;
    const rows = Array.isArray(state.payload && state.payload.forecasts) ? state.payload.forecasts : [];
    const q = ((document.getElementById("p4SearchForecasts") || {}).value || "").trim().toLowerCase();
    const methodFilter = ((document.getElementById("p4FilterForecastMethod") || {}).value || "all").toLowerCase();

    const filtered = rows.filter((row) => {
      if (methodFilter !== "all" && String(row.method || "").toLowerCase() !== methodFilter) {
        return false;
      }
      if (!q) return true;
      const hay = [row.id, row.horizon_days, row.method, row.sample_count].join(" ").toLowerCase();
      return hay.includes(q);
    });

    if (!filtered.length) {
      renderEmptyRow(tbody, 5, rows.length ? "No forecasts match filter." : "No forecasts recorded.");
      return;
    }

    clearChildren(tbody);
    filtered.forEach((row) => {
      const tr = document.createElement("tr");
      tr.appendChild(createCell("#" + String(row.id || ""), "tabular-nums"));
      tr.appendChild(createCell(String(row.horizon_days || 0) + "d (" + String(row.sample_count || 0) + " n)", "tabular-nums"));
      tr.appendChild(createCell(createBadge(String(row.method || "unknown"), statusVariant(row.method))));
      tr.appendChild(
        createCell(
          formatUsd(row.p10_revenue, 2) +
            " / " +
            formatUsd(row.p50_revenue, 2) +
            " / " +
            formatUsd(row.p90_revenue, 2),
          "tabular-nums"
        )
      );
      tr.appendChild(createCell(formatUsd(row.p50_ecpm, 3), "tabular-nums"));
      tbody.appendChild(tr);
    });
  }

  function renderCalibrationTable(payload) {
    const section = document.getElementById("p4CalibrationSection");
    const tbody = document.getElementById("p4BodyCalibration");
    const badge = document.getElementById("p4CalibrationCountBadge");
    if (!section || !tbody) return;

    const rows = Array.isArray(payload && payload.calibration_reports) ? payload.calibration_reports : [];
    section.classList.remove("d-none");
    if (badge) badge.textContent = rows.length + " reports";
    if (!rows.length) {
      renderEmptyRow(tbody, 6, "No calibration reports yet \u2014 click Run Calibration Check.");
      return;
    }

    clearChildren(tbody);
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const drift = Boolean(row.a3_drift_detected || row.a5_drift_detected);
      const cov = row.a3_coverage_pct != null ? row.a3_coverage_pct : row.coverage_pct;
      const mae = row.a3_p50_mae != null ? row.a3_p50_mae : row.p50_mae;
      tr.appendChild(createCell("#" + String(row.id || ""), "tabular-nums"));
      tr.appendChild(createCell(createBadge(String(row.status || "ok"), statusVariant(row.status))));
      tr.appendChild(createCell(cov != null ? (Number(cov) * 100).toFixed(1) + "%" : "--", "tabular-nums"));
      tr.appendChild(createCell(mae != null ? Number(mae).toFixed(4) : "--", "tabular-nums"));
      tr.appendChild(createCell(row.a5_mape != null ? (Number(row.a5_mape) * 100).toFixed(1) + "%" : "--", "tabular-nums"));
      tr.appendChild(createCell(createBadge(drift ? "DRIFT ALERT" : "CALIBRATED", drift ? "danger" : "success")));
      tbody.appendChild(tr);
    });
  }

  function renderAll(payload) {
    state.payload = payload;
    renderErrorBanner(payload);
    renderKpis(payload);
    renderCharts(payload);
    renderDevicesTable();
    renderSessionsTable();
    renderCgnatTable();
    renderForecastsTable();
    renderCalibrationTable(payload);
  }

  async function fetchDashboard() {
    if (state.isFetching) return;
    state.isFetching = true;
    try {
      const resp = await fetch("/api/phase4/dashboard", { cache: "no-store" });
      const data = await resp.json();
      renderAll(data);
    } catch (err) {
      renderAll({
        ok: false,
        db_status: "error",
        error: "Failed to reach /api/phase4/dashboard: " + String(err),
        kpis: {},
        charts: {},
        sessions: [],
        cgnat_slots: [],
        forecasts: [],
        farm_devices: [],
        calibration_reports: [],
      });
    } finally {
      state.isFetching = false;
    }
  }

  async function runCalibrationCheck() {
    const btn = document.getElementById("p4BtnRunCalibration");
    if (btn) btn.disabled = true;
    try {
      const resp = await fetch("/api/phase4/calibration/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await resp.json();
      if (resp.ok && data && data.ok) {
        const rep = data.report || {};
        const msg = "Calibration check complete (" + String(rep.status || "ok") + ")";
        if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
          window.AdsterraShell.toast(msg, "success");
        }
      } else {
        const errMsg = (data && data.error) || ("HTTP " + resp.status);
        if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
          window.AdsterraShell.toast("Calibration error: " + errMsg, "error");
        }
      }
    } catch (err) {
      if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
        window.AdsterraShell.toast("Calibration request failed: " + String(err), "error");
      }
    } finally {
      if (btn) btn.disabled = false;
      await fetchDashboard();
    }
  }

  function bindControls() {
    const refreshBtn = document.getElementById("p4BtnRefresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => fetchDashboard());
    }
    const calBtn = document.getElementById("p4BtnRunCalibration");
    if (calBtn) {
      calBtn.addEventListener("click", () => runCalibrationCheck());
    }

    const bindInput = (id, handler) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", handler);
      el.addEventListener("change", handler);
    };

    bindInput("p4SearchDevices", renderDevicesTable);
    bindInput("p4FilterDeviceStatus", renderDevicesTable);
    bindInput("p4SearchSessions", renderSessionsTable);
    bindInput("p4FilterSessionStatus", renderSessionsTable);
    bindInput("p4SearchCgnat", renderCgnatTable);
    bindInput("p4FilterCgnatActive", renderCgnatTable);
    bindInput("p4SearchForecasts", renderForecastsTable);
    bindInput("p4FilterForecastMethod", renderForecastsTable);

    window.addEventListener("crm:view-activated", (ev) => {
      if (ev && ev.detail && ev.detail.view === "phase4-farm") {
        if (state.payload) {
          renderCharts(state.payload);
        }
        fetchDashboard();
      }
    });

    window.addEventListener("crm:theme-changed", () => {
      if (state.payload && isPhase4Visible()) {
        renderCharts(state.payload);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindControls();
    fetchDashboard();
    const root = document.getElementById("view-phase4-farm");
    const intervalMs = Math.max(
      1000,
      Number((root && root.getAttribute("data-refresh-ms")) || 5000) || 5000
    );
    state.pollTimer = setInterval(() => {
      if (isPhase4Visible()) {
        fetchDashboard();
      }
    }, intervalMs);
  });
})();
