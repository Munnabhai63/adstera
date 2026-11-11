"""Component U2 View Renderer — Overview KPI Sparklines, Tabbed Analytics, Runner Ops, 10-Domain Fleet & Timeline."""

from __future__ import annotations


def _render_kpi_strip() -> str:
    """Render 4 Vuexy sparkline/gauge KPI summary cards at the top of Overview."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-header pb-0 d-flex justify-content-between align-items-start">
          <div class="card-title mb-0">
            <h5 class="mb-1">Sessions Today</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2KpiDiurnalTarget">Target: --/hr</p>
          </div>
          <span class="badge bg-label-primary rounded-pill">24h Pace</span>
        </div>
        <div class="card-body d-flex flex-column justify-content-between pt-2">
          <div id="u2SparkSessions" style="min-height: 76px;"></div>
          <div class="d-flex justify-content-between align-items-center mt-2">
            <h3 class="mb-0 tabular-nums" id="u2KpiSessionsToday">0</h3>
            <span class="badge bg-label-info tabular-nums" id="u2KpiDailyProgress">Live</span>
          </div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-header pb-0 d-flex justify-content-between align-items-start">
          <div class="card-title mb-0">
            <h5 class="mb-1">CTR &amp; Ad Safety</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2KpiImpsClicks">0 Imps / 0 Clicks</p>
          </div>
          <span class="badge bg-label-success rounded-pill" id="u2KpiCtrBadge">Safe &le; 5%</span>
        </div>
        <div class="card-body d-flex align-items-center justify-content-between pt-2">
          <div>
            <h3 class="mb-1 tabular-nums" id="u2KpiCtrText">0.0%</h3>
            <small class="text-body-secondary d-block">Rolling Last 100</small>
          </div>
          <div id="u2CtrGauge" style="min-height: 92px; width: 112px;"></div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-header pb-0 d-flex justify-content-between align-items-start">
          <div class="card-title mb-0">
            <h5 class="mb-1">Est. Revenue</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2KpiCpm">eCPM: $0.00</p>
          </div>
          <span class="badge bg-label-success rounded-pill tabular-nums" id="u2KpiMonthlyEst">30d: $0.00</span>
        </div>
        <div class="card-body d-flex flex-column justify-content-between pt-2">
          <div id="u2SparkRevenue" style="min-height: 76px;"></div>
          <div class="d-flex justify-content-between align-items-center mt-2">
            <h3 class="mb-0 text-success tabular-nums" id="u2KpiRevenue">$0.00</h3>
            <small class="text-body-secondary">7d Model</small>
          </div>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-header pb-0 d-flex justify-content-between align-items-start">
          <div class="card-title mb-0">
            <h5 class="mb-1">Publisher Fleet</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2KpiNetSummary">Proxy / ADB Ready</p>
          </div>
          <span class="badge bg-label-warning rounded-pill tabular-nums" id="u2KpiProxiesPill">0 IPs</span>
        </div>
        <div class="card-body d-flex flex-column justify-content-between pt-3">
          <div class="d-flex justify-content-between align-items-baseline mb-2">
            <div>
              <h3 class="mb-0 tabular-nums" id="u2KpiDomainsCount">10 / 10</h3>
              <small class="text-body-secondary">Active Domains</small>
            </div>
            <div class="text-end">
              <h4 class="mb-0 text-primary tabular-nums" id="u2KpiPendingTopics">--</h4>
              <small class="text-body-secondary">Queued Topics</small>
            </div>
          </div>
          <div class="d-flex gap-2 mt-2">
            <a href="#autopublish" data-crm-view="autopublish" class="btn btn-sm btn-label-primary flex-fill">CMS Queue</a>
            <a href="#settings" data-crm-view="settings" class="btn btn-sm btn-label-secondary flex-fill">API Health</a>
          </div>
        </div>
      </div>
    </div>
  </div>"""


def _render_analytics_and_runner_row() -> str:
    """Render Vuexy Earning Reports multi-tab chart center + Live Runner Ops card."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-12 col-xl-8">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-3">
          <div class="card-title mb-0">
            <h5 class="mb-1">Revenue Analytics &amp; Traffic Intelligence</h5>
            <p class="card-subtitle text-body-secondary mb-0">Interactive Vuexy multi-view telemetry &amp; 7-day projection model</p>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="badge bg-label-success tabular-nums" id="u2MonthlyBadge">Projected 30d: $0.00</span>
            <button type="button" id="u2BtnRefreshCharts" onclick="window.AdsterraOverview.refreshCharts(true)" class="btn btn-sm btn-label-primary d-inline-flex align-items-center gap-1">
              <i class="icon-base ti tabler-refresh icon-16px"></i>
              <span>Refresh</span>
            </button>
            <a href="/api/stats/csv" download="stats.csv" class="btn btn-sm btn-label-secondary d-inline-flex align-items-center gap-1">
              <i class="icon-base ti tabler-download icon-16px"></i>
              <span>CSV</span>
            </a>
          </div>
        </div>
        <div class="card-body">
          <div class="u2-tablist nav nav-tabs widget-nav-tabs pb-4 gap-3 d-flex flex-nowrap" id="u2AnalyticsTablist" role="tablist" aria-label="Analytics visualizations">
            <button type="button" role="tab" id="u2TabBtnHourly" aria-selected="true" class="u2-tab-btn btn btn-label-secondary d-flex flex-column align-items-center justify-content-center" data-u2-tab="hourly">
              <span class="badge bg-label-primary rounded p-2"><i class="icon-base ti tabler-chart-bar icon-md" aria-hidden="true"></i></span>
              <span class="tab-widget-title small fw-semibold mb-0 mt-2">Hourly Traffic</span>
            </button>
            <button type="button" role="tab" id="u2TabBtnForecast" aria-selected="false" tabindex="-1" class="u2-tab-btn btn btn-label-secondary d-flex flex-column align-items-center justify-content-center" data-u2-tab="forecast">
              <span class="badge bg-label-success rounded p-2"><i class="icon-base ti tabler-trending-up icon-md" aria-hidden="true"></i></span>
              <span class="tab-widget-title small fw-semibold mb-0 mt-2">7-Day Forecast</span>
            </button>
            <button type="button" role="tab" id="u2TabBtnDomains" aria-selected="false" tabindex="-1" class="u2-tab-btn btn btn-label-secondary d-flex flex-column align-items-center justify-content-center" data-u2-tab="domains">
              <span class="badge bg-label-info rounded p-2"><i class="icon-base ti tabler-world icon-md" aria-hidden="true"></i></span>
              <span class="tab-widget-title small fw-semibold mb-0 mt-2">Domain Split</span>
            </button>
            <button type="button" role="tab" id="u2TabBtnDiurnal" aria-selected="false" tabindex="-1" class="u2-tab-btn btn btn-label-secondary d-flex flex-column align-items-center justify-content-center" data-u2-tab="diurnal">
              <span class="badge bg-label-warning rounded p-2"><i class="icon-base ti tabler-clock-24 icon-md" aria-hidden="true"></i></span>
              <span class="tab-widget-title small fw-semibold mb-0 mt-2">Diurnal Curve</span>
            </button>
          </div>

          <div id="u2PanelHourly" role="tabpanel" aria-labelledby="u2TabBtnHourly" tabindex="0">
            <div id="u2ChartHourly" style="min-height: 255px;"></div>
            <p class="small text-body-secondary mb-0 mt-2" id="u2HourlySummary">Loading hourly pacing from sessions.db...</p>
          </div>

          <div id="u2PanelForecast" role="tabpanel" aria-labelledby="u2TabBtnForecast" hidden="until-found">
            <div id="u2ChartForecast" style="min-height: 215px;"></div>
            <div class="row g-2 mt-2" id="u2ForecastTiles"></div>
          </div>

          <div id="u2PanelDomains" role="tabpanel" aria-labelledby="u2TabBtnDomains" hidden="until-found">
            <div id="u2ChartDomains" style="min-height: 255px;"></div>
            <p class="small text-body-secondary mb-0 mt-2" id="u2DomainsSummary">Comparing live impressions &amp; clicks across all active domains.</p>
          </div>

          <div id="u2PanelDiurnal" role="tabpanel" aria-labelledby="u2TabBtnDiurnal" hidden="until-found">
            <div id="u2ChartDiurnal" style="min-height: 255px;"></div>
            <p class="small text-body-secondary mb-0 mt-2" id="u2DiurnalSummary">24-hour organic traffic shaping curve from config.yaml.</p>
          </div>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-4">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-start gap-2">
          <div class="card-title mb-0">
            <h5 class="mb-1">Live Runner &amp; Identity</h5>
            <p class="card-subtitle text-body-secondary mb-0">Session Engine Control</p>
          </div>
          <span class="badge bg-label-secondary" id="u2RunnerBadge">STOPPED</span>
        </div>
        <div class="card-body d-flex flex-column gap-3">
          <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
            <span class="badge bg-label-primary" id="u2RunnerModeBadge">PROXY POOL</span>
            <span class="small text-body-secondary tabular-nums">PID: <strong id="u2MetaPid">&mdash;</strong></span>
          </div>

          <div class="d-grid gap-2" style="grid-template-columns: repeat(3, 1fr);">
            <button type="button" id="u2BtnStart" onclick="window.AdsterraOverview.startRunner()" class="btn btn-success btn-sm d-inline-flex align-items-center justify-content-center gap-1">
              <i class="icon-base ti tabler-player-play icon-16px"></i>
              <span>Start</span>
            </button>
            <button type="button" id="u2BtnStop" onclick="window.AdsterraOverview.stopRunner()" disabled class="btn btn-label-warning btn-sm d-inline-flex align-items-center justify-content-center gap-1">
              <i class="icon-base ti tabler-player-pause icon-16px"></i>
              <span>Stop</span>
            </button>
            <button type="button" id="u2BtnForceStop" onclick="window.AdsterraShell.forceStopAll()" class="btn btn-danger btn-sm d-inline-flex align-items-center justify-content-center gap-1">
              <i class="icon-base ti tabler-player-stop icon-16px"></i>
              <span>Force</span>
            </button>
          </div>

          <div class="border rounded p-3 bg-body-tertiary">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
              <span class="small fw-semibold">Active User-Agent</span>
              <span class="badge bg-label-secondary" id="u2UaLiveBadge">IDLE</span>
            </div>
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
              <span class="badge bg-label-info" id="u2UaDeviceBadge">Ready</span>
              <button type="button" id="u2BtnSyncUa" onclick="window.AdsterraOverview.syncUserAgents()" class="btn btn-xs btn-label-primary">
                <i class="icon-base ti tabler-refresh icon-14px me-1"></i>Sync UA Pool
              </button>
            </div>
            <div class="u2-ua-code font-monospace small p-2 rounded border mb-2" id="u2UaText">Ready &mdash; Fresh fingerprint selects on launch</div>
            <div class="d-flex justify-content-between small text-body-secondary">
              <span>IP: <strong id="u2UaIp">&mdash;</strong></span>
              <span>At: <strong id="u2UaTime">&mdash;</strong></span>
            </div>
            <div class="small text-body-secondary text-truncate mt-1">Target: <strong id="u2UaTarget" class="font-monospace">&mdash;</strong></div>
          </div>

          <div class="row g-2 border-top pt-3 mt-auto">
            <div class="col-4 text-center border-end">
              <div class="small text-body-secondary">Diurnal/hr</div>
              <div class="fw-semibold tabular-nums" id="u2MetaHourlyTarget">--</div>
            </div>
            <div class="col-4 text-center border-end">
              <div class="small text-body-secondary">UA Pool</div>
              <div class="fw-semibold tabular-nums" id="u2MetaUaPool">--</div>
            </div>
            <div class="col-4 text-center">
              <div class="small text-body-secondary">Proxies</div>
              <div class="fw-semibold tabular-nums" id="u2MetaProxies">--</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>"""


def _render_fleet_and_breakdown_row() -> str:
    """Render responsive 10-Domain Governance table + Vuexy Device/Fleet Share card."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-12 col-xl-8">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
          <div class="card-title mb-0">
            <h5 class="mb-1">10-Domain Fleet Governance &amp; Circuit Breakers</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2FleetSummaryText">Independent per-domain CTR protection (&le; 5.0%)</p>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="badge bg-label-success" id="u2BreakerBadge">0 Breakers Tripped</span>
            <button type="button" id="u2BtnResetBreakers" onclick="window.AdsterraOverview.resetCircuitBreakers()" class="btn btn-sm btn-label-warning">
              <i class="icon-base ti tabler-lock-open icon-16px me-1"></i>Reset Breakers
            </button>
          </div>
        </div>
        <div class="card-body p-0">
          <div class="u2-table-wrap" tabindex="0" role="region" aria-labelledby="u2FleetCaption">
            <table class="table table-hover align-middle mb-0 u2-responsive-table">
              <caption id="u2FleetCaption" class="visually-hidden">Today traffic metrics and circuit breaker health for all 10 publisher domains</caption>
              <thead>
                <tr>
                  <th scope="col">Domain</th>
                  <th scope="col">Sessions</th>
                  <th scope="col">Imps / Clicks</th>
                  <th scope="col">CTR Headroom</th>
                  <th scope="col">Status</th>
                  <th scope="col">CPM</th>
                  <th scope="col" class="text-end">Revenue</th>
                </tr>
              </thead>
              <tbody id="u2DomainsTbody">
                <tr><td colspan="7" class="text-center text-body-secondary py-5">Loading 10-domain fleet telemetry...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-4">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-start">
          <div class="card-title mb-0">
            <h5 class="mb-1">Device Mix &amp; Top Domains</h5>
            <p class="card-subtitle text-body-secondary mb-0" id="u2TotalUaSubtitle">useragent.in pool distribution</p>
          </div>
          <span class="badge bg-label-info">82 / 18 Split</span>
        </div>
        <div class="card-body d-flex flex-column gap-4">
          <ul class="list-unstyled mb-0 d-flex flex-column gap-3" id="u2UaMixList">
            <li class="d-flex align-items-center justify-content-between">
              <span class="text-body-secondary small">Loading device mix...</span>
            </li>
          </ul>
          <div class="border-top pt-3">
            <h6 class="small text-uppercase text-body-secondary fw-semibold mb-3">Impression Leaders Today</h6>
            <ul class="list-unstyled mb-0 d-flex flex-column gap-3" id="u2TopDomainsList">
              <li class="text-body-secondary small">Waiting for session telemetry...</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>"""


def _render_timeline_and_console_row() -> str:
    """Render Vuexy Activity Timeline (recent sessions) + Live Process Console."""
    return """
  <div class="row g-6">
    <div class="col-12 col-lg-6">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
          <div class="card-title mb-0 d-flex align-items-center gap-2">
            <i class="icon-base ti tabler-list-details icon-20px text-primary" aria-hidden="true"></i>
            <div>
              <h5 class="mb-0">Live Activity Timeline</h5>
              <small class="text-body-secondary" id="u2TimelineCount">Recent browser sessions</small>
            </div>
          </div>
          <div class="btn-group btn-group-sm" role="group" aria-label="Filter session events">
            <button type="button" class="btn btn-label-primary active" data-u2-tl-filter="all" onclick="window.AdsterraOverview.setTimelineFilter('all')">All</button>
            <button type="button" class="btn btn-label-secondary" data-u2-tl-filter="clicks" onclick="window.AdsterraOverview.setTimelineFilter('clicks')">Clicks</button>
            <button type="button" class="btn btn-label-secondary" data-u2-tl-filter="issues" onclick="window.AdsterraOverview.setTimelineFilter('issues')">Issues</button>
          </div>
        </div>
        <div class="card-body u2-timeline-scroll">
          <ul class="timeline mb-0" id="u2ActivityTimeline">
            <li class="timeline-item timeline-item-transparent">
              <span class="timeline-point timeline-point-secondary"></span>
              <div class="timeline-event">
                <div class="timeline-header mb-1">
                  <h6 class="mb-0">Waiting for session telemetry...</h6>
                </div>
                <p class="mb-0 text-body-secondary small">Sessions recorded in sessions.db appear here live.</p>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="col-12 col-lg-6">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
          <div class="card-title mb-0 d-flex align-items-center gap-2">
            <i class="icon-base ti tabler-terminal-2 icon-20px text-info" aria-hidden="true"></i>
            <div>
              <h5 class="mb-0">Live Runner Console</h5>
              <small class="text-body-secondary">Auto-refreshes every 3s</small>
            </div>
          </div>
          <div class="d-flex gap-2">
            <button type="button" id="u2BtnPauseScroll" aria-pressed="false" onclick="window.AdsterraOverview.toggleLogScroll()" class="btn btn-sm btn-label-secondary">Auto-Scroll: ON</button>
            <button type="button" id="u2BtnCopyLogs" onclick="window.AdsterraOverview.copyLogs()" class="btn btn-sm btn-label-info">
              <i class="icon-base ti tabler-copy icon-16px me-1"></i>Copy
            </button>
          </div>
        </div>
        <div class="card-body">
          <div class="u2-console-viewport font-monospace" id="u2ConsoleBox" tabindex="0" aria-label="Runner stdout log output">Waiting for logs...</div>
        </div>
      </div>
    </div>
  </div>"""


def render_overview_view() -> str:
    """Render the full Component U2 Overview & Live Ops workspace."""
    return "\n".join([
        '<section id="view-overview" class="crm-view active">',
        _render_kpi_strip(),
        _render_analytics_and_runner_row(),
        _render_fleet_and_breakdown_row(),
        _render_timeline_and_console_row(),
        "</section>",
    ])
