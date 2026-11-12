"""Vuexy v3.1.0 Phase 4 Autonomous Phone Farm & AI Ops Dashboard View."""
from __future__ import annotations

from typing import Optional


def _render_kpi_cards() -> str:
    """Render the 5 Vuexy KPI cards for Phase 4 farm telemetry."""
    return """
  <div class="row g-4 mb-6">
    <div class="col-sm-6 col-xl">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Total Sessions</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-primary"><i class="icon-base ti tabler-activity icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="p4KpiSessions">0</h3>
          <small class="text-body-secondary d-block tabular-nums" id="p4KpiSessionsSub">0 completed &middot; 0 failed</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xl">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Active Devices</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-success"><i class="icon-base ti tabler-device-mobile icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="p4KpiDevices">0</h3>
          <small class="text-body-secondary d-block tabular-nums" id="p4KpiDevicesSub">0 healthy &middot; 0 CGNAT slots</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xl">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">IP Collisions Prevented</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-info"><i class="icon-base ti tabler-shield-check icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="p4KpiCollisions">0</h3>
          <small class="text-body-secondary d-block tabular-nums" id="p4KpiCollisionsSub">0 session blocks &middot; 0 subnet cooldowns</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xl">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">P50 Forecast vs. Actual</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-warning"><i class="icon-base ti tabler-chart-line icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="p4KpiForecast">$0.00 / $0.00</h3>
          <small class="text-body-secondary d-block tabular-nums" id="p4KpiForecastSub">P10 $0.00 &ndash; P90 $0.00</small>
        </div>
      </div>
    </div>

    <div class="col-sm-12 col-xl">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">SAFE MODE Status</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-secondary" id="p4KpiSafeIconBox"><i class="icon-base ti tabler-shield-lock icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-center gap-2 mb-1">
            <span class="badge bg-label-success" id="p4KpiSafeMode">NORMAL</span>
          </div>
          <small class="text-body-secondary d-block text-truncate" id="p4KpiSafeModeSub">0 clean windows</small>
        </div>
      </div>
    </div>
  </div>
"""


def _render_charts_row() -> str:
    """Render ApexCharts containers for P10/P50/P90 Revenue Forecast and Sessions & Device Activity."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-12 col-xl-7">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2 pb-2">
          <div>
            <h5 class="mb-1">P10 / P50 / P90 Revenue Forecast vs. Actuals</h5>
            <small class="text-body-secondary">IRLS quantile bands compared against realized reward / API revenue</small>
          </div>
          <span class="badge bg-label-primary tabular-nums" id="p4ForecastChartMeta">Waiting for data</span>
        </div>
        <div class="card-body">
          <div id="p4ChartForecast" style="min-height: 290px;"></div>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-5">
      <div class="card h-100">
        <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2 pb-2">
          <div>
            <h5 class="mb-1">Sessions &amp; Device Activity</h5>
            <small class="text-body-secondary">Per-device session volume &amp; clicks across USB hub farm</small>
          </div>
          <span class="badge bg-label-info tabular-nums" id="p4ActivityChartMeta">0 devices</span>
        </div>
        <div class="card-body">
          <div id="p4ChartActivity" style="min-height: 290px;"></div>
        </div>
      </div>
    </div>
  </div>
"""


def _render_tables_section() -> str:
    """Render interactive searchable/filterable Vuexy tables for all Phase 3 tables."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-12">
      <div class="card">
        <div class="card-header d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
          <div>
            <h5 class="mb-1">Farm Devices (<code>p3_farm_devices</code>)</h5>
            <small class="text-body-secondary">USB hub port mapping, CDP/B1 ports, health &amp; quarantine telemetry</small>
          </div>
          <div class="d-flex flex-wrap gap-2">
            <input type="search" id="p4SearchDevices" class="form-control form-control-sm" style="width: 210px;" placeholder="Search device ID or port..." aria-label="Search farm devices" />
            <select id="p4FilterDeviceStatus" class="form-select form-select-sm" style="width: 150px;" aria-label="Filter farm device status">
              <option value="all">All Statuses</option>
              <option value="healthy">Healthy</option>
              <option value="quarantined">Quarantined</option>
              <option value="offline">Offline</option>
            </select>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0" id="p4TableDevices">
            <thead>
              <tr>
                <th scope="col">Device ID</th>
                <th scope="col">USB Port</th>
                <th scope="col">CDP / B1 Ports</th>
                <th scope="col">Status</th>
                <th scope="col">Failures</th>
                <th scope="col">Sessions / Clicks</th>
                <th scope="col">Last Seen</th>
              </tr>
            </thead>
            <tbody id="p4BodyDevices">
              <tr><td colspan="7" class="text-center text-body-secondary py-4">Loading farm devices...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12">
      <div class="card">
        <div class="card-header d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
          <div>
            <h5 class="mb-1">Recent Sessions (<code>p3_sessions</code>)</h5>
            <small class="text-body-secondary">Live &amp; paper execution log with CGNAT /24 &amp; /20 subnet provenance</small>
          </div>
          <div class="d-flex flex-wrap gap-2">
            <input type="search" id="p4SearchSessions" class="form-control form-control-sm" style="width: 220px;" placeholder="Search session, device, domain..." aria-label="Search sessions" />
            <select id="p4FilterSessionStatus" class="form-select form-select-sm" style="width: 160px;" aria-label="Filter session status">
              <option value="all">All Statuses</option>
              <option value="completed">Completed</option>
              <option value="started">Started</option>
              <option value="failed">Failed / Error</option>
              <option value="blocked">Blocked / Collision</option>
            </select>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0" id="p4TableSessions">
            <thead>
              <tr>
                <th scope="col">Session ID</th>
                <th scope="col">Device</th>
                <th scope="col">Mode</th>
                <th scope="col">Domain</th>
                <th scope="col">IP / Subnet (/24)</th>
                <th scope="col">Status</th>
                <th scope="col">Dwell (s)</th>
                <th scope="col">Started</th>
              </tr>
            </thead>
            <tbody id="p4BodySessions">
              <tr><td colspan="8" class="text-center text-body-secondary py-4">Loading sessions...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-6">
      <div class="card h-100">
        <div class="card-header d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-2">
          <div>
            <h5 class="mb-1">CGNAT Carrier Slots (<code>p3_cgnat_slots</code>)</h5>
            <small class="text-body-secondary">/24 &amp; /20 mobile-tower IP cooldown locks</small>
          </div>
          <div class="d-flex gap-2">
            <input type="search" id="p4SearchCgnat" class="form-control form-control-sm" style="width: 170px;" placeholder="Search IP or subnet..." aria-label="Search CGNAT slots" />
            <select id="p4FilterCgnatActive" class="form-select form-select-sm" style="width: 120px;" aria-label="Filter CGNAT slot state">
              <option value="all">All</option>
              <option value="1">Active</option>
              <option value="0">Released</option>
            </select>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0" id="p4TableCgnat">
            <thead>
              <tr>
                <th scope="col">Device</th>
                <th scope="col">IP Address</th>
                <th scope="col">/24 &bull; /20</th>
                <th scope="col">State</th>
                <th scope="col">Acquired</th>
              </tr>
            </thead>
            <tbody id="p4BodyCgnat">
              <tr><td colspan="5" class="text-center text-body-secondary py-4">Loading CGNAT slots...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12 col-xl-6">
      <div class="card h-100">
        <div class="card-header d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-2">
          <div>
            <h5 class="mb-1">Quantile Forecasts (<code>p3_forecasts</code>)</h5>
            <small class="text-body-secondary">P10 / P50 / P90 revenue &amp; eCPM projections</small>
          </div>
          <div class="d-flex gap-2">
            <input type="search" id="p4SearchForecasts" class="form-control form-control-sm" style="width: 160px;" placeholder="Filter method/horizon..." aria-label="Search forecasts" />
            <select id="p4FilterForecastMethod" class="form-select form-select-sm" style="width: 145px;" aria-label="Filter forecast method">
              <option value="all">All Methods</option>
              <option value="irls_quantile">IRLS Quantile</option>
              <option value="median_fallback">Median Fallback</option>
            </select>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0" id="p4TableForecasts">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Horizon</th>
                <th scope="col">Method</th>
                <th scope="col">P10 / P50 / P90 Rev</th>
                <th scope="col">P50 eCPM</th>
              </tr>
            </thead>
            <tbody id="p4BodyForecasts">
              <tr><td colspan="5" class="text-center text-body-secondary py-4">Loading forecasts...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12" id="p4CalibrationSection">
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <div>
            <h5 class="mb-1">Calibration Drift Monitor (<code>p3_calibration_reports</code>)</h5>
            <small class="text-body-secondary">Rolling P10&ndash;P90 coverage &amp; A5 RPM drift alerts</small>
          </div>
          <span class="badge bg-label-primary" id="p4CalibrationCountBadge">0 reports</span>
        </div>
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0" id="p4TableCalibration">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Status</th>
                <th scope="col">Coverage</th>
                <th scope="col">P50 MAE</th>
                <th scope="col">A5 MAPE</th>
                <th scope="col">Drift / Retrain</th>
              </tr>
            </thead>
            <tbody id="p4BodyCalibration">
              <tr><td colspan="6" class="text-center text-body-secondary py-4">Loading calibration reports...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
"""


def render_phase4_farm_view(
    refresh_interval_ms: int = 5000,
    *,
    active: bool = False,
) -> str:
    """Render the modular Vuexy Phase 4 farm & AI Ops workspace section."""
    view_cls = "crm-view active" if active else "crm-view"
    return f"""
<section id="view-phase4-farm" class="{view_cls}" data-refresh-ms="{int(refresh_interval_ms)}">
  <div id="p4DbErrorBanner" class="alert alert-danger d-flex align-items-start justify-content-between gap-3 mb-6 d-none" role="alert" aria-live="assertive">
    <div class="d-flex align-items-start gap-2">
      <i class="icon-base ti tabler-alert-triangle icon-22px mt-1"></i>
      <div>
        <h6 class="alert-heading mb-1" id="p4DbErrorTitle">Database Unavailable</h6>
        <div class="small" id="p4DbErrorMessage">Unable to query Phase 3 SQLite database.</div>
      </div>
    </div>
    <span class="badge bg-label-danger text-uppercase" id="p4DbErrorCode">ERROR</span>
  </div>

  <div class="card mb-6">
    <div class="card-body d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-3 py-4">
      <div>
        <div class="d-flex align-items-center gap-2 mb-1">
          <h4 class="mb-0">Phase 4 &middot; Autonomous Farm &amp; AI Ops</h4>
          <span class="badge bg-label-info" id="p4DbStatusBadge">CONNECTING</span>
        </div>
        <small class="text-body-secondary tabular-nums" id="p4LastUpdatedText">Syncing live SQLite telemetry...</small>
      </div>
      <div class="d-flex flex-wrap align-items-center gap-2">
        <button type="button" class="btn btn-sm btn-label-primary" id="p4BtnRunCalibration">
          <i class="icon-base ti tabler-activity-heartbeat icon-16px me-1"></i>Run Calibration Check
        </button>
        <button type="button" class="btn btn-sm btn-primary" id="p4BtnRefresh">
          <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Refresh Now
        </button>
      </div>
    </div>
  </div>

  {_render_kpi_cards()}
  {_render_charts_row()}
  {_render_tables_section()}
</section>
"""


def render_phase4_dashboard_page(
    refresh_interval_ms: int = 5000,
    initial_title: Optional[str] = None,
) -> str:
    """Render the standalone Vuexy v3.1.0 HTML document for the Phase 4 Dashboard."""
    title = initial_title or "AdsterraFleet | Phase 4 Autonomous Farm Dashboard"
    body = render_phase4_farm_view(refresh_interval_ms=refresh_interval_ms, active=True)

    return f"""<!doctype html>
<html
  lang="en"
  class="layout-navbar-fixed layout-compact"
  dir="ltr"
  data-skin="default"
  data-bs-theme="system"
  data-assets-path="/crm-assets/"
  data-template="adstera-crm">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, minimum-scale=1.0, maximum-scale=1.0" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="color-scheme" content="light dark" />
    <script>
      (function () {{
        try {{
          var tName = document.documentElement.getAttribute("data-template") || "adstera-crm";
          var stored = localStorage.getItem("templateCustomizer-" + tName + "--Theme") || "system";
          var meta = document.querySelector('meta[name="color-scheme"]');
          if (meta) {{
            meta.content = stored === "light" ? "light" : stored === "dark" ? "dark" : "light dark";
          }}
          var resolved = stored === "system"
            ? (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
            : stored;
          document.documentElement.setAttribute("data-bs-theme", resolved);
        }} catch (_) {{}}
      }})();
    </script>
    <title>{title}</title>
    <link rel="icon" type="image/x-icon" href="/crm-assets/img/favicon/favicon.ico" />
    <link rel="stylesheet" href="/crm-assets/vendor/fonts/iconify-icons.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/core.css" />
    <link rel="stylesheet" href="/crm-assets/css/demo.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/apex-charts/apex-charts.css" />
    <link rel="stylesheet" href="/crm-assets/css/cms-shell.css" />
  </head>
  <body>
    <div class="layout-wrapper layout-content-navbar layout-without-menu">
      <div class="layout-container">
        <div class="layout-page">
          <nav class="layout-navbar container-xxl navbar-detached navbar navbar-expand-xl align-items-center bg-navbar-theme" id="layout-navbar">
            <div class="navbar-nav-right d-flex align-items-center justify-content-between w-100">
              <div class="d-flex align-items-center gap-2">
                <span class="fw-bold text-primary">AdsterraFleet</span>
                <span class="text-body-secondary small">/ Phase 4 Live Operations</span>
              </div>
              <div class="d-flex align-items-center gap-2">
                <span class="badge bg-label-primary" id="p4NavRefreshBadge">Auto-Refresh {int(refresh_interval_ms / 1000)}s</span>
              </div>
            </div>
          </nav>

          <div class="content-wrapper">
            <div class="container-xxl flex-grow-1 container-p-y">
              {body}
            </div>

            <footer class="content-footer footer bg-footer-theme">
              <div class="container-xxl">
                <div class="footer-container d-flex align-items-center justify-content-between py-4 flex-md-row flex-column">
                  <div class="text-body">
                    AdsterraFleet Phase 4 Autonomous Farm &amp; AI Ops &bull; Read-Only SQLite Telemetry
                  </div>
                  <div class="d-flex gap-3">
                    <a href="/api/phase4/health" class="footer-link">Health JSON</a>
                    <a href="/api/phase4/dashboard" class="footer-link">Dashboard API</a>
                  </div>
                </div>
              </div>
            </footer>
            <div class="content-backdrop fade"></div>
          </div>
        </div>
      </div>
    </div>

    <script src="/crm-assets/vendor/libs/popper/popper.js"></script>
    <script src="/crm-assets/vendor/js/bootstrap.js"></script>
    <script src="/crm-assets/vendor/libs/apex-charts/apexcharts.js"></script>
    <script src="/crm-assets/js/crm-phase4.js"></script>
  </body>
</html>
"""
