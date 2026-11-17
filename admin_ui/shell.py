"""Vuexy v3.1.0 Master Shell Renderer — Component U1 + Modular Views."""

from __future__ import annotations

from admin_ui.views import (
    render_autopublish_view,
    render_growth_view,
    render_live_workflow_view,
    render_monetization_view,
    render_network_view,
    render_overview_view,
    render_phase4_farm_view,
    render_profile_view,
    render_settings_view,
)


def _render_sidebar() -> str:
    """Return the Vuexy vertical collapsible sidebar with 6 modular workspaces."""
    return """
<aside id="layout-menu" class="layout-menu menu-vertical menu" data-bs-theme="dark">
  <div class="app-brand demo">
    <a href="#overview" class="app-brand-link" data-crm-view="overview">
      <span class="app-brand-logo demo">
        <span class="text-primary">
          <svg width="30" height="22" viewBox="0 0 32 22" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path fill-rule="evenodd" clip-rule="evenodd" d="M0.00172773 0V6.85398C0.00172773 6.85398 -0.133178 9.01207 1.98092 10.8388L13.6912 21.9964L19.7809 21.9181L18.8042 9.88248L16.4951 7.17289L9.23799 0H0.00172773Z" fill="currentColor" />
            <path fill-rule="evenodd" clip-rule="evenodd" d="M7.77295 16.3566L23.6563 0H32V6.88383C32 6.88383 31.8262 9.17836 30.6591 10.4057L19.7824 22H13.6938L7.77295 16.3566Z" fill="currentColor" />
          </svg>
        </span>
      </span>
      <span class="app-brand-text demo menu-text fw-bold ms-3">AdsterraFleet</span>
    </a>

    <a href="javascript:void(0);" class="layout-menu-toggle menu-link text-large ms-auto" aria-label="Collapse sidebar">
      <i class="icon-base ti menu-toggle-icon d-none d-xl-block"></i>
      <i class="icon-base ti tabler-x d-block d-xl-none"></i>
    </a>
  </div>

  <div class="menu-inner-shadow"></div>

  <ul class="menu-inner py-1">
    <li class="menu-header small">
      <span class="menu-header-text">Command Workspaces</span>
    </li>
    <li class="menu-item active">
      <a href="#overview" class="menu-link" data-crm-view="overview">
        <i class="menu-icon icon-base ti tabler-smart-home"></i>
        <div>Overview &amp; Live Ops</div>
        <span class="badge text-bg-success rounded-pill ms-auto">U2</span>
      </a>
    </li>
    <li class="menu-item">
      <a href="#phase4-farm" class="menu-link" data-crm-view="phase4-farm">
        <i class="menu-icon icon-base ti tabler-cpu"></i>
        <div>Phase 4 Farm &amp; AI Ops</div>
        <span class="badge text-bg-secondary rounded-pill ms-auto" id="sidebarPhase4Badge">P4</span>
      </a>
    </li>
    <li class="menu-item">
      <a href="#workflow-live" class="menu-link" data-crm-view="workflow-live">
        <i class="menu-icon icon-base ti tabler-git-branch"></i>
        <div>Live Workflow</div>
        <span class="badge text-bg-warning rounded-pill ms-auto" id="sidebarWorkflowBadge">LIVE</span>
      </a>
    </li>
    <li class="menu-item">
      <a href="#autopublish" class="menu-link" data-crm-view="autopublish">
        <i class="menu-icon icon-base ti tabler-sparkles"></i>
        <div>AutoPublish CMS</div>
        <span class="badge text-bg-primary rounded-pill ms-auto" id="sidebarAutopublishBadge">0</span>
      </a>
    </li>
    <li class="menu-item">
      <a href="#content" class="menu-link" data-crm-view="content">
        <i class="menu-icon icon-base ti tabler-file-text"></i>
        <div>Content</div>
      </a>
    </li>

    <li class="menu-header small">
      <span class="menu-header-text">Revenue &amp; Traffic</span>
    </li>
    <li class="menu-item">
      <a href="#monetization" class="menu-link" data-crm-view="monetization">
        <i class="menu-icon icon-base ti tabler-currency-dollar"></i>
        <div>Monetization &amp; Ads</div>
      </a>
    </li>
    <li class="menu-item">
      <a href="#network" class="menu-link" data-crm-view="network">
        <i class="menu-icon icon-base ti tabler-network"></i>
        <div>Network &amp; Proxies</div>
      </a>
    </li>
    <li class="menu-item">
      <a href="#growth" class="menu-link" data-crm-view="growth">
        <i class="menu-icon icon-base ti tabler-trending-up"></i>
        <div>Growth, SEO &amp; Push</div>
      </a>
    </li>

    <li class="menu-header small">
      <span class="menu-header-text">System &amp; Legacy Switch</span>
    </li>
    <li class="menu-item">
      <a href="#profile" class="menu-link" data-crm-view="profile">
        <i class="menu-icon icon-base ti tabler-user-shield"></i>
        <div>Profile &amp; Security</div>
        <span class="badge text-bg-info rounded-pill ms-auto">U2.5</span>
      </a>
    </li>
    <li class="menu-item">
      <a href="#settings" class="menu-link" data-crm-view="settings">
        <i class="menu-icon icon-base ti tabler-settings"></i>
        <div>Settings &amp; Theme</div>
      </a>
    </li>
    <li class="menu-item">
      <a href="/classic" class="menu-link">
        <i class="menu-icon icon-base ti tabler-arrow-back-up"></i>
        <div>Classic Legacy UI</div>
      </a>
    </li>
    <li class="menu-item">
      <a href="/autopublish" class="menu-link">
        <i class="menu-icon icon-base ti tabler-rocket"></i>
        <div>Classic AutoPublish</div>
      </a>
    </li>
  </ul>
</aside>
"""


def _render_navbar() -> str:
    """Return the Vuexy sticky top navbar with search, theme switcher, status pill & Force Stop."""
    return """
<nav class="layout-navbar container-xxl navbar-detached navbar navbar-expand-xl align-items-center bg-navbar-theme" id="layout-navbar">
  <div class="layout-menu-toggle navbar-nav align-items-xl-center me-3 me-xl-0 d-xl-none">
    <a class="nav-item nav-link px-0 me-xl-6" href="javascript:void(0)" aria-label="Open menu">
      <i class="icon-base ti tabler-menu-2 icon-md"></i>
    </a>
  </div>

  <div class="navbar-nav-right d-flex align-items-center justify-content-end" id="navbar-collapse">
    <div class="navbar-nav align-items-center">
      <div class="nav-item navbar-search-wrapper px-md-0 px-2 mb-0">
        <a class="nav-item nav-link search-toggler d-flex align-items-center px-0" href="javascript:void(0);">
          <span class="d-inline-block text-body-secondary fw-normal" id="autocomplete"></span>
        </a>
      </div>
    </div>

    <ul class="navbar-nav flex-row align-items-center ms-md-auto gap-2">
      <li class="nav-item d-none d-md-flex align-items-center">
        <span class="badge bg-label-success d-inline-flex align-items-center px-3 py-2" id="shellStatusPill">
          <span id="shellRunnerDot" class="status-dot-idle me-2"></span>
          <span id="shellRunnerText" class="fw-semibold">CHECKING...</span>
        </span>
      </li>

      <li class="nav-item d-none d-lg-flex align-items-center">
        <span class="badge bg-label-primary px-3 py-2 tabular-nums" id="shellDomainsPill">10 Sites · -- Queued</span>
      </li>

      <li class="nav-item">
        <button
          type="button"
          id="shellForceStopBtn"
          onclick="window.AdsterraShell.forceStopAll()"
          class="btn btn-sm btn-danger d-inline-flex align-items-center gap-1"
          title="Stop active runners safely"
        >
          <i class="icon-base ti tabler-player-stop icon-16px"></i>
          <span class="d-none d-sm-inline">Force Stop</span>
        </button>
      </li>

      <li class="nav-item dropdown">
        <a
          class="nav-link dropdown-toggle hide-arrow btn btn-icon btn-text-secondary rounded-pill"
          id="nav-theme"
          href="javascript:void(0);"
          data-bs-toggle="dropdown"
          aria-label="Toggle color theme"
        >
          <i class="icon-base ti tabler-sun icon-22px theme-icon-active text-heading"></i>
          <span class="d-none ms-2" id="nav-theme-text">Toggle theme</span>
        </a>
        <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="nav-theme-text">
          <li>
            <button type="button" class="dropdown-item align-items-center" data-bs-theme-value="light" aria-pressed="false">
              <span><i class="icon-base ti tabler-sun icon-22px me-3" data-icon="sun"></i>Light</span>
            </button>
          </li>
          <li>
            <button type="button" class="dropdown-item align-items-center" data-bs-theme-value="dark" aria-pressed="false">
              <span><i class="icon-base ti tabler-moon-stars icon-22px me-3" data-icon="moon-stars"></i>Dark</span>
            </button>
          </li>
          <li>
            <button type="button" class="dropdown-item align-items-center" data-bs-theme-value="system" aria-pressed="false">
              <span><i class="icon-base ti tabler-device-desktop-analytics icon-22px me-3" data-icon="device-desktop-analytics"></i>System</span>
            </button>
          </li>
        </ul>
      </li>

      <li class="nav-item dropdown-shortcuts navbar-dropdown dropdown d-none d-sm-block">
        <a class="nav-link dropdown-toggle hide-arrow btn btn-icon btn-text-secondary rounded-pill" href="javascript:void(0);" data-bs-toggle="dropdown" aria-label="Quick routes">
          <i class="icon-base ti tabler-layout-grid-add icon-22px text-heading"></i>
        </a>
        <div class="dropdown-menu dropdown-menu-end p-0">
          <div class="dropdown-menu-header border-bottom">
            <div class="dropdown-header d-flex align-items-center py-3">
              <h6 class="mb-0 me-auto">Quick Switch</h6>
            </div>
          </div>
          <div class="dropdown-shortcuts-list scrollable-container">
            <div class="row row-bordered overflow-visible g-0">
              <div class="dropdown-shortcuts-item col">
                <span class="dropdown-shortcuts-icon rounded-circle mb-3"><i class="icon-base ti tabler-layout-dashboard icon-26px text-heading"></i></span>
                <a href="/classic" class="stretched-link">Classic UI</a>
                <small>Legacy /classic</small>
              </div>
              <div class="dropdown-shortcuts-item col">
                <span class="dropdown-shortcuts-icon rounded-circle mb-3"><i class="icon-base ti tabler-rocket icon-26px text-heading"></i></span>
                <a href="/autopublish" class="stretched-link">AutoPublish</a>
                <small>Pipeline Stream</small>
              </div>
              <div class="dropdown-shortcuts-item col">
                <span class="dropdown-shortcuts-icon rounded-circle mb-3"><i class="icon-base ti tabler-cpu icon-26px text-heading"></i></span>
                <a href="#phase4-farm" class="stretched-link" data-crm-view="phase4-farm">Phase 4 Farm</a>
                <small>CGNAT &amp; AI Ops</small>
              </div>
            </div>
          </div>
        </div>
      </li>

      <!-- Notification Bell -->
      <li class="nav-item dropdown-notifications navbar-dropdown dropdown me-2">
        <a
          class="nav-link dropdown-toggle hide-arrow btn btn-icon btn-text-secondary rounded-pill"
          id="shellNotifBellBtn"
          href="javascript:void(0);"
          data-bs-toggle="dropdown"
          data-bs-auto-close="outside"
          aria-expanded="false"
          aria-label="Notifications"
        >
          <span class="position-relative">
            <i class="icon-base ti tabler-bell icon-22px text-heading"></i>
            <span id="shellNotifDot" class="badge rounded-pill bg-danger badge-dot badge-notifications border d-none"></span>
          </span>
        </a>
        <ul class="dropdown-menu dropdown-menu-end p-0">
          <li class="dropdown-menu-header border-bottom">
            <div class="dropdown-header d-flex align-items-center py-3">
              <h6 class="mb-0 me-auto">Notifications</h6>
              <div class="d-flex align-items-center h6 mb-0">
                <span class="badge bg-label-primary me-2" id="shellNotifBadge">0 New</span>
                <button
                  type="button"
                  id="shellNotifMarkAllBtn"
                  class="dropdown-notifications-all p-2 btn btn-icon"
                  title="Mark all as read"
                  aria-label="Mark all notifications as read"
                >
                  <i class="icon-base ti tabler-mail-opened text-heading"></i>
                </button>
              </div>
            </div>
          </li>
          <li class="dropdown-notifications-list scrollable-container">
            <ul class="list-group list-group-flush" id="shellNotifList">
              <li class="list-group-item py-3 text-body-secondary small">Loading alerts...</li>
            </ul>
          </li>
          <li class="border-top">
            <div class="d-grid p-3">
              <button type="button" class="btn btn-primary btn-sm d-flex justify-content-center" id="shellNotifViewAllBtn">
                <small class="align-middle fw-medium">View All Alerts &amp; Security</small>
              </button>
            </div>
          </li>
        </ul>
      </li>

      <li class="nav-item navbar-dropdown dropdown-user dropdown">
        <a class="nav-link dropdown-toggle hide-arrow p-0" href="javascript:void(0);" data-bs-toggle="dropdown" aria-label="Operator menu">
          <div class="avatar avatar-online">
            <img id="shellNavUserAvatar" src="/crm-assets/img/avatars/1.png" alt="Operator Avatar" class="rounded-circle" />
          </div>
        </a>
        <ul class="dropdown-menu dropdown-menu-end">
          <li>
            <a class="dropdown-item mt-0" href="#profile" data-crm-view="profile" data-u25-tab="account">
              <div class="d-flex align-items-center">
                <div class="flex-shrink-0 me-2">
                  <div class="avatar avatar-online">
                    <img id="shellNavMenuAvatar" src="/crm-assets/img/avatars/1.png" alt="Operator" class="rounded-circle" />
                  </div>
                </div>
                <div class="flex-grow-1">
                  <h6 class="mb-0" id="shellNavUserName">Master Operator</h6>
                  <small class="text-body-secondary" id="shellNavUserRole">Lead Publisher Admin</small>
                </div>
              </div>
            </a>
          </li>
          <li><div class="dropdown-divider my-1 mx-n2"></div></li>
          <li><a class="dropdown-item" href="#profile" data-crm-view="profile" data-u25-tab="account"><i class="icon-base ti tabler-user me-3 icon-md"></i><span>My Profile</span></a></li>
          <li><a class="dropdown-item" href="#profile" data-crm-view="profile" data-u25-tab="security"><i class="icon-base ti tabler-shield-lock me-3 icon-md"></i><span>Security &amp; Auth Lock</span></a></li>
          <li><a class="dropdown-item" href="#profile" data-crm-view="profile" data-u25-tab="connections"><i class="icon-base ti tabler-plug-connected me-3 icon-md"></i><span>Connected APIs</span></a></li>
          <li><a class="dropdown-item" href="#settings" data-crm-view="settings"><i class="icon-base ti tabler-palette me-3 icon-md"></i><span>Theme &amp; Customizer</span></a></li>
          <li><a class="dropdown-item" href="/"><i class="icon-base ti tabler-arrow-back-up me-3 icon-md"></i><span>Open Classic Dashboard</span></a></li>
          <li><div class="dropdown-divider my-1 mx-n2"></div></li>
          <li>
            <button type="button" class="dropdown-item text-danger" id="shellLogoutBtn">
              <i class="icon-base ti tabler-logout me-3 icon-md"></i><span>Sign Out / Lock CRM</span>
            </button>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</nav>
"""


def _render_staged_sections() -> str:
    """All U1-U5 workspaces are live; keep helper returning empty markup for compatibility."""
    return ""


def render_crm_shell() -> str:
    """Render the complete Vuexy v3.1.0 Admin Shell with all U1-U5 modular workspaces."""
    sidebar = _render_sidebar()
    navbar = _render_navbar()
    overview = render_overview_view()
    phase4_view = render_phase4_farm_view(active=False)
    live_workflow_view = render_live_workflow_view(active=False)
    autopublish_view = render_autopublish_view()
    monetization_view = render_monetization_view()
    network_view = render_network_view()
    growth_view = render_growth_view()
    staged = _render_staged_sections()
    profile_view = render_profile_view()
    settings_view = render_settings_view()

    return f"""<!doctype html>
<html
  lang="en"
  class="layout-navbar-fixed layout-menu-fixed layout-compact"
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
    <title>AdsterraFleet CRM | Overview &amp; Live Ops</title>
    <link rel="icon" type="image/x-icon" href="/crm-assets/img/favicon/favicon.ico" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500;1,600;1,700&display=swap" rel="stylesheet" />

    <link rel="stylesheet" href="/crm-assets/vendor/fonts/iconify-icons.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/fonts/flag-icons.css" />
    <script src="/crm-assets/vendor/libs/@algolia/autocomplete-js.js"></script>

    <link rel="stylesheet" href="/crm-assets/vendor/libs/node-waves/node-waves.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/pickr/pickr-themes.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/core.css" />
    <link rel="stylesheet" href="/crm-assets/css/demo.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/perfect-scrollbar/perfect-scrollbar.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/notyf/notyf.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/sweetalert2/sweetalert2.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/libs/apex-charts/apex-charts.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/pages/page-profile.css" />
    <link rel="stylesheet" href="/crm-assets/css/cms-shell.css" />

    <script src="/crm-assets/vendor/js/helpers.js"></script>
    <script src="/crm-assets/vendor/js/template-customizer.js"></script>
    <script src="/crm-assets/js/config.js"></script>
  </head>

  <body>
    <div class="layout-wrapper layout-content-navbar">
      <div class="layout-container">
        {sidebar}

        <div class="layout-page">
          {navbar}

          <div class="content-wrapper">
            <div class="container-xxl flex-grow-1 container-p-y">
              <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-4">
                <div class="d-flex align-items-center gap-2">
                  <span class="text-body-secondary small">AdsterraFleet CMS</span>
                  <i class="icon-base ti tabler-chevron-right icon-14px text-body-secondary"></i>
                  <span class="fw-semibold" id="shellActiveBreadcrumb">Overview &amp; Live Ops</span>
                </div>
                <span class="badge bg-label-primary" id="shellActiveLayerBadge">Layer U1 + U2</span>
              </div>

              {overview}
              {phase4_view}
              {live_workflow_view}
              {autopublish_view}
              {monetization_view}
              {network_view}
              {growth_view}
              {staged}
              {profile_view}
              {settings_view}
            </div>

            <footer class="content-footer footer bg-footer-theme">
              <div class="container-xxl">
                <div class="footer-container d-flex align-items-center justify-content-between py-4 flex-md-row flex-column">
                  <div class="text-body">
                    AdsterraFleet Publisher Command Center &bull; Vuexy CRM Architecture (Component U1&ndash;U6 Live)
                  </div>
                  <div class="d-flex gap-3">
                    <a href="/classic" class="footer-link">Classic UI (/classic)</a>
                    <a href="/autopublish" class="footer-link">AutoPublish (/autopublish)</a>
                  </div>
                </div>
              </div>
            </footer>

            <div class="content-backdrop fade"></div>
          </div>
        </div>
      </div>

      <div class="layout-overlay layout-menu-toggle"></div>
      <div class="drag-target"></div>
    </div>

    <script src="/crm-assets/vendor/libs/jquery/jquery.js"></script>
    <script src="/crm-assets/vendor/libs/popper/popper.js"></script>
    <script src="/crm-assets/vendor/js/bootstrap.js"></script>
    <script src="/crm-assets/vendor/libs/node-waves/node-waves.js"></script>
    <script src="/crm-assets/vendor/libs/pickr/pickr.js"></script>
    <script src="/crm-assets/vendor/libs/perfect-scrollbar/perfect-scrollbar.js"></script>
    <script src="/crm-assets/vendor/libs/hammer/hammer.js"></script>
    <script src="/crm-assets/vendor/libs/notyf/notyf.js"></script>
    <script src="/crm-assets/vendor/libs/sweetalert2/sweetalert2.js"></script>
    <script src="/crm-assets/vendor/libs/apex-charts/apexcharts.js"></script>
    <script src="/crm-assets/vendor/js/menu.js"></script>
    <script src="/crm-assets/js/main.js"></script>
    <script src="/crm-assets/js/crm-shell.js"></script>
    <script src="/crm-assets/js/crm-overview.js"></script>
    <script src="/crm-assets/js/crm-phase4.js"></script>
    <script src="/crm-assets/js/crm-workflow.js"></script>
    <script src="/crm-assets/js/crm-autopublish.js"></script>
    <script src="/crm-assets/js/crm-monetization.js"></script>
    <script src="/crm-assets/js/crm-network-growth.js"></script>
    <script src="/crm-assets/js/crm-profile.js"></script>
  </body>
</html>
"""
