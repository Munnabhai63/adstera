"""Component U4 View Renderer — Monetization, Display Banner Vault, CPL Leads & Smartlinks (#view-monetization)."""

from __future__ import annotations

from admin_ui.views.autopublish import DOMAINS_META


def _domain_options_html() -> str:
    """Return <option> elements for all 10 .com publisher domains."""
    return "\n".join(
        f'<option value="{slug}.com">{slug}.com &mdash; {niche}</option>'
        for slug, _, niche in DOMAINS_META
    )


def _render_kpi_strip() -> str:
    """Render 4 Vuexy summary KPI cards for Revenue, Handshakes, Banner Vault, and CPL Bounties."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Adsterra Official Revenue</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-warning"><i class="icon-base ti tabler-coin icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u4KpiRevenue">$0.000</h3>
          <small class="text-body-secondary d-block tabular-nums" id="u4KpiApiImps">0 Imps / 0 Clicks Counted</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Confirmed Handshakes</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-success"><i class="icon-base ti tabler-radar-2 icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-baseline gap-2 mb-1">
            <h3 class="mb-0 tabular-nums" id="u4KpiHandshakes">0</h3>
            <span class="badge bg-label-success tabular-nums" id="u4KpiRateBadge">100.0%</span>
          </div>
          <small class="text-body-secondary d-block tabular-nums" id="u4KpiSessions">0 Sessions Dispatched</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Banner Vault Coverage</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-info"><i class="icon-base ti tabler-layout-board icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-2 tabular-nums" id="u4KpiBannerCoverage">0 / 30</h3>
          <div class="progress" style="height: 6px;">
            <div class="progress-bar bg-info" id="u4BannerProgress" role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">CPL Bounties &amp; Personas</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-primary"><i class="icon-base ti tabler-users-group icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-baseline gap-2 mb-1">
            <h3 class="mb-0 tabular-nums" id="u4KpiBounty">$0.00</h3>
            <span class="badge bg-label-primary tabular-nums" id="u4KpiPersonaCount">0 personas</span>
          </div>
          <small class="text-body-secondary d-block tabular-nums" id="u4KpiLeadsCount">0 Leads Recorded Today</small>
        </div>
      </div>
    </div>
  </div>
"""


def _render_funnel_card() -> str:
    """Render Adsterra Real-Time Funnel Proof & Live Handshake Tester card."""
    opts = _domain_options_html()
    funnel_stages = [
        (1, "Session Dispatched", "Anti-detect IP & FP"),
        (2, "Ad Unit In-View", "Human scroll & dwell"),
        (3, "Bézier Ad Click", "Target Smartlink hit"),
        (4, "Gateway 200/302", "Edge beacon logged"),
        (5, "Adsterra Reconciled", "Official API synced"),
    ]
    steps_html = "\n".join(
        f"""
        <div class="u3-step-node" data-u4-stage="{num}">
          <div class="u3-step-circle tabular-nums">{num}</div>
          <div class="u3-step-meta">
            <div class="fw-semibold small">{title}</div>
            <div class="text-body-secondary u3-step-sub">{desc}</div>
          </div>
        </div>
        """
        for num, title, desc in funnel_stages
    )
    return f"""
  <div class="card mb-6">
    <div class="card-header d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 pb-3">
      <div>
        <h5 class="mb-1">Adsterra Revenue Funnel &amp; Handshake Verification</h5>
        <p class="card-subtitle text-body-secondary mb-0">
          Real Chromium outbound Smartlink telemetry reconciled against <code>api3.adsterratools.com</code>
        </p>
      </div>
      <div class="d-flex flex-wrap align-items-center gap-2">
        <select id="u4FunnelDomain" class="form-select form-select-sm" style="width: auto; min-width: 210px;" aria-label="Select target domain for handshake verification">
          {opts}
        </select>
        <button type="button" class="btn btn-sm btn-success" id="u4BtnRunFunnel">
          <i class="icon-base ti tabler-activity-heartbeat icon-16px me-1"></i>Verify Live Handshake
        </button>
        <button type="button" class="btn btn-sm btn-primary" id="u4BtnSyncApi">
          <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Sync Adsterra API
        </button>
        <a href="/classic#bannerVaultCard" class="btn btn-sm btn-label-secondary">
          <i class="icon-base ti tabler-external-link icon-16px me-1"></i>Classic
        </a>
      </div>
    </div>

    <div class="card-body pt-2">
      <div class="u3-stepper-track mb-4" id="u4FunnelStepper">
        {steps_html}
      </div>

      <div id="u4FunnelResultBox" class="p-3 rounded border bg-body-tertiary d-none" role="status" aria-live="polite">
        <div class="d-flex justify-content-between align-items-center mb-2 gap-2">
          <strong class="small" id="u4FunnelResultTitle">Verification running...</strong>
          <small class="text-body-secondary tabular-nums" id="u4FunnelResultMeta"></small>
        </div>
        <div id="u4FunnelLogs" class="u4-funnel-logs font-monospace small"></div>
      </div>
    </div>
  </div>
"""


def _render_banner_vault_card() -> str:
    """Render Layer 1 Display Banner Vault (728x90, 300x250, NativeBanner) with accessible toolbar & form."""
    opts = _domain_options_html()
    return f"""
  <div class="card mb-6" id="u4BannerVaultCard">
    <div class="card-header d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 pb-3">
      <div>
        <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
          <h5 class="mb-0">Layer 1 &middot; Display Banner Vault</h5>
          <span class="badge bg-label-info tabular-nums" id="u4BvSummaryBadge">0 / 30 Configured</span>
        </div>
        <p class="card-subtitle text-body-secondary mb-0">
          Manage Adsterra 728&times;90, 300&times;250 &amp; NativeBanner codes across all 10 Cloudflare domains
        </p>
      </div>

      <div class="u4-toolbar d-flex flex-wrap align-items-center gap-2" role="toolbar" focusgroup="toolbar wrap" aria-label="Display Banner Vault actions">
        <div role="group" aria-label="API sync and local HTML injection" class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-sm btn-outline-info u4-tb-btn" id="u4BtnSyncPlacements" title="Fetch placement IDs from Adsterra API">
            <i class="icon-base ti tabler-cloud-download icon-16px me-1"></i>Sync Placements
          </button>
          <button type="button" class="btn btn-sm btn-label-secondary u4-tb-btn" id="u4BtnInjectLocal" title="Inject saved codes into local sites/ HTML files">
            <i class="icon-base ti tabler-code icon-16px me-1"></i>Inject Local HTML
          </button>
        </div>
        <span role="separator" aria-orientation="vertical" class="u4-tb-sep"></span>
        <div role="group" aria-label="Production Cloudflare deployment">
          <button type="button" class="btn btn-sm btn-success u4-tb-btn" id="u4BtnDeployCf" title="Inject slots and push to Cloudflare Pages">
            <i class="icon-base ti tabler-rocket icon-16px me-1"></i>Inject &amp; Deploy Cloudflare
          </button>
        </div>
      </div>
    </div>

    <div class="card-body pt-2">
      <div id="u4BvActionStatus" class="alert alert-info py-2 px-3 mb-4 d-none" role="status" aria-live="polite"></div>

      <form id="u4BannerForm" class="p-4 rounded border bg-body-tertiary mb-5" novalidate>
        <div class="row g-3 align-items-end mb-3">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold" for="u4BvDomain">Target Publisher Domain</label>
            <select id="u4BvDomain" class="form-select form-select-sm" name="domain">
              {opts}
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold" for="u4BvSlot">Ad Placement Format</label>
            <select id="u4BvSlot" class="form-select form-select-sm" name="slot">
              <option value="auto">Auto-Detect Slot (Single or Bulk All 3)</option>
              <option value="728x90">728&times;90 Leaderboard</option>
              <option value="300x250">300&times;250 Medium Rectangle</option>
              <option value="native">NativeBanner</option>
            </select>
          </div>
          <div class="col-12 col-md-4 d-flex justify-content-md-end">
            <button type="submit" class="btn btn-sm btn-primary w-100 w-md-auto" id="u4BtnSaveSnippet">
              <i class="icon-base ti tabler-device-floppy icon-16px me-1"></i>Validate &amp; Save Snippet
            </button>
          </div>
        </div>

        <div class="u25-field">
          <label class="form-label small fw-semibold" for="u4BvSnippet">Official Adsterra &ldquo;Get Code&rdquo; JS Snippet(s)</label>
          <textarea
            id="u4BvSnippet"
            class="form-control font-monospace small"
            rows="3"
            required
            minlength="20"
            aria-describedby="u4BvSnippetErr"
            placeholder="Paste official Adsterra 'Get Code' JS snippet(s) (atOptions + invoke.js or NativeBanner container + invoke.js)..."></textarea>
          <div id="u4BvSnippetErr" class="u25-error-msg">
            Paste a valid Adsterra snippet (at least 20 characters including placement key / invoke.js script).
          </div>
        </div>
      </form>

      <div tabindex="0" role="region" aria-labelledby="u4BvCaption" class="table-wrapper u3-table-region">
        <table class="table table-hover align-middle mb-0 u4-bv-table" id="u4BannerTable">
          <caption id="u4BvCaption" class="visually-hidden">10-Domain Display Banner Slot Coverage Matrix</caption>
          <thead>
            <tr>
              <th scope="col">Domain</th>
              <th scope="col">Domain ID</th>
              <th scope="col">728&times;90 Leaderboard</th>
              <th scope="col">300&times;250 Sidebar</th>
              <th scope="col">NativeBanner</th>
              <th scope="col">Ready</th>
            </tr>
          </thead>
          <tbody id="u4BannerBody">
            <tr>
              <td colspan="6" class="text-center text-body-secondary py-5">Loading Display Banner inventory...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
"""


def _render_streams_tabs_card() -> str:
    """Render tabbed Revenue Handshakes, CPL Leads, SERP Queries & Direct Smartlinks + Personas."""
    return """
  <div class="card">
    <div class="card-header pb-0">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-2 mb-3">
        <div>
          <h5 class="mb-0">Revenue Streams, CPL Leads, SERP &amp; Direct Links</h5>
          <small class="text-body-secondary">Switch tabs with mouse or Left/Right arrow keys</small>
        </div>
        <button type="button" class="btn btn-sm btn-label-secondary" id="u4BtnRefreshAll">
          <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Refresh Data
        </button>
      </div>

      <ul class="nav nav-tabs u25-profile-tabs" role="tablist" aria-label="Monetization telemetry tabs" id="u4StreamTabs">
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link active" id="u4TabHandshakesBtn" role="tab" aria-selected="true" aria-controls="u4PanelHandshakes" data-u4-tab="handshakes">
            <i class="icon-base ti tabler-arrows-exchange icon-16px me-1"></i>Handshakes &amp; API Sync
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link" id="u4TabLeadsBtn" role="tab" aria-selected="false" aria-controls="u4PanelLeads" data-u4-tab="leads" tabindex="-1">
            <i class="icon-base ti tabler-currency-dollar icon-16px me-1"></i>CPL Lead Bounties
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link" id="u4TabSerpBtn" role="tab" aria-selected="false" aria-controls="u4PanelSerp" data-u4-tab="serp" tabindex="-1">
            <i class="icon-base ti tabler-search icon-16px me-1"></i>SERP Organic Queries
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link" id="u4TabSmartlinksBtn" role="tab" aria-selected="false" aria-controls="u4PanelSmartlinks" data-u4-tab="smartlinks" tabindex="-1">
            <i class="icon-base ti tabler-link icon-16px me-1"></i>Direct Links &amp; Personas
          </button>
        </li>
      </ul>
    </div>

    <div class="card-body pt-4">
      <div id="u4PanelHandshakes" class="u4-tab-panel" role="tabpanel" aria-labelledby="u4TabHandshakesBtn">
        <h6 class="mb-2">Live Adsterra Outbound Network Handshakes</h6>
        <div tabindex="0" role="region" aria-labelledby="u4HsCaption" class="table-wrapper u3-table-region mb-5">
          <table class="table table-hover align-middle mb-0 u4-hs-table" id="u4HandshakesTable">
            <caption id="u4HsCaption" class="visually-hidden">Recent Adsterra gateway HTTP handshakes</caption>
            <thead>
              <tr>
                <th scope="col">Website</th>
                <th scope="col">Timestamp</th>
                <th scope="col">Gateway URL</th>
                <th scope="col">Status</th>
                <th scope="col">Latency</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody id="u4HandshakesBody">
              <tr>
                <td colspan="6" class="text-center text-body-secondary py-4">Loading recent handshakes...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center mb-2 gap-2">
          <h6 class="mb-0">Official Adsterra API Reconciliation</h6>
          <small class="text-body-secondary">api3.adsterratools.com</small>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4SyncCaption" class="table-wrapper u3-table-region mb-5">
          <table class="table table-hover align-middle mb-0 u4-sync-table" id="u4SyncTable">
            <caption id="u4SyncCaption" class="visually-hidden">Adsterra official API reconciliation records</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Date</th>
                <th scope="col">API Imps</th>
                <th scope="col">Clicks</th>
                <th scope="col">CTR</th>
                <th scope="col">eCPM</th>
                <th scope="col">Revenue</th>
                <th scope="col">Local Imps</th>
                <th scope="col">Variance</th>
              </tr>
            </thead>
            <tbody id="u4SyncBody">
              <tr>
                <td colspan="9" class="text-center text-body-secondary py-4">Click &ldquo;Sync Adsterra API&rdquo; above to reconcile live records.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap justify-content-between align-items-center mb-2 gap-2">
          <div>
            <h6 class="mb-0">3-Layer Zero-Waste Domain Audit &amp; Root-Cause CPM Diagnostic</h6>
            <small class="text-body-secondary" id="u4ZeroWasteMeta">Bot Sessions vs. HTTP 200 Beacons vs. Official Adsterra API</small>
          </div>
          <button type="button" class="btn btn-xs btn-outline-primary" id="u4BtnRunLiveAudit">
            <i class="icon-base ti tabler-stethoscope icon-14px me-1"></i>Refresh 3-Layer Audit
          </button>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4ZwCaption" class="table-wrapper u3-table-region mb-5">
          <table class="table table-hover align-middle mb-0 u4-zw-table" id="u4ZeroWasteTable">
            <caption id="u4ZwCaption" class="visually-hidden">Zero-waste 3-layer domain reconciliation and CPM diagnostic</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Beacons (HTTP 200)</th>
                <th scope="col">API Imps</th>
                <th scope="col">Clicks / CTR</th>
                <th scope="col">eCPM / Rev</th>
                <th scope="col">Count Ratio</th>
                <th scope="col">Root-Cause Diagnosis &amp; Auto-Action</th>
              </tr>
            </thead>
            <tbody id="u4ZeroWasteBody">
              <tr>
                <td colspan="7" class="text-center text-body-secondary py-4">Loading 3-Layer Zero-Waste Audit...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center mb-2 gap-2">
          <h6 class="mb-0">Adsterra Placement-Level Breakdown (Popunder / Native / 728x90 / 300x250 / Smartlink)</h6>
          <small class="text-body-secondary">Official Placement Group-By</small>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4PlCaption" class="table-wrapper u3-table-region mb-5">
          <table class="table table-hover align-middle mb-0 u4-pl-table" id="u4PlacementsTable">
            <caption id="u4PlCaption" class="visually-hidden">Adsterra placement level CPM and impression breakdown</caption>
            <thead>
              <tr>
                <th scope="col">Placement</th>
                <th scope="col">Domain &bull; Unit</th>
                <th scope="col">API Imps</th>
                <th scope="col">Clicks</th>
                <th scope="col">CTR</th>
                <th scope="col">eCPM</th>
                <th scope="col">Revenue</th>
                <th scope="col">Unit Role</th>
              </tr>
            </thead>
            <tbody id="u4PlacementsBody">
              <tr>
                <td colspan="8" class="text-center text-body-secondary py-4">Loading placement-level telemetry...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center mb-2 gap-2">
          <h6 class="mb-0">4-Dimension Sensitive Zero-Leak Audit (COUNTRY &bull; DEVICE FORMAT &bull; OPERATING SYSTEM &bull; BROWSER)</h6>
          <small class="text-body-secondary">27,103 UA Pool Hardware Lock</small>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4FdCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u4-fd-table" id="u4FourDimTable">
            <caption id="u4FdCaption" class="visually-hidden">4-Dimension Country, Device Format, Operating System and Browser zero-leak audit</caption>
            <thead>
              <tr>
                <th scope="col">Sensitive Tab</th>
                <th scope="col">Detected Value</th>
                <th scope="col">Sessions</th>
                <th scope="col">Impressions</th>
                <th scope="col">Clicks</th>
                <th scope="col">Hardware / Header Lock</th>
                <th scope="col">Leak Status</th>
              </tr>
            </thead>
            <tbody id="u4FourDimBody">
              <tr>
                <td colspan="7" class="text-center text-body-secondary py-4">Loading 4-Dimension Zero-Leak telemetry...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div id="u4PanelLeads" class="u4-tab-panel" role="tabpanel" aria-labelledby="u4TabLeadsBtn" hidden="until-found">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h6 class="mb-0">High-Payout CPL / CPA Lead Conversions</h6>
            <small class="text-body-secondary">Post-click authentic US persona lead submissions ($1.50&ndash;$4.50 bounty)</small>
          </div>
          <button type="button" class="btn btn-sm btn-primary" id="u4BtnSimLead">
            <i class="icon-base ti tabler-plus icon-16px me-1"></i>+1 CPL Lead Submission
          </button>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4LeadsCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u4-leads-table" id="u4LeadsTable">
            <caption id="u4LeadsCaption" class="visually-hidden">CPL and CPA lead conversion log</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Persona</th>
                <th scope="col">Email</th>
                <th scope="col">Fields</th>
                <th scope="col">Dwell</th>
                <th scope="col">Bounty</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody id="u4LeadsBody">
              <tr>
                <td colspan="7" class="text-center text-body-secondary py-4">No lead conversions recorded today.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div id="u4PanelSerp" class="u4-tab-panel" role="tabpanel" aria-labelledby="u4TabSerpBtn" hidden="until-found">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h6 class="mb-0">Dynamic SERP Organic Search Referrer Matrix</h6>
            <small class="text-body-secondary">Geo-matched organic Google/Bing search queries reducing IVT flags</small>
          </div>
          <button type="button" class="btn btn-sm btn-outline-info" id="u4BtnRefreshSerp">
            <i class="icon-base ti tabler-sparkles icon-16px me-1"></i>Refresh Organic Queries
          </button>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4SerpCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u4-serp-table" id="u4SerpTable">
            <caption id="u4SerpCaption" class="visually-hidden">Synthesized geo-matched search queries per domain</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Geo City / State</th>
                <th scope="col">Synthesized Search Query</th>
                <th scope="col">Referrer Engine</th>
              </tr>
            </thead>
            <tbody id="u4SerpBody">
              <tr>
                <td colspan="4" class="text-center text-body-secondary py-4">Loading dynamic SERP queries...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div id="u4PanelSmartlinks" class="u4-tab-panel" role="tabpanel" aria-labelledby="u4TabSmartlinksBtn" hidden="until-found">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h6 class="mb-0">10-Domain Direct Smartlinks Matrix</h6>
            <small class="text-body-secondary">Accessible 1-click copy with keyboard &amp; status confirmation</small>
          </div>
          <span class="badge bg-label-success">10 Domains Active</span>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4LinksCaption" class="table-wrapper u3-table-region mb-5">
          <table class="table table-hover align-middle mb-0 u4-links-table" id="u4SmartlinksTable">
            <caption id="u4LinksCaption" class="visually-hidden">10-domain direct Adsterra smartlinks directory</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Niche CTA</th>
                <th scope="col">Direct Smartlink URL</th>
                <th scope="col">Status</th>
                <th scope="col">Copy</th>
              </tr>
            </thead>
            <tbody id="u4SmartlinksBody">
              <tr>
                <td colspan="5" class="text-center text-body-secondary py-4">Loading Adsterra Smartlink registry...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h6 class="mb-0">Synthetic High-Intent Personas</h6>
            <small class="text-body-secondary">Warmed browser identity metadata (credentials remain masked in state/)</small>
          </div>
          <button type="button" class="btn btn-sm btn-primary" id="u4BtnGenAccount">
            <i class="icon-base ti tabler-user-plus icon-16px me-1"></i>+ Generate Persona
          </button>
        </div>
        <div tabindex="0" role="region" aria-labelledby="u4AccCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u4-acc-table" id="u4AccountsTable">
            <caption id="u4AccCaption" class="visually-hidden">Synthetic high-intent browser personas</caption>
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">Full Name</th>
                <th scope="col">Geo</th>
                <th scope="col">Credit Score</th>
                <th scope="col">Status</th>
                <th scope="col">Cookies</th>
              </tr>
            </thead>
            <tbody id="u4AccountsBody">
              <tr>
                <td colspan="6" class="text-center text-body-secondary py-4">Loading persona accounts...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
"""


def render_monetization_view() -> str:
    """Render the complete Component U4 Monetization, Adsterra Vault & CPL Leads workspace."""
    return (
        '<section id="view-monetization" class="crm-view">'
        + _render_kpi_strip()
        + _render_funnel_card()
        + _render_banner_vault_card()
        + _render_streams_tabs_card()
        + "</section>"
    )
