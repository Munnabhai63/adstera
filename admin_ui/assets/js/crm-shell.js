/**
 * AdsterraFleet Vuexy CRM Shell Controller — Component U1
 * Handles SPA workspace navigation, Light/Dark/System theme sync,
 * Semi-Dark sidebar toggle, live navbar telemetry polling, and Force Stop action.
 */
(function () {
  "use strict";

  const VALID_VIEWS = [
    "overview",
    "phase4-farm",
    "autopublish",
    "monetization",
    "network",
    "growth",
    "profile",
    "settings",
  ];

  const VIEW_META = {
    overview: { title: "Overview & Live Ops", layer: "Layer U1 + U2" },
    "phase4-farm": { title: "Phase 4 Farm, CGNAT & AI Ops", layer: "Phase 3 + Phase 4" },
    autopublish: { title: "AutoPublish & 20-Topic CMS", layer: "Layer U3" },
    monetization: { title: "Monetization, Adsterra & Leads", layer: "Layer U4" },
    network: { title: "Network, Proxies, ADB & Config", layer: "Layer U5" },
    growth: { title: "Growth, GSC SEO, Push & Telegram", layer: "Layer U5" },
    profile: { title: "Operator Profile, Auth & Notifications", layer: "Layer U2.5" },
    settings: { title: "System & Appearance Settings", layer: "Layer U1 + U5" },
  };

  let notyf = null;
  let telemetryTimer = null;

  function getTemplateKey(suffix) {
    const tName = document.documentElement.getAttribute("data-template") || "adstera-crm";
    return "templateCustomizer-" + tName + "--" + suffix;
  }

  function initToast() {
    if (typeof Notyf !== "undefined") {
      notyf = new Notyf({
        duration: 3200,
        position: { x: "right", y: "bottom" },
        dismissible: true,
      });
    }
  }

  function showToast(msg, type = "success") {
    if (!notyf) {
      console.log(`[Toast:${type}]`, msg);
      return;
    }
    notyf.dismissAll();
    if (type === "error") {
      notyf.error(String(msg));
    } else {
      notyf.success(String(msg));
    }
  }

  function getStoredThemeMode() {
    try {
      return (
        localStorage.getItem(getTemplateKey("Theme")) ||
        window.templateCustomizer?.settings?.defaultTheme ||
        "system"
      );
    } catch (_) {
      return "system";
    }
  }

  function resolveEffectiveTheme(mode) {
    if (mode === "system") {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return mode === "dark" ? "dark" : "light";
  }

  function syncMetaColorScheme(mode) {
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (!meta) return;
    if (mode === "light") {
      meta.setAttribute("content", "light");
    } else if (mode === "dark") {
      meta.setAttribute("content", "dark");
    } else {
      meta.setAttribute("content", "light dark");
    }
  }

  function updateThemeInspector() {
    const stored = getStoredThemeMode();
    const effective = resolveEffectiveTheme(stored);
    syncMetaColorScheme(stored);

    const menuEl = document.getElementById("layout-menu");
    const isSemiDark = menuEl?.getAttribute("data-bs-theme") === "dark" && effective === "light";
    const isCollapsed = document.documentElement.classList.contains("layout-menu-collapsed");

    const modeBadge = document.getElementById("shellThemeModeReadout");
    const effBadge = document.getElementById("shellThemeEffectiveReadout");
    const semiBadge = document.getElementById("shellSemiDarkReadout");
    const menuStateBadge = document.getElementById("shellMenuStateReadout");

    if (modeBadge) modeBadge.textContent = stored.toUpperCase();
    if (effBadge) effBadge.textContent = effective.toUpperCase();
    if (semiBadge) semiBadge.textContent = isSemiDark ? "SEMI-DARK ON" : effective === "dark" ? "FULL DARK" : "LIGHT";
    if (menuStateBadge) menuStateBadge.textContent = isCollapsed ? "COLLAPSED" : "EXPANDED";

    document.querySelectorAll("[data-shell-theme-btn]").forEach((btn) => {
      const target = btn.getAttribute("data-shell-theme-btn");
      btn.classList.toggle("active", target === stored);
    });
  }

  function setThemeMode(mode) {
    const allowed = ["light", "dark", "system"];
    const next = allowed.includes(mode) ? mode : "system";
    const tName = document.documentElement.getAttribute("data-template") || "adstera-crm";

    if (window.Helpers) {
      window.Helpers.setStoredTheme(tName, next);
      window.Helpers.setTheme(next);
      window.Helpers.showActiveTheme(next, false);
      window.Helpers.syncCustomOptions(next);
    } else {
      try {
        localStorage.setItem(getTemplateKey("Theme"), next);
      } catch (_) {}
      document.documentElement.setAttribute("data-bs-theme", resolveEffectiveTheme(next));
    }

    const menuEl = document.getElementById("layout-menu");
    if (menuEl && next === "dark") {
      menuEl.setAttribute("data-bs-theme", "dark");
    }
    syncMetaColorScheme(next);
    updateThemeInspector();
    window.dispatchEvent(
      new CustomEvent("crm:theme-changed", { detail: { theme: resolveEffectiveTheme(next) } })
    );
    showToast(`Theme switched to ${next.toUpperCase()}`);
  }

  function toggleSemiDarkSidebar() {
    const menuEl = document.getElementById("layout-menu");
    if (!menuEl) return;
    const currentlyDark = menuEl.getAttribute("data-bs-theme") === "dark";
    const nextVal = !currentlyDark;

    if (window.templateCustomizer && typeof window.templateCustomizer.setSemiDark === "function") {
      window.templateCustomizer.setSemiDark(nextVal);
    } else {
      if (nextVal) {
        menuEl.setAttribute("data-bs-theme", "dark");
      } else {
        menuEl.removeAttribute("data-bs-theme");
      }
    }
    updateThemeInspector();
    showToast(`Sidebar Semi-Dark: ${nextVal ? "ON" : "OFF"}`);
  }

  function toggleSidebarCollapse() {
    if (window.Helpers && typeof window.Helpers.toggleCollapsed === "function") {
      window.Helpers.toggleCollapsed();
      setTimeout(updateThemeInspector, 120);
    }
  }

  function activateView(viewId, updateHash = true) {
    const targetId = VALID_VIEWS.includes(viewId) ? viewId : "overview";

    document.querySelectorAll(".crm-view").forEach((el) => {
      el.classList.toggle("active", el.id === `view-${targetId}`);
    });

    document.querySelectorAll("[data-crm-view]").forEach((link) => {
      const linkView = link.getAttribute("data-crm-view");
      const li = link.closest(".menu-item");
      if (li) {
        li.classList.toggle("active", linkView === targetId);
      }
    });

    const bc = document.getElementById("shellActiveBreadcrumb");
    const badge = document.getElementById("shellActiveLayerBadge");
    if (bc && VIEW_META[targetId]) bc.textContent = VIEW_META[targetId].title;
    if (badge && VIEW_META[targetId]) badge.textContent = VIEW_META[targetId].layer;

    if (updateHash && window.location.hash !== `#${targetId}`) {
      history.replaceState(null, "", `#${targetId}`);
    }

    if (window.Helpers && window.Helpers.isSmallScreen && window.Helpers.isSmallScreen()) {
      window.Helpers.setCollapsed(true);
    }

    window.dispatchEvent(new CustomEvent("crm:view-activated", { detail: { view: targetId } }));
  }

  function closeSearchOverlayIfOpen() {
    const overlay = document.querySelector(".aa-DetachedOverlay");
    if (!overlay) return;
    const cancelBtn = overlay.querySelector(".aa-DetachedCancelButton");
    if (cancelBtn) cancelBtn.click();
  }

  function bindNavigation() {
    document.querySelectorAll("[data-crm-view]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.preventDefault();
        const view = el.getAttribute("data-crm-view");
        activateView(view, true);
      });
    });

    // Auto-close Algolia Ctrl+K search modal when selecting same-page #hash routes
    document.addEventListener("click", (ev) => {
      const link = ev.target.closest('.aa-DetachedOverlay a[href^="#"], .aa-Panel a[href^="#"]');
      if (!link) return;
      const target = (link.getAttribute("href") || "").replace(/^#/, "");
      if (VALID_VIEWS.includes(target)) {
        ev.preventDefault();
        closeSearchOverlayIfOpen();
        activateView(target, true);
      }
    });

    window.addEventListener("hashchange", () => {
      closeSearchOverlayIfOpen();
      const h = (window.location.hash || "#overview").replace(/^#/, "");
      if (VALID_VIEWS.includes(h)) {
        activateView(h, false);
      }
    });
  }

  async function refreshShellTelemetry(manualPing = false) {
    const t0 = performance.now();
    try {
      const [rStatus, rAuto, rGsc, rPush] = await Promise.all([
        fetch("/api/status", { cache: "no-store" }),
        fetch("/api/autopublish/stats?domain=tazaloan", { cache: "no-store" }),
        fetch("/api/gsc/status", { cache: "no-store" }),
        fetch("/api/push/status", { cache: "no-store" }),
      ]);

      const latencyMs = Math.round(performance.now() - t0);
      const statusData = rStatus.ok ? await rStatus.json() : {};
      const autoData = rAuto.ok ? await rAuto.json() : {};
      const gscData = rGsc.ok ? await rGsc.json() : {};
      const pushData = rPush.ok ? await rPush.json() : {};

      const isRunning = Boolean(statusData.is_running);
      const domainsCount = Array.isArray(statusData.domains) ? statusData.domains.length : 10;
      const pendingByDomain = autoData.pending_by_domain || {};
      const totalPending = Object.values(pendingByDomain).reduce(
        (acc, v) => acc + (Number(v) || 0),
        0
      );
      const intervalMins = autoData.speed_config?.interval_minutes ?? 20;
      const parallelDoms = autoData.speed_config?.parallel_domains ?? 2;

      const dotEl = document.getElementById("shellRunnerDot");
      const textEl = document.getElementById("shellRunnerText");
      const pillDomains = document.getElementById("shellDomainsPill");
      const sidebarBadge = document.getElementById("sidebarAutopublishBadge");

      if (dotEl) {
        dotEl.className = isRunning ? "status-dot-live me-2" : "status-dot-idle me-2";
      }
      if (textEl) {
        textEl.textContent = isRunning ? "RUNNER ACTIVE" : "MAIN OFF · SAFE";
      }
      if (pillDomains) {
        pillDomains.textContent = `${domainsCount} Sites · ${totalPending} Queued`;
      }
      if (sidebarBadge) {
        sidebarBadge.textContent = String(totalPending);
      }

      const kpiDomains = document.getElementById("u1KpiDomains");
      const kpiPending = document.getElementById("u1KpiPending");
      const kpiCadence = document.getElementById("u1KpiCadence");
      const kpiGscPush = document.getElementById("u1KpiGscPush");
      const pingOut = document.getElementById("u1ApiPingReadout");

      if (kpiDomains) kpiDomains.textContent = `${domainsCount} / 10`;
      if (kpiPending) kpiPending.textContent = String(totalPending);
      if (kpiCadence) kpiCadence.textContent = `${parallelDoms}x / ${intervalMins}m`;

      const vapidOk = Boolean(pushData.vapid?.configured);
      const pushCov = pushData.sites_coverage?.ready_domains ?? 0;
      const pushTot = pushData.sites_coverage?.total_domains ?? 10;
      const pushSubEl = document.getElementById("u1KpiPushSub");
      const gscLive = gscData.auth?.configured ? "GSC LIVE" : "GSC READY";
      if (kpiGscPush) {
        kpiGscPush.textContent = `${pushCov} / ${pushTot}`;
      }
      if (pushSubEl) {
        pushSubEl.textContent = `VAPID ${vapidOk ? "OK" : "MISSING"} · Lock ${pushData.onesignal?.delivery_locked ? "ON" : "OPEN"}`;
      }

      if (pingOut) {
        pingOut.textContent = `4 Live APIs OK in ${latencyMs} ms (${gscLive}, ${pushCov}/${pushTot} Push SW, ${totalPending} Pending Topics)`;
      }

      if (manualPing) {
        showToast(`Live API health OK (${latencyMs} ms)`);
      }

      // Non-blocking Phase 4 health probe for sidebar badge
      (async () => {
        try {
          const p4Badge = document.getElementById("sidebarPhase4Badge");
          if (!p4Badge) return;
          const rP4 = await fetch("/api/phase4/health", { cache: "no-store" });
          if (!rP4.ok) return;
          const p4Data = await rP4.json();
          if (p4Data.safe_mode_active) {
            p4Badge.textContent = "SAFE";
            p4Badge.className = "badge text-bg-danger rounded-pill ms-auto";
          } else if (p4Data.db_ok) {
            p4Badge.textContent = "OK";
            p4Badge.className = "badge text-bg-success rounded-pill ms-auto";
          } else {
            p4Badge.textContent = "P4";
            p4Badge.className = "badge text-bg-secondary rounded-pill ms-auto";
          }
        } catch (_) {}
      })();
    } catch (err) {
      const pingOut = document.getElementById("u1ApiPingReadout");
      if (pingOut) pingOut.textContent = `Telemetry check error: ${err}`;
      if (manualPing) showToast("Telemetry check failed", "error");
    }
  }

  async function forceStopAll() {
    let confirmed = true;
    if (typeof Swal !== "undefined") {
      const res = await Swal.fire({
        title: "Force Stop All Runners?",
        text: "Stops active traffic runners immediately. AutoPublish UI remains accessible.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Yes, Force Stop",
        customClass: {
          confirmButton: "btn btn-danger me-2",
          cancelButton: "btn btn-label-secondary",
        },
        buttonsStyling: false,
      });
      confirmed = Boolean(res.isConfirmed);
    }
    if (!confirmed) return;

    try {
      const r = await fetch("/api/force-stop", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showToast("Force Stop signal delivered cleanly");
      await refreshShellTelemetry(false);
    } catch (err) {
      showToast(`Force Stop error: ${err}`, "error");
    }
  }

  function bindThemeSync() {
    document.querySelectorAll("[data-bs-theme-value]").forEach((el) => {
      el.addEventListener("click", () => {
        setTimeout(() => {
          syncMetaColorScheme(getStoredThemeMode());
          updateThemeInspector();
          window.dispatchEvent(
            new CustomEvent("crm:theme-changed", {
              detail: { theme: resolveEffectiveTheme(getStoredThemeMode()) },
            })
          );
        }, 40);
      });
    });

    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        setTimeout(() => {
          updateThemeInspector();
          window.dispatchEvent(
            new CustomEvent("crm:theme-changed", {
              detail: { theme: resolveEffectiveTheme(getStoredThemeMode()) },
            })
          );
        }, 40);
      });
    }

    window.addEventListener("storage", (e) => {
      if (e.key && e.key.includes("--Theme")) {
        const next = getStoredThemeMode();
        if (window.Helpers) {
          window.Helpers.setTheme(next);
          window.Helpers.showActiveTheme(next, false);
        }
        updateThemeInspector();
        window.dispatchEvent(
          new CustomEvent("crm:theme-changed", { detail: { theme: resolveEffectiveTheme(next) } })
        );
      }
    });

    const obs = new MutationObserver(() => updateThemeInspector());
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-bs-theme", "class"],
    });
    const menuEl = document.getElementById("layout-menu");
    if (menuEl) {
      obs.observe(menuEl, { attributes: true, attributeFilter: ["data-bs-theme"] });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initToast();
    bindNavigation();
    bindThemeSync();

    const initialHash = (window.location.hash || "#overview").replace(/^#/, "");
    activateView(VALID_VIEWS.includes(initialHash) ? initialHash : "overview", false);

    updateThemeInspector();
    refreshShellTelemetry(false);
    telemetryTimer = setInterval(() => refreshShellTelemetry(false), 12000);
  });

  window.AdsterraShell = {
    activateView,
    setTheme: setThemeMode,
    toggleSemiDark: toggleSemiDarkSidebar,
    toggleCollapse: toggleSidebarCollapse,
    pingApis: () => refreshShellTelemetry(true),
    testToast: () => showToast("Vuexy Notification System working cleanly"),
    toast: showToast,
    getTheme: () => resolveEffectiveTheme(getStoredThemeMode()),
    forceStopAll,
  };
})();
