/**
 * AdsterraFleet Vuexy CRM Controller — Component U5 (Network, Proxies, ADB, Config, GSC, Push & Telegram)
 * Enforces XSS-safe DOM construction, dirty-form preservation, post-interaction validation,
 * accessible keyboard tabs, native switch/accordion progressive enhancement, and copy commands.
 */
(function () {
  "use strict";

  const POLL_MS = 20000;
  let pollTimer = null;
  let copyTimer = null;
  let copyCount = 0;
  let formHydratedOnce = false;
  const dirtyControls = new Set();

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clearEl(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function isViewActive(id) {
    return Boolean(document.getElementById(id)?.classList.contains("active"));
  }

  function toast(msg, type = "success") {
    if (window.AdsterraShell?.toast) {
      window.AdsterraShell.toast(msg, type);
    }
  }

  function setStatusAlert(alertId, msg, level = "info") {
    const box = document.getElementById(alertId);
    if (!box) return;
    box.className = `alert alert-${level} py-2 px-3 mb-3 small`;
    box.textContent = msg;
    box.classList.remove("d-none");
  }

  function formatInt(val) {
    const n = Number(val);
    return Number.isFinite(n) ? n.toLocaleString() : "0";
  }

  function safeTimeLabel(ts) {
    if (!ts) return "--";
    const s = String(ts);
    return s.length > 16 ? s.slice(11, 19) || s.slice(0, 19) : s;
  }

  function canOverwriteInput(inputEl) {
    if (!inputEl) return false;
    if (!formHydratedOnce) return true;
    if (document.activeElement === inputEl) return false;
    return !dirtyControls.has(inputEl.id);
  }

  function trackDirty(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.querySelectorAll("input, textarea, select").forEach((ctrl) => {
      const mark = () => {
        if (ctrl.id) dirtyControls.add(ctrl.id);
      };
      ctrl.addEventListener("input", mark);
      ctrl.addEventListener("change", mark);
    });
  }

  function clearDirtyForForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.querySelectorAll("input, textarea, select").forEach((ctrl) => {
      if (ctrl.id) dirtyControls.delete(ctrl.id);
    });
  }

  /* Post-interaction accessible validation matching modern-web-guidance */
  function validateField(ctrl) {
    if (!ctrl || ctrl.disabled) return true;
    let valid = ctrl.checkValidity();
    if (valid && ctrl.id === "u5TargetUrls") {
      const lines = ctrl.value
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const allHttp = lines.length > 0 && lines.every((u) => /^https?:\/\//i.test(u));
      if (!allHttp) {
        valid = false;
      }
    }
    ctrl.setAttribute("aria-invalid", valid ? "false" : "true");
    ctrl.classList.toggle("user-invalid-fallback", !valid);
    return valid;
  }

  function bindValidation(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.querySelectorAll("input, textarea, select").forEach((ctrl) => {
      let touched = false;
      ctrl.addEventListener("blur", () => {
        touched = true;
        validateField(ctrl);
      });
      ctrl.addEventListener("input", () => {
        if (touched || ctrl.classList.contains("user-invalid-fallback")) {
          validateField(ctrl);
        }
      });
      ctrl.addEventListener("change", () => {
        if (touched || ctrl.classList.contains("user-invalid-fallback")) {
          validateField(ctrl);
        }
      });
    });
  }

  function validateFormOnSubmit(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    let firstInvalid = null;
    form.querySelectorAll("input, textarea, select").forEach((ctrl) => {
      if (!validateField(ctrl) && !firstInvalid) {
        firstInvalid = ctrl;
      }
    });
    if (firstInvalid) {
      firstInvalid.focus();
      return false;
    }
    return true;
  }

  /* Accessible Toolbar arrow-key fallback ONLY when native focusgroup is unsupported */
  function bindToolbarFallbacks() {
    if ("focusGroup" in HTMLElement.prototype) return;
    document.querySelectorAll('#view-network [role="toolbar"], #view-growth [role="toolbar"]').forEach((bar) => {
      const getItems = () =>
        Array.from(bar.querySelectorAll("button, a[href], input, select")).filter(
          (item) => !item.disabled && item.offsetParent !== null
        );
      bar.addEventListener("keydown", (ev) => {
        const items = getItems();
        if (!items.length) return;
        const idx = items.indexOf(document.activeElement);
        if (idx === -1) return;
        let nextIdx = idx;
        if (ev.key === "ArrowRight") nextIdx = (idx + 1) % items.length;
        else if (ev.key === "ArrowLeft") nextIdx = (idx - 1 + items.length) % items.length;
        else if (ev.key === "Home") nextIdx = 0;
        else if (ev.key === "End") nextIdx = items.length - 1;
        else return;
        ev.preventDefault();
        items[nextIdx].focus();
      });
    });
  }

  /* Native switch control enhancement marker for browsers lacking HTML switch support */
  function initSwitchFallback() {
    const hasNativeSwitch = "switch" in HTMLInputElement.prototype;
    document.querySelectorAll('input[type="checkbox"][switch]').forEach((sw) => {
      if (!hasNativeSwitch) {
        sw.setAttribute("role", "switch");
        sw.setAttribute("data-switch-enhanced", "true");
      }
    });
  }

  /* Target URL Pool chips synchronized with #u5TargetUrls */
  function parseTargetUrlsText() {
    const ta = document.getElementById("u5TargetUrls");
    if (!ta) return [];
    return ta.value
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function renderUrlChips() {
    const urls = parseTargetUrlsText();
    const countBadge = document.getElementById("u5TargetUrlsCount");
    const box = document.getElementById("u5UrlPills");
    if (countBadge) {
      countBadge.textContent = `${urls.length} URL${urls.length === 1 ? "" : "s"} Active`;
    }
    if (!box) return;
    clearEl(box);

    urls.forEach((url, idx) => {
      const chip = el("span", "badge bg-label-primary d-inline-flex align-items-center gap-1 u5-url-chip");
      chip.appendChild(el("span", "font-monospace", url));
      const rm = el("button", "btn-close u5-chip-rm");
      rm.type = "button";
      rm.setAttribute("aria-label", `Remove ${url}`);
      rm.addEventListener("click", () => {
        const next = parseTargetUrlsText().filter((_, i) => i !== idx);
        const ta = document.getElementById("u5TargetUrls");
        if (ta) {
          ta.value = next.join("\n");
          dirtyControls.add("u5TargetUrls");
          validateField(ta);
          renderUrlChips();
        }
      });
      chip.appendChild(rm);
      box.appendChild(chip);
    });
  }

  /* Renderers for #view-network */
  function renderFailoverStatus(data) {
    const s = data?.status || {};
    const modeEl = document.getElementById("u5KpiTransport");
    const tripsEl = document.getElementById("u5KpiTripsRecoveries");
    const latEl = document.getElementById("u5KpiLatency");
    const enEl = document.getElementById("u5FoEnabled");
    const phEl = document.getElementById("u5FoPrimaryHealth");
    const thEl = document.getElementById("u5FoThreshold");
    const failEl = document.getElementById("u5FoFailures");

    const mode = s.active_mode || "PRIMARY_MOBILE";
    if (modeEl) modeEl.textContent = mode.replace(/_/g, " ");
    if (latEl) latEl.textContent = `${s.last_latency_ms ?? 0} ms`;
    if (tripsEl) {
      tripsEl.textContent = `${s.total_failovers ?? 0} Trips / ${s.total_recoveries ?? 0} Recoveries`;
    }
    if (enEl) enEl.textContent = s.enabled ? "Auto Failover Active" : "Disabled";
    if (phEl) {
      phEl.textContent = s.primary_healthy ? "ONLINE (Healthy)" : "DEGRADED (Using Fallback)";
      phEl.className = `fw-semibold mt-1 ${s.primary_healthy ? "text-success" : "text-warning"}`;
    }
    if (thEl) thEl.textContent = `${s.latency_threshold_ms ?? 1500} ms`;
    if (failEl) {
      failEl.textContent = `${s.consecutive_primary_failures ?? 0} Primary / ${s.consecutive_fallback_failures ?? 0} Fallback`;
    }
  }

  function renderAdbStatus(data) {
    const devs = Array.isArray(data?.devices) ? data.devices : [];
    const ip = data?.ip_info || {};
    const kpiStat = document.getElementById("u5KpiAdbStatus");
    const kpiIp = document.getElementById("u5KpiAdbIp");
    const ipBox = document.getElementById("u5AdbIpBox");
    const devBox = document.getElementById("u5AdbDevicesBox");
    const pathEl = document.getElementById("u5AdbPath");

    const onlineCount = devs.filter((d) => String(d.status).toLowerCase() === "device").length;
    if (kpiStat) {
      kpiStat.textContent = onlineCount > 0 ? `CONNECTED (${onlineCount})` : "OFFLINE (0)";
      kpiStat.className = `mb-1 ${onlineCount > 0 ? "text-success" : "text-warning"}`;
    }
    const ipSummary = ip.ip ? `${ip.ip} (${ip.city || "?"}, ${ip.country || "?"} · ${ip.org || "Carrier"})` : "No public mobile probe";
    if (kpiIp) kpiIp.textContent = ipSummary;
    if (ipBox) ipBox.textContent = ipSummary;
    if (pathEl) pathEl.textContent = data?.adb_path || "adb (PATH)";

    if (devBox) {
      if (!devs.length) {
        devBox.textContent = "No Android USB debugging device detected. Falling back safely to proxy pool if enabled.";
      } else {
        devBox.textContent = devs.map((d) => `${d.id} [${d.status}]`).join(" | ");
      }
    }
  }

  function countValidProxyLines(rawText) {
    return String(rawText || "")
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter((s) => s && !s.startsWith("#")).length;
  }

  function updateProxyCountBadges(rawText) {
    const cnt = countValidProxyLines(rawText);
    const kpi = document.getElementById("u5KpiProxyCount");
    const badge = document.getElementById("u5ProxyPoolBadge");
    if (kpi) kpi.textContent = String(cnt);
    if (badge) badge.textContent = `${cnt} Valid`;
  }

  function hydrateConfigAndStatus(cfgData, statusData) {
    const cfg = cfgData?.config || {};
    const target = cfg.target || {};
    const sched = cfg.scheduler || {};
    const net = cfg.network || {};
    const proxyCfg = cfg.proxy || {};
    const browserCfg = cfg.browser || {};
    const proxiesTxt = cfgData?.proxies ?? "";

    const setVal = (id, val) => {
      const ctrl = document.getElementById(id);
      if (ctrl && canOverwriteInput(ctrl)) {
        ctrl.value = val;
      }
    };

    const urlsList = Array.isArray(target.urls) && target.urls.length
      ? target.urls
      : target.url
      ? [target.url]
      : [];
    setVal("u5TargetUrls", urlsList.join("\n"));
    renderUrlChips();

    setVal("u5NetworkMode", net.mode || "mobile_tether");
    setVal("u5AirplaneWait", net.airplane_mode_wait ?? 4);
    setVal("u5MinDwell", target.min_dwell ?? 25);
    setVal("u5MaxDwell", target.max_dwell ?? 110);
    setVal("u5ClickProb", target.click_prob ?? 0.06);
    setVal("u5AdClicksMax", target.ad_clicks_max ?? 2);
    setVal("u5DailyCap", sched.daily_cap ?? 2000);
    setVal("u5Concurrency", sched.concurrency ?? 1);
    setVal("u5ProxyApiUrl", proxyCfg.api_url || "");
    setVal("u5ProxiesText", proxiesTxt);
    updateProxyCountBadges(proxiesTxt);
    formHydratedOnce = true;

    const nmEl = document.getElementById("u5KpiNetworkMode");
    if (nmEl) nmEl.textContent = `Mode: ${net.mode || "mobile_tether"}`;

    const hlBadge = document.getElementById("u5HeadlessBadge");
    if (hlBadge) {
      const isHeadless = Boolean(browserCfg.headless);
      hlBadge.textContent = isHeadless ? "HEADLESS (REVIEW)" : "HEAD-ON SAFE";
      hlBadge.className = `badge ${isHeadless ? "bg-label-warning" : "bg-label-info"} ms-1`;
    }

    if (statusData) {
      const ua = statusData.ua_stats || {};
      const uaEl = document.getElementById("u5KpiUaPool");
      if (uaEl) {
        uaEl.textContent = `${formatInt(ua.total || 27103)} UAs (${formatInt(ua.desktop_count || 0)} Desk / ${formatInt(ua.mobile_count || 0)} Mob)`;
      }
      const domStats = statusData.domain_stats || [];
      const tripped = Array.isArray(domStats) ? domStats.filter((d) => d.tripped || d.breaker_tripped).length : 0;
      const brkBadge = document.getElementById("u5KpiBreakerBadge");
      if (brkBadge) {
        brkBadge.textContent = `${tripped} Tripped`;
        brkBadge.className = `badge ${tripped > 0 ? "bg-label-danger" : "bg-label-success"}`;
      }
    }
  }

  /* Renderers for #view-growth */
  function renderGscStatus(data) {
    const auth = data?.auth || {};
    const summary = data?.summary || {};
    const domains = Array.isArray(data?.domains) ? data.domains : [];

    const kpiAuth = document.getElementById("u5KpiGscAuth");
    const kpiLive = document.getElementById("u5KpiGscLive");
    const kpiImps = document.getElementById("u5KpiGscImps");
    const kpiClicks = document.getElementById("u5KpiGscClicks");
    const clientEmail = document.getElementById("u5GscClientEmail");
    const authType = document.getElementById("u5GscAuthType");

    const configured = Boolean(auth.configured);
    const hasLiveProps = Boolean(summary.live_domains_count > 0);
    if (kpiAuth) {
      kpiAuth.textContent = hasLiveProps ? "CONNECTED" : "GSC NOT CONNECTED";
      kpiAuth.className = `mb-1 ${hasLiveProps ? "text-success" : "text-danger"}`;
    }
    if (kpiLive) {
      kpiLive.textContent = hasLiveProps ? `${summary.live_domains_count ?? 0} / ${summary.total_domains ?? 10} Live Properties` : "--";
    }
    if (kpiImps) kpiImps.textContent = hasLiveProps && summary.total_impressions_7d !== null ? formatInt(summary.total_impressions_7d) : "--";
    if (kpiClicks) {
      kpiClicks.textContent = hasLiveProps && summary.total_clicks_7d !== null ? `${formatInt(summary.total_clicks_7d)} Clicks · Pos ${summary.avg_position ?? "--"}` : "--";
    }
    if (clientEmail) clientEmail.textContent = auth.client_email || "Not Configured";
    if (authType) authType.textContent = auth.auth_type || "unconfigured";

    const tbody = document.getElementById("u5GscBody");
    if (!tbody) return;
    clearEl(tbody);

    if (!domains.length) {
      const tr = el("tr");
      const td = el("td", "text-center text-body-secondary py-5", "No GSC metrics cached yet.");
      td.colSpan = 8;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    domains.forEach((row) => {
      const tr = el("tr");
      const domName = row.domain || "--";
      const th = el("th", null, domName);
      th.setAttribute("scope", "row");
      tr.appendChild(th);

      const tdSrc = el("td");
      const isLive = Boolean(row.connected && row.data_source === "google_search_console_api");
      tdSrc.appendChild(el("span", `badge ${isLive ? "bg-label-success" : "bg-label-danger"}`, isLive ? "LIVE API" : "GSC NOT CONNECTED"));
      tr.appendChild(tdSrc);

      const propTxt = row.property_url || row.site_url || (isLive ? `sc-domain:${domName}` : "--");
      tr.appendChild(el("td", "font-monospace small u5-wrap-text", propTxt));
      tr.appendChild(el("td", "text-end tabular-nums", row.impressions !== null && row.impressions !== undefined ? formatInt(row.impressions) : "--"));
      tr.appendChild(el("td", "text-end tabular-nums", row.clicks !== null && row.clicks !== undefined ? formatInt(row.clicks) : "--"));

      const ctrVal = row.ctr !== null && row.ctr !== undefined ? `${(Number(row.ctr) * 100).toFixed(2)}%` : "--";
      tr.appendChild(el("td", "text-end tabular-nums", ctrVal));
      tr.appendChild(el("td", "text-end tabular-nums", row.avg_position !== null && row.avg_position !== undefined ? `#${Number(row.avg_position).toFixed(1)}` : "--"));
      tr.appendChild(el("td", "small text-body-secondary u5-wrap-text", (row.top_queries && row.top_queries[0]?.query) || row.top_query || "--"));
      tbody.appendChild(tr);
    });
  }

  function renderPushStatus(data) {
    const vapid = data?.vapid || {};
    const os = data?.onesignal || {};
    const subs = data?.subscribers || {};
    const cov = data?.sites_coverage || {};

    const locked = Boolean(os.delivery_locked ?? (os.collect_only !== false));
    const sw = document.getElementById("u5SwitchDeliveryLock");
    if (sw) sw.checked = locked;

    const kpiSubs = document.getElementById("u5KpiPushSubs");
    const kpiLock = document.getElementById("u5KpiPushLockBadge");
    const kpiCov = document.getElementById("u5KpiPushCoverage");
    if (kpiSubs) kpiSubs.textContent = formatInt(subs.total_subscribers ?? 0);
    if (kpiLock) {
      kpiLock.textContent = locked ? "LOCK ON" : "DELIVERY LIVE";
      kpiLock.className = `badge ${locked ? "bg-label-success" : "bg-label-danger"}`;
    }
    if (kpiCov) {
      kpiCov.textContent = `${cov.ready_domains ?? 0} / ${cov.total_domains ?? 10} Sites SW Ready`;
    }

    const pubEl = document.getElementById("u5VapidPubCode");
    const fpEl = document.getElementById("u5VapidFp");
    if (pubEl) pubEl.textContent = vapid.public_key || "VAPID key not generated yet";
    if (fpEl) fpEl.textContent = vapid.fingerprint || "--";

    if (canOverwriteInput(document.getElementById("u5OsAppId")) && os.app_id) {
      document.getElementById("u5OsAppId").value = os.app_id;
    }

    const tbody = document.getElementById("u5PushBody");
    if (!tbody) return;
    clearEl(tbody);

    const domRows = Array.isArray(cov.domains) ? cov.domains : [];
    const byDomain = subs.by_domain || {};

    if (!domRows.length) {
      const tr = el("tr");
      const td = el("td", "text-center text-body-secondary py-5", "No domains found.");
      td.colSpan = 7;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    domRows.forEach((d) => {
      const tr = el("tr");
      const th = el("th", null, d.domain || "--");
      th.setAttribute("scope", "row");
      tr.appendChild(th);

      const mkBadge = (ok, yes = "Ready", no = "Missing") =>
        el("span", `badge ${ok ? "bg-label-success" : "bg-label-danger"}`, ok ? yes : no);

      const tdCol = el("td");
      tdCol.appendChild(mkBadge(Boolean(d.has_collector)));
      tr.appendChild(tdCol);

      const tdSw = el("td");
      tdSw.appendChild(mkBadge(Boolean(d.has_push_sw), "Active", "Missing"));
      tr.appendChild(tdSw);

      const tdOs = el("td");
      tdOs.appendChild(mkBadge(Boolean(d.has_onesignal_sw), "Active", "Missing"));
      tr.appendChild(tdOs);

      const tdMon = el("td");
      tdMon.appendChild(
        el("span", `badge ${d.monetag_sw_preserved ? "bg-label-info" : "bg-label-secondary"}`, d.monetag_sw_preserved ? "Preserved" : "None")
      );
      tr.appendChild(tdMon);

      tr.appendChild(el("td", "text-end tabular-nums", formatInt(byDomain[d.domain] ?? 0)));

      const tdState = el("td");
      const safe = Boolean(d.ready) && !d.secret_leak;
      tdState.appendChild(el("span", `badge ${safe ? "bg-label-success" : "bg-label-warning"}`, safe ? "Collect Ready" : "Needs Sync"));
      tr.appendChild(tdState);
      tbody.appendChild(tr);
    });
  }

  function renderTelegramStatus(data) {
    const sum = data?.summary || {};
    const alerts = Array.isArray(data?.recent_alerts) ? data.recent_alerts : [];

    const kpiBot = document.getElementById("u5KpiTgBot");
    const kpiCount = document.getElementById("u5KpiTgAlerts");
    if (kpiBot) kpiBot.textContent = data?.bot_username || "@Liveadsterabot";
    if (kpiCount) {
      kpiCount.textContent = `${sum.total ?? 0} Alerts Today (${data?.configured ? "Live Bot" : "Dry/Log"})`;
    }

    const setTxt = (id, v) => {
      const n = document.getElementById(id);
      if (n) n.textContent = formatInt(v ?? 0);
    };
    setTxt("u5TgTotal", sum.total ?? 0);
    setTxt("u5TgInfo", sum.INFO ?? 0);
    setTxt("u5TgWarn", sum.WARNING ?? 0);
    setTxt("u5TgCrit", sum.CRITICAL ?? 0);

    const tbody = document.getElementById("u5TgBody");
    if (!tbody) return;
    clearEl(tbody);

    if (!alerts.length) {
      const tr = el("tr");
      const td = el("td", "text-center text-body-secondary py-5", "No alerts dispatched yet today.");
      td.colSpan = 6;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    alerts.slice(0, 15).forEach((a) => {
      const tr = el("tr");
      const th = el("th", "tabular-nums small", safeTimeLabel(a.ts));
      th.setAttribute("scope", "row");
      tr.appendChild(th);

      const lvl = String(a.level || "INFO").toUpperCase();
      const lvlCls =
        lvl === "CRITICAL" ? "bg-label-danger" : lvl === "WARNING" ? "bg-label-warning" : "bg-label-success";
      const tdLvl = el("td");
      tdLvl.appendChild(el("span", `badge ${lvlCls}`, lvl));
      tr.appendChild(tdLvl);

      tr.appendChild(el("td", "small", a.alert_type || "--"));
      tr.appendChild(el("td", "small font-monospace", a.domain || "fleet"));
      tr.appendChild(el("td", "small u5-wrap-text", (a.message || "").replace(/<[^>]+>/g, " ").trim()));

      const tdDel = el("td");
      tdDel.appendChild(
        el("span", `badge ${a.delivered ? "bg-label-success" : "bg-label-secondary"}`, a.delivered ? "Sent" : "Logged")
      );
      tr.appendChild(tdDel);
      tbody.appendChild(tr);
    });
  }

  /* Data Refreshers */
  async function refreshNetworkData() {
    const [rFailover, rAdb, rConfig, rStatus] = await Promise.allSettled([
      fetch("/api/failover/status", { cache: "no-store" }),
      fetch("/api/adb/status", { cache: "no-store" }),
      fetch("/api/config", { cache: "no-store" }),
      fetch("/api/status", { cache: "no-store" }),
    ]);

    if (rFailover.status === "fulfilled" && rFailover.value.ok) {
      renderFailoverStatus(await rFailover.value.json());
    }
    if (rAdb.status === "fulfilled" && rAdb.value.ok) {
      renderAdbStatus(await rAdb.value.json());
    }
    const cfgJson = rConfig.status === "fulfilled" && rConfig.value.ok ? await rConfig.value.json() : null;
    const stJson = rStatus.status === "fulfilled" && rStatus.value.ok ? await rStatus.value.json() : null;
    if (cfgJson) {
      hydrateConfigAndStatus(cfgJson, stJson);
    }
  }

  async function refreshGrowthData() {
    const [rGsc, rPush, rTg] = await Promise.allSettled([
      fetch("/api/gsc/status", { cache: "no-store" }),
      fetch("/api/push/status", { cache: "no-store" }),
      fetch("/api/telegram/status", { cache: "no-store" }),
    ]);

    if (rGsc.status === "fulfilled" && rGsc.value.ok) {
      renderGscStatus(await rGsc.value.json());
    }
    if (rPush.status === "fulfilled" && rPush.value.ok) {
      renderPushStatus(await rPush.value.json());
    }
    if (rTg.status === "fulfilled" && rTg.value.ok) {
      renderTelegramStatus(await rTg.value.json());
    }
  }

  /* Accessible Growth Tabs (ArrowLeft/Right + Home/End + hidden="until-found" + beforematch) */
  function bindGrowthTabs() {
    const tablist = document.getElementById("u5GrowthTabs");
    if (!tablist) return;
    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));

    function activateTab(tab) {
      tabs.forEach((btn) => {
        const selected = btn === tab;
        btn.classList.toggle("active", selected);
        btn.setAttribute("aria-selected", selected ? "true" : "false");
        btn.setAttribute("tabindex", selected ? "0" : "-1");

        const panelId = btn.getAttribute("aria-controls");
        const panel = panelId ? document.getElementById(panelId) : null;
        if (panel) {
          if (selected) {
            panel.removeAttribute("hidden");
          } else {
            panel.setAttribute("hidden", "until-found");
          }
        }
      });
    }

    tabs.forEach((btn, idx) => {
      btn.addEventListener("click", () => activateTab(btn));
      btn.addEventListener("keydown", (ev) => {
        let next = idx;
        if (ev.key === "ArrowRight") next = (idx + 1) % tabs.length;
        else if (ev.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
        else if (ev.key === "Home") next = 0;
        else if (ev.key === "End") next = tabs.length - 1;
        else return;
        ev.preventDefault();
        tabs[next].focus();
        activateTab(tabs[next]);
      });

      const panelId = btn.getAttribute("aria-controls");
      const panel = panelId ? document.getElementById(panelId) : null;
      if (panel) {
        panel.addEventListener("beforematch", () => activateTab(btn));
      }
    });
  }

  /* Accessible Copy Command (--copy on VAPID Public Key) */
  function showCopyFeedback(btn, ok) {
    const tip = document.getElementById("u5VapidCopyTip");
    if (ok) {
      copyCount += 1;
      btn.setAttribute("data-copied", "");
      btn.removeAttribute("data-failed");
      if (tip) tip.textContent = copyCount % 2 === 1 ? "Copied" : "Copied\u00A0";
    } else {
      btn.setAttribute("data-failed", "");
      btn.removeAttribute("data-copied");
      if (tip) tip.textContent = "Copy failed";
    }
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => {
      btn.removeAttribute("data-copied");
      btn.removeAttribute("data-failed");
    }, 2200);
  }

  async function executeVapidCopy(btn) {
    const target = document.getElementById("u5VapidPubCode");
    const txt = (target?.textContent || "").trim();
    if (!txt || txt.startsWith("Loading")) return;
    try {
      await navigator.clipboard.writeText(txt);
      showCopyFeedback(btn, true);
    } catch (_) {
      showCopyFeedback(btn, false);
    }
  }

  function bindCopyCommand() {
    const btn = document.getElementById("u5VapidCopyBtn");
    if (!btn) return;
    if ("CommandEvent" in window) {
      document.addEventListener(
        "command",
        (ev) => {
          if (ev.command !== "--copy" || ev.source !== btn) return;
          executeVapidCopy(btn);
        },
        { capture: true }
      );
    } else {
      btn.addEventListener("click", () => executeVapidCopy(btn));
    }
  }

  /* Network Actions */
  function bindNetworkActions() {
    document.getElementById("u5TargetUrls")?.addEventListener("input", renderUrlChips);
    document.getElementById("u5ProxiesText")?.addEventListener("input", (e) => {
      updateProxyCountBadges(e.target.value);
    });
    document.getElementById("u5BtnToggleProxyMask")?.addEventListener("click", () => {
      const btn = document.getElementById("u5BtnToggleProxyMask");
      const ta = document.getElementById("u5ProxiesText");
      if (!btn || !ta) return;
      const nextMasked = btn.getAttribute("aria-pressed") !== "true";
      ta.dataset.masked = nextMasked ? "true" : "false";
      btn.setAttribute("aria-pressed", nextMasked ? "true" : "false");
      btn.classList.toggle("btn-outline-secondary", nextMasked);
      btn.classList.toggle("btn-outline-warning", !nextMasked);
      const icon = btn.querySelector("i");
      if (icon) icon.className = `icon-base ti ${nextMasked ? "tabler-eye-off" : "tabler-eye"} icon-14px me-1`;
    });

    document.getElementById("u5BtnAddUrl")?.addEventListener("click", () => {
      const inp = document.getElementById("u5NewUrlInput");
      const ta = document.getElementById("u5TargetUrls");
      const raw = (inp?.value || "").trim();
      if (!/^https?:\/\/.+/.test(raw)) {
        toast("Enter a valid https:// or http:// URL first", "error");
        inp?.focus();
        return;
      }
      const existing = parseTargetUrlsText();
      if (!existing.includes(raw)) {
        existing.push(raw);
        if (ta) {
          ta.value = existing.join("\n");
          dirtyControls.add("u5TargetUrls");
          validateField(ta);
        }
        renderUrlChips();
      }
      if (inp) inp.value = "";
    });

    document.getElementById("u5ConfigForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!validateFormOnSubmit("u5ConfigForm")) return;

      const minD = Number(document.getElementById("u5MinDwell").value);
      const maxD = Number(document.getElementById("u5MaxDwell").value);
      if (maxD < minD) {
        toast("Max Dwell must be greater than or equal to Min Dwell", "error");
        document.getElementById("u5MaxDwell").focus();
        return;
      }

      const btn = document.getElementById("u5BtnSaveConfig");
      if (btn) btn.disabled = true;
      try {
        const urls = parseTargetUrlsText();
        const r = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            urls,
            network_mode: document.getElementById("u5NetworkMode").value,
            airplane_mode_wait: Number(document.getElementById("u5AirplaneWait").value),
            min_dwell: minD,
            max_dwell: maxD,
            click_prob: Number(document.getElementById("u5ClickProb").value),
            ad_clicks_max: Number(document.getElementById("u5AdClicksMax").value),
            daily_cap: Number(document.getElementById("u5DailyCap").value),
            concurrency: Number(document.getElementById("u5Concurrency").value),
            proxy_api_url: document.getElementById("u5ProxyApiUrl").value.trim(),
          }),
        });
        const data = await r.json();
        if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
        clearDirtyForForm("u5ConfigForm");
        setStatusAlert("u5NetworkStatusAlert", `Saved runner config (${urls.length} URLs active in pool).`, "success");
        toast("Runner config saved to config.yaml");
        await refreshNetworkData();
      } catch (err) {
        setStatusAlert("u5NetworkStatusAlert", `Config save failed: ${err}`, "danger");
        toast(`Config save error: ${err}`, "error");
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("u5ProxyFetchForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!validateFormOnSubmit("u5ProxyFetchForm")) return;
      const apiUrl = document.getElementById("u5ProxyApiUrl").value.trim();
      const btn = document.getElementById("u5BtnFetchProxies");
      if (btn) btn.disabled = true;
      try {
        const r = await fetch("/api/proxies/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_url: apiUrl }),
        });
        const data = await r.json();
        if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
        const ta = document.getElementById("u5ProxiesText");
        if (ta && typeof data.proxies === "string") {
          ta.value = data.proxies;
          dirtyControls.delete("u5ProxiesText");
          updateProxyCountBadges(data.proxies);
        }
        setStatusAlert("u5NetworkStatusAlert", `Fetched ${data.count ?? 0} proxies from provider API.`, "success");
        toast(`Fetched ${data.count ?? 0} proxies`);
      } catch (err) {
        setStatusAlert("u5NetworkStatusAlert", `Proxy fetch error: ${err}`, "warning");
        toast(`Proxy fetch error: ${err}`, "error");
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("u5ProxySaveForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const ta = document.getElementById("u5ProxiesText");
      const btn = document.getElementById("u5BtnSaveProxies");
      if (btn) btn.disabled = true;
      try {
        const r = await fetch("/api/proxies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ proxies: ta?.value || "" }),
        });
        const data = await r.json();
        if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
        clearDirtyForForm("u5ProxySaveForm");
        updateProxyCountBadges(ta?.value || "");
        setStatusAlert("u5NetworkStatusAlert", `Saved proxies.txt (${data.count ?? 0} valid non-comment entries).`, "success");
        toast(`Saved ${data.count ?? 0} proxies`);
      } catch (err) {
        setStatusAlert("u5NetworkStatusAlert", `Save proxies error: ${err}`, "danger");
        toast(`Save proxies failed: ${err}`, "error");
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("u5BtnProbeFailover")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnProbeFailover");
      btn.disabled = true;
      try {
        const r = await fetch("/api/failover/test", { method: "POST" });
        const data = await r.json();
        const h = data.health || {};
        setStatusAlert(
          "u5NetworkStatusAlert",
          `Failover Probe: healthy=${h.healthy}, latency=${h.latency_ms}ms, devices=${h.devices} (${h.reason || "OK"})`,
          h.healthy ? "success" : "warning"
        );
        await refreshNetworkData();
      } catch (err) {
        setStatusAlert("u5NetworkStatusAlert", `Failover probe failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnSwapFailover")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnSwapFailover");
      btn.disabled = true;
      try {
        const r = await fetch("/api/failover/switch", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert("u5NetworkStatusAlert", `Hot-swapped active carrier to: ${data.active_mode}`, "info");
        toast(`Transport switched: ${data.active_mode}`);
        await refreshNetworkData();
      } catch (err) {
        toast(`Hot-swap failed: ${err}`, "error");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnResetBreakers")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnResetBreakers");
      btn.disabled = true;
      try {
        const r = await fetch("/api/circuit-breaker/reset", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert("u5NetworkStatusAlert", "All domain CTR circuit breakers and Active UA state reset cleanly.", "success");
        toast("Circuit breakers reset");
        await refreshNetworkData();
      } catch (err) {
        toast(`Reset failed: ${err}`, "error");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnSyncUa")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnSyncUa");
      btn.disabled = true;
      try {
        const r = await fetch("/api/useragents/sync", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert("u5NetworkStatusAlert", `User-Agent pool synced (${formatInt(data.total || 27103)} UAs ready).`, "success");
        toast("User-Agent pool synced");
        await refreshNetworkData();
      } catch (err) {
        toast(`UA sync failed: ${err}`, "error");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnRefreshAdb")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnRefreshAdb");
      btn.disabled = true;
      try {
        const r = await fetch("/api/adb/status", { cache: "no-store" });
        if (r.ok) renderAdbStatus(await r.json());
        toast("ADB status refreshed");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnRotateAdb")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnRotateAdb");
      btn.disabled = true;
      const waitSec = Number(document.getElementById("u5AirplaneWait")?.value || 4);
      try {
        const r = await fetch("/api/adb/rotate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ airplane_wait: waitSec }),
        });
        const data = await r.json();
        setStatusAlert(
          "u5NetworkStatusAlert",
          data.ok
            ? `Flight Mode Rotated IP: ${data.data?.old_ip || "?"} -> ${data.data?.new_ip || "?"}`
            : `ADB Rotate: ${data.msg || "No USB device attached"}`,
          data.ok ? "success" : "warning"
        );
        await refreshNetworkData();
      } catch (err) {
        setStatusAlert("u5NetworkStatusAlert", `ADB rotation error: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });
  }

  /* Growth Actions (GSC, Push, Telegram) */
  function bindGrowthActions() {
    document.getElementById("u5BtnRefreshGrowth")?.addEventListener("click", async () => {
      await refreshGrowthData();
      toast("Growth telemetry refreshed");
    });

    document.getElementById("u5BtnToggleOsKey")?.addEventListener("click", () => {
      const inp = document.getElementById("u5OsRestKey");
      const btn = document.getElementById("u5BtnToggleOsKey");
      if (!inp || !btn) return;
      const show = inp.type === "password";
      inp.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide OneSignal REST API Key" : "Show OneSignal REST API Key");
      const icon = btn.querySelector("i");
      if (icon) icon.className = `icon-base ti ${show ? "tabler-eye-off" : "tabler-eye"} icon-16px`;
    });

    document.getElementById("u5BtnSyncGsc")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnSyncGsc");
      btn.disabled = true;
      try {
        const r = await fetch("/api/gsc/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ days: 7 }),
        });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert("u5GrowthStatusAlert", "Layer 5 GSC Search Analytics synced cleanly across 10 domains.", "success");
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `GSC sync failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnWeeklyGsc")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnWeeklyGsc");
      btn.disabled = true;
      try {
        const r = await fetch("/api/gsc/weekly-report", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert(
          "u5GrowthStatusAlert",
          `Weekly GSC report saved (${data.date || "today"}) | Telegram sent: ${Boolean(data.telegram_sent)}`,
          "success"
        );
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `Weekly GSC report failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5GscCredForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!validateFormOnSubmit("u5GscCredForm")) return;
      const ta = document.getElementById("u5GscJson");
      const btn = document.getElementById("u5BtnSaveGscCreds");
      btn.disabled = true;
      try {
        const r = await fetch("/api/gsc/credentials", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ credentials_json: ta.value }),
        });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        ta.value = "";
        ta.removeAttribute("aria-invalid");
        ta.classList.remove("user-invalid-fallback");
        setStatusAlert("u5GrowthStatusAlert", "GSC credentials saved securely in gitignored state/ directory.", "success");
        toast("GSC credentials saved");
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `Invalid GSC JSON: ${err}`, "danger");
        ta.focus();
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnRotateVapid")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnRotateVapid");
      btn.disabled = true;
      try {
        const r = await fetch("/api/push/vapid/generate", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert(
          "u5GrowthStatusAlert",
          `Rotated P-256 VAPID keypair (${data.vapid?.fingerprint || "OK"}). Remember to Sync Sites SW.`,
          "success"
        );
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `VAPID rotation failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnInjectPush")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnInjectPush");
      btn.disabled = true;
      try {
        const r = await fetch("/api/push/inject", { method: "POST" });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        setStatusAlert(
          "u5GrowthStatusAlert",
          `Synced Push SW & collector scripts (${data.sites_coverage?.ready_domains ?? 0}/10 domains ready).`,
          "success"
        );
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `Sites SW sync failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5BtnTestPushLock")?.addEventListener("click", async () => {
      const btn = document.getElementById("u5BtnTestPushLock");
      btn.disabled = true;
      try {
        const r = await fetch("/api/push/deliver-test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain: "loanraaj.com" }),
        });
        const data = await r.json();
        const res = data.result || {};
        const blocked = res.status === "blocked_testing_phase" || res.blocked === true;
        setStatusAlert(
          "u5GrowthStatusAlert",
          blocked
            ? `Delivery Lock VERIFIED (${res.reason || "blocked_testing_phase"}) — 0 broadcasts sent during testing phase.`
            : `Delivery check result: ${res.status || "OK"}`,
          blocked ? "success" : "warning"
        );
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `Lock check failed: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("u5OsForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!validateFormOnSubmit("u5OsForm")) return;
      const btn = document.getElementById("u5BtnSaveOneSignal");
      const keyInp = document.getElementById("u5OsRestKey");
      btn.disabled = true;
      try {
        const r = await fetch("/api/push/onesignal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            app_id: document.getElementById("u5OsAppId").value.trim(),
            rest_api_key: keyInp.value.trim(),
            domain: document.getElementById("u5OsDomain").value.trim(),
          }),
        });
        const data = await r.json();
        if (!r.ok || data.success === false) throw new Error(data.error || `HTTP ${r.status}`);
        keyInp.value = "";
        clearDirtyForForm("u5OsForm");
        setStatusAlert("u5GrowthStatusAlert", "OneSignal settings saved locally in gitignored state/push_network.json.", "success");
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `OneSignal save error: ${err}`, "danger");
      } finally {
        btn.disabled = false;
      }
    });

    const postTelegram = async (endpoint, label) => {
      try {
        const r = await fetch(endpoint, { method: "POST" });
        const data = await r.json();
        setStatusAlert("u5GrowthStatusAlert", `${label}: ${data.success ? "Completed" : data.error || "Check logs"}`, data.success ? "success" : "warning");
        await refreshGrowthData();
      } catch (err) {
        setStatusAlert("u5GrowthStatusAlert", `${label} error: ${err}`, "danger");
      }
    };

    document.getElementById("u5BtnTgTest")?.addEventListener("click", () => postTelegram("/api/telegram/test", "Telegram Test Ping"));
    document.getElementById("u5BtnTgHeartbeat")?.addEventListener("click", () => postTelegram("/api/telegram/heartbeat", "Telegram Heartbeat"));
    document.getElementById("u5BtnTgDailyReport")?.addEventListener("click", () => postTelegram("/api/telegram/daily-report", "Telegram Daily Report"));
  }

  function refreshActiveU5Views() {
    if (isViewActive("view-network")) refreshNetworkData();
    if (isViewActive("view-growth")) refreshGrowthData();
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("view-network") && !document.getElementById("view-growth")) return;

    initSwitchFallback();
    bindToolbarFallbacks();
    bindGrowthTabs();
    bindCopyCommand();

    trackDirty("u5ConfigForm");
    trackDirty("u5ProxyFetchForm");
    trackDirty("u5ProxySaveForm");

    ["u5ConfigForm", "u5ProxyFetchForm", "u5GscCredForm", "u5OsForm"].forEach(bindValidation);

    bindNetworkActions();
    bindGrowthActions();

    window.addEventListener("crm:view-activated", (ev) => {
      const v = ev?.detail?.view;
      if (v === "network") refreshNetworkData();
      else if (v === "growth") refreshGrowthData();
    });

    refreshActiveU5Views();
    pollTimer = setInterval(refreshActiveU5Views, POLL_MS);
  });
})();
