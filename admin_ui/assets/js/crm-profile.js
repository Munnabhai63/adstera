/**
 * Component U2.5 — Operator Profile, Auth Gate, Notification Bell & Connections Vault
 */
(function () {
  "use strict";

  const TAB_MAP = {
    account: "u25TabAccount",
    security: "u25TabSecurity",
    connections: "u25TabConnections",
    alerts: "u25TabAlerts",
  };

  let currentProfile = null;
  let pollTimer = null;
  const flaggedInvalid = new WeakSet();
  const announcedInvalid = new WeakSet();
  let announcerEl = null;
  let announceTimer = null;
  let lastAnnouncedEl = null;

  function el(id) {
    return document.getElementById(id);
  }

  function toast(msg, type) {
    if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
      window.AdsterraShell.toast(msg, type || "success");
    }
  }

  function formatRelativeTime(tsStr) {
    if (!tsStr) return "just now";
    const norm = tsStr.includes("T") ? tsStr : tsStr.replace(" ", "T") + "Z";
    const dt = new Date(norm);
    if (Number.isNaN(dt.getTime())) return tsStr.slice(0, 16);
    const diffSec = Math.max(0, Math.round((Date.now() - dt.getTime()) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  }

  function levelBadgeMeta(level) {
    switch (String(level || "INFO").toUpperCase()) {
      case "CRITICAL":
        return { cls: "bg-label-danger", icon: "tabler-alert-octagon" };
      case "WARNING":
        return { cls: "bg-label-warning", icon: "tabler-alert-triangle" };
      case "SUCCESS":
        return { cls: "bg-label-success", icon: "tabler-circle-check" };
      default:
        return { cls: "bg-label-info", icon: "tabler-info-circle" };
    }
  }

  // Accessible :user-invalid ARIA sync + polite live region announcer
  function ensureAnnouncer() {
    if (!announcerEl) {
      announcerEl = document.createElement("div");
      announcerEl.setAttribute("aria-live", "polite");
      announcerEl.className = "visually-hidden";
      document.body.appendChild(announcerEl);
    }
    return announcerEl;
  }

  function linkErrorDesc(input, shown) {
    const errId = input.dataset ? input.dataset.error : "";
    if (!errId) return;
    const ids = (input.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter((id) => id && id !== errId);
    if (shown) ids.push(errId);
    if (ids.length) input.setAttribute("aria-describedby", ids.join(" "));
    else input.removeAttribute("aria-describedby");
  }

  function syncFieldAria(input, announce) {
    if (!input || !input.matches || !input.matches("input, textarea, select")) return;
    const invalid = input.matches(":user-invalid");
    if (invalid) {
      input.setAttribute("aria-invalid", "true");
      linkErrorDesc(input, true);
      flaggedInvalid.add(input);
      if (announce && !announcedInvalid.has(input)) {
        announcedInvalid.add(input);
        const errNode = input.dataset.error ? el(input.dataset.error) : null;
        if (errNode) {
          const live = ensureAnnouncer();
          clearTimeout(announceTimer);
          live.textContent = "";
          lastAnnouncedEl = input;
          announceTimer = setTimeout(() => {
            live.textContent = errNode.textContent.trim();
          }, 350);
        }
      }
    } else if (flaggedInvalid.has(input) || input.getAttribute("aria-invalid") !== "true") {
      input.setAttribute("aria-invalid", "false");
      linkErrorDesc(input, false);
      flaggedInvalid.delete(input);
      announcedInvalid.delete(input);
      if (lastAnnouncedEl === input && announcerEl) {
        clearTimeout(announceTimer);
        announcerEl.textContent = "";
      }
    }
  }

  function initAccessibleValidation(form) {
    if (!form) return;
    form.querySelectorAll("input, textarea, select").forEach((inp) => {
      inp.setAttribute("aria-invalid", "false");
    });
    form.addEventListener("blur", (e) => syncFieldAria(e.target, true), true);
    form.addEventListener("input", (e) => {
      if (e.target && e.target.hasAttribute("aria-invalid")) syncFieldAria(e.target, false);
    });
    form.addEventListener("invalid", (e) => {
      announcedInvalid.add(e.target);
      syncFieldAria(e.target, false);
    }, true);
  }

  function activateProfileTab(tabKey) {
    const targetKey = TAB_MAP[tabKey] ? tabKey : "account";
    const tabBtns = document.querySelectorAll("#u25ProfileTabs [role='tab']");
    tabBtns.forEach((btn) => {
      const isSelected = btn.dataset.u25Tab === targetKey;
      btn.classList.toggle("active", isSelected);
      btn.setAttribute("aria-selected", String(isSelected));
      btn.setAttribute("tabindex", isSelected ? "0" : "-1");
    });
    Object.entries(TAB_MAP).forEach(([k, panelId]) => {
      const panel = el(panelId);
      if (panel) panel.hidden = k !== targetKey;
    });
  }

  function renderNotificationItem(item, compact) {
    const li = document.createElement("li");
    li.className = "list-group-item list-group-item-action" + (item.read ? " opacity-75" : "");
    const row = document.createElement("div");
    row.className = "d-flex align-items-start gap-3";

    const meta = levelBadgeMeta(item.level);
    const avWrap = document.createElement("div");
    avWrap.className = "flex-shrink-0";
    const avBox = document.createElement("span");
    avBox.className = `avatar-initial rounded-circle d-inline-flex align-items-center justify-content-center ${meta.cls}`;
    avBox.style.width = compact ? "34px" : "38px";
    avBox.style.height = compact ? "34px" : "38px";
    const icon = document.createElement("i");
    icon.className = `icon-base ti ${meta.icon} icon-18px`;
    avBox.appendChild(icon);
    avWrap.appendChild(avBox);

    const body = document.createElement("div");
    body.className = "flex-grow-1 min-w-0";
    const titleEl = document.createElement("h6");
    titleEl.className = "small mb-1 fw-semibold text-truncate";
    titleEl.textContent = item.title || "System Notification";
    const msgEl = document.createElement("small");
    msgEl.className = "mb-1 d-block text-body text-break";
    msgEl.textContent = item.message || "";
    const footEl = document.createElement("small");
    footEl.className = "text-body-secondary";
    footEl.textContent = `${item.domain || "fleet"} · ${formatRelativeTime(item.ts)}`;
    body.appendChild(titleEl);
    body.appendChild(msgEl);
    body.appendChild(footEl);

    const actions = document.createElement("div");
    actions.className = "flex-shrink-0 d-flex align-items-center gap-2";
    if (!item.read) {
      const dotBtn = document.createElement("button");
      dotBtn.type = "button";
      dotBtn.className = "btn btn-sm btn-icon btn-text-primary rounded-pill";
      dotBtn.title = "Mark notification as read";
      dotBtn.setAttribute("aria-label", "Mark notification as read");
      const dot = document.createElement("span");
      dot.className = "badge badge-dot bg-primary";
      dotBtn.appendChild(dot);
      dotBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        markNotificationsRead([item.id], false);
      });
      actions.appendChild(dotBtn);
    }

    row.appendChild(avWrap);
    row.appendChild(body);
    row.appendChild(actions);
    li.appendChild(row);
    li.addEventListener("click", () => {
      if (!item.read) markNotificationsRead([item.id], false);
      if (window.AdsterraShell) window.AdsterraShell.activateView("profile");
      activateProfileTab("alerts");
    });
    return li;
  }

  function applyNotificationsPayload(data) {
    const items = Array.isArray(data.items) ? data.items : [];
    const unread = Number(data.unread_count || 0);

    const dot = el("shellNotifDot");
    const badge = el("shellNotifBadge");
    const tabCount = el("u25TabAlertCount");
    if (dot) dot.classList.toggle("d-none", unread <= 0);
    if (badge) badge.textContent = `${unread} New`;
    if (tabCount) {
      tabCount.textContent = String(unread);
      tabCount.classList.toggle("d-none", unread <= 0);
    }

    const navList = el("shellNotifList");
    if (navList) {
      navList.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "list-group-item py-4 text-center text-body-secondary small";
        empty.textContent = "All clear — zero active alerts.";
        navList.appendChild(empty);
      } else {
        items.slice(0, 6).forEach((it) => navList.appendChild(renderNotificationItem(it, true)));
      }
    }

    const fullList = el("u25FullAlertsList");
    if (fullList) {
      fullList.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "list-group-item py-4 text-center text-body-secondary small";
        empty.textContent = "No alerts recorded yet.";
        fullList.appendChild(empty);
      } else {
        items.forEach((it) => fullList.appendChild(renderNotificationItem(it, false)));
      }
    }
  }

  async function refreshNotifications() {
    try {
      const res = await fetch("/api/notifications", { cache: "no-store" });
      if (res.status === 401) {
        window.location.href = "/crm/login";
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      applyNotificationsPayload(data);
    } catch (_) {}
  }

  async function markNotificationsRead(ids, markAll) {
    try {
      const res = await fetch("/api/notifications/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(markAll ? { all: true } : { ids }),
      });
      if (!res.ok) return;
      const data = await res.json();
      applyNotificationsPayload(data);
      if (markAll) toast("All notifications marked as read.", "success");
    } catch (_) {}
  }

  function syncAvatarChoiceButtons(avatarPath) {
    const input = el("u25AvatarInput");
    if (input) input.value = avatarPath;
    document.querySelectorAll("#u25AvatarPicker .u25-avatar-choice").forEach((btn) => {
      const active = btn.dataset.avatar === avatarPath;
      btn.setAttribute("aria-pressed", String(active));
    });
  }

  function renderConnections(connections) {
    const grid = el("u25ConnectionsGrid");
    if (!grid) return;
    grid.replaceChildren();
    (connections || []).forEach((conn) => {
      const col = document.createElement("div");
      col.className = "col-12 col-lg-6";
      const card = document.createElement("div");
      card.className = "border rounded p-3 d-flex flex-wrap flex-sm-nowrap align-items-center justify-content-between gap-3 h-100";

      const left = document.createElement("div");
      left.className = "d-flex align-items-center gap-3 min-w-0";
      const av = document.createElement("span");
      av.className = `avatar-initial rounded bg-label-${conn.color || "primary"} d-inline-flex align-items-center justify-content-center flex-shrink-0`;
      av.style.width = "40px";
      av.style.height = "40px";
      const ic = document.createElement("i");
      ic.className = `icon-base ti ${conn.icon || "tabler-plug"} icon-20px`;
      av.appendChild(ic);

      const meta = document.createElement("div");
      meta.className = "min-w-0";
      const h = document.createElement("h6");
      h.className = "mb-0 text-truncate";
      h.textContent = conn.name;
      const sub = document.createElement("small");
      sub.className = "text-body-secondary d-block text-truncate";
      sub.textContent = `${conn.category} · ${conn.detail}`;
      meta.appendChild(h);
      meta.appendChild(sub);
      left.appendChild(av);
      left.appendChild(meta);

      const right = document.createElement("div");
      right.className = "d-flex flex-column align-items-end gap-1 flex-shrink-0";
      const badge = document.createElement("span");
      badge.className = `badge ${conn.configured ? "bg-label-success" : "bg-label-warning"}`;
      badge.textContent = conn.status_label || (conn.configured ? "Ready" : "Pending");
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "btn btn-xs btn-label-secondary";
      openBtn.textContent = "Open";
      openBtn.addEventListener("click", () => {
        if (window.AdsterraShell && conn.target_view) {
          window.AdsterraShell.activateView(conn.target_view);
        }
      });
      right.appendChild(badge);
      right.appendChild(openBtn);

      card.appendChild(left);
      card.appendChild(right);
      col.appendChild(card);
      grid.appendChild(col);
    });
  }

  function renderSessions(sessions) {
    const wrap = el("u25ActiveSessionsList");
    if (!wrap) return;
    wrap.replaceChildren();
    if (!sessions || !sessions.length) {
      const p = document.createElement("p");
      p.className = "text-body-secondary small mb-0";
      p.textContent = "No active login cookies yet (Open Localhost Mode active).";
      wrap.appendChild(p);
      return;
    }
    const ul = document.createElement("ul");
    ul.className = "list-unstyled mb-0 d-flex flex-column gap-2";
    sessions.forEach((sess) => {
      const li = document.createElement("li");
      li.className = "d-flex justify-content-between align-items-center border rounded p-2 gap-2";
      const left = document.createElement("div");
      left.className = "min-w-0";
      const ua = document.createElement("div");
      ua.className = "small fw-semibold text-truncate";
      ua.textContent = sess.user_agent || "Browser Session";
      const ts = document.createElement("small");
      ts.className = "text-body-secondary";
      ts.textContent = `Started ${formatRelativeTime(sess.created_at)}`;
      left.appendChild(ua);
      left.appendChild(ts);

      const badge = document.createElement("span");
      badge.className = `badge ${sess.is_current ? "bg-label-success" : "bg-label-secondary"}`;
      badge.textContent = sess.is_current ? "Current" : "Active";
      li.appendChild(left);
      li.appendChild(badge);
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
  }

  function applyProfilePayload(payload) {
    const prof = payload.profile || {};
    currentProfile = prof;

    if (el("shellNavUserAvatar")) el("shellNavUserAvatar").src = prof.avatar;
    if (el("shellNavMenuAvatar")) el("shellNavMenuAvatar").src = prof.avatar;
    if (el("shellNavUserName")) el("shellNavUserName").textContent = prof.display_name || "Master Operator";
    if (el("shellNavUserRole")) el("shellNavUserRole").textContent = prof.role || "Lead Publisher Admin";

    if (el("u25ProfileBannerAvatar")) el("u25ProfileBannerAvatar").src = prof.avatar;
    if (el("u25ProfileBannerName")) el("u25ProfileBannerName").textContent = prof.display_name || "Master Operator";
    if (el("u25ProfileBannerRole")) el("u25ProfileBannerRole").textContent = prof.role || "";
    if (el("u25ProfileBannerOrg")) el("u25ProfileBannerOrg").textContent = prof.organization || "";
    if (el("u25ProfileBannerLocation")) el("u25ProfileBannerLocation").textContent = prof.location || "";

    const lockBadge = el("u25LockStateBadge");
    if (lockBadge) {
      if (prof.require_login) {
        lockBadge.className = "badge bg-label-primary";
        lockBadge.textContent = "Protected · Sign-In Gate ON";
      } else if (prof.has_password) {
        lockBadge.className = "badge bg-label-info";
        lockBadge.textContent = "Password Ready · Quick Lock Enabled";
      } else {
        lockBadge.className = "badge bg-label-success";
        lockBadge.textContent = "Unlocked · Localhost Open";
      }
    }

    if (el("u25DisplayName")) el("u25DisplayName").value = prof.display_name || "";
    if (el("u25Email")) el("u25Email").value = prof.email || "";
    if (el("u25Role")) el("u25Role").value = prof.role || "";
    if (el("u25Organization")) el("u25Organization").value = prof.organization || "";
    if (el("u25Location")) el("u25Location").value = prof.location || "";
    if (el("u25Bio")) el("u25Bio").value = prof.bio || "";
    syncAvatarChoiceButtons(prof.avatar || "/crm-assets/img/avatars/1.png");

    if (el("u25SummaryAuthMode")) el("u25SummaryAuthMode").textContent = prof.require_login ? "Sign-In Gate ON" : "Open Localhost";
    if (el("u25SummaryPasswordStatus")) el("u25SummaryPasswordStatus").textContent = prof.has_password ? "Configured (PBKDF2)" : "Not Set";
    if (el("u25SummarySessionsCount")) el("u25SummarySessionsCount").textContent = String((payload.sessions || []).length);
    if (el("u25SummaryUpdatedAt")) el("u25SummaryUpdatedAt").textContent = formatRelativeTime(prof.updated_at);

    const hasPw = Boolean(prof.has_password);
    if (el("u25CurrentPwWrap")) el("u25CurrentPwWrap").classList.toggle("d-none", !hasPw);
    if (el("u25CurrentPassword")) el("u25CurrentPassword").required = hasPw;
    if (el("u25ClearPasswordBtn")) el("u25ClearPasswordBtn").classList.toggle("d-none", !hasPw);
    if (el("u25RequireLoginSwitch")) el("u25RequireLoginSwitch").checked = Boolean(prof.require_login);

    renderConnections(payload.connections || []);
    renderSessions(payload.sessions || []);
  }

  async function refreshProfile() {
    try {
      const res = await fetch("/api/profile", { cache: "no-store" });
      if (res.status === 401) {
        window.location.href = "/crm/login";
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      if (data.ok) applyProfilePayload(data);
    } catch (_) {}
  }

  async function handleLogout() {
    try {
      const res = await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await res.json();
      window.location.href = data.redirect || "/crm/login";
    } catch (_) {
      window.location.href = "/crm/login";
    }
  }

  function bindTabsAndDeepLinks() {
    const tabList = el("u25ProfileTabs");
    if (tabList) {
      const tabs = Array.from(tabList.querySelectorAll("[role='tab']"));
      tabs.forEach((btn, idx) => {
        btn.addEventListener("click", () => activateProfileTab(btn.dataset.u25Tab));
        btn.addEventListener("keydown", (e) => {
          let nextIdx = -1;
          if (e.key === "ArrowRight") nextIdx = (idx + 1) % tabs.length;
          else if (e.key === "ArrowLeft") nextIdx = (idx - 1 + tabs.length) % tabs.length;
          else if (e.key === "Home") nextIdx = 0;
          else if (e.key === "End") nextIdx = tabs.length - 1;
          if (nextIdx >= 0) {
            e.preventDefault();
            tabs[nextIdx].focus();
            activateProfileTab(tabs[nextIdx].dataset.u25Tab);
          }
        });
      });
    }

    document.addEventListener("click", (e) => {
      const trigger = e.target.closest("[data-crm-view='profile'][data-u25-tab]");
      if (trigger) {
        activateProfileTab(trigger.dataset.u25Tab);
      }
    });
  }

  function bindFormsAndActions() {
    document.querySelectorAll("#u25AvatarPicker .u25-avatar-choice").forEach((btn) => {
      btn.addEventListener("click", () => syncAvatarChoiceButtons(btn.dataset.avatar));
    });

    document.querySelectorAll(".u25-pw-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const inp = el(btn.dataset.target);
        if (!inp) return;
        const show = inp.type === "password";
        inp.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", String(show));
        const ic = btn.querySelector("i");
        if (ic) ic.className = show ? "icon-base ti tabler-eye icon-18px" : "icon-base ti tabler-eye-off icon-18px";
      });
    });

    const profileForm = el("u25ProfileForm");
    if (profileForm) {
      initAccessibleValidation(profileForm);
      profileForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!profileForm.checkValidity()) {
          const bad = profileForm.querySelector(":invalid");
          if (bad) bad.focus();
          return;
        }
        const saveBtn = el("u25SaveProfileBtn");
        if (saveBtn) saveBtn.disabled = true;
        try {
          const body = {
            display_name: el("u25DisplayName").value,
            email: el("u25Email").value,
            role: el("u25Role").value,
            organization: el("u25Organization").value,
            location: el("u25Location").value,
            bio: el("u25Bio").value,
            avatar: el("u25AvatarInput").value,
          };
          const res = await fetch("/api/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          const data = await res.json();
          if (data.ok) {
            await refreshProfile();
            toast(data.msg || "Operator profile saved.", "success");
          } else {
            toast(data.error || "Could not save profile.", "error");
          }
        } finally {
          if (saveBtn) saveBtn.disabled = false;
        }
      });
    }

    const reloadBtn = el("u25ReloadProfileBtn");
    if (reloadBtn) {
      reloadBtn.addEventListener("click", () => refreshProfile());
    }

    const pwForm = el("u25PasswordForm");
    if (pwForm) {
      initAccessibleValidation(pwForm);
      const newPw = el("u25NewPassword");
      const confPw = el("u25ConfirmPassword");
      if (confPw && newPw) {
        confPw.addEventListener("input", () => {
          confPw.setCustomValidity(confPw.value && confPw.value !== newPw.value ? "Passwords do not match" : "");
          syncFieldAria(confPw, false);
        });
      }
      pwForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (confPw && newPw) {
          confPw.setCustomValidity(confPw.value !== newPw.value ? "Passwords do not match" : "");
        }
        if (!pwForm.checkValidity()) {
          const bad = pwForm.querySelector(":invalid");
          if (bad) bad.focus();
          return;
        }
        const saveBtn = el("u25SavePasswordBtn");
        if (saveBtn) saveBtn.disabled = true;
        try {
          const res = await fetch("/api/profile/password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              current_password: el("u25CurrentPassword") ? el("u25CurrentPassword").value : "",
              new_password: newPw.value,
              confirm_password: confPw.value,
            }),
          });
          const data = await res.json();
          if (data.ok) {
            pwForm.reset();
            await refreshProfile();
            toast(data.msg || "Password updated.", "success");
          } else {
            toast(data.error || "Password update failed.", "error");
          }
        } finally {
          if (saveBtn) saveBtn.disabled = false;
        }
      });
    }

    const clearPwBtn = el("u25ClearPasswordBtn");
    if (clearPwBtn) {
      clearPwBtn.addEventListener("click", async () => {
        const curPw = el("u25CurrentPassword") ? el("u25CurrentPassword").value : "";
        if (!curPw) {
          toast("Enter Current Password first to remove password lock.", "error");
          if (el("u25CurrentPassword")) el("u25CurrentPassword").focus();
          return;
        }
        const res = await fetch("/api/profile/password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "clear_password", current_password: curPw }),
        });
        const data = await res.json();
        if (data.ok) {
          if (el("u25PasswordForm")) el("u25PasswordForm").reset();
          await refreshProfile();
          toast(data.msg || "Password removed.", "success");
        } else {
          toast(data.error || "Failed to remove password.", "error");
        }
      });
    }

    const gateBtn = el("u25ApplyGateBtn");
    if (gateBtn) {
      gateBtn.addEventListener("click", async () => {
        const sw = el("u25RequireLoginSwitch");
        const enabled = Boolean(sw && sw.checked);
        const res = await fetch("/api/profile/password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "toggle_gate", require_login: enabled }),
        });
        const data = await res.json();
        if (data.ok) {
          await refreshProfile();
          toast(data.msg || "Access policy updated.", "success");
        } else {
          if (sw && currentProfile) sw.checked = Boolean(currentProfile.require_login);
          toast(data.error || "Could not update Sign-In Gate.", "error");
        }
      });
    }

    ["shellLogoutBtn", "u25LockNowBtn", "u25LockSessionBtn2"].forEach((id) => {
      const btn = el(id);
      if (btn) btn.addEventListener("click", handleLogout);
    });

    const markAllNav = el("shellNotifMarkAllBtn");
    if (markAllNav) markAllNav.addEventListener("click", () => markNotificationsRead([], true));
    const markAllTab = el("u25MarkAllReadBtn2");
    if (markAllTab) markAllTab.addEventListener("click", () => markNotificationsRead([], true));

    const viewAllBtn = el("shellNotifViewAllBtn");
    if (viewAllBtn) {
      viewAllBtn.addEventListener("click", () => {
        if (window.AdsterraShell) window.AdsterraShell.activateView("profile");
        activateProfileTab("alerts");
      });
    }

    const testAlertBtn = el("u25TestAlertBtn");
    if (testAlertBtn) {
      testAlertBtn.addEventListener("click", async () => {
        const res = await fetch("/api/notifications/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        if (res.ok) {
          const data = await res.json();
          applyNotificationsPayload(data);
          toast("Live alert logged and pushed to Notification Bell.", "success");
        }
      });
    }

    const refreshConnBtn = el("u25RefreshConnectionsBtn");
    if (refreshConnBtn) refreshConnBtn.addEventListener("click", refreshProfile);
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindTabsAndDeepLinks();
    bindFormsAndActions();
    refreshProfile();
    refreshNotifications();
    pollTimer = setInterval(refreshNotifications, 15000);
  });

  window.addEventListener("crm:view-activated", (e) => {
    if (e.detail && e.detail.view === "profile") {
      refreshProfile();
      refreshNotifications();
    }
  });
})();
