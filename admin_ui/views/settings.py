"""System Settings, Multi-Theme Inspector & Rollout Tracker View (U1 + U2)."""

from __future__ import annotations


def render_settings_view() -> str:
    """Render the System Settings & Layer Rollout workspace inside #view-settings."""
    return """
<section id="view-settings" class="crm-view">
  <div class="row g-6">
    <div class="col-lg-6">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-center">
          <div>
            <h5 class="card-title mb-0">Theme &amp; Appearance Controls</h5>
            <small class="text-body-secondary">Light, Dark, System + Semi-Dark Sidebar + Collapse</small>
          </div>
          <span class="badge bg-label-primary" id="shellThemeModeReadout">SYSTEM</span>
        </div>
        <div class="card-body">
          <div class="d-flex flex-wrap gap-2 mb-4" role="group" aria-label="Theme mode quick switch">
            <button type="button" class="btn btn-outline-primary" data-shell-theme-btn="light" onclick="window.AdsterraShell.setTheme('light')">
              <i class="icon-base ti tabler-sun me-1"></i> Light
            </button>
            <button type="button" class="btn btn-outline-primary" data-shell-theme-btn="dark" onclick="window.AdsterraShell.setTheme('dark')">
              <i class="icon-base ti tabler-moon-stars me-1"></i> Dark
            </button>
            <button type="button" class="btn btn-outline-primary" data-shell-theme-btn="system" onclick="window.AdsterraShell.setTheme('system')">
              <i class="icon-base ti tabler-device-desktop-analytics me-1"></i> System
            </button>
          </div>

          <div class="d-flex flex-wrap gap-2 mb-4">
            <button type="button" class="btn btn-label-secondary" onclick="window.AdsterraShell.toggleSemiDark()">
              <i class="icon-base ti tabler-layout-sidebar me-1"></i> Toggle Semi-Dark Sidebar
            </button>
            <button type="button" class="btn btn-label-secondary" onclick="window.AdsterraShell.toggleCollapse()">
              <i class="icon-base ti tabler-layout-sidebar-left-collapse me-1"></i> Collapse / Expand Menu
            </button>
            <button type="button" id="btnShellPing" onclick="window.AdsterraShell.pingApis()" class="btn btn-primary d-inline-flex align-items-center gap-1">
              <i class="icon-base ti tabler-activity icon-18px"></i>
              <span>Ping Live APIs</span>
            </button>
            <button type="button" onclick="window.AdsterraShell.testToast()" class="btn btn-label-info d-inline-flex align-items-center gap-1">
              <i class="icon-base ti tabler-bell icon-18px"></i>
              <span>Test Toast</span>
            </button>
          </div>

          <ul class="list-group list-group-flush border-top pt-2">
            <li class="list-group-item d-flex justify-content-between px-0">
              <span class="text-body-secondary">Rendered Color Scheme</span>
              <span class="fw-semibold" id="shellThemeEffectiveReadout">--</span>
            </li>
            <li class="list-group-item d-flex justify-content-between px-0">
              <span class="text-body-secondary">Sidebar Style</span>
              <span class="fw-semibold" id="shellSemiDarkReadout">--</span>
            </li>
            <li class="list-group-item d-flex justify-content-between px-0">
              <span class="text-body-secondary">Sidebar Width State</span>
              <span class="fw-semibold" id="shellMenuStateReadout">--</span>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-start gap-2 px-0">
              <span class="text-body-secondary">Backend Live API Telemetry</span>
              <span class="fw-semibold text-success text-end crm-api-readout" id="u1ApiPingReadout">Connecting...</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="col-lg-6">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-center">
          <div>
            <h5 class="card-title mb-0">Vuexy Migration Progress (U1-U6)</h5>
            <small class="text-body-secondary">Zero-breakage modular component extraction</small>
          </div>
          <span class="badge bg-label-success">Step 6 / 6 Live</span>
        </div>
        <div class="card-body">
          <div class="table-responsive">
            <table class="table table-sm mb-0">
              <thead>
                <tr>
                  <th scope="col">Layer</th>
                  <th scope="col">Component Scope</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><span class="fw-semibold">U1</span></td>
                  <td>Master Shell, Assets, Nav, Light/Dark/System</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U2</span></td>
                  <td>Overview KPI Sparklines, Tabbed Charts, Runner &amp; Timeline</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U2.5</span></td>
                  <td>Operator Profile, Avatar, Auth Lock &amp; Notification Bell</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U3</span></td>
                  <td>AutoPublish 20-Topic CMS, Stages 1-5 &amp; Preview Modal</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U4</span></td>
                  <td>Adsterra Funnel, Layer 1 Banner Vault &amp; CPL Leads</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U5</span></td>
                  <td>Network, Proxies, ADB, GSC, Push &amp; Telegram</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
                <tr>
                  <td><span class="fw-semibold">U6</span></td>
                  <td>Root (<code>/</code>) Cutover &amp; Legacy <code>/classic</code> Fallback</td>
                  <td><span class="badge bg-label-success">Live &amp; Active</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
"""
