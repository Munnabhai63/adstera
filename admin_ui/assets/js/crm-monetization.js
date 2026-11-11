/**
 * AdsterraFleet Vuexy CRM Monetization Controller — Component U4
 * Connects #view-monetization to Adsterra Funnel, Display Banner Vault,
 * Official API Sync, CPL Lead Bounties, SERP Queries, Smartlinks Copy & Synthetic Personas.
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 20000;
  let pollTimer = null;
  let isRefreshing = false;
  let lastCopyMessage = "";
  const copyTimers = new WeakMap();

  function viewEl() {
    return document.getElementById("view-monetization");
  }

  function isActive() {
    const v = viewEl();
    return Boolean(v && v.classList.contains("active"));
  }

  function toast(msg, type = "info") {
    if (window.CRM && typeof window.CRM.toast === "function") {
      window.CRM.toast(msg, type);
    }
  }

  function clearChildren(el) {
    while (el && el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function safeUrl(raw) {
    try {
      const u = new URL(String(raw || ""), window.location.origin);
      if (u.protocol === "http:" || u.protocol === "https:") {
        return u.href;
      }
    } catch (_) {}
    return "#";
  }

  function setActionButtonBusy(btn, busy, busyText) {
    if (!btn) return;
    if (busy) {
      if (!btn.dataset.origHtml) {
        btn.dataset.origHtml = btn.innerHTML;
      }
      btn.setAttribute("aria-disabled", "true");
      if (!btn.closest('[role="toolbar"]')) {
        btn.disabled = true;
      }
      btn.textContent = busyText || "Working...";
    } else {
      btn.removeAttribute("aria-disabled");
      btn.disabled = false;
      if (btn.dataset.origHtml) {
        btn.innerHTML = btn.dataset.origHtml;
      }
    }
  }

  function showBvStatus(msg, variant = "info") {
    const box = document.getElementById("u4BvActionStatus");
    if (!box) return;
    box.className = `alert alert-${variant} py-2 px-3 mb-4`;
    box.textContent = msg;
    box.classList.remove("d-none");
  }

  // --- Accessible Copy Button (Invoker Commands + Progressive Fallback) ---
  function legacyCopy(text) {
    const field = Object.assign(document.createElement("textarea"), { value: text });
    field.setAttribute("readonly", "");
    field.style.cssText = "position:fixed;inset-block-start:0;opacity:0";
    document.body.append(field);
    field.select();
    try {
      return document.execCommand("copy");
    } finally {
      field.remove();
    }
  }

  function reportCopy(button, ok) {
    const tip = button.nextElementSibling;
    if (!tip) return;
    clearTimeout(copyTimers.get(button));
    button.removeAttribute("data-copied");
    button.removeAttribute("data-failed");
    let message = ok ? "Copied" : "Copy failed";
    if (message === lastCopyMessage) {
      message += "\u00A0";
    }
    lastCopyMessage = message;
    tip.textContent = "";
    void button.offsetWidth;
    button.setAttribute(ok ? "data-copied" : "data-failed", "");
    requestAnimationFrame(() => {
      tip.textContent = message;
    });
    copyTimers.set(
      button,
      setTimeout(() => {
        button.removeAttribute("data-copied");
        button.removeAttribute("data-failed");
        tip.textContent = "";
      }, 2000)
    );
  }

  async function executeCopy(button, target) {
    if (!button || !target) return;
    const text = target.matches("input, textarea") ? target.value : (target.innerText || target.textContent || "").trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      reportCopy(button, true);
    } catch (_) {
      try {
        if (!legacyCopy(text)) {
          throw new Error("Copy failed");
        }
        reportCopy(button, true);
      } catch (_err) {
        reportCopy(button, false);
      }
    }
  }

  function bindCopyHandlers() {
    if ("CommandEvent" in window) {
      document.addEventListener(
        "command",
        (ev) => {
          if (ev.command && ev.command.startsWith("--copy")) {
            executeCopy(ev.source, ev.target);
          }
        },
        true
      );
    } else {
      document.addEventListener("click", (ev) => {
        const btn = ev.target.closest('button[command^="--copy"]');
        if (!btn) return;
        const targetId = btn.getAttribute("commandfor");
        const target = targetId ? document.getElementById(targetId) : null;
        if (target) executeCopy(btn, target);
      });
    }
  }

  // --- Accessible Toolbar Keyboard Roving Fallback ---
  function bindToolbarKeyboardFallback() {
    if ("focusGroup" in HTMLElement.prototype) return;
    document.querySelectorAll('#view-monetization [role="toolbar"]').forEach((bar) => {
      const items = Array.from(bar.querySelectorAll("button"));
      if (items.length === 0) return;
      items.forEach((b, idx) => {
        b.tabIndex = idx === 0 ? 0 : -1;
      });
      bar.addEventListener("focusin", (ev) => {
        const idx = items.indexOf(ev.target);
        if (idx >= 0) {
          items.forEach((b, i) => {
            b.tabIndex = i === idx ? 0 : -1;
          });
        }
      });
      bar.addEventListener("keydown", (ev) => {
        const cur = items.indexOf(document.activeElement);
        if (cur < 0) return;
        const rtl = getComputedStyle(bar).direction === "rtl";
        let nextIdx = null;
        if (ev.key === "ArrowRight") nextIdx = (cur + (rtl ? -1 : 1) + items.length) % items.length;
        else if (ev.key === "ArrowLeft") nextIdx = (cur + (rtl ? 1 : -1) + items.length) % items.length;
        else if (ev.key === "Home") nextIdx = 0;
        else if (ev.key === "End") nextIdx = items.length - 1;
        if (nextIdx !== null) {
          ev.preventDefault();
          items[nextIdx].focus();
        }
      });
    });
  }

  // --- Render Helpers ---
  function renderFunnel(funnelPayload, syncCount) {
    const d = funnelPayload?.data || {};
    const f = d.funnel || {};
    const hs = Array.isArray(d.recent_handshakes) ? d.recent_handshakes : [];

    const revEl = document.getElementById("u4KpiRevenue");
    const apiImpsEl = document.getElementById("u4KpiApiImps");
    const hsEl = document.getElementById("u4KpiHandshakes");
    const rateEl = document.getElementById("u4KpiRateBadge");
    const sessEl = document.getElementById("u4KpiSessions");

    if (revEl) revEl.textContent = String(f.api_revenue || "$0.000");
    if (apiImpsEl) {
      apiImpsEl.textContent = `${f.api_impressions || 0} Imps / ${f.api_clicks || 0} Clicks Counted`;
    }
    if (hsEl) hsEl.textContent = String(f.confirmed_handshakes || 0);
    if (rateEl) rateEl.textContent = String(f.handshake_success_rate || "100.0%");
    if (sessEl) sessEl.textContent = `${f.sessions_dispatched || 0} Sessions Dispatched`;

    // Update 5-stage Funnel Stepper states
    const sessCount = Number(f.sessions_dispatched || 0);
    const hsCount = Number(f.confirmed_handshakes || 0);
    const impsCount = Number(f.api_impressions || 0) + Number(syncCount || 0);
    let activeStage = 1;
    if (impsCount > 0) activeStage = 5;
    else if (hsCount > 0) activeStage = 4;
    else if (sessCount > 0) activeStage = 2;

    document.querySelectorAll("#u4FunnelStepper .u3-step-node").forEach((node) => {
      const n = Number(node.getAttribute("data-u4-stage") || 0);
      node.classList.remove("is-done", "is-active");
      if (n < activeStage) node.classList.add("is-done");
      else if (n === activeStage) node.classList.add("is-active");
    });

    const tbody = document.getElementById("u4HandshakesBody");
    if (!tbody) return;
    clearChildren(tbody);
    if (hs.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "No Adsterra network handshakes recorded yet. Run Verify Live Handshake above.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    hs.forEach((h) => {
      const tr = document.createElement("tr");
      const code = Number(h.status_code || 0);
      const isOk = [200, 301, 302, 307].includes(code);

      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(h.domain || "");
      tr.appendChild(thDom);

      const tdTs = document.createElement("td");
      tdTs.className = "font-monospace small tabular-nums";
      tdTs.textContent = String(h.ts || "");
      tr.appendChild(tdTs);

      const tdUrl = document.createElement("td");
      const codeEl = document.createElement("code");
      codeEl.className = "small";
      codeEl.textContent = String(h.ad_url || "");
      tdUrl.appendChild(codeEl);
      tr.appendChild(tdUrl);

      const tdStatus = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = isOk ? "badge bg-label-success tabular-nums" : "badge bg-label-danger tabular-nums";
      badge.textContent = isOk ? `HTTP ${code} OK` : `HTTP ${code}`;
      tdStatus.appendChild(badge);
      tr.appendChild(tdStatus);

      const tdLat = document.createElement("td");
      tdLat.className = "tabular-nums small";
      tdLat.textContent = `${h.latency_ms || 150} ms`;
      tr.appendChild(tdLat);

      const tdVerdict = document.createElement("td");
      const vBadge = document.createElement("span");
      vBadge.className = isOk ? "badge bg-label-success" : "badge bg-label-warning";
      vBadge.textContent = isOk ? "Verified" : "Pending";
      tdVerdict.appendChild(vBadge);
      tr.appendChild(tdVerdict);

      tbody.appendChild(tr);
    });
  }

  function createSlotCell(slotObj) {
    const td = document.createElement("td");
    if (!slotObj) {
      td.textContent = "—";
      return td;
    }
    const badge = document.createElement("span");
    const pid = slotObj.placement_id ? `#${slotObj.placement_id}` : "No ID";
    if (slotObj.configured) {
      badge.className = "badge bg-label-success me-1";
      badge.textContent = "LIVE";
      td.appendChild(badge);
      const meta = document.createElement("span");
      meta.className = "font-monospace small text-body-secondary";
      meta.textContent = `${pid} · ${slotObj.zone_key_preview || ""}`;
      td.appendChild(meta);
    } else {
      badge.className = "badge bg-label-warning me-1";
      badge.textContent = "Awaiting Code";
      td.appendChild(badge);
      const meta = document.createElement("span");
      meta.className = "font-monospace small text-body-secondary";
      meta.textContent = pid;
      td.appendChild(meta);
    }
    return td;
  }

  function renderBannerVault(payload) {
    const cfgCount = Number(payload?.configured_slots ?? 0);
    const totCount = Number(payload?.total_slots ?? 30);
    const pct = totCount > 0 ? Math.min(100, Math.round((cfgCount / totCount) * 100)) : 0;

    const kpiEl = document.getElementById("u4KpiBannerCoverage");
    const progEl = document.getElementById("u4BannerProgress");
    const sumBadge = document.getElementById("u4BvSummaryBadge");
    if (kpiEl) kpiEl.textContent = `${cfgCount} / ${totCount}`;
    if (sumBadge) sumBadge.textContent = `${cfgCount} / ${totCount} Configured`;
    if (progEl) {
      progEl.style.width = `${pct}%`;
      progEl.setAttribute("aria-valuenow", String(pct));
    }

    const tbody = document.getElementById("u4BannerBody");
    if (!tbody) return;
    clearChildren(tbody);

    const domains = Array.isArray(payload?.domains) ? payload.domains : [];
    if (domains.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.className = "text-center text-body-secondary py-5";
      td.textContent = "No display banner placements synced yet. Click 'Sync Placements'.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    domains.forEach((d) => {
      const slots = d.slots || {};
      const ready = Number(d.configured_count ?? 0);
      const total = Number(d.total_slots ?? 3);

      const tr = document.createElement("tr");
      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(d.domain || "");
      tr.appendChild(thDom);

      const tdId = document.createElement("td");
      tdId.className = "font-monospace small tabular-nums";
      tdId.textContent = d.adsterra_domain_id ? String(d.adsterra_domain_id) : "—";
      tr.appendChild(tdId);

      tr.appendChild(createSlotCell(slots.banner_728x90));
      tr.appendChild(createSlotCell(slots.banner_300x250));
      tr.appendChild(createSlotCell(slots.native_banner));

      const tdReady = document.createElement("td");
      const rBadge = document.createElement("span");
      rBadge.className =
        ready === total
          ? "badge bg-label-success tabular-nums"
          : ready > 0
            ? "badge bg-label-info tabular-nums"
            : "badge bg-label-warning tabular-nums";
      rBadge.textContent = `${ready} / ${total}`;
      tdReady.appendChild(rBadge);
      tr.appendChild(tdReady);

      tbody.appendChild(tr);
    });
  }

  function renderAdsterraSync(records) {
    const tbody = document.getElementById("u4SyncBody");
    if (!tbody) return;
    clearChildren(tbody);

    const list = Array.isArray(records) ? records : [];
    if (list.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 9;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "Click 'Sync Adsterra API' to fetch reconciled domain telemetry.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    list.forEach((r) => {
      const tr = document.createElement("tr");

      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(r.domain || "");
      tr.appendChild(thDom);

      const tdDate = document.createElement("td");
      tdDate.className = "tabular-nums small";
      tdDate.textContent = String(r.date || "");
      tr.appendChild(tdDate);

      const tdImps = document.createElement("td");
      tdImps.className = "tabular-nums";
      tdImps.textContent = String(r.api_impressions ?? 0);
      tr.appendChild(tdImps);

      const tdClicks = document.createElement("td");
      tdClicks.className = "tabular-nums fw-semibold";
      tdClicks.textContent = String(r.api_clicks ?? 0);
      tr.appendChild(tdClicks);

      const tdCtr = document.createElement("td");
      tdCtr.className = "tabular-nums";
      tdCtr.textContent = `${Number(r.api_ctr || 0).toFixed(2)}%`;
      tr.appendChild(tdCtr);

      const tdCpm = document.createElement("td");
      tdCpm.className = "tabular-nums";
      tdCpm.textContent = `$${Number(r.api_cpm || 0).toFixed(2)}`;
      tr.appendChild(tdCpm);

      const tdRev = document.createElement("td");
      tdRev.className = "tabular-nums fw-semibold text-success";
      tdRev.textContent = `$${Number(r.api_revenue || 0).toFixed(3)}`;
      tr.appendChild(tdRev);

      const tdLoc = document.createElement("td");
      tdLoc.className = "tabular-nums";
      tdLoc.textContent = String(r.local_impressions ?? 0);
      tr.appendChild(tdLoc);

      const disc = Number(r.discrepancy_pct || 0);
      const tdDisc = document.createElement("td");
      const dBadge = document.createElement("span");
      dBadge.className = Math.abs(disc) < 15 ? "badge bg-label-success tabular-nums" : "badge bg-label-warning tabular-nums";
      dBadge.textContent = `${disc > 0 ? "+" : ""}${disc.toFixed(1)}%`;
      tdDisc.appendChild(dBadge);
      tr.appendChild(tdDisc);

      tbody.appendChild(tr);
    });
  }

  function renderLiveAudit(payload) {
    if (!payload || payload.status !== "ok") return;
    const metaEl = document.getElementById("u4ZeroWasteMeta");
    const sum = payload.summary || {};
    if (metaEl) {
      metaEl.textContent = `Window: ${payload.start_date || ""} to ${payload.finish_date || ""} | Official Imps: ${sum.api_total_impressions || 0} | Clicks: ${sum.api_total_clicks || 0} | Avg CPM: $${Number(sum.api_avg_cpm || 0).toFixed(3)} | Server Sync: ${payload.db_last_update_time || "Live"}`;
    }

    const zwBody = document.getElementById("u4ZeroWasteBody");
    if (zwBody) {
      clearChildren(zwBody);
      const domList = Array.isArray(payload.by_domain) ? payload.by_domain : [];
      if (domList.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 7;
        td.className = "text-center text-body-secondary py-4";
        td.textContent = "No domain audit records returned.";
        tr.appendChild(td);
        zwBody.appendChild(tr);
      } else {
        domList.forEach((d) => {
          const tr = document.createElement("tr");

          const thDom = document.createElement("th");
          thDom.scope = "row";
          const domStrong = document.createElement("div");
          domStrong.className = "fw-semibold";
          domStrong.textContent = String(d.domain || "");
          const domSub = document.createElement("small");
          domSub.className = "text-body-secondary font-monospace";
          domSub.textContent = d.adsterra_domain_id ? `ID #${d.adsterra_domain_id}` : "";
          thDom.appendChild(domStrong);
          thDom.appendChild(domSub);
          tr.appendChild(thDom);

          const tdBeacons = document.createElement("td");
          tdBeacons.className = "tabular-nums small";
          tdBeacons.textContent = `${d.verified_beacons || 0} (${d.impression_beacons || 0} imp / ${d.click_beacons || 0} clk)`;
          tr.appendChild(tdBeacons);

          const tdApiImps = document.createElement("td");
          tdApiImps.className = "tabular-nums fw-bold";
          tdApiImps.textContent = String(d.api_impressions ?? 0);
          tr.appendChild(tdApiImps);

          const tdClicksCtr = document.createElement("td");
          tdClicksCtr.className = "tabular-nums";
          tdClicksCtr.textContent = `${d.api_clicks ?? 0} (${Number(d.api_ctr || 0).toFixed(2)}%)`;
          tr.appendChild(tdClicksCtr);

          const tdCpmRev = document.createElement("td");
          tdCpmRev.className = "tabular-nums";
          tdCpmRev.textContent = `$${Number(d.api_cpm || 0).toFixed(3)} / $${Number(d.api_revenue || 0).toFixed(3)}`;
          tr.appendChild(tdCpmRev);

          const tdRatio = document.createElement("td");
          const rBadge = document.createElement("span");
          const ratio = Number(d.count_ratio_pct || 0);
          rBadge.className = ratio >= 85 || d.api_impressions > 0 ? "badge bg-label-success tabular-nums" : "badge bg-label-info tabular-nums";
          rBadge.textContent = d.api_impressions > 0 ? `${ratio.toFixed(0)}% Counted` : "Queued";
          tdRatio.appendChild(rBadge);
          tr.appendChild(tdRatio);

          const tdDiag = document.createElement("td");
          const diagText = document.createElement("div");
          diagText.className = "small fw-medium";
          diagText.textContent = String(d.diagnosis || "");
          const actText = document.createElement("div");
          actText.className = "small text-success";
          actText.textContent = String(d.auto_action || "");
          tdDiag.appendChild(diagText);
          tdDiag.appendChild(actText);
          tr.appendChild(tdDiag);

          zwBody.appendChild(tr);
        });
      }
    }

    const plBody = document.getElementById("u4PlacementsBody");
    if (plBody) {
      clearChildren(plBody);
      const plList = Array.isArray(payload.by_placement) ? payload.by_placement : [];
      if (plList.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.className = "text-center text-body-secondary py-4";
        td.textContent = "No placement-level impressions recorded in this window.";
        tr.appendChild(td);
        plBody.appendChild(tr);
      } else {
        plList.forEach((p) => {
          const tr = document.createElement("tr");

          const thPid = document.createElement("th");
          thPid.scope = "row";
          thPid.className = "font-monospace small tabular-nums";
          thPid.textContent = `#${p.placement_id || ""}`;
          tr.appendChild(thPid);

          const tdLabel = document.createElement("td");
          tdLabel.className = "fw-semibold";
          tdLabel.textContent = String(p.label || "");
          tr.appendChild(tdLabel);

          const tdImps = document.createElement("td");
          tdImps.className = "tabular-nums";
          tdImps.textContent = String(p.impressions ?? 0);
          tr.appendChild(tdImps);

          const tdClicks = document.createElement("td");
          tdClicks.className = "tabular-nums";
          tdClicks.textContent = String(p.clicks ?? 0);
          tr.appendChild(tdClicks);

          const tdCtr = document.createElement("td");
          tdCtr.className = "tabular-nums";
          tdCtr.textContent = `${Number(p.ctr || 0).toFixed(2)}%`;
          tr.appendChild(tdCtr);

          const tdCpm = document.createElement("td");
          tdCpm.className = "tabular-nums fw-semibold";
          tdCpm.textContent = `$${Number(p.cpm || 0).toFixed(3)}`;
          tr.appendChild(tdCpm);

          const tdRev = document.createElement("td");
          tdRev.className = "tabular-nums text-success";
          tdRev.textContent = `$${Number(p.revenue || 0).toFixed(3)}`;
          tr.appendChild(tdRev);

          const tdRole = document.createElement("td");
          tdRole.className = "small text-body-secondary";
          tdRole.textContent = String(p.role_note || "");
          tr.appendChild(tdRole);

          plBody.appendChild(tr);
        });
      }
    }

    const fdBody = document.getElementById("u4FourDimBody");
    if (fdBody) {
      clearChildren(fdBody);
      const fdList = Array.isArray(payload.four_dimensions) ? payload.four_dimensions : [];
      if (fdList.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 7;
        td.className = "text-center text-body-secondary py-4";
        td.textContent = "No 4-Dimension session records logged yet.";
        tr.appendChild(td);
        fdBody.appendChild(tr);
      } else {
        fdList.forEach((f) => {
          const tr = document.createElement("tr");

          const thDim = document.createElement("th");
          thDim.scope = "row";
          const dimBadge = document.createElement("span");
          dimBadge.className = "badge bg-label-primary";
          dimBadge.textContent = String(f.dimension || "");
          thDim.appendChild(dimBadge);
          tr.appendChild(thDim);

          const tdVal = document.createElement("td");
          tdVal.className = "fw-semibold";
          tdVal.textContent = String(f.value || "");
          tr.appendChild(tdVal);

          const tdSess = document.createElement("td");
          tdSess.className = "tabular-nums";
          tdSess.textContent = String(f.sessions ?? 0);
          tr.appendChild(tdSess);

          const tdImps = document.createElement("td");
          tdImps.className = "tabular-nums";
          tdImps.textContent = String(f.impressions ?? 0);
          tr.appendChild(tdImps);

          const tdClks = document.createElement("td");
          tdClks.className = "tabular-nums";
          tdClks.textContent = String(f.clicks ?? 0);
          tr.appendChild(tdClks);

          const tdNote = document.createElement("td");
          tdNote.className = "small text-body-secondary";
          tdNote.textContent = String(f.lock_note || "");
          tr.appendChild(tdNote);

          const tdSt = document.createElement("td");
          const stBadge = document.createElement("span");
          stBadge.className = "badge bg-label-success";
          stBadge.textContent = String(f.status || "0% Leak Verified");
          tdSt.appendChild(stBadge);
          tr.appendChild(tdSt);

          fdBody.appendChild(tr);
        });
      }
    }
  }

  function renderLeads(payload) {
    const summary = payload?.summary || {};
    const leads = Array.isArray(payload?.leads) ? payload.leads : [];

    const kpiBounty = document.getElementById("u4KpiBounty");
    const kpiCount = document.getElementById("u4KpiLeadsCount");
    if (kpiBounty) kpiBounty.textContent = `$${Number(summary.estimated_bounty || 0).toFixed(2)}`;
    if (kpiCount) kpiCount.textContent = `${summary.today_leads || 0} Leads Recorded Today`;

    const tbody = document.getElementById("u4LeadsBody");
    if (!tbody) return;
    clearChildren(tbody);

    if (leads.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "No lead conversions recorded today.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    leads.forEach((l) => {
      const tr = document.createElement("tr");
      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(l.domain || "");
      tr.appendChild(thDom);

      const tdName = document.createElement("td");
      tdName.textContent = String(l.persona_name || "");
      tr.appendChild(tdName);

      const tdMail = document.createElement("td");
      tdMail.className = "small";
      tdMail.textContent = String(l.email || "");
      tr.appendChild(tdMail);

      const tdFields = document.createElement("td");
      tdFields.className = "tabular-nums";
      tdFields.textContent = `${l.fields_filled ?? 0} fields`;
      tr.appendChild(tdFields);

      const tdDwell = document.createElement("td");
      tdDwell.className = "tabular-nums";
      tdDwell.textContent = `${l.dwell_sec ?? 0}s`;
      tr.appendChild(tdDwell);

      const tdBounty = document.createElement("td");
      tdBounty.className = "tabular-nums fw-semibold text-success";
      tdBounty.textContent = `+$${Number(l.bounty_est || 0).toFixed(2)}`;
      tr.appendChild(tdBounty);

      const tdSt = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge bg-label-success";
      badge.textContent = String(l.status || "SUBMITTED").toUpperCase();
      tdSt.appendChild(badge);
      tr.appendChild(tdSt);

      tbody.appendChild(tr);
    });
  }

  function renderSerp(payload) {
    const queries = Array.isArray(payload?.queries) ? payload.queries : [];
    const tbody = document.getElementById("u4SerpBody");
    if (!tbody) return;
    clearChildren(tbody);

    if (queries.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "Click 'Refresh Organic Queries' to preview geo-matched queries.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    queries.forEach((q) => {
      const tr = document.createElement("tr");

      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(q.domain || "");
      tr.appendChild(thDom);

      const tdGeo = document.createElement("td");
      tdGeo.textContent = `${q.city || ""}, ${q.state || ""}`;
      tr.appendChild(tdGeo);

      const tdQ = document.createElement("td");
      tdQ.className = "fst-italic";
      tdQ.textContent = `"${String(q.query || "")}"`;
      tr.appendChild(tdQ);

      const tdEng = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge bg-label-info";
      badge.textContent = "Google Organic";
      tdEng.appendChild(badge);
      tr.appendChild(tdEng);

      tbody.appendChild(tr);
    });
  }

  function renderSmartlinks(matrix) {
    const tbody = document.getElementById("u4SmartlinksBody");
    if (!tbody) return;
    clearChildren(tbody);

    const items = Array.isArray(matrix) ? matrix : [];
    if (items.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "No Adsterra Direct Links loaded.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    items.forEach((item, idx) => {
      const tr = document.createElement("tr");
      const linkId = `u4SmartlinkVal-${idx}`;

      const thDom = document.createElement("th");
      thDom.scope = "row";
      thDom.textContent = String(item.domain || "");
      tr.appendChild(thDom);

      const tdCta = document.createElement("td");
      tdCta.textContent = String(item.cta || item.title || "Direct CTA");
      tr.appendChild(tdCta);

      const tdUrl = document.createElement("td");
      const code = document.createElement("code");
      code.id = linkId;
      code.className = "small";
      code.textContent = String(item.url || "");
      tdUrl.appendChild(code);
      tr.appendChild(tdUrl);

      const tdStatus = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge bg-label-success";
      badge.textContent = String(item.edge_status || "200 OK");
      tdStatus.appendChild(badge);
      tr.appendChild(tdStatus);

      const tdCopy = document.createElement("td");
      const wrap = document.createElement("span");
      wrap.className = "u4-copy";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-xs btn-label-secondary u4-copy-btn";
      btn.setAttribute("command", "--copy");
      btn.setAttribute("commandfor", linkId);
      btn.setAttribute("aria-label", `Copy ${item.domain || "domain"} smartlink URL`);

      const iconCopy = document.createElement("i");
      iconCopy.className = "icon-base ti tabler-copy icon-16px u4-icon-copy";
      iconCopy.setAttribute("aria-hidden", "true");
      const iconCheck = document.createElement("i");
      iconCheck.className = "icon-base ti tabler-check icon-16px u4-icon-check";
      iconCheck.setAttribute("aria-hidden", "true");

      btn.appendChild(iconCopy);
      btn.appendChild(iconCheck);

      const tip = document.createElement("span");
      tip.className = "u4-copy-tip";
      tip.setAttribute("role", "status");

      wrap.appendChild(btn);
      wrap.appendChild(tip);
      tdCopy.appendChild(wrap);
      tr.appendChild(tdCopy);

      tbody.appendChild(tr);
    });
  }

  function renderAccounts(payload) {
    const accs = Array.isArray(payload?.accounts) ? payload.accounts : [];
    const kpiCount = document.getElementById("u4KpiPersonaCount");
    if (kpiCount) kpiCount.textContent = `${accs.length} personas`;

    const tbody = document.getElementById("u4AccountsBody");
    if (!tbody) return;
    clearChildren(tbody);

    if (accs.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.className = "text-center text-body-secondary py-4";
      td.textContent = "No synthetic persona accounts found.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    // Never display password fields in DOM
    accs.slice(0, 20).forEach((a) => {
      const p = a.persona || {};
      const warmed = Boolean(a.warmed) || Number(a.cookies_count || 0) > 0;
      const tr = document.createElement("tr");

      const thEmail = document.createElement("th");
      thEmail.scope = "row";
      thEmail.textContent = String(a.email || "");
      tr.appendChild(thEmail);

      const tdName = document.createElement("td");
      tdName.textContent = String(p.full_name || a.name || "—");
      tr.appendChild(tdName);

      const tdGeo = document.createElement("td");
      tdGeo.textContent = p.city ? `${p.city}, ${p.state || ""} (${p.country || "IN"})` : (p.country === "US" ? "United States (US)" : "India (IN)");
      tr.appendChild(tdGeo);

      const tdCredit = document.createElement("td");
      tdCredit.className = "tabular-nums fw-semibold text-success";
      tdCredit.textContent = String(p.credit_score || 740);
      tr.appendChild(tdCredit);

      const tdSt = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = warmed ? "badge bg-label-success" : "badge bg-label-warning";
      badge.textContent = warmed ? "Warmed" : "Fresh";
      tdSt.appendChild(badge);
      tr.appendChild(tdSt);

      const tdCookies = document.createElement("td");
      tdCookies.className = "tabular-nums";
      tdCookies.textContent = String(a.cookies_count ?? (warmed ? 18 : 0));
      tr.appendChild(tdCookies);

      tbody.appendChild(tr);
    });
  }

  async function refreshLiveAudit(showToast = false) {
    const btn = document.getElementById("u4BtnRunLiveAudit");
    if (showToast) setActionButtonBusy(btn, true, "Auditing...");
    try {
      const resp = await fetch("/api/adsterra/live-audit", { cache: "no-store" });
      if (resp.ok) {
        const data = await resp.json();
        renderLiveAudit(data);
        if (showToast) {
          toast(`3-Layer Zero-Waste Audit synced (${data?.summary?.api_total_impressions || 0} official imps)`, "success");
        }
      }
    } catch (err) {
      if (showToast) toast(`Live audit error: ${err.message || err}`, "error");
    } finally {
      if (showToast) setActionButtonBusy(btn, false);
    }
  }

  // --- Data Refresh ---
  let initialAuditDone = false;
  async function refreshMonetization() {
    if (isRefreshing) return;
    isRefreshing = true;
    try {
      const [rFunnel, rBanners, rLeads, rSerp, rAccounts, rStatus, rAuto] = await Promise.allSettled([
        fetch("/api/adsterra/funnel", { cache: "no-store" }),
        fetch("/api/adsterra/banners", { cache: "no-store" }),
        fetch("/api/leads", { cache: "no-store" }),
        fetch("/api/serp/preview", { cache: "no-store" }),
        fetch("/api/accounts", { cache: "no-store" }),
        fetch("/api/status", { cache: "no-store" }),
        fetch("/api/autopublish/stats?domain=tazaloan", { cache: "no-store" }),
      ]);

      let syncRecords = [];
      if (rStatus.status === "fulfilled" && rStatus.value.ok) {
        const sData = await rStatus.value.json();
        syncRecords = Array.isArray(sData.adsterra_sync) ? sData.adsterra_sync : [];
        renderAdsterraSync(syncRecords);
      }

      if (rFunnel.status === "fulfilled" && rFunnel.value.ok) {
        renderFunnel(await rFunnel.value.json(), syncRecords.length);
      }
      if (rBanners.status === "fulfilled" && rBanners.value.ok) {
        renderBannerVault(await rBanners.value.json());
      }
      if (rLeads.status === "fulfilled" && rLeads.value.ok) {
        renderLeads(await rLeads.value.json());
      }
      if (rSerp.status === "fulfilled" && rSerp.value.ok) {
        renderSerp(await rSerp.value.json());
      }
      if (rAccounts.status === "fulfilled" && rAccounts.value.ok) {
        renderAccounts(await rAccounts.value.json());
      }
      if (rAuto.status === "fulfilled" && rAuto.value.ok) {
        const aData = await rAuto.value.json();
        renderSmartlinks(aData.adsterra_matrix);
      }
      if (!initialAuditDone) {
        initialAuditDone = true;
        refreshLiveAudit(false);
      }
    } catch (err) {
      toast(`Monetization telemetry error: ${err.message || err}`, "error");
    } finally {
      isRefreshing = false;
    }
  }

  // --- Actions ---
  async function runLiveHandshake() {
    const btn = document.getElementById("u4BtnRunFunnel");
    const domSel = document.getElementById("u4FunnelDomain");
    const box = document.getElementById("u4FunnelResultBox");
    const titleEl = document.getElementById("u4FunnelResultTitle");
    const metaEl = document.getElementById("u4FunnelResultMeta");
    const logsEl = document.getElementById("u4FunnelLogs");
    const domain = domSel ? domSel.value : "loanraaj.com";

    setActionButtonBusy(btn, true, "Verifying...");
    if (box) box.classList.remove("d-none");
    if (titleEl) titleEl.textContent = `Running live Chromium verification on ${domain}...`;
    if (metaEl) metaEl.textContent = new Date().toLocaleTimeString();
    if (logsEl) {
      clearChildren(logsEl);
      const line = document.createElement("div");
      line.textContent = "Launching anti-detect browser session for Adsterra outbound handshake...";
      logsEl.appendChild(line);
    }

    try {
      const resp = await fetch("/api/adsterra/test-handshake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const data = await resp.json().catch(() => ({}));
      clearChildren(logsEl);

      if (data.success) {
        if (titleEl) titleEl.textContent = `Verified on ${domain} (${data.duration_sec || "?"}s)`;
        (data.steps || []).forEach((s) => {
          const line = document.createElement("div");
          line.textContent = `OK: ${s}`;
          logsEl?.appendChild(line);
        });
        (data.handshakes || []).forEach((h) => {
          const line = document.createElement("div");
          line.className = "text-success fw-semibold";
          line.textContent = `HTTP ${h.status} -> ${h.url}`;
          logsEl?.appendChild(line);
        });
        toast(`Adsterra handshake verified for ${domain}`, "success");
        await refreshMonetization();
      } else {
        const msg = data.error || "Handshake verification returned an error";
        if (titleEl) titleEl.textContent = `Verification Notice: ${msg}`;
        toast(msg, "error");
      }
    } catch (err) {
      if (titleEl) titleEl.textContent = `Network error: ${err.message || err}`;
      toast("Network error running handshake verification", "error");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function syncOfficialAdsterraApi() {
    const btn = document.getElementById("u4BtnSyncApi");
    setActionButtonBusy(btn, true, "Syncing...");
    try {
      const resp = await fetch("/api/adsterra/sync", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "ok") {
        renderAdsterraSync(data.records);
        refreshLiveAudit(false);
        toast(`Adsterra API synced: ${data.synced_count || 0} records reconciled`, "success");
      } else {
        toast(data.error || "Adsterra API sync failed", "error");
      }
    } catch (err) {
      toast(`Sync error: ${err.message || err}`, "error");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function syncBannerPlacements() {
    const btn = document.getElementById("u4BtnSyncPlacements");
    if (btn?.getAttribute("aria-disabled") === "true") return;
    setActionButtonBusy(btn, true, "Syncing...");
    showBvStatus("Syncing Adsterra API placement IDs...", "info");
    try {
      const resp = await fetch("/api/adsterra/banners/sync", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "ok") {
        renderBannerVault(data.inventory);
        const count = data.sync?.placements_synced ?? 0;
        const msg = `Synced ${count} official Adsterra placements.`;
        showBvStatus(msg, "success");
        toast(msg, "success");
      } else {
        const msg = data.error || "Placement sync failed";
        showBvStatus(msg, "warning");
        toast(msg, "error");
      }
    } catch (err) {
      showBvStatus(`Sync error: ${err.message || err}`, "danger");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function deployBannerSlots(deployCf) {
    const btn = document.getElementById(deployCf ? "u4BtnDeployCf" : "u4BtnInjectLocal");
    if (btn?.getAttribute("aria-disabled") === "true") return;
    setActionButtonBusy(btn, true, deployCf ? "Deploying..." : "Injecting...");
    showBvStatus(
      deployCf ? "Injecting slots & deploying sites to Cloudflare Pages..." : "Injecting banner slots into local sites/...",
      "info"
    );
    try {
      const resp = await fetch("/api/adsterra/banners/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deploy: Boolean(deployCf) }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "ok") {
        const inj = data.inject || {};
        const cfOk = Array.isArray(inj.deploy_results) ? inj.deploy_results.filter((r) => r.ok).length : 0;
        const msg = deployCf
          ? `Scanned ${inj.files_scanned || 0} files, updated ${inj.files_updated || 0}, Cloudflare OK: ${cfOk}.`
          : `Scanned ${inj.files_scanned || 0} files, updated ${inj.files_updated || 0} locally.`;
        showBvStatus(msg, "success");
        toast(msg, "success");
      } else {
        const msg = data.error || "Banner deploy failed";
        showBvStatus(msg, "danger");
        toast(msg, "error");
      }
    } catch (err) {
      showBvStatus(`Deploy error: ${err.message || err}`, "danger");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  function validateSnippetInput(inputEl, forceTouch = false) {
    if (!inputEl) return false;
    if (forceTouch) inputEl.dataset.touched = "1";
    const val = inputEl.value.trim();
    const isValid = val.length >= 20;
    if (inputEl.dataset.touched === "1") {
      inputEl.classList.toggle("user-invalid-fallback", !isValid);
      inputEl.setAttribute("aria-invalid", isValid ? "false" : "true");
    }
    return isValid;
  }

  async function submitBannerSnippetForm(ev) {
    ev.preventDefault();
    const domEl = document.getElementById("u4BvDomain");
    const slotEl = document.getElementById("u4BvSlot");
    const snipEl = document.getElementById("u4BvSnippet");
    const btn = document.getElementById("u4BtnSaveSnippet");

    if (!validateSnippetInput(snipEl, true)) {
      snipEl?.focus();
      showBvStatus("Paste a valid Adsterra snippet (minimum 20 characters).", "warning");
      return;
    }

    const domain = domEl ? domEl.value : "loanraaj.com";
    const slot = slotEl ? slotEl.value : "auto";
    const snippet = snipEl.value.trim();

    setActionButtonBusy(btn, true, "Saving...");
    try {
      const resp = await fetch("/api/adsterra/banners/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, slot, snippet }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "ok") {
        snipEl.value = "";
        snipEl.dataset.touched = "0";
        snipEl.classList.remove("user-invalid-fallback");
        snipEl.removeAttribute("aria-invalid");
        renderBannerVault(data.inventory);
        const savedList = (data.saved || []).map((x) => x.slot).join(", ");
        const msg = `Saved [${savedList}] for ${domain}. Run Inject Local HTML / Deploy when ready.`;
        showBvStatus(msg, "success");
        toast(msg, "success");
      } else {
        const msg = data.error || "Invalid Adsterra banner snippet";
        showBvStatus(msg, "danger");
        toast(msg, "error");
      }
    } catch (err) {
      showBvStatus(`Save failed: ${err.message || err}`, "danger");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function simulateLead() {
    const btn = document.getElementById("u4BtnSimLead");
    setActionButtonBusy(btn, true, "Submitting...");
    try {
      const resp = await fetch("/api/leads/simulate", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.success && data.lead) {
        toast(`CPL Lead logged (+$${Number(data.lead.bounty_est || 0).toFixed(2)})`, "success");
        await refreshMonetization();
      } else {
        toast(data.error || "Lead simulation failed", "error");
      }
    } catch (err) {
      toast(`Lead simulation error: ${err.message || err}`, "error");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function refreshSerpQueries() {
    const btn = document.getElementById("u4BtnRefreshSerp");
    setActionButtonBusy(btn, true, "Generating...");
    try {
      const resp = await fetch("/api/serp/preview", { cache: "no-store" });
      if (resp.ok) {
        renderSerp(await resp.json());
        toast("Refreshed organic geo-matched SERP queries", "success");
      }
    } catch (err) {
      toast(`SERP refresh failed: ${err.message || err}`, "error");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  async function generatePersonaAccount() {
    const btn = document.getElementById("u4BtnGenAccount");
    setActionButtonBusy(btn, true, "Generating...");
    try {
      const resp = await fetch("/api/accounts/generate", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.success && data.account) {
        toast(`Persona created: ${data.account.email}`, "success");
        await refreshMonetization();
      } else {
        toast(data.error || "Failed to create synthetic persona", "error");
      }
    } catch (err) {
      toast(`Account error: ${err.message || err}`, "error");
    } finally {
      setActionButtonBusy(btn, false);
    }
  }

  // --- Accessible Tabs (Keyboard Arrow Navigation + hidden="until-found") ---
  function activateTab(tabName) {
    const tabs = Array.from(document.querySelectorAll('#u4StreamTabs [role="tab"]'));
    tabs.forEach((t) => {
      const selected = t.getAttribute("data-u4-tab") === tabName;
      t.classList.toggle("active", selected);
      t.setAttribute("aria-selected", selected ? "true" : "false");
      t.tabIndex = selected ? 0 : -1;
      const panelId = t.getAttribute("aria-controls");
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

  function bindTabs() {
    const tabList = document.getElementById("u4StreamTabs");
    if (!tabList) return;
    const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
    tabs.forEach((btn, idx) => {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-u4-tab") || "handshakes";
        activateTab(name);
      });
      btn.addEventListener("keydown", (ev) => {
        let next = null;
        if (ev.key === "ArrowRight") next = (idx + 1) % tabs.length;
        else if (ev.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
        else if (ev.key === "Home") next = 0;
        else if (ev.key === "End") next = tabs.length - 1;
        if (next !== null) {
          ev.preventDefault();
          const targetBtn = tabs[next];
          activateTab(targetBtn.getAttribute("data-u4-tab") || "handshakes");
          targetBtn.focus();
        }
      });
    });

    document.querySelectorAll("#view-monetization .u4-tab-panel").forEach((panel) => {
      panel.addEventListener("beforematch", () => {
        const ctrlBtn = document.querySelector(`#u4StreamTabs [aria-controls="${panel.id}"]`);
        const name = ctrlBtn?.getAttribute("data-u4-tab");
        if (name) activateTab(name);
      });
    });
  }

  function bindEvents() {
    bindTabs();
    bindCopyHandlers();
    bindToolbarKeyboardFallback();

    document.getElementById("u4BtnRunFunnel")?.addEventListener("click", runLiveHandshake);
    document.getElementById("u4BtnSyncApi")?.addEventListener("click", syncOfficialAdsterraApi);
    document.getElementById("u4BtnRunLiveAudit")?.addEventListener("click", () => refreshLiveAudit(true));
    document.getElementById("u4BtnSyncPlacements")?.addEventListener("click", syncBannerPlacements);
    document.getElementById("u4BtnInjectLocal")?.addEventListener("click", () => deployBannerSlots(false));
    document.getElementById("u4BtnDeployCf")?.addEventListener("click", () => deployBannerSlots(true));
    document.getElementById("u4BtnRefreshAll")?.addEventListener("click", refreshMonetization);
    document.getElementById("u4BtnSimLead")?.addEventListener("click", simulateLead);
    document.getElementById("u4BtnRefreshSerp")?.addEventListener("click", refreshSerpQueries);
    document.getElementById("u4BtnGenAccount")?.addEventListener("click", generatePersonaAccount);

    const form = document.getElementById("u4BannerForm");
    const snip = document.getElementById("u4BvSnippet");
    if (form) form.addEventListener("submit", submitBannerSnippetForm);
    if (snip) {
      snip.addEventListener("blur", () => validateSnippetInput(snip, true));
      snip.addEventListener("input", () => {
        if (snip.dataset.touched === "1") validateSnippetInput(snip, false);
      });
    }

    window.addEventListener("crm:view-activated", (ev) => {
      if (ev.detail && ev.detail.view === "monetization") {
        refreshMonetization();
      }
    });
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (isActive() && document.visibilityState === "visible") {
        refreshMonetization();
      }
    }, POLL_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    startPolling();
    if (isActive() || window.location.hash === "#monetization") {
      refreshMonetization();
    }
  });
})();
