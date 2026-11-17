"""Content Workspace & Deploy View Renderer (#view-content)."""
from __future__ import annotations

DOMAINS_LIST = [
    "loanraaj.com",
    "rechargetak.com",
    "rechargepur.com",
    "tazaloan.com",
    "loankiseva.com",
    "karzseva.com",
    "loantau.com",
    "tazabhav.com",
    "tazarokda.com",
    "rechargekar.com",
]


def render_content_view() -> str:
    """Render the Content Workspace and Cloudflare Pages deployment management view."""
    domain_checkboxes = "\n".join(
        f"""
        <div class="form-check form-check-inline me-3 mb-2">
          <input class="form-check-input deploy-domain-checkbox" type="checkbox" id="chk_{d.replace('.', '_')}" value="{d}" checked />
          <label class="form-check-label small font-monospace" for="chk_{d.replace('.', '_')}">{d}</label>
        </div>"""
        for d in DOMAINS_LIST
    )

    return f"""
<section id="view-content" class="crm-view">
  <!-- DEPLOY CONTROL CARD -->
  <div class="card mb-6">
    <div class="card-header border-bottom d-flex flex-wrap align-items-center justify-content-between gap-3">
      <div>
        <h5 class="card-title mb-1">Cloudflare Edge Deployment</h5>
        <p class="text-body-secondary small mb-0">Deploy static article corpus and host-level 301 redirects to Cloudflare global CDN</p>
      </div>
      <div class="d-flex align-items-center gap-2">
        <button type="button" class="btn btn-sm btn-outline-secondary" id="btnSelectAllDomains">Toggle All</button>
        <button type="button" class="btn btn-sm btn-primary d-flex align-items-center gap-1" id="btnDeployCloudflare">
          <i class="icon-base ti tabler-cloud-upload icon-16px" id="deployIcon"></i>
          <span class="spinner-border spinner-border-sm d-none" id="deploySpinner" role="status"></span>
          <span id="deployBtnText">Deploy to Cloudflare</span>
        </button>
      </div>
    </div>
    <div class="card-body pt-4">
      <div class="mb-3">
        <label class="form-label small fw-semibold text-body-secondary mb-2">Target Domains:</label>
        <div class="d-flex flex-wrap align-items-center" id="deployDomainSelector">
          {domain_checkboxes}
        </div>
      </div>
      
      <!-- DEPLOY RESULT / ERROR TAIL -->
      <div id="deployOutputContainer" class="d-none">
        <div class="d-flex align-items-center justify-content-between mb-1">
          <span class="small fw-semibold" id="deployStatusTitle">Deployment Output</span>
          <span class="badge" id="deployStatusBadge">READY</span>
        </div>
        <pre id="deployOutputTail" class="bg-dark text-white p-3 rounded font-monospace small mb-0" style="max-height: 220px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;"></pre>
      </div>
    </div>
  </div>

  <!-- CONTENT WORKSPACE CARD -->
  <div class="card">
    <div class="card-header border-bottom d-flex flex-wrap align-items-center justify-content-between gap-3">
      <div class="d-flex align-items-center gap-3">
        <h5 class="card-title mb-0">Article Corpus &amp; Redirects</h5>
        <div class="btn-group btn-group-sm" role="group" aria-label="Content Filter">
          <button type="button" class="btn btn-outline-primary active" data-content-filter="all">All</button>
          <button type="button" class="btn btn-outline-primary" data-content-filter="published">Published (&ge;3000)</button>
          <button type="button" class="btn btn-outline-primary" data-content-filter="stubs">Redirect Stubs</button>
        </div>
      </div>
      <div class="d-flex align-items-center gap-2">
        <div class="input-group input-group-sm" style="width: 250px;">
          <span class="input-group-text"><i class="icon-base ti tabler-search icon-14px"></i></span>
          <input type="text" class="form-control" id="contentSearchInput" placeholder="Search slug or domain..." />
        </div>
        <button type="button" class="btn btn-sm btn-icon btn-outline-secondary" id="btnRefreshContent" title="Refresh articles">
          <i class="icon-base ti tabler-refresh icon-16px"></i>
        </button>
      </div>
    </div>

    <!-- KPI STRIP -->
    <div class="card-body border-bottom py-3">
      <div class="row g-3 text-center">
        <div class="col-6 col-md-3">
          <span class="text-body-secondary small">Total Indexed</span>
          <h4 class="mb-0 fw-bold tabular-nums" id="kpiTotalIndexed">--</h4>
        </div>
        <div class="col-6 col-md-3">
          <span class="text-body-secondary small">Published Articles (&ge;3000)</span>
          <h4 class="mb-0 fw-bold text-success tabular-nums" id="kpiPublishedArticles">--</h4>
        </div>
        <div class="col-6 col-md-3">
          <span class="text-body-secondary small">301 Redirect Stubs</span>
          <h4 class="mb-0 fw-bold text-warning tabular-nums" id="kpiRedirectStubs">--</h4>
        </div>
        <div class="col-6 col-md-3">
          <span class="text-body-secondary small">Network Domains</span>
          <h4 class="mb-0 fw-bold text-primary tabular-nums" id="kpiNetworkDomains">--</h4>
        </div>
      </div>
    </div>

    <!-- ARTICLES TABLE -->
    <div class="table-responsive text-nowrap">
      <table class="table table-hover mb-0" id="contentArticlesTable">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Slug</th>
            <th class="text-end">Words</th>
            <th>Status</th>
            <th>Modified</th>
          </tr>
        </thead>
        <tbody id="contentArticlesTbody">
          <tr>
            <td colspan="5" class="text-center py-4 text-body-secondary">
              <span class="spinner-border spinner-border-sm me-2" role="status"></span>Loading corpus articles...
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ARTICLE DETAIL DIALOG -->
  <dialog id="contentDetailDialog" class="u3-preview-dialog card shadow-lg border p-0 rounded" style="max-width: 720px; width: 90vw;">
    <div class="card-header border-bottom d-flex align-items-center justify-content-between p-4">
      <div>
        <h5 class="card-title mb-1" id="detailModalTitle">Article Details</h5>
        <span class="badge bg-label-primary font-monospace" id="detailModalDomain">domain.com</span>
      </div>
      <button type="button" class="btn-close" id="detailModalCloseBtn" aria-label="Close"></button>
    </div>
    <div class="card-body p-4" id="detailModalBody">
      <div class="mb-3">
        <label class="form-label small fw-semibold text-body-secondary mb-1">Headline (H1)</label>
        <p class="mb-0 fw-semibold" id="detailModalH1">--</p>
      </div>
      <div class="mb-3">
        <label class="form-label small fw-semibold text-body-secondary mb-1">Meta Description</label>
        <p class="text-body-secondary small mb-0" id="detailModalMeta">--</p>
      </div>
      <div class="row g-3 mb-4">
        <div class="col-6">
          <div class="border rounded p-3 text-center">
            <span class="text-body-secondary small">Prose Word Count</span>
            <h4 class="mb-0 fw-bold tabular-nums text-success" id="detailModalWords">--</h4>
          </div>
        </div>
        <div class="col-6">
          <div class="border rounded p-3 text-center">
            <span class="text-body-secondary small">Content Images (&ge;5)</span>
            <h4 class="mb-0 fw-bold tabular-nums text-primary" id="detailModalImages">--</h4>
          </div>
        </div>
      </div>
      <div>
        <label class="form-label small fw-semibold text-body-secondary mb-2">Sections (H2 Headings)</label>
        <ul class="list-group list-group-flush border rounded small" id="detailModalH2List">
          <li class="list-group-item text-body-secondary">No headings detected.</li>
        </ul>
      </div>
    </div>
    <div class="card-footer border-top d-flex justify-content-end p-3">
      <button type="button" class="btn btn-sm btn-secondary" id="detailModalDoneBtn">Close</button>
    </div>
  </dialog>
</section>
"""
