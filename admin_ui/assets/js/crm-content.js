/**
 * AdsterraFleet Vuexy CRM — Content Workspace & Deploy Controller (#view-content)
 */
(function () {
  "use strict";

  let articlesData = [];
  let currentFilter = "all";
  let searchQuery = "";

  function el(tag, cls = "", text = "") {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function formatTime(isoStr) {
    if (!isoStr) return "--";
    try {
      const d = new Date(isoStr);
      return isNaN(d.getTime()) ? isoStr : d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return isoStr;
    }
  }

  async function fetchArticles() {
    const tbody = document.getElementById("contentArticlesTbody");
    try {
      const res = await fetch("/api/content/articles", { cache: "no-store" });
      if (!res.ok) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">Failed to load articles (${res.status})</td></tr>`;
        return;
      }
      const data = await res.json();
      articlesData = Array.isArray(data) ? data : (data.articles || []);
      updateKpis();
      renderTable();
    } catch (err) {
      console.error("[crm-content] fetch error:", err);
      if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">Network error loading articles</td></tr>`;
    }
  }

  function updateKpis() {
    const kpiTotal = document.getElementById("kpiTotalIndexed");
    const kpiPub = document.getElementById("kpiPublishedArticles");
    const kpiStubs = document.getElementById("kpiRedirectStubs");
    const kpiDoms = document.getElementById("kpiNetworkDomains");

    const stubs = articlesData.filter((a) => a.is_stub);
    const pub = articlesData.filter((a) => !a.is_stub && (a.prose_words >= 3000));
    const doms = new Set(articlesData.map((a) => a.domain));

    if (kpiTotal) kpiTotal.textContent = articlesData.length;
    if (kpiPub) kpiPub.textContent = pub.length;
    if (kpiStubs) kpiStubs.textContent = stubs.length;
    if (kpiDoms) kpiDoms.textContent = doms.size || 10;
  }

  function renderTable() {
    const tbody = document.getElementById("contentArticlesTbody");
    if (!tbody) return;

    let filtered = articlesData;

    if (currentFilter === "published") {
      filtered = filtered.filter((a) => !a.is_stub && a.prose_words >= 3000);
    } else if (currentFilter === "stubs") {
      filtered = filtered.filter((a) => a.is_stub);
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((a) => (a.domain || "").toLowerCase().includes(q) || (a.slug || "").toLowerCase().includes(q));
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-body-secondary">No articles found matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    filtered.forEach((art) => {
      const tr = el("tr");
      tr.style.cursor = "pointer";
      tr.addEventListener("click", () => openArticleDetail(art));

      // Domain
      const tdDom = el("td", "font-monospace small", art.domain);
      tr.appendChild(tdDom);

      // Slug
      const tdSlug = el("td", "font-monospace small");
      const aLink = el("span", "text-primary fw-semibold", art.slug);
      tdSlug.appendChild(aLink);
      tr.appendChild(tdSlug);

      // Words
      const tdWords = el("td", "text-end tabular-nums", art.is_stub ? "--" : String(art.prose_words ?? 0));
      tr.appendChild(tdWords);

      // Status
      const tdStatus = el("td");
      if (art.is_stub) {
        const dest = art.destination ? ` -> ${art.destination}` : "";
        tdStatus.appendChild(el("span", "badge bg-label-warning small", `301 Redirect${dest}`));
      } else if (art.prose_words >= 3000) {
        tdStatus.appendChild(el("span", "badge bg-label-success small", "Published (>=3000)"));
      } else {
        tdStatus.appendChild(el("span", "badge bg-label-secondary small", "Thin (<3000)"));
      }
      tr.appendChild(tdStatus);

      // Modified
      const tdMod = el("td", "small text-body-secondary tabular-nums", formatTime(art.last_modified));
      tr.appendChild(tdMod);

      tbody.appendChild(tr);
    });
  }

  async function openArticleDetail(art) {
    const dialog = document.getElementById("contentDetailDialog");
    if (!dialog) return;

    const modalTitle = document.getElementById("detailModalTitle");
    const modalDom = document.getElementById("detailModalDomain");
    const modalH1 = document.getElementById("detailModalH1");
    const modalMeta = document.getElementById("detailModalMeta");
    const modalWords = document.getElementById("detailModalWords");
    const modalImgs = document.getElementById("detailModalImages");
    const modalH2 = document.getElementById("detailModalH2List");

    if (modalTitle) modalTitle.textContent = art.slug;
    if (modalDom) modalDom.textContent = art.domain;
    if (modalH1) modalH1.textContent = "Loading...";
    if (modalMeta) modalMeta.textContent = "Loading...";
    if (modalWords) modalWords.textContent = art.is_stub ? "Stub" : String(art.prose_words);
    if (modalImgs) modalImgs.textContent = "--";
    if (modalH2) modalH2.innerHTML = '<li class="list-group-item text-body-secondary">Loading headings...</li>';

    dialog.showModal();

    try {
      const res = await fetch(`/api/content/article?domain=${encodeURIComponent(art.domain)}&slug=${encodeURIComponent(art.slug)}`);
      if (!res.ok) {
        if (modalH1) modalH1.textContent = art.is_stub ? "301 Redirect Stub" : "Failed to load details";
        if (modalMeta) modalMeta.textContent = art.is_stub ? `Redirects to ${art.destination || "category"}` : "Error fetching article details";
        if (modalH2) modalH2.innerHTML = '<li class="list-group-item text-body-secondary">No headings.</li>';
        return;
      }
      const d = await res.json();
      if (modalH1) modalH1.textContent = d.h1 || d.title || art.slug;
      if (modalMeta) modalMeta.textContent = d.meta_description || "None";
      if (modalWords) modalWords.textContent = d.word_count ?? art.prose_words ?? 0;
      if (modalImgs) modalImgs.textContent = d.image_count ?? 0;
      if (modalH2) {
        modalH2.innerHTML = "";
        const h2s = d.h2_list || [];
        if (h2s.length === 0) {
          modalH2.innerHTML = '<li class="list-group-item text-body-secondary">No H2 headings found.</li>';
        } else {
          h2s.forEach((h) => {
            const li = el("li", "list-group-item", h);
            modalH2.appendChild(li);
          });
        }
      }
    } catch (e) {
      console.error("[crm-content] detail fetch error:", e);
    }
  }

  async function triggerDeploy() {
    const btn = document.getElementById("btnDeployCloudflare");
    const spinner = document.getElementById("deploySpinner");
    const icon = document.getElementById("deployIcon");
    const btnText = document.getElementById("deployBtnText");
    const outBox = document.getElementById("deployOutputContainer");
    const outTail = document.getElementById("deployOutputTail");
    const badge = document.getElementById("deployStatusBadge");
    const title = document.getElementById("deployStatusTitle");

    const checkedBoxes = Array.from(document.querySelectorAll(".deploy-domain-checkbox:checked"));
    const selectedDomains = checkedBoxes.map((c) => c.value);

    if (selectedDomains.length === 0) {
      alert("Please select at least one domain to deploy.");
      return;
    }

    if (btn) btn.disabled = true;
    if (spinner) spinner.classList.remove("d-none");
    if (icon) icon.classList.add("d-none");
    if (btnText) btnText.textContent = "Deploying...";
    if (outBox) outBox.classList.remove("d-none");
    if (badge) {
      badge.className = "badge bg-label-primary";
      badge.textContent = "DEPLOYING";
    }
    if (title) title.textContent = `Deploying ${selectedDomains.length} domain(s)...`;
    if (outTail) outTail.textContent = "Initiating Cloudflare deployment process...";

    try {
      const res = await fetch("/api/deploy/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domains: selectedDomains.length === 10 ? "all" : selectedDomains }),
      });

      const body = await res.json().catch(() => ({}));

      if (res.status === 409) {
        if (badge) {
          badge.className = "badge bg-label-warning";
          badge.textContent = "CONFLICT (409)";
        }
        if (outTail) outTail.textContent = "Deployment rejected: Another deployment is already in progress.";
        return;
      }

      if (!res.ok || body.ok === false) {
        if (badge) {
          badge.className = "badge bg-label-danger";
          badge.textContent = "FAILED";
        }
        const errorMsg = body.error || (body.results && body.results[0] && body.results[0].tail) || "Deployment failed.";
        if (outTail) outTail.textContent = errorMsg;
        return;
      }

      if (badge) {
        badge.className = "badge bg-label-success";
        badge.textContent = "SUCCESS";
      }
      if (title) title.textContent = "Deployment Completed";
      const tails = (body.results || []).map((r) => `[${r.domain}] ${r.status}:\n${r.tail || "ok"}`).join("\n\n");
      if (outTail) outTail.textContent = tails || "All requested domains deployed successfully.";
    } catch (err) {
      if (badge) {
        badge.className = "badge bg-label-danger";
        badge.textContent = "ERROR";
      }
      if (outTail) outTail.textContent = String(err);
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.classList.add("d-none");
      if (icon) icon.classList.remove("d-none");
      if (btnText) btnText.textContent = "Deploy to Cloudflare";
    }
  }

  function bindEvents() {
    // Filter buttons
    document.querySelectorAll("[data-content-filter]").forEach((b) => {
      b.addEventListener("click", () => {
        document.querySelectorAll("[data-content-filter]").forEach((btn) => btn.classList.remove("active"));
        b.classList.add("active");
        currentFilter = b.getAttribute("data-content-filter");
        renderTable();
      });
    });

    // Search input
    const searchInput = document.getElementById("contentSearchInput");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        searchQuery = (e.target.value || "").trim();
        renderTable();
      });
    }

    // Refresh button
    const btnRef = document.getElementById("btnRefreshContent");
    if (btnRef) btnRef.addEventListener("click", () => fetchArticles());

    // Toggle All domains
    const btnToggleAll = document.getElementById("btnSelectAllDomains");
    if (btnToggleAll) {
      btnToggleAll.addEventListener("click", () => {
        const boxes = document.querySelectorAll(".deploy-domain-checkbox");
        const allChecked = Array.from(boxes).every((c) => c.checked);
        boxes.forEach((c) => (c.checked = !allChecked));
      });
    }

    // Deploy button
    const btnDeploy = document.getElementById("btnDeployCloudflare");
    if (btnDeploy) btnDeploy.addEventListener("click", triggerDeploy);

    // Dialog close buttons
    const dialog = document.getElementById("contentDetailDialog");
    const closeBtn = document.getElementById("detailModalCloseBtn");
    const doneBtn = document.getElementById("detailModalDoneBtn");

    if (closeBtn && dialog) closeBtn.addEventListener("click", () => dialog.close());
    if (doneBtn && dialog) doneBtn.addEventListener("click", () => dialog.close());
    if (dialog) {
      dialog.addEventListener("click", (ev) => {
        if (ev.target === dialog) dialog.close();
      });
    }

    // Intercept sidebar click for data-crm-view="content"
    document.addEventListener(
      "click",
      (ev) => {
        const link = ev.target.closest('[data-crm-view="content"]');
        if (!link) return;
        ev.preventDefault();
        ev.stopPropagation();

        document.querySelectorAll(".crm-view").forEach((el) => el.classList.remove("active"));
        const viewEl = document.getElementById("view-content");
        if (viewEl) viewEl.classList.add("active");

        document.querySelectorAll("[data-crm-view]").forEach((l) => {
          const li = l.closest(".menu-item");
          if (li) li.classList.toggle("active", l.getAttribute("data-crm-view") === "content");
        });

        const bc = document.getElementById("shellActiveBreadcrumb");
        const badge = document.getElementById("shellActiveLayerBadge");
        if (bc) bc.textContent = "Content Workspace & Edge Deployment";
        if (badge) badge.textContent = "Round 22";

        history.replaceState(null, "", "#content");
        fetchArticles();
      },
      true
    );

    // Initial check if hash is #content
    if (window.location.hash === "#content") {
      setTimeout(() => {
        const link = document.querySelector('[data-crm-view="content"]');
        if (link) link.click();
      }, 100);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bindEvents();
      fetchArticles();
    });
  } else {
    bindEvents();
    fetchArticles();
  }
})();
