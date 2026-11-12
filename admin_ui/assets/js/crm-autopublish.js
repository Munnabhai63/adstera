/**
 * AdsterraFleet Vuexy CRM AutoPublish Controller — Component U3
 * Connects #view-autopublish to /api/autopublish/* endpoints with:
 * - 10-domain pills & fleet pipeline schedule matrix
 * - Live 5-stage pipeline stepper
 * - Sortable & filterable 20-Topic Intelligence matrix (in-place DOM row reordering)
 * - Upcoming High-CPC Queue, Google Trends India & Adsterra placement summary
 * - Real-time Published Posts stream + native <dialog> Desktop/Mobile previewer
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 15000;
  const DOMAINS = [
    "tazaloan",
    "loanraaj",
    "rechargetak",
    "rechargepur",
    "loankiseva",
    "karzseva",
    "loantau",
    "tazabhav",
    "tazarokda",
    "rechargekar",
  ];

  const STAGE_NAMES = {
    1: "Topic Discovery",
    2: "Top-5 CPC Winners",
    3: "Deep AI Writing",
    4: "Anti-AI Gate Audit",
    5: "Cloudflare & GSC",
  };

  const textCollator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

  let activeDomain = "tazaloan";
  let lastPayload = null;
  let pollTimer = null;
  let sortState = { key: "composite", type: "number", dir: "descending" };
  let isFetching = false;

  function viewEl() {
    return document.getElementById("view-autopublish");
  }

  function isActive() {
    const v = viewEl();
    return Boolean(v && v.classList.contains("active"));
  }

  function toast(msg, type = "info") {
    if (window.AdsterraShell && typeof window.AdsterraShell.toast === "function") {
      window.AdsterraShell.toast(msg, type);
    } else if (window.CRM && typeof window.CRM.toast === "function") {
      window.CRM.toast(msg, type);
    }
  }

  function showActionStatus(msg, variant = "info") {
    const box = document.getElementById("u3ActionStatus");
    if (!box) return;
    box.className = `alert alert-${variant} py-2 px-3 mt-3 mb-0`;
    box.textContent = msg;
    box.classList.remove("d-none");
  }

  function clearChildren(el) {
    while (el && el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function setBtnBusy(btn, busy, busyLabel) {
    if (!btn) return;
    if (busy) {
      if (!btn.dataset.origHtml) {
        btn.dataset.origHtml = btn.innerHTML;
      }
      btn.disabled = true;
      btn.textContent = busyLabel || "Running...";
    } else {
      btn.disabled = false;
      if (btn.dataset.origHtml) {
        btn.innerHTML = btn.dataset.origHtml;
      }
    }
  }

  function safeUrl(raw) {
    try {
      const parsed = new URL(String(raw || ""), window.location.origin);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return parsed.href;
      }
    } catch (_) {}
    return "#";
  }

  function moveRow(tbody, row) {
    if (typeof tbody.moveBefore === "function") {
      tbody.moveBefore(row, null);
    } else {
      tbody.appendChild(row);
    }
  }

  function renderDomainPills(data) {
    const container = document.getElementById("u3DomainPills");
    if (!container) return;
    clearChildren(container);

    const pendingByDom = data?.pending_by_domain || {};
    const allPipes = data?.all_pipelines || {};
    const stuckMins = Number(data?.speed_config?.stuck_stage_minutes ?? 30);

    DOMAINS.forEach((dom) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "u3-domain-pill";
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", dom === activeDomain ? "true" : "false");

      const nameSpan = document.createElement("span");
      nameSpan.textContent = dom;
      btn.appendChild(nameSpan);

      const qCount = Number(pendingByDom[dom] || 0);
      const qBadge = document.createElement("span");
      qBadge.className =
        dom === activeDomain
          ? "badge rounded-pill bg-white text-primary tabular-nums"
          : "badge rounded-pill bg-label-secondary tabular-nums";
      qBadge.textContent = `${qCount}q`;
      btn.appendChild(qBadge);

      const pipe = allPipes[dom];
      if (pipe && isDomainStuck(pipe, stuckMins)) {
        const warn = document.createElement("span");
        warn.className = "badge rounded-pill bg-label-warning";
        warn.textContent = "!";
        warn.title = "Pipeline stage stale or stuck";
        btn.appendChild(warn);
      }

      btn.addEventListener("click", () => {
        if (dom !== activeDomain) {
          switchDomain(dom);
        }
      });

      container.appendChild(btn);
    });
  }

  function isDomainStuck(pipe, stuckMins) {
    if (!pipe || !pipe.updated_at) return false;
    const ts = Date.parse(String(pipe.updated_at).replace(" ", "T") + (String(pipe.updated_at).includes("Z") ? "" : "Z"));
    if (!Number.isFinite(ts)) return false;
    const ageMin = (Date.now() - ts) / 60000;
    const st = Number(pipe.stage_num || 1);
    return ageMin >= stuckMins && st > 1 && st < 5;
  }

  function renderKpis(data) {
    const speedCfg = data.speed_config || {};
    const intervalMins = speedCfg.interval_minutes ?? 20;
    const parallelDoms = speedCfg.parallel_domains ?? 2;

    const elTotal = document.getElementById("u3KpiTotalPublished");
    const elCadence = document.getElementById("u3KpiCadenceMeta");
    const elModel = document.getElementById("u3KpiActiveModel");
    const elCadBadge = document.getElementById("u3CadenceBadge");
    const elDomLabel = document.getElementById("u3ActiveDomainLabel");

    if (elTotal) elTotal.textContent = String(data.total_published ?? 0);
    if (elCadence) elCadence.textContent = `${intervalMins}m · ${parallelDoms} Parallel`;
    if (elModel) elModel.textContent = String(data.active_model || "FreeLLMAPI Auto");
    if (elCadBadge) elCadBadge.textContent = `${intervalMins}m • ${parallelDoms} Parallel`;
    if (elDomLabel) elDomLabel.textContent = `${activeDomain}.com`;

    const idxStats = data.index_stats || {};
    const elIdxRate = document.getElementById("u3KpiIndexRate");
    const elIdxSub = document.getElementById("u3KpiIndexSub");
    if (elIdxRate) elIdxRate.textContent = String(idxStats.overall_index_rate || "0.0%");
    if (elIdxSub) {
      const idx = idxStats.total_indexed ?? 0;
      const tot = idxStats.total_network_articles ?? 0;
      const modeLabel = idxStats.gsc_configured ? "GSC Verified" : "Est.";
      elIdxSub.textContent = `${idx} / ${tot} (${modeLabel})`;
    }

    const pipe = data.pipeline || {};
    const elAiScore = document.getElementById("u3KpiAntiAiScore");
    const elAiGate = document.getElementById("u3KpiAntiAiGate");
    if (elAiScore) {
      const s = Number(pipe.anti_ai_score ?? 0);
      const w = Number(pipe.words_written ?? 0);
      if (w === 0 && s === 0) {
        elAiScore.textContent = "Pre-Draft";
      } else {
        elAiScore.textContent = `${Number.isFinite(s) ? s.toFixed(1) : "99.0"}%`;
      }
    }
    if (elAiGate) elAiGate.textContent = String(data.anti_ai_gate || "Anti-AI Gate Active");

    const pendingByDom = data.pending_by_domain || {};
    const totalPending = Object.values(pendingByDom).reduce((acc, n) => acc + (Number(n) || 0), 0);
    const activePending = Number(pendingByDom[activeDomain] || 0);
    const elQueueCount = document.getElementById("u3KpiQueueCount");
    const elTokens = document.getElementById("u3KpiTokenAllowance");
    if (elQueueCount) elQueueCount.textContent = `${totalPending} (${activePending} active)`;
    if (elTokens) elTokens.textContent = String(data.token_allowance || "7.4B Tokens / Month");

    const sidebarBadge = document.getElementById("sidebarAutopublishBadge");
    if (sidebarBadge) sidebarBadge.textContent = String(totalPending);
  }

  function renderStepper(data) {
    const pipe = data.pipeline || {};
    const stageNum = Math.max(1, Math.min(5, Number(pipe.stage_num || 1)));

    const domEl = document.getElementById("u3StepperDomain");
    const msgEl = document.getElementById("u3PipelineMsg");
    const wordsEl = document.getElementById("u3PipelineWords");
    const aiEl = document.getElementById("u3PipelineAiScore");
    const topicEl = document.getElementById("u3PipelineTopic");
    const pillEl = document.getElementById("u3PipelineStagePill");

    if (domEl) domEl.textContent = `${activeDomain}.com`;
    if (msgEl) msgEl.textContent = String(pipe.message || "Pipeline idle / awaiting cadence trigger");
    if (wordsEl) wordsEl.textContent = `${Number(pipe.words_written || 0)} words`;
    if (aiEl) aiEl.textContent = `Anti-AI ${Number(pipe.anti_ai_score ?? 99).toFixed(1)}%`;
    if (topicEl) topicEl.textContent = String(pipe.active_topic || "Awaiting topic selection");
    if (pillEl) {
      const sName = pipe.stage_name || STAGE_NAMES[stageNum] || "Stage";
      pillEl.textContent = `Stage ${stageNum} / 5 • ${sName}`;
    }

    document.querySelectorAll("#u3StepperTrack .u3-step-node").forEach((node) => {
      const n = Number(node.getAttribute("data-stage-node") || 0);
      node.classList.remove("is-done", "is-active");
      if (n < stageNum) {
        node.classList.add("is-done");
      } else if (n === stageNum) {
        node.classList.add("is-active");
      }
    });
  }

  function renderFleetGrid(data) {
    const grid = document.getElementById("u3FleetGrid");
    const stuckBadge = document.getElementById("u3StuckBadge");
    if (!grid) return;
    clearChildren(grid);

    const allPipes = data.all_pipelines || {};
    const pendingByDom = data.pending_by_domain || {};
    const stuckMins = Number(data?.speed_config?.stuck_stage_minutes ?? 30);
    let stuckTotal = 0;

    DOMAINS.forEach((dom) => {
      const pipe = allPipes[dom] || {};
      const stageNum = Number(pipe.stage_num || 1);
      const qCount = Number(pendingByDom[dom] || 0);
      const stuck = isDomainStuck(pipe, stuckMins);
      if (stuck) stuckTotal += 1;

      const card = document.createElement("div");
      card.className = "u3-fleet-card";
      if (dom === activeDomain) card.classList.add("is-selected");
      if (stuck) card.classList.add("is-stuck");
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", `Inspect ${dom}.com pipeline`);

      const topRow = document.createElement("div");
      topRow.className = "d-flex justify-content-between align-items-center mb-1 gap-1";

      const title = document.createElement("strong");
      title.className = "small";
      title.textContent = `${dom}.com`;

      const stagePill = document.createElement("span");
      stagePill.className = stuck
        ? "badge bg-label-warning tabular-nums"
        : stageNum >= 5
          ? "badge bg-label-success tabular-nums"
          : "badge bg-label-primary tabular-nums";
      stagePill.textContent = stuck ? `Stuck S${stageNum}` : `S${stageNum}/5`;

      topRow.appendChild(title);
      topRow.appendChild(stagePill);
      card.appendChild(topRow);

      const topicP = document.createElement("div");
      topicP.className = "u3-fleet-topic text-body-secondary mb-2";
      topicP.textContent = String(pipe.active_topic || "Awaiting next 20m cadence run");
      card.appendChild(topicP);

      const botRow = document.createElement("div");
      botRow.className = "d-flex justify-content-between align-items-center small";

      const qSpan = document.createElement("span");
      qSpan.className = "text-body-secondary tabular-nums";
      qSpan.textContent = `${qCount} queued • ${Number(pipe.words_written || 0)}w`;

      botRow.appendChild(qSpan);

      if (stuck) {
        const kickBtn = document.createElement("button");
        kickBtn.type = "button";
        kickBtn.className = "btn btn-xs btn-warning";
        kickBtn.textContent = "Kick";
        kickBtn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          postAction("/api/autopublish/kick", { domains: [dom] }, kickBtn, "Kicking...");
        });
        botRow.appendChild(kickBtn);
      }

      card.appendChild(botRow);

      card.addEventListener("click", () => {
        if (dom !== activeDomain) switchDomain(dom);
      });
      card.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          if (dom !== activeDomain) switchDomain(dom);
        }
      });

      grid.appendChild(card);
    });

    if (stuckBadge) {
      if (stuckTotal > 0) {
        stuckBadge.textContent = `${stuckTotal} Stuck`;
        stuckBadge.classList.remove("d-none");
      } else {
        stuckBadge.classList.add("d-none");
      }
    }
  }

  function buildCandidatesRows(candidates) {
    const tbody = document.getElementById("u3CandidatesBody");
    if (!tbody) return;
    clearChildren(tbody);

    if (!Array.isArray(candidates) || candidates.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.className = "text-center text-body-secondary py-5";
      td.textContent = "No 20-topic candidates found yet. Click 'Discover 20 Topics' to scout.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      applyCandidateFilters();
      return;
    }

    candidates.forEach((item, idx) => {
      const rank = idx + 1;
      const isWinner = Number(item.is_winner || 0) === 1 || rank <= 5;
      const cpc = Number(item.commercial_intent_score ?? 0);
      const trend = Number(item.trend_velocity_score ?? 0);
      const composite = Number(item.composite_score ?? 0);
      const topicText = String(item.topic || "");
      const catText = String(item.category || "General");

      const tr = document.createElement("tr");
      tr.dataset.rank = String(rank);
      tr.dataset.topic = topicText;
      tr.dataset.category = catText;
      tr.dataset.cpc = String(cpc);
      tr.dataset.trend = String(trend);
      tr.dataset.composite = String(composite);
      tr.dataset.winner = isWinner ? "1" : "0";

      // Col 1: Row header (sticky on mobile card layout)
      const thRank = document.createElement("th");
      thRank.scope = "row";
      thRank.className = "tabular-nums";
      thRank.textContent = `#${rank}`;
      tr.appendChild(thRank);

      const tdTopic = document.createElement("td");
      tdTopic.className = "fw-medium";
      tdTopic.textContent = topicText;
      tr.appendChild(tdTopic);

      const tdCat = document.createElement("td");
      const catBadge = document.createElement("span");
      catBadge.className = "badge bg-label-secondary";
      catBadge.textContent = catText;
      tdCat.appendChild(catBadge);
      tr.appendChild(tdCat);

      const tdCpc = document.createElement("td");
      tdCpc.className = "tabular-nums";
      tdCpc.textContent = cpc.toFixed(1);
      tr.appendChild(tdCpc);

      const tdTrend = document.createElement("td");
      tdTrend.className = "tabular-nums";
      tdTrend.textContent = trend.toFixed(1);
      tr.appendChild(tdTrend);

      const tdComp = document.createElement("td");
      tdComp.className = "fw-semibold tabular-nums";
      tdComp.textContent = composite.toFixed(1);
      tr.appendChild(tdComp);

      const tdTier = document.createElement("td");
      const tierBadge = document.createElement("span");
      tierBadge.className = isWinner ? "badge bg-label-success" : "badge bg-label-secondary";
      tierBadge.textContent = isWinner ? "Top-5 Winner" : "Reserve";
      tdTier.appendChild(tierBadge);
      tr.appendChild(tdTier);

      tbody.appendChild(tr);
    });

    applyCandidateSort(sortState.key, sortState.type, sortState.dir, false);
    applyCandidateFilters();
  }

  function applyCandidateSort(key, type, forcedDir = null, toggle = true) {
    const table = document.getElementById("u3CandidatesTable");
    const tbody = document.getElementById("u3CandidatesBody");
    if (!table || !tbody) return;

    let nextDir = forcedDir || "descending";
    if (toggle) {
      if (sortState.key === key) {
        nextDir = sortState.dir === "descending" ? "ascending" : "descending";
      } else {
        nextDir = type === "text" ? "ascending" : "descending";
      }
    }
    sortState = { key, type, dir: nextDir };

    // Reset aria-sort on every column header
    table.querySelectorAll("thead th[aria-sort]").forEach((th) => {
      const btn = th.querySelector(".u3-sort-btn");
      if (btn && btn.getAttribute("data-sort-key") === key) {
        th.setAttribute("aria-sort", nextDir);
      } else {
        th.setAttribute("aria-sort", "none");
      }
    });

    const rows = Array.from(tbody.querySelectorAll("tr")).filter((r) => r.dataset.rank);
    if (rows.length <= 1) return;

    const factor = nextDir === "ascending" ? 1 : -1;
    rows.sort((a, b) => {
      const av = a.dataset[key] ?? "";
      const bv = b.dataset[key] ?? "";
      if (type === "number") {
        const na = Number(av) || 0;
        const nb = Number(bv) || 0;
        return (na - nb) * factor;
      }
      return textCollator.compare(av, bv) * factor;
    });

    // In-place DOM node reordering (never innerHTML rebuild)
    rows.forEach((row) => moveRow(tbody, row));
  }

  function applyCandidateFilters() {
    const tbody = document.getElementById("u3CandidatesBody");
    const searchEl = document.getElementById("u3CandidateSearch");
    const winnersEl = document.getElementById("u3WinnersOnly");
    const countLabel = document.getElementById("u3CandidatesCountLabel");
    if (!tbody) return;

    const q = (searchEl?.value || "").trim().toLowerCase();
    const winnersOnly = Boolean(winnersEl?.checked);
    const rows = Array.from(tbody.querySelectorAll("tr")).filter((r) => r.dataset.rank);

    let visibleCount = 0;
    rows.forEach((row) => {
      const matchWinner = !winnersOnly || row.dataset.winner === "1";
      const hay = `${row.dataset.topic || ""} ${row.dataset.category || ""}`.toLowerCase();
      const matchQuery = !q || hay.includes(q);
      const show = matchWinner && matchQuery;
      row.hidden = !show;
      if (show) visibleCount += 1;
    });

    if (countLabel) {
      countLabel.textContent = `${visibleCount} of ${rows.length} topics`;
    }
  }

  function renderQueue(queue) {
    const list = document.getElementById("u3QueueList");
    const badge = document.getElementById("u3QueueBadge");
    if (!list) return;
    clearChildren(list);

    const items = Array.isArray(queue) ? queue : [];
    if (badge) badge.textContent = `${items.length} queued`;

    if (items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "text-body-secondary small py-4 text-center";
      empty.textContent = "Pending queue is empty. Click 'Discover 20 Topics' to replenish Top-5 winners.";
      list.appendChild(empty);
      return;
    }

    items.forEach((qItem) => {
      const row = document.createElement("div");
      row.className = "p-2 rounded border bg-body-tertiary";

      const meta = document.createElement("div");
      meta.className = "d-flex justify-content-between align-items-center mb-1 gap-2";

      const leftMeta = document.createElement("div");
      leftMeta.className = "d-flex align-items-center gap-1 flex-wrap";

      const domBadge = document.createElement("span");
      domBadge.className = "badge bg-label-primary";
      domBadge.textContent = String(qItem.domain || "");

      const catBadge = document.createElement("span");
      catBadge.className = "badge bg-label-secondary";
      catBadge.textContent = String(qItem.category || "Guide");

      leftMeta.appendChild(domBadge);
      leftMeta.appendChild(catBadge);

      const score = document.createElement("span");
      score.className = "badge bg-label-success tabular-nums";
      score.textContent = `${Number(qItem.priority_score || 0).toFixed(1)} pts`;

      meta.appendChild(leftMeta);
      meta.appendChild(score);
      row.appendChild(meta);

      const topicDiv = document.createElement("div");
      topicDiv.className = "small fw-medium";
      topicDiv.textContent = String(qItem.topic || "");
      row.appendChild(topicDiv);

      list.appendChild(row);
    });
  }

  function renderTrendsAndAdsterra(data) {
    const chips = document.getElementById("u3TrendsChips");
    if (chips) {
      clearChildren(chips);
      const trends = Array.isArray(data.google_trends) ? data.google_trends : [];
      if (trends.length === 0) {
        const span = document.createElement("span");
        span.className = "text-body-secondary small";
        span.textContent = "No live breakout trends cached yet.";
        chips.appendChild(span);
      } else {
        trends.slice(0, 10).forEach((t) => {
          const badge = document.createElement("span");
          badge.className = "badge bg-label-info";
          badge.textContent = String(t);
          chips.appendChild(badge);
        });
      }
    }

    const matrix = Array.isArray(data.adsterra_matrix) ? data.adsterra_matrix : [];
    const match = matrix.find((m) => String(m.domain || "").startsWith(`${activeDomain}.`)) || matrix[0];
    const titleEl = document.getElementById("u3AdTitle");
    const statusEl = document.getElementById("u3AdEdgeStatus");
    const urlEl = document.getElementById("u3AdUrl");
    if (match) {
      if (titleEl) titleEl.textContent = `${match.name || match.domain} — ${match.cta || "Smartlink CTA"}`;
      if (statusEl) statusEl.textContent = String(match.edge_status || "200 OK");
      if (urlEl) urlEl.textContent = String(match.url || "Configured in adsterra_links.py");
    }
  }

  function renderPublishedPosts(posts) {
    const tbody = document.getElementById("u3PublishedBody");
    if (!tbody) return;
    clearChildren(tbody);

    const items = Array.isArray(posts) ? posts : [];
    if (items.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "text-center text-body-secondary py-5";
      td.textContent = "No published posts logged yet.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    items.forEach((p) => {
      const dom = String(p.domain || "");
      const slug = String(p.slug || "");
      const title = String(p.title || slug);
      const cat = String(p.category || "Article");
      const words = Number(p.words || 0);
      const qScore = Number(p.quality_score ?? 98);

      const tr = document.createElement("tr");
      tr.dataset.domain = dom;
      tr.dataset.search = `${title} ${dom} ${cat} ${slug}`.toLowerCase();

      const thTitle = document.createElement("th");
      thTitle.scope = "row";
      thTitle.textContent = title;
      tr.appendChild(thTitle);

      const tdSite = document.createElement("td");
      const siteBadge = document.createElement("span");
      siteBadge.className = "badge bg-label-primary me-1";
      siteBadge.textContent = dom;
      const catSpan = document.createElement("span");
      catSpan.className = "small text-body-secondary";
      catSpan.textContent = cat;
      tdSite.appendChild(siteBadge);
      tdSite.appendChild(catSpan);
      tr.appendChild(tdSite);

      const tdWords = document.createElement("td");
      tdWords.className = "tabular-nums";
      tdWords.textContent = `${words}w`;
      tr.appendChild(tdWords);

      const tdQual = document.createElement("td");
      const qualBadge = document.createElement("span");
      qualBadge.className = qScore >= 90 ? "badge bg-label-success tabular-nums" : "badge bg-label-warning tabular-nums";
      qualBadge.textContent = `${qScore.toFixed(0)}%`;
      tdQual.appendChild(qualBadge);
      tr.appendChild(tdQual);

      const tdActions = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "d-flex flex-wrap gap-1";

      const prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "btn btn-xs btn-primary";
      prevBtn.textContent = "Preview";
      prevBtn.addEventListener("click", () => openArticlePreview(p));
      wrap.appendChild(prevBtn);

      const liveLink = document.createElement("a");
      liveLink.className = "btn btn-xs btn-label-secondary";
      liveLink.href = safeUrl(p.live_url);
      liveLink.target = "_blank";
      liveLink.rel = "noopener noreferrer";
      liveLink.textContent = "Live";
      wrap.appendChild(liveLink);

      tdActions.appendChild(wrap);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });

    applyPostFilters();
  }

  function applyPostFilters() {
    const tbody = document.getElementById("u3PublishedBody");
    const activeOnlyEl = document.getElementById("u3PostsActiveOnly");
    const searchEl = document.getElementById("u3PostSearch");
    if (!tbody) return;

    const onlyActive = Boolean(activeOnlyEl?.checked);
    const q = (searchEl?.value || "").trim().toLowerCase();

    tbody.querySelectorAll("tr").forEach((tr) => {
      if (!tr.dataset.domain) return;
      const matchDom = !onlyActive || tr.dataset.domain === activeDomain;
      const matchQ = !q || (tr.dataset.search || "").includes(q);
      tr.hidden = !(matchDom && matchQ);
    });
  }

  function setPreviewMode(mode) {
    const iframe = document.getElementById("u3PreviewIframe");
    const btnDesk = document.getElementById("u3PreviewModeDesktop");
    const btnMob = document.getElementById("u3PreviewModeMobile");
    if (!iframe || !btnDesk || !btnMob) return;

    const isMob = mode === "mobile";
    iframe.classList.toggle("is-mobile", isMob);
    btnDesk.setAttribute("aria-pressed", String(!isMob));
    btnMob.setAttribute("aria-pressed", String(isMob));
    btnDesk.className = isMob ? "btn btn-outline-primary" : "btn btn-primary";
    btnMob.className = isMob ? "btn btn-primary" : "btn btn-outline-primary";
  }

  function openArticlePreview(post) {
    const dialog = document.getElementById("u3PreviewDialog");
    const iframe = document.getElementById("u3PreviewIframe");
    const status = document.getElementById("u3PreviewStatus");
    const titleEl = document.getElementById("u3PreviewTitle");
    const domBadge = document.getElementById("u3PreviewDomainBadge");
    const qBadge = document.getElementById("u3PreviewQualityBadge");
    const extLink = document.getElementById("u3PreviewExternalLink");
    if (!dialog || !iframe) return;

    if (titleEl) titleEl.textContent = String(post.title || post.slug || "Article Preview");
    if (domBadge) domBadge.textContent = String(post.domain || activeDomain);
    if (qBadge) qBadge.textContent = `${Number(post.quality_score ?? 98).toFixed(0)}% Anti-AI`;
    if (extLink) extLink.href = safeUrl(post.live_url);

    setPreviewMode("desktop");
    if (status) {
      status.textContent = "Loading article preview...";
      status.classList.remove("d-none");
    }

    const baseSrc =
      post.preview_url ||
      `/api/autopublish/preview?domain=${encodeURIComponent(String(post.domain || activeDomain))}&slug=${encodeURIComponent(String(post.slug || ""))}`;
    const previewSrc = baseSrc.includes("?") ? `${baseSrc}&safe=1` : `${baseSrc}?safe=1`;

    iframe.onload = () => {
      if (status) status.classList.add("d-none");
    };
    iframe.src = previewSrc;

    dialog.returnValue = "";
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  async function refreshAutoPublish(domain = activeDomain) {
    if (isFetching) return;
    isFetching = true;
    try {
      const resp = await fetch(`/api/autopublish/stats?domain=${encodeURIComponent(domain)}`, {
        cache: "no-store",
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      lastPayload = data;
      if (data.active_domain && DOMAINS.includes(data.active_domain)) {
        activeDomain = data.active_domain;
        const sel = document.getElementById("u3DomainSelect");
        if (sel && sel.value !== activeDomain) sel.value = activeDomain;
      }

      renderDomainPills(data);
      renderKpis(data);
      renderStepper(data);
      renderFleetGrid(data);
      buildCandidatesRows(data.candidates);
      renderQueue(data.queue);
      renderTrendsAndAdsterra(data);
      renderPublishedPosts(data.posts);
    } catch (err) {
      showActionStatus(`Failed to load AutoPublish telemetry: ${err.message || err}`, "danger");
    } finally {
      isFetching = false;
    }
  }

  function switchDomain(dom) {
    if (!DOMAINS.includes(dom)) return;
    activeDomain = dom;
    const sel = document.getElementById("u3DomainSelect");
    if (sel) sel.value = dom;
    refreshAutoPublish(dom);
  }

  async function postAction(endpoint, body, btn, busyLabel) {
    setBtnBusy(btn, true, busyLabel);
    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.success === false) {
        const msg = data.error || data.message || `Action failed (HTTP ${resp.status})`;
        showActionStatus(msg, "warning");
        toast(msg, "error");
      } else {
        const msg =
          data.message ||
          (Array.isArray(data.candidates)
            ? `Scouted ${data.candidates.length} high-CPC topics for ${data.domain || activeDomain}.`
            : data.kicked_count !== undefined
              ? `Kicked ${data.kicked_count} stuck domain(s) back to queue.`
              : "AutoPublish action completed.");
        showActionStatus(msg, "success");
        toast(msg, "success");
      }
      await refreshAutoPublish(activeDomain);
    } catch (err) {
      const msg = `Network error: ${err.message || err}`;
      showActionStatus(msg, "danger");
      toast(msg, "error");
    } finally {
      setBtnBusy(btn, false);
    }
  }

  function bindEvents() {
    const sel = document.getElementById("u3DomainSelect");
    if (sel) {
      sel.addEventListener("change", () => switchDomain(sel.value));
    }

    const btnScout = document.getElementById("u3BtnScout20");
    if (btnScout) {
      btnScout.addEventListener("click", () =>
        postAction("/api/autopublish/refresh-candidates", { domain: activeDomain }, btnScout, "Scouting...")
      );
    }

    const btnKick = document.getElementById("u3BtnKick");
    if (btnKick) {
      btnKick.addEventListener("click", () =>
        postAction("/api/autopublish/kick", {}, btnKick, "Kicking...")
      );
    }

    const btnBatch = document.getElementById("u3BtnBatch");
    if (btnBatch) {
      btnBatch.addEventListener("click", () =>
        postAction("/api/autopublish/trigger-batch", { parallel_domains: 2 }, btnBatch, "Publishing 2...")
      );
    }

    const btnTrig = document.getElementById("u3BtnTrigger");
    if (btnTrig) {
      btnTrig.addEventListener("click", () =>
        postAction("/api/autopublish/trigger", { domain: activeDomain }, btnTrig, "Publishing...")
      );
    }

    const btnRefresh = document.getElementById("u3BtnRefresh");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => refreshAutoPublish(activeDomain));
    }

    document.querySelectorAll("#u3CandidatesTable .u3-sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-sort-key") || "composite";
        const type = btn.getAttribute("data-sort-type") || "number";
        applyCandidateSort(key, type, null, true);
      });
    });

    const candSearch = document.getElementById("u3CandidateSearch");
    const winnersOnly = document.getElementById("u3WinnersOnly");
    if (candSearch) candSearch.addEventListener("input", applyCandidateFilters);
    if (winnersOnly) winnersOnly.addEventListener("change", applyCandidateFilters);

    const postSearch = document.getElementById("u3PostSearch");
    const postsActiveOnly = document.getElementById("u3PostsActiveOnly");
    if (postSearch) postSearch.addEventListener("input", applyPostFilters);
    if (postsActiveOnly) postsActiveOnly.addEventListener("change", applyPostFilters);

    const dialog = document.getElementById("u3PreviewDialog");
    const closeBtn = document.getElementById("u3PreviewCloseBtn");
    const iframe = document.getElementById("u3PreviewIframe");
    const btnDesk = document.getElementById("u3PreviewModeDesktop");
    const btnMob = document.getElementById("u3PreviewModeMobile");

    if (btnDesk) btnDesk.addEventListener("click", () => setPreviewMode("desktop"));
    if (btnMob) btnMob.addEventListener("click", () => setPreviewMode("mobile"));
    if (closeBtn && dialog) {
      closeBtn.addEventListener("click", () => dialog.close("close-button"));
    }
    if (dialog) {
      dialog.addEventListener("click", (ev) => {
        if (ev.target === dialog) {
          dialog.close("backdrop");
        }
      });
      dialog.addEventListener("close", () => {
        if (iframe) iframe.src = "about:blank";
      });
    }

    window.addEventListener("crm:view-activated", (ev) => {
      if (ev.detail && ev.detail.view === "autopublish") {
        refreshAutoPublish(activeDomain);
      }
    });
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (isActive() && document.visibilityState === "visible") {
        refreshAutoPublish(activeDomain);
      }
    }, POLL_INTERVAL_MS);
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    startPolling();
    if (isActive() || window.location.hash === "#autopublish") {
      refreshAutoPublish(activeDomain);
    }
  });
})();
