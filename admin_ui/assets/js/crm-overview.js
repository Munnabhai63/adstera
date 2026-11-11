/**
 * AdsterraFleet Vuexy CRM Overview Controller — Component U2
 * Wires ApexCharts (KPI Sparklines, CTR Radial Gauge, 4-Tab Analytics),
 * Runner Start/Stop, Active UA Inspector, 10-Domain Governance,
 * Activity Timeline, and Live Console Logs to existing HTTP APIs.
 */
(function () {
  "use strict";

  const TAB_KEYS = ["hourly", "forecast", "domains", "diurnal"];
  const charts = {};
  let activeTab = "hourly";
  let timelineFilter = "all";
  let logAutoScroll = true;
  let lastRawLogs = [];

  const cache = {
    status: null,
    charts: null,
    autopublish: null,
    config: null,
  };

  function toast(msg, type = "success") {
    if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
      window.AdsterraShell.toast(msg, type);
    } else {
      console.log(`[U2:${type}]`, msg);
    }
  }

  function esc(val) {
    return String(val == null ? "" : val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function cssVar(name, fallback) {
    const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return val || fallback;
  }

  function getPalette() {
    const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
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
      trackBg: isDark ? "#3c415e" : "#efeff5",
      cardBg: cssVar("--bs-paper-bg", isDark ? "#2f3349" : "#ffffff"),
    };
  }

  function upsertChart(key, selector, options) {
    if (typeof ApexCharts === "undefined") return;
    const el = document.querySelector(selector);
    if (!el || el.offsetParent === null) return;

    if (charts[key]) {
      try {
        charts[key].updateOptions(options, false, false);
        return;
      } catch (_) {
        try {
          charts[key].destroy();
        } catch (__) {}
        delete charts[key];
      }
    }
    const inst = new ApexCharts(el, options);
    inst.render();
    charts[key] = inst;
  }

  function renderKpiSparklines() {
    const p = getPalette();
    const hourly = cache.charts?.hourly || [];
    const sessSeries = hourly.length ? hourly.map((h) => Number(h.sessions || 0)) : [0, 0, 0, 0, 0, 0, 0];
    const sessCats = hourly.length ? hourly.map((h) => h.hour) : ["00h", "04h", "08h", "12h", "16h", "20h", "23h"];

    upsertChart("sparkSessions", "#u2SparkSessions", {
      chart: { height: 76, type: "bar", toolbar: { show: false }, sparkline: { enabled: true } },
      plotOptions: {
        bar: {
          columnWidth: "52%",
          borderRadius: 4,
          colors: { backgroundBarColors: sessSeries.map(() => p.trackBg), backgroundBarRadius: 4 },
        },
      },
      colors: [p.primary],
      series: [{ name: "Sessions", data: sessSeries }],
      xaxis: { categories: sessCats },
      tooltip: { theme: p.isDark ? "dark" : "light", y: { formatter: (v) => `${v} sessions` } },
    });

    const ctrVal = Number(cache.status?.ctr || 0) * 100;
    const safePct = Math.min(100, Math.round((ctrVal / 5.0) * 100));
    const gaugeColor = ctrVal > 5.0 ? p.danger : ctrVal > 3.8 ? p.warning : p.success;

    upsertChart("ctrGauge", "#u2CtrGauge", {
      chart: { height: 108, type: "radialBar", sparkline: { enabled: true } },
      series: [safePct],
      colors: [gaugeColor],
      plotOptions: {
        radialBar: {
          startAngle: -130,
          endAngle: 130,
          hollow: { size: "60%" },
          track: { background: p.trackBg, strokeWidth: "100%" },
          dataLabels: {
            name: { show: false },
            value: {
              offsetY: 5,
              fontSize: "13px",
              fontWeight: 700,
              color: p.heading,
              formatter: () => `${ctrVal.toFixed(1)}%`,
            },
          },
        },
      },
      stroke: { lineCap: "round" },
    });

    const f7 = cache.charts?.forecast_7d || [];
    const revSeries = f7.length ? f7.map((d) => Number(d.projected_usd || 0)) : [0, 0, 0, 0, 0, 0, 0];
    const revCats = f7.length ? f7.map((d) => String(d.day_name || "").slice(0, 3)) : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    upsertChart("sparkRevenue", "#u2SparkRevenue", {
      chart: { height: 76, type: "area", toolbar: { show: false }, sparkline: { enabled: true } },
      colors: [p.success],
      stroke: { width: 2, curve: "smooth" },
      fill: {
        type: "gradient",
        gradient: { shadeIntensity: 1, opacityFrom: 0.42, opacityTo: 0.05, stops: [0, 100] },
      },
      series: [{ name: "Projected USD", data: revSeries }],
      xaxis: { categories: revCats },
      tooltip: { theme: p.isDark ? "dark" : "light", y: { formatter: (v) => `$${Number(v).toFixed(2)}` } },
    });
  }

  function renderActiveAnalyticsChart() {
    const p = getPalette();

    if (activeTab === "hourly") {
      const hourly = cache.charts?.hourly || [];
      const cats = hourly.length ? hourly.map((h) => h.hour) : ["00:00"];
      const imps = hourly.length ? hourly.map((h) => Number(h.impressions || 0)) : [0];
      const sess = hourly.length ? hourly.map((h) => Number(h.sessions || 0)) : [0];

      upsertChart("tabHourly", "#u2ChartHourly", {
        chart: { height: 265, type: "bar", toolbar: { show: false } },
        colors: [p.primary, p.info],
        plotOptions: { bar: { columnWidth: "46%", borderRadius: 5 } },
        dataLabels: { enabled: false },
        grid: { borderColor: p.border, strokeDashArray: 4, padding: { bottom: 6 } },
        series: [
          { name: "Impressions", data: imps },
          { name: "Sessions", data: sess },
        ],
        xaxis: { categories: cats, labels: { style: { colors: p.textMuted, fontSize: "12px" } } },
        yaxis: { labels: { style: { colors: p.textMuted, fontSize: "12px" } } },
        legend: { position: "top", labels: { colors: p.heading } },
        tooltip: { theme: p.isDark ? "dark" : "light" },
      });

      const sumEl = document.getElementById("u2HourlySummary");
      if (sumEl) {
        if (!hourly.length) {
          sumEl.textContent = "No sessions recorded today yet — hourly impression pacing updates automatically.";
        } else {
          const totI = imps.reduce((a, b) => a + b, 0);
          const totS = sess.reduce((a, b) => a + b, 0);
          sumEl.textContent = `Today across ${hourly.length} active hour slots: ${totS} sessions generating ${totI} verified ad impressions.`;
        }
      }
      return;
    }

    if (activeTab === "forecast") {
      const f7 = cache.charts?.forecast_7d || [];
      const cats = f7.map((f) => String(f.day_name || "").slice(0, 3) || f.date || "");
      const proj = f7.map((f) => Number(f.projected_usd || 0));
      const hi = f7.map((f) => Number(f.confidence_high || 0));

      upsertChart("tabForecast", "#u2ChartForecast", {
        chart: { height: 215, type: "bar", toolbar: { show: false } },
        colors: [p.success, p.info],
        plotOptions: { bar: { columnWidth: "48%", borderRadius: 5 } },
        dataLabels: { enabled: false },
        grid: { borderColor: p.border, strokeDashArray: 4 },
        series: [
          { name: "Projected ($)", data: proj },
          { name: "Upper Band ($)", data: hi },
        ],
        xaxis: { categories: cats.length ? cats : ["No Data"], labels: { style: { colors: p.textMuted } } },
        yaxis: {
          labels: {
            style: { colors: p.textMuted },
            formatter: (v) => `$${Number(v).toFixed(2)}`,
          },
        },
        legend: { position: "top", labels: { colors: p.heading } },
        tooltip: { theme: p.isDark ? "dark" : "light", y: { formatter: (v) => `$${Number(v).toFixed(2)}` } },
      });

      const tiles = document.getElementById("u2ForecastTiles");
      if (tiles) {
        tiles.innerHTML = f7.length
          ? f7
              .map(
                (f) => `<div class="col-6 col-md-4 col-lg"><div class="border rounded p-2 text-center bg-body-tertiary">
                    <div class="small text-body-secondary">${esc(String(f.day_name || "").slice(0, 3))}</div>
                    <div class="fw-bold text-success tabular-nums">$${Number(f.projected_usd || 0).toFixed(2)}</div>
                    <div class="text-body-secondary tabular-nums" style="font-size: 0.7rem;">$${Number(f.confidence_low || 0).toFixed(1)}-$${Number(f.confidence_high || 0).toFixed(1)}</div>
                  </div></div>`
              )
              .join("")
          : '<div class="col-12 small text-body-secondary">Forecast populates as daily sessions accumulate.</div>';
      }
      return;
    }

    if (activeTab === "domains") {
      const doms = cache.charts?.domains?.length
        ? cache.charts.domains
        : (cache.status?.domains || []).map((d) => ({
            domain: d.domain,
            impressions: d.impressions || 0,
            sessions: d.sessions || 0,
          }));
      const top = doms.slice(0, 10);

      upsertChart("tabDomains", "#u2ChartDomains", {
        chart: { height: 260, type: "bar", toolbar: { show: false } },
        colors: [p.info, p.primary],
        plotOptions: { bar: { horizontal: true, barHeight: "58%", borderRadius: 4 } },
        dataLabels: { enabled: false },
        grid: { borderColor: p.border, strokeDashArray: 4 },
        series: [
          { name: "Impressions", data: top.map((d) => Number(d.impressions || 0)) },
          { name: "Sessions", data: top.map((d) => Number(d.sessions || 0)) },
        ],
        xaxis: { categories: top.map((d) => d.domain), labels: { style: { colors: p.textMuted } } },
        yaxis: { labels: { style: { colors: p.textMuted, fontSize: "11px" } } },
        legend: { position: "top", labels: { colors: p.heading } },
        tooltip: { theme: p.isDark ? "dark" : "light" },
      });
      return;
    }

    if (activeTab === "diurnal") {
      const sched = cache.config?.scheduler || {};
      const baseRate = Number(sched.sessions_per_hour || 150);
      const weights = Array.isArray(sched.diurnal) && sched.diurnal.length === 24
        ? sched.diurnal
        : [0.25, 0.18, 0.14, 0.12, 0.14, 0.28, 0.52, 0.78, 0.95, 1.0, 0.92, 0.86, 0.82, 0.85, 0.9, 0.94, 0.98, 1.0, 0.95, 0.84, 0.68, 0.52, 0.4, 0.32];
      const targets = weights.map((w) => Math.max(1, Math.round(baseRate * Number(w || 0))));
      const cats = weights.map((_, i) => `${String(i).padStart(2, "0")}h`);
      const nowH = new Date().getHours();

      upsertChart("tabDiurnal", "#u2ChartDiurnal", {
        chart: { height: 265, type: "area", toolbar: { show: false } },
        colors: [p.warning],
        stroke: { width: 2.5, curve: "smooth" },
        fill: { type: "gradient", gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.05 } },
        dataLabels: { enabled: false },
        grid: { borderColor: p.border, strokeDashArray: 4, padding: { bottom: 8 } },
        series: [{ name: "Hourly Session Target", data: targets }],
        xaxis: { categories: cats, labels: { style: { colors: p.textMuted, fontSize: "11px" } } },
        yaxis: { labels: { style: { colors: p.textMuted } } },
        annotations: {
          xaxis: [
            {
              x: cats[nowH],
              borderColor: p.primary,
              label: { text: `Now (${cats[nowH]})`, style: { color: "#fff", background: p.primary } },
            },
          ],
        },
        tooltip: { theme: p.isDark ? "dark" : "light" },
      });

      const dSum = document.getElementById("u2DiurnalSummary");
      if (dSum) {
        dSum.textContent = `Current hour (${cats[nowH]}) shaped pace: ~${targets[nowH]} sessions/hr from base rate ${baseRate}/hr (Daily Cap: ${sched.daily_cap || 2000}).`;
      }
    }
  }

  function renderAllCharts() {
    renderKpiSparklines();
    renderActiveAnalyticsChart();
  }

  function selectAnalyticsTab(tabKey) {
    if (!TAB_KEYS.includes(tabKey)) return;
    activeTab = tabKey;

    const panelMap = {
      hourly: "u2PanelHourly",
      forecast: "u2PanelForecast",
      domains: "u2PanelDomains",
      diurnal: "u2PanelDiurnal",
    };

    document.querySelectorAll(".u2-tab-btn").forEach((btn) => {
      const isMatch = btn.getAttribute("data-u2-tab") === tabKey;
      btn.setAttribute("aria-selected", String(isMatch));
      if (isMatch) {
        btn.removeAttribute("tabindex");
        btn.classList.add("active");
      } else {
        btn.setAttribute("tabindex", "-1");
        btn.classList.remove("active");
      }
    });

    Object.entries(panelMap).forEach(([k, id]) => {
      const panel = document.getElementById(id);
      if (!panel) return;
      if (k === tabKey) {
        panel.removeAttribute("hidden");
        panel.setAttribute("tabindex", "0");
      } else {
        panel.setAttribute("hidden", "until-found");
        panel.removeAttribute("tabindex");
      }
    });

    requestAnimationFrame(() => renderActiveAnalyticsChart());
  }

  function bindTabsKeyboardAndMatch() {
    const tablist = document.getElementById("u2AnalyticsTablist");
    if (!tablist) return;

    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    tabs.forEach((btn, idx) => {
      btn.addEventListener("click", () => {
        selectAnalyticsTab(btn.getAttribute("data-u2-tab"));
      });

      btn.addEventListener("keydown", (ev) => {
        let nextIdx = idx;
        if (ev.key === "ArrowRight") nextIdx = (idx + 1) % tabs.length;
        else if (ev.key === "ArrowLeft") nextIdx = (idx - 1 + tabs.length) % tabs.length;
        else if (ev.key === "Home") nextIdx = 0;
        else if (ev.key === "End") nextIdx = tabs.length - 1;
        else return;

        ev.preventDefault();
        tabs[nextIdx].focus();
        selectAnalyticsTab(tabs[nextIdx].getAttribute("data-u2-tab"));
      });
    });

    const panelToTab = {
      u2PanelHourly: "hourly",
      u2PanelForecast: "forecast",
      u2PanelDomains: "domains",
      u2PanelDiurnal: "diurnal",
    };
    Object.entries(panelToTab).forEach(([panelId, key]) => {
      const pEl = document.getElementById(panelId);
      if (pEl) {
        pEl.addEventListener("beforematch", () => selectAnalyticsTab(key));
      }
    });
  }

  function applyStatusToDom(data) {
    if (!data) return;
    const isRunning = Boolean(data.is_running);
    const metrics = data.metrics || {};

    const elSess = document.getElementById("u2KpiSessionsToday");
    const elDiurnal = document.getElementById("u2KpiDiurnalTarget");
    const elImpsClicks = document.getElementById("u2KpiImpsClicks");
    const elCtrText = document.getElementById("u2KpiCtrText");
    const elCtrBadge = document.getElementById("u2KpiCtrBadge");
    const elRev = document.getElementById("u2KpiRevenue");
    const elCpm = document.getElementById("u2KpiCpm");
    const elDomsCount = document.getElementById("u2KpiDomainsCount");
    const elNetSummary = document.getElementById("u2KpiNetSummary");
    const elProxiesPill = document.getElementById("u2KpiProxiesPill");

    if (elSess) elSess.textContent = String(data.today ?? 0);
    if (elDiurnal) elDiurnal.textContent = `Target: ${data.hourly_target ?? 150}/hr`;
    if (elImpsClicks) elImpsClicks.textContent = `${metrics.impressions ?? 0} Imps / ${metrics.clicks ?? 0} Clicks`;

    const ctrPct = Number(data.ctr || 0) * 100;
    if (elCtrText) elCtrText.textContent = `${ctrPct.toFixed(1)}%`;
    if (elCtrBadge) {
      elCtrBadge.textContent = ctrPct > 5.0 ? "HIGH CTR ALERT" : "Safe <= 5%";
      elCtrBadge.className = `badge rounded-pill ${ctrPct > 5.0 ? "bg-label-danger" : "bg-label-success"}`;
    }

    if (elRev) elRev.textContent = `$${Number(metrics.revenue || 0).toFixed(2)}`;
    if (elCpm) elCpm.textContent = `eCPM: $${Number(metrics.cpm || 0).toFixed(2)}`;

    const domList = Array.isArray(data.domains) ? data.domains : [];
    if (elDomsCount) elDomsCount.textContent = `${domList.length} / 10`;

    const isMobile = data.network_mode === "mobile_tether";
    if (elNetSummary) {
      elNetSummary.textContent = isMobile
        ? `Mobile ADB (${data.mobile_info?.carrier || "4G/5G"})`
        : "Proxy Pool Mode";
    }
    if (elProxiesPill) {
      elProxiesPill.textContent = isMobile ? "ADB LIVE" : `${data.proxies_count ?? 0} Proxies`;
    }

    const badgeRun = document.getElementById("u2RunnerBadge");
    const badgeMode = document.getElementById("u2RunnerModeBadge");
    const btnStart = document.getElementById("u2BtnStart");
    const btnStop = document.getElementById("u2BtnStop");
    const metaPid = document.getElementById("u2MetaPid");
    const metaTarget = document.getElementById("u2MetaHourlyTarget");
    const metaUa = document.getElementById("u2MetaUaPool");
    const metaProx = document.getElementById("u2MetaProxies");

    if (badgeRun) {
      badgeRun.textContent = isRunning ? `RUNNING (${data.pid})` : "STOPPED";
      badgeRun.className = `badge ${isRunning ? "bg-label-success" : "bg-label-secondary"}`;
    }
    if (badgeMode) {
      badgeMode.textContent = isMobile ? "MOBILE ADB IP" : "PROXY POOL";
      badgeMode.className = `badge ${isMobile ? "bg-label-info" : "bg-label-primary"}`;
    }
    if (btnStart) btnStart.disabled = isRunning;
    if (btnStop) btnStop.disabled = !isRunning;
    if (metaPid) metaPid.textContent = isRunning && data.pid ? String(data.pid) : "\u2014";
    if (metaTarget) metaTarget.textContent = `${data.hourly_target ?? 150}`;
    if (metaUa) metaUa.textContent = Number(data.ua_stats?.total || 27103).toLocaleString();
    if (metaProx) metaProx.textContent = String(data.proxies_count ?? 0);

    const ua = data.active_ua || {};
    const uaLiveBadge = document.getElementById("u2UaLiveBadge");
    const uaDevBadge = document.getElementById("u2UaDeviceBadge");
    const uaText = document.getElementById("u2UaText");
    const uaIp = document.getElementById("u2UaIp");
    const uaTime = document.getElementById("u2UaTime");
    const uaTarget = document.getElementById("u2UaTarget");

    if (uaLiveBadge) {
      if (ua.active) {
        uaLiveBadge.textContent = "CONNECTED";
        uaLiveBadge.className = "badge bg-label-success";
      } else if (isRunning) {
        uaLiveBadge.textContent = "ROTATING";
        uaLiveBadge.className = "badge bg-label-warning";
      } else {
        uaLiveBadge.textContent = "IDLE";
        uaLiveBadge.className = "badge bg-label-secondary";
      }
    }
    if (uaDevBadge) uaDevBadge.textContent = ua.device_label || "Ready";
    if (uaText) uaText.textContent = ua.user_agent || "Ready \u2014 Fresh fingerprint selects on launch";
    if (uaIp) uaIp.textContent = ua.proxy_id || "\u2014";
    if (uaTime) uaTime.textContent = ua.updated_at || "\u2014";
    if (uaTarget) uaTarget.textContent = ua.target_url || "\u2014";

    renderDomainsTable(domList, data.circuit_breaker || {});
    renderBreakdownCard(domList, data.ua_stats || {});
    renderTimeline(data.recent_sessions || []);
    renderConsole(data.logs || []);
  }

  function renderDomainsTable(domList, cb) {
    const badge = document.getElementById("u2BreakerBadge");
    const tbody = document.getElementById("u2DomainsTbody");
    const pausedCount = Array.isArray(cb.paused_domains) ? cb.paused_domains.length : 0;

    if (badge) {
      if (pausedCount > 0 || cb.global_pause) {
        badge.textContent = cb.global_pause && !pausedCount ? "Global Pause Active" : `${pausedCount} Paused`;
        badge.className = "badge bg-label-danger";
      } else {
        badge.textContent = "0 Breakers Tripped";
        badge.className = "badge bg-label-success";
      }
    }

    if (!tbody) return;
    if (!domList.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary py-5">No domain telemetry recorded yet</td></tr>';
      return;
    }

    tbody.innerHTML = domList
      .map((d) => {
        const ctrPct = Number(d.ctr || 0);
        const headroomPct = Math.min(100, Math.round((ctrPct / 5.0) * 100));
        let pillCls = "bg-label-success";
        let barCls = "bg-success";
        if (d.status === "GUARD_ACTIVE") {
          pillCls = "bg-label-warning";
          barCls = "bg-warning";
        } else if (d.status === "PAUSED" || d.status === "CIRCUIT_PAUSED") {
          pillCls = "bg-label-danger";
          barCls = "bg-danger";
        }
        const reasonAttr = d.breaker_reason ? ` title="${esc(d.breaker_reason)}"` : "";
        return `<tr>
          <th scope="row" class="fw-semibold">${esc(d.domain)}</th>
          <td data-label="Sessions" class="tabular-nums">${Number(d.sessions || 0)}</td>
          <td data-label="Imps / Clicks" class="tabular-nums"><span>${Number(d.impressions || 0)} / <strong>${Number(d.clicks || 0)}</strong></span></td>
          <td data-label="CTR Headroom">
            <div class="d-flex align-items-center gap-2" style="min-width: 110px;">
              <div class="progress flex-grow-1" style="height: 6px;">
                <div class="progress-bar ${barCls}" style="width: ${headroomPct}%"></div>
              </div>
              <span class="small tabular-nums">${ctrPct.toFixed(1)}%</span>
            </div>
          </td>
          <td data-label="Status"><span${reasonAttr} class="badge ${pillCls}">${esc(d.status || "ACTIVE")}</span></td>
          <td data-label="CPM" class="tabular-nums">$${Number(d.cpm || 2.5).toFixed(2)}</td>
          <td data-label="Revenue" class="text-end fw-semibold text-primary tabular-nums">$${Number(d.estimated_revenue || 0).toFixed(2)}</td>
        </tr>`;
      })
      .join("");
  }

  function renderBreakdownCard(domList, uaStats) {
    const mixEl = document.getElementById("u2UaMixList");
    const subEl = document.getElementById("u2TotalUaSubtitle");
    const topEl = document.getElementById("u2TopDomainsList");

    const total = Number(uaStats.total || 27103);
    const desk = Number(uaStats.desktop_count || 8989);
    const mob = Number(uaStats.mobile_count || 18114);
    const deskShare = Math.round((desk / Math.max(1, total)) * 100);
    const mobShare = Math.max(0, 100 - deskShare);

    if (subEl) subEl.textContent = `${total.toLocaleString()} UAs indexed (useragent.in)`;

    if (mixEl) {
      mixEl.innerHTML = `
        <li>
          <div class="d-flex justify-content-between small mb-1">
            <span><i class="icon-base ti tabler-device-desktop me-1 text-primary" aria-hidden="true"></i>Desktop Fingerprint Pool</span>
            <strong class="tabular-nums">${desk.toLocaleString()} (${deskShare}%)</strong>
          </div>
          <div class="progress" style="height: 7px;"><div class="progress-bar bg-primary" style="width: ${deskShare}%"></div></div>
        </li>
        <li>
          <div class="d-flex justify-content-between small mb-1">
            <span><i class="icon-base ti tabler-device-mobile me-1 text-info" aria-hidden="true"></i>Mobile / Touch Pool</span>
            <strong class="tabular-nums">${mob.toLocaleString()} (${mobShare}%)</strong>
          </div>
          <div class="progress" style="height: 7px;"><div class="progress-bar bg-info" style="width: ${mobShare}%"></div></div>
        </li>`;
    }

    if (topEl) {
      const sorted = [...domList].sort((a, b) => Number(b.impressions || 0) - Number(a.impressions || 0)).slice(0, 4);
      const peak = Math.max(1, ...sorted.map((d) => Number(d.impressions || 0)));
      topEl.innerHTML = sorted.length
        ? sorted
            .map((d) => {
              const imps = Number(d.impressions || 0);
              const pct = Math.min(100, Math.round((imps / peak) * 100));
              return `<li>
                <div class="d-flex justify-content-between small mb-1">
                  <span class="fw-medium">${esc(d.domain)}</span>
                  <span class="text-body-secondary tabular-nums">${imps} imps &middot; ${Number(d.sessions || 0)} sess</span>
                </div>
                <div class="progress" style="height: 6px;"><div class="progress-bar bg-success" style="width: ${pct}%"></div></div>
              </li>`;
            })
            .join("")
        : '<li class="small text-body-secondary">Waiting for domain impressions...</li>';
    }
  }

  function renderTimeline(sessions) {
    const ul = document.getElementById("u2ActivityTimeline");
    const countEl = document.getElementById("u2TimelineCount");
    if (!ul) return;

    const filtered = (sessions || []).filter((s) => {
      if (timelineFilter === "clicks") return Number(s.ad_clicks || 0) > 0;
      if (timelineFilter === "issues") return s.status !== "ok" || Boolean(s.error_reason);
      return true;
    });

    if (countEl) countEl.textContent = `Showing ${filtered.length} of ${(sessions || []).length} recent sessions`;

    if (!filtered.length) {
      ul.innerHTML = `<li class="timeline-item timeline-item-transparent">
        <span class="timeline-point timeline-point-secondary"></span>
        <div class="timeline-event">
          <div class="timeline-header mb-1"><h6 class="mb-0">No matching sessions</h6></div>
          <p class="mb-0 text-body-secondary small">Adjust the filter or run sessions to see live activity here.</p>
        </div>
      </li>`;
      return;
    }

    ul.innerHTML = filtered
      .slice(0, 10)
      .map((s) => {
        const hasClick = Number(s.ad_clicks || 0) > 0;
        const isErr = s.status !== "ok";
        const dotCls = isErr ? "timeline-point-danger" : hasClick ? "timeline-point-success" : "timeline-point-primary";
        const badgeCls = isErr ? "bg-label-danger" : hasClick ? "bg-label-success" : "bg-label-info";
        const refText = s.referrer ? esc(String(s.referrer).replace(/^https?:\/\//, "").slice(0, 40)) : "direct visit";
        const note = s.error_reason ? `<div class="small text-danger mt-1">${esc(s.error_reason)}</div>` : "";
        return `<li class="timeline-item timeline-item-transparent">
          <span class="timeline-point ${dotCls}"></span>
          <div class="timeline-event pb-1">
            <div class="timeline-header mb-1">
              <h6 class="mb-0">${esc(s.domain || "loanraaj.com")} <span class="badge ${badgeCls} ms-1">${esc(s.status || "ok")}</span></h6>
              <small class="text-body-secondary tabular-nums">${esc(s.ts || "")}</small>
            </div>
            <p class="mb-0 small text-body-secondary">
              IP <code>${esc(s.proxy_id || "-")}</code> &bull; Dwell <strong>${Number(s.dwell || 0)}s</strong> &bull; ${Number(s.pages || 1)}p &bull; ${Number(s.impressions || 0)} imps / <strong>${Number(s.ad_clicks || 0)} clicks</strong> &bull; ${refText}
            </p>
            ${note}
          </div>
        </li>`;
      })
      .join("");
  }

  function renderConsole(logs) {
    lastRawLogs = Array.isArray(logs) ? logs : [];
    const box = document.getElementById("u2ConsoleBox");
    if (!box) return;
    if (!lastRawLogs.length) {
      box.innerHTML = '<div class="u2-console-line text-secondary">Runner idle &mdash; waiting for stdout logs...</div>';
      return;
    }
    box.innerHTML = lastRawLogs.map((l) => `<div class="u2-console-line">${esc(l)}</div>`).join("");
    if (logAutoScroll) {
      box.scrollTop = box.scrollHeight;
    }
  }

  async function fetchStatusAndAutopublish() {
    try {
      const [rSt, rAuto] = await Promise.all([
        fetch("/api/status", { cache: "no-store" }),
        fetch("/api/autopublish/stats?domain=tazaloan", { cache: "no-store" }),
      ]);
      if (rSt.ok) {
        cache.status = await rSt.json();
        applyStatusToDom(cache.status);
      }
      if (rAuto.ok) {
        cache.autopublish = await rAuto.json();
        const pendingByDom = cache.autopublish?.pending_by_domain || {};
        const pendingTotal = Object.values(pendingByDom).reduce((a, b) => a + (Number(b) || 0), 0);
        const pendEl = document.getElementById("u2KpiPendingTopics");
        if (pendEl) pendEl.textContent = String(pendingTotal);
      }
    } catch (err) {
      console.debug("U2 status poll error:", err);
    }
  }

  async function refreshCharts(manual = false) {
    try {
      const [rCh, rCfg] = await Promise.all([
        fetch("/api/analytics/charts", { cache: "no-store" }),
        cache.config ? Promise.resolve(null) : fetch("/api/config", { cache: "no-store" }),
      ]);
      if (rCh.ok) {
        cache.charts = await rCh.json();
        const mUsd = `$${Number(cache.charts.monthly_estimate_usd || 0).toFixed(2)}`;
        const b1 = document.getElementById("u2MonthlyBadge");
        const b2 = document.getElementById("u2KpiMonthlyEst");
        if (b1) b1.textContent = `Projected 30d: ${mUsd}`;
        if (b2) b2.textContent = `30d: ${mUsd}`;
      }
      if (rCfg && rCfg.ok) {
        const cfgPayload = await rCfg.json();
        cache.config = cfgPayload.config || {};
      }
      renderAllCharts();
      if (manual) toast("Analytics charts refreshed");
    } catch (err) {
      console.debug("U2 charts refresh error:", err);
      if (manual) toast("Chart refresh failed", "error");
    }
  }

  async function startRunner() {
    const btn = document.getElementById("u2BtnStart");
    if (btn) btn.disabled = true;
    try {
      const cfg = cache.config || {};
      const st = cache.status || {};
      const mode = st.network_mode || cfg.network?.mode || "proxy";
      if (mode === "proxy" && Number(st.proxies_count || 0) === 0) {
        toast("Add proxies in Network panel or switch to Mobile ADB before starting.", "error");
        return;
      }
      if (mode === "mobile_tether") {
        const adbRes = await fetch("/api/adb/status", { cache: "no-store" });
        const adb = adbRes.ok ? await adbRes.json() : {};
        if (!adb.ok || !Array.isArray(adb.devices) || !adb.devices.length) {
          toast("No USB ADB phone detected for Mobile Tethering mode.", "error");
          return;
        }
      }
      const res = await fetch("/api/start", { method: "POST" });
      const data = await res.json();
      toast(data.msg || (data.ok ? "Runner started" : "Unable to start"), data.ok ? "success" : "error");
      await fetchStatusAndAutopublish();
    } catch (err) {
      toast(`Start error: ${err}`, "error");
    } finally {
      if (btn) btn.disabled = Boolean(cache.status?.is_running);
    }
  }

  async function stopRunner() {
    try {
      const res = await fetch("/api/stop", { method: "POST" });
      const data = await res.json();
      toast(data.msg || "Stop signal sent", data.ok ? "success" : "error");
      await fetchStatusAndAutopublish();
    } catch (err) {
      toast(`Stop error: ${err}`, "error");
    }
  }

  async function resetCircuitBreakers() {
    try {
      const res = await fetch("/api/circuit-breaker/reset", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        toast("Circuit breakers and active UA lock reset cleanly");
        await fetchStatusAndAutopublish();
      } else {
        toast(data.error || "Breaker reset failed", "error");
      }
    } catch (err) {
      toast(`Breaker reset error: ${err}`, "error");
    }
  }

  async function syncUserAgents() {
    const btn = document.getElementById("u2BtnSyncUa");
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/useragents/sync", { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        toast(`Synced ${Number(data.total || 0).toLocaleString()} User-Agents`);
        await fetchStatusAndAutopublish();
      } else {
        toast(data.error || "UA sync failed", "error");
      }
    } catch (err) {
      toast(`UA sync error: ${err}`, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function setTimelineFilter(next) {
    timelineFilter = next;
    document.querySelectorAll("[data-u2-tl-filter]").forEach((btn) => {
      const match = btn.getAttribute("data-u2-tl-filter") === next;
      btn.classList.toggle("active", match);
      btn.classList.toggle("btn-label-primary", match);
      btn.classList.toggle("btn-label-secondary", !match);
    });
    renderTimeline(cache.status?.recent_sessions || []);
  }

  function toggleLogScroll() {
    logAutoScroll = !logAutoScroll;
    const btn = document.getElementById("u2BtnPauseScroll");
    if (btn) {
      btn.textContent = `Auto-Scroll: ${logAutoScroll ? "ON" : "PAUSED"}`;
      btn.setAttribute("aria-pressed", String(!logAutoScroll));
    }
  }

  async function copyLogs() {
    const txt = lastRawLogs.join("\n") || "No runner logs";
    try {
      await navigator.clipboard.writeText(txt);
      toast("Console logs copied to clipboard");
    } catch (_) {
      toast("Clipboard permission unavailable", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    if (!document.getElementById("view-overview")) return;
    bindTabsKeyboardAndMatch();
    await Promise.all([fetchStatusAndAutopublish(), refreshCharts(false)]);
    renderAllCharts();

    setInterval(fetchStatusAndAutopublish, 3000);
    setInterval(() => refreshCharts(false), 12000);

    window.addEventListener("crm:theme-changed", () => {
      setTimeout(renderAllCharts, 60);
    });

    window.addEventListener("crm:view-activated", (ev) => {
      if (ev.detail?.view === "overview") {
        setTimeout(renderAllCharts, 80);
      }
    });
  });

  window.AdsterraOverview = {
    refreshAll: () => Promise.all([fetchStatusAndAutopublish(), refreshCharts(false)]),
    refreshCharts,
    selectTab: selectAnalyticsTab,
    startRunner,
    stopRunner,
    resetCircuitBreakers,
    syncUserAgents,
    setTimelineFilter,
    toggleLogScroll,
    copyLogs,
  };
})();
