"""Component U3 View Renderer — AutoPublish & 20-Topic Intelligence CMS (#view-autopublish)."""

from __future__ import annotations

DOMAINS_META = [
    ("tazaloan", "TazaLoan.com", "Personal & Instant Loans"),
    ("loanraaj", "LoanRaaj.com", "Business & Mudra Loans"),
    ("rechargetak", "RechargeTak.com", "5G Plans & SIM Guides"),
    ("rechargepur", "RechargePur.com", "DTH, Broadband & OTT"),
    ("loankiseva", "LoanKiSeva.com", "Education & Govt Loans"),
    ("karzseva", "KarzSeva.com", "Home & Mortgage EMIs"),
    ("loantau", "LoanTau.com", "Instant EMI & NBFC"),
    ("tazabhav", "TazaBhav.com", "Gold, Petrol & Mandi"),
    ("tazarokda", "TazaRokda.com", "Digital Banking & UPI"),
    ("rechargekar", "RechargeKar.com", "Mobile & EV Savings"),
]


def _render_command_header() -> str:
    """Render top command bar with domain selector pills and parallel publish actions."""
    options_html = "\n".join(
        f'<option value="{slug}">{label} &mdash; {niche}</option>'
        for slug, label, niche in DOMAINS_META
    )
    return f"""
  <div class="card mb-6">
    <div class="card-body">
      <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-4 mb-4">
        <div>
          <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
            <h4 class="mb-0">AutoPublish &amp; 20-Topic CMS</h4>
            <span class="badge bg-label-success" id="u3GatewayBadge">FreeLLMAPI Online</span>
            <span class="badge bg-label-primary tabular-nums" id="u3CadenceBadge">20m &bull; 2 Parallel</span>
          </div>
          <p class="text-body-secondary mb-0 small" id="u3ActiveSummary">
            Active Domain: <strong id="u3ActiveDomainLabel">tazaloan.com</strong> &bull; Aggressive Top-5 CPC Winner Funnel &amp; Anti-AI Burstiness Gate
          </p>
        </div>

        <div class="d-flex flex-wrap align-items-center gap-2">
          <div class="input-group input-group-sm" style="width: auto; min-width: 220px;">
            <label class="input-group-text" for="u3DomainSelect">
              <i class="icon-base ti tabler-world icon-16px"></i>
            </label>
            <select id="u3DomainSelect" class="form-select form-select-sm" aria-label="Select publishing domain">
              {options_html}
            </select>
          </div>

          <button type="button" class="btn btn-sm btn-outline-primary" id="u3BtnScout20">
            <i class="icon-base ti tabler-radar-2 icon-16px me-1"></i>Discover 20 Topics
          </button>
          <button type="button" class="btn btn-sm btn-outline-warning" id="u3BtnKick">
            <i class="icon-base ti tabler-bolt icon-16px me-1"></i>Kick Stuck
          </button>
          <button type="button" class="btn btn-sm btn-primary" id="u3BtnBatch">
            <i class="icon-base ti tabler-layers-intersect icon-16px me-1"></i>Publish 2 Parallel
          </button>
          <button type="button" class="btn btn-sm btn-success" id="u3BtnTrigger">
            <i class="icon-base ti tabler-send icon-16px me-1"></i>Publish Single
          </button>
          <button type="button" class="btn btn-sm btn-label-secondary" id="u3BtnRefresh" aria-label="Refresh AutoPublish stats">
            <i class="icon-base ti tabler-refresh icon-16px"></i>
          </button>
          <a href="/autopublish" class="btn btn-sm btn-label-secondary">
            <i class="icon-base ti tabler-external-link icon-16px me-1"></i>Classic
          </a>
        </div>
      </div>

      <div class="u3-domain-pills" id="u3DomainPills" role="tablist" aria-label="Quick 10-domain selector"></div>

      <div id="u3ActionStatus" class="alert alert-info py-2 px-3 mt-3 mb-0 d-none" role="status" aria-live="polite"></div>
    </div>
  </div>
"""


def _render_kpi_strip() -> str:
    """Render 4 Vuexy metric cards for AutoPublish velocity, GSC index rate, Anti-AI gate, and Queue."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Total Fleet Published</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-success"><i class="icon-base ti tabler-news icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u3KpiTotalPublished">0</h3>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="badge bg-label-primary tabular-nums" id="u3KpiCadenceMeta">20m Cycle</span>
            <small class="text-body-secondary text-truncate" id="u3KpiActiveModel">Loading model...</small>
          </div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Network Indexation Rate</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-info"><i class="icon-base ti tabler-brand-google icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u3KpiIndexRate">0.0%</h3>
          <div class="d-flex justify-content-between align-items-center gap-2">
            <small class="text-body-secondary tabular-nums" id="u3KpiIndexSub">0 / 0 Indexed</small>
            <button type="button" class="btn btn-xs btn-label-info" data-crm-view="growth" id="u3JumpGscBtn">
              GSC View
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Anti-AI Gate Audit</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-warning"><i class="icon-base ti tabler-shield-check icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u3KpiAntiAiScore">99.0%</h3>
          <small class="text-body-secondary d-block text-truncate" id="u3KpiAntiAiGate">Burstiness &ge; 4.0 Active</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Queued CPC Topics</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-primary"><i class="icon-base ti tabler-list-numbers icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u3KpiQueueCount">0</h3>
          <small class="text-body-secondary d-block text-truncate" id="u3KpiTokenAllowance">7.4B Tokens / Month Pool</small>
        </div>
      </div>
    </div>
  </div>
"""


def _render_stepper_and_fleet() -> str:
    """Render 5-stage active domain pipeline stepper + 10-domain fleet schedule matrix."""
    stages = [
        (1, "Topic Discovery", "Scout 20 candidates"),
        (2, "Top-5 CPC Winners", "Score & rank matrix"),
        (3, "Deep AI Writing", "1400+ word SEO draft"),
        (4, "Anti-AI Gate", "Cliché & burstiness audit"),
        (5, "Cloudflare & GSC", "Edge deploy + ping"),
    ]
    steps_html = "\n".join(
        f"""
        <div class="u3-step-node" data-stage-node="{num}">
          <div class="u3-step-circle tabular-nums">{num}</div>
          <div class="u3-step-meta">
            <div class="fw-semibold small">{title}</div>
            <div class="text-body-secondary u3-step-sub">{desc}</div>
          </div>
        </div>
        """
        for num, title, desc in stages
    )
    return f"""
  <div class="row g-6 mb-6">
    <div class="col-12">
      <div class="card">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-3 pb-3">
          <div>
            <h5 class="mb-1">Live 5-Stage Pipeline &mdash; <span class="text-primary" id="u3StepperDomain">tazaloan.com</span></h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u3PipelineMsg">Syncing stage telemetry...</p>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="badge bg-label-secondary tabular-nums" id="u3PipelineWords">0 words</span>
            <span class="badge bg-label-success tabular-nums" id="u3PipelineAiScore">Anti-AI 99%</span>
          </div>
        </div>
        <div class="card-body pt-2">
          <div class="u3-stepper-track mb-4" id="u3StepperTrack">
            {steps_html}
          </div>
          <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 p-3 rounded bg-body-tertiary border">
            <div class="small">
              <span class="text-body-secondary me-1">Active Topic:</span>
              <strong id="u3PipelineTopic">Waiting for queue...</strong>
            </div>
            <span class="badge bg-label-primary" id="u3PipelineStagePill">Stage 1 / 5</span>
          </div>
        </div>
      </div>
    </div>

    <div class="col-12">
      <div class="card">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2 pb-3">
          <div>
            <h5 class="mb-0">10-Domain Parallel Pipeline &amp; Schedule Matrix</h5>
            <small class="text-body-secondary">Live stage, queue depth &amp; stuck detection across the entire fleet (click any card to inspect)</small>
          </div>
          <span class="badge bg-label-warning d-none" id="u3StuckBadge">0 Stuck</span>
        </div>
        <div class="card-body pt-2">
          <div class="u3-fleet-grid" id="u3FleetGrid">
            <div class="text-body-secondary small py-3">Loading 10-domain pipeline telemetry...</div>
          </div>
        </div>
      </div>
    </div>
  </div>
"""


def _render_candidates_table() -> str:
    """Render sortable & filterable 20-Topic Intelligence & Winner Matrix."""
    return """
  <div class="card mb-6">
    <div class="card-header d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
      <div>
        <h5 class="mb-1">20-Topic Intelligence &amp; Winner Matrix</h5>
        <p class="card-subtitle text-body-secondary mb-0">
          20 scouted topics ranked by Commercial CPC Intent, Trend Velocity &amp; Composite Score &bull; <span id="u3CandidatesCountLabel" class="tabular-nums">0 topics</span>
        </p>
      </div>
      <div class="d-flex flex-wrap align-items-center gap-3">
        <div class="form-check form-switch mb-0">
          <input class="form-check-input" type="checkbox" id="u3WinnersOnly" />
          <label class="form-check-label small" for="u3WinnersOnly">Top-5 Winners Only</label>
        </div>
        <div class="input-group input-group-sm" style="min-width: 210px; max-width: 280px;">
          <span class="input-group-text"><i class="icon-base ti tabler-search icon-16px"></i></span>
          <input type="search" class="form-control" id="u3CandidateSearch" placeholder="Filter topics or category..." aria-label="Filter 20-topic matrix" />
        </div>
      </div>
    </div>

    <div class="card-body p-0">
      <div tabindex="0" role="region" aria-labelledby="u3CandidatesCaption" class="table-wrapper u3-table-region">
        <table class="table table-hover align-middle mb-0 u3-candidates-table" id="u3CandidatesTable">
          <caption id="u3CandidatesCaption" class="visually-hidden">20-Topic Intelligence and Winner Matrix for selected publishing domain</caption>
          <thead>
            <tr>
              <th scope="col" aria-sort="none">
                <button type="button" class="u3-sort-btn" data-sort-key="rank" data-sort-type="number">
                  Rank <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col" aria-sort="none">
                <button type="button" class="u3-sort-btn" data-sort-key="topic" data-sort-type="text">
                  Topic Title <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col" aria-sort="none">
                <button type="button" class="u3-sort-btn" data-sort-key="category" data-sort-type="text">
                  Category <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col" aria-sort="none">
                <button type="button" class="u3-sort-btn" data-sort-key="cpc" data-sort-type="number">
                  CPC Intent <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col" aria-sort="none">
                <button type="button" class="u3-sort-btn" data-sort-key="trend" data-sort-type="number">
                  Trend <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col" aria-sort="descending">
                <button type="button" class="u3-sort-btn" data-sort-key="composite" data-sort-type="number">
                  Composite <span class="u3-sort-ind" aria-hidden="true"></span>
                </button>
              </th>
              <th scope="col">Tier</th>
            </tr>
          </thead>
          <tbody id="u3CandidatesBody">
            <tr>
              <td colspan="7" class="text-center text-body-secondary py-5">Loading 20-topic intelligence matrix...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
"""


def _render_queue_trends_and_posts() -> str:
    """Render Pending Queue + Google Trends column alongside Real-Time Published Posts stream."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-12 col-xl-5 d-flex flex-column gap-6">
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center pb-2">
          <div>
            <h5 class="mb-0">Upcoming High-CPC Queue</h5>
            <small class="text-body-secondary">Priority-sorted pending pipeline across fleet</small>
          </div>
          <span class="badge bg-label-primary tabular-nums" id="u3QueueBadge">0 queued</span>
        </div>
        <div class="card-body pt-2 u3-queue-scroll">
          <div id="u3QueueList" class="d-flex flex-column gap-2">
            <div class="text-body-secondary small py-3">Loading pending queue...</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center pb-2">
          <div>
            <h5 class="mb-0">Live Google Trends India &amp; Ad Placements</h5>
            <small class="text-body-secondary">Real-time breakout signals + active domain Adsterra link</small>
          </div>
          <button type="button" class="btn btn-xs btn-label-primary" data-crm-view="monetization">
            Ad Matrix
          </button>
        </div>
        <div class="card-body pt-2">
          <div class="d-flex flex-wrap gap-2 mb-4" id="u3TrendsChips">
            <span class="badge bg-label-secondary">Loading live trends...</span>
          </div>
          <div class="p-3 rounded border bg-body-tertiary small" id="u3AdsterraCardSummary">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <strong id="u3AdTitle">Adsterra Direct Placement</strong>
              <span class="badge bg-label-success" id="u3AdEdgeStatus">200 OK</span>
            </div>
            <div class="text-body-secondary text-truncate" id="u3AdUrl">Waiting for active domain placement...</div>
          </div>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-7">
      <div class="card h-100">
        <div class="card-header d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-3 pb-3">
          <div>
            <h5 class="mb-0">Published Posts &amp; Live Inspector</h5>
            <small class="text-body-secondary">Open Desktop/Mobile interactive preview or verify live Cloudflare URL</small>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <div class="form-check form-switch mb-0">
              <input class="form-check-input" type="checkbox" id="u3PostsActiveOnly" />
              <label class="form-check-label small" for="u3PostsActiveOnly">Active Domain Only</label>
            </div>
            <div class="input-group input-group-sm" style="width: 190px;">
              <span class="input-group-text"><i class="icon-base ti tabler-search icon-16px"></i></span>
              <input type="search" class="form-control" id="u3PostSearch" placeholder="Search posts..." aria-label="Search published posts" />
            </div>
          </div>
        </div>
        <div class="card-body p-0">
          <div tabindex="0" role="region" aria-labelledby="u3PublishedCaption" class="table-wrapper u3-table-region u3-posts-scroll">
            <table class="table table-hover align-middle mb-0 u3-posts-table" id="u3PublishedTable">
              <caption id="u3PublishedCaption" class="visually-hidden">Published articles stream with desktop and mobile preview launcher</caption>
              <thead>
                <tr>
                  <th scope="col">Article Title</th>
                  <th scope="col">Site / Category</th>
                  <th scope="col">Words</th>
                  <th scope="col">Quality</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody id="u3PublishedBody">
                <tr>
                  <td colspan="5" class="text-center text-body-secondary py-5">Loading published posts...</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
"""


def _render_preview_dialog() -> str:
    """Render accessible native <dialog> article inspector (Desktop 100% / Mobile 390px)."""
    return """
  <dialog id="u3PreviewDialog" class="u3-preview-dialog" aria-labelledby="u3PreviewTitle">
    <div class="u3-dialog-header d-flex flex-wrap justify-content-between align-items-center gap-2">
      <div class="d-flex flex-column">
        <div class="d-flex align-items-center gap-2">
          <span class="badge bg-label-primary" id="u3PreviewDomainBadge">tazaloan</span>
          <span class="badge bg-label-success tabular-nums" id="u3PreviewQualityBadge">99% Anti-AI</span>
        </div>
        <h5 class="mb-0 mt-1 text-truncate" id="u3PreviewTitle" style="max-width: 56ch;">Article Preview</h5>
      </div>

      <div class="d-flex align-items-center gap-2">
        <div class="btn-group btn-group-sm" role="group" aria-label="Preview viewport width">
          <button type="button" class="btn btn-primary" id="u3PreviewModeDesktop" aria-pressed="true">
            <i class="icon-base ti tabler-device-desktop icon-16px me-1"></i>Desktop
          </button>
          <button type="button" class="btn btn-outline-primary" id="u3PreviewModeMobile" aria-pressed="false">
            <i class="icon-base ti tabler-device-mobile icon-16px me-1"></i>Mobile 390px
          </button>
        </div>
        <a href="#" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-label-secondary" id="u3PreviewExternalLink">
          <i class="icon-base ti tabler-external-link icon-16px"></i>
        </a>
        <button type="button" class="btn-close" id="u3PreviewCloseBtn" aria-label="Close article preview" autofocus></button>
      </div>
    </div>

    <div class="u3-dialog-body">
      <div id="u3PreviewStatus" class="text-body-secondary small py-4 text-center d-none">Loading article preview...</div>
      <div class="u3-preview-stage">
        <iframe id="u3PreviewIframe" class="u3-preview-iframe" title="Article desktop and mobile preview" sandbox="allow-popups allow-popups-to-escape-sandbox"></iframe>
      </div>
    </div>

    <div class="u3-dialog-footer d-flex justify-content-between align-items-center">
      <small class="text-body-secondary">Press Esc or Close to return to AutoPublish CMS</small>
      <form method="dialog">
        <button type="submit" class="btn btn-sm btn-primary">Done</button>
      </form>
    </div>
  </dialog>
"""


def render_autopublish_view() -> str:
    """Render the complete Component U3 AutoPublish & 20-Topic CMS workspace section."""
    return (
        '<section id="view-autopublish" class="crm-view">'
        + _render_command_header()
        + _render_kpi_strip()
        + _render_stepper_and_fleet()
        + _render_candidates_table()
        + _render_queue_trends_and_posts()
        + _render_preview_dialog()
        + "</section>"
    )
