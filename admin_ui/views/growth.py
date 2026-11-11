"""Component U5 View Renderer — Growth, GSC SEO, Web Push & Telegram Alerts (#view-growth)."""

from __future__ import annotations


def _render_kpi_strip() -> str:
    """Render 4 Vuexy summary KPI cards for Layer 5 GSC, Search Traffic, Layer 6 Push & Layer 3 Telegram."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Layer 5 · Search Console</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-warning"><i class="icon-base ti tabler-brand-google icon-18px"></i></span>
            </span>
          </div>
          <h4 class="mb-1" id="u5KpiGscAuth">Checking...</h4>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiGscLive">0 / 10 Live Properties</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">7d Organic Performance</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-info"><i class="icon-base ti tabler-chart-line icon-18px"></i></span>
            </span>
          </div>
          <h3 class="mb-1 tabular-nums" id="u5KpiGscImps">0</h3>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiGscClicks">0 Clicks · Pos --</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Layer 6 · Push Vault</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-success"><i class="icon-base ti tabler-bell-ringing icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-baseline gap-2 mb-1">
            <h3 class="mb-0 tabular-nums" id="u5KpiPushSubs">0</h3>
            <span class="badge bg-label-success" id="u5KpiPushLockBadge">LOCK ON</span>
          </div>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiPushCoverage">0 / 10 Sites SW Ready</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Layer 3 · Telegram Bot</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-primary"><i class="icon-base ti tabler-brand-telegram icon-18px"></i></span>
            </span>
          </div>
          <h4 class="mb-1 u5-wrap-text" id="u5KpiTgBot">@Liveadsterabot</h4>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiTgAlerts">0 Alerts Today</small>
        </div>
      </div>
    </div>
  </div>
"""


def _render_gsc_panel() -> str:
    """Render Layer 5 Google Search Console OAuth2 & Weekly Indexing tab panel."""
    return """
      <div id="u5PanelGsc" class="u4-tab-panel" role="tabpanel" aria-labelledby="u5TabGscBtn">
        <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 mb-4">
          <div>
            <h6 class="mb-1" id="u5GscFormTitle">Google Search Console API v3/v1 &amp; Weekly Digest</h6>
            <small class="text-body-secondary">Live Search Analytics, Sitemaps &amp; URL Inspection; clearly tags fallback estimates as mock</small>
          </div>
          <div role="toolbar" aria-label="Google Search Console Actions" focusgroup="toolbar wrap" class="d-flex flex-wrap align-items-center gap-2">
            <button type="button" class="btn btn-sm btn-primary u4-tb-btn" id="u5BtnSyncGsc">
              <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Sync GSC (7d)
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary u4-tb-btn" id="u5BtnWeeklyGsc">
              <i class="icon-base ti tabler-report-analytics icon-16px me-1"></i>Weekly Report
            </button>
            <a href="/classic" class="btn btn-sm btn-label-secondary u4-tb-btn">
              <i class="icon-base ti tabler-external-link icon-16px me-1"></i>Classic
            </a>
          </div>
        </div>

        <details class="border rounded p-3 mb-4 bg-body-tertiary u5-acc-item" id="u5GscSetupDetails">
          <summary class="fw-semibold u5-acc-summary">
            <span>Connect Service Account / OAuth2 Credentials (Stored safely in gitignored <code>state/</code>)</span>
          </summary>
          <div class="u5-acc-body pt-3">
            <p class="small text-body-secondary mb-2">
              Service Identity: <strong id="u5GscClientEmail">Not Configured</strong> &middot;
              Auth Mode: <code id="u5GscAuthType">unconfigured</code>
            </p>
            <form id="u5GscCredForm" aria-labelledby="u5GscFormTitle" novalidate>
              <div class="u25-field mb-3">
                <label class="form-label" for="u5GscJson">Google Service Account / OAuth2 JSON (Write-only &mdash; never echoed back)</label>
                <textarea
                  id="u5GscJson"
                  name="credentials_json"
                  class="form-control font-monospace small"
                  rows="4"
                  required
                  minlength="20"
                  autocomplete="off"
                  autocorrect="off"
                  autocapitalize="none"
                  spellcheck="false"
                  aria-describedby="u5GscJsonErr"
                  placeholder='{"type": "service_account", "client_email": "...", "private_key": "..."}'></textarea>
                <div id="u5GscJsonErr" class="u25-error-msg">Paste a valid Service Account or OAuth2 JSON payload (minimum 20 characters).</div>
              </div>
              <div class="d-flex justify-content-end">
                <button type="submit" class="btn btn-sm btn-primary" id="u5BtnSaveGscCreds">
                  <i class="icon-base ti tabler-key icon-16px me-1"></i>Save GSC Credentials
                </button>
              </div>
            </form>
          </div>
        </details>

        <div tabindex="0" role="region" aria-labelledby="u5GscCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u5-gsc-table" id="u5GscTable">
            <caption id="u5GscCaption" class="visually-hidden">10-Domain Google Search Console performance and source status</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Source</th>
                <th scope="col">GSC Property</th>
                <th scope="col" class="text-end">7d Imps</th>
                <th scope="col" class="text-end">7d Clicks</th>
                <th scope="col" class="text-end">CTR</th>
                <th scope="col" class="text-end">Avg Pos</th>
                <th scope="col">Top Query</th>
              </tr>
            </thead>
            <tbody id="u5GscBody">
              <tr><td colspan="8" class="text-center text-body-secondary py-5">Loading Layer 5 Search Console metrics...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
"""


def _render_push_panel() -> str:
    """Render Layer 6 P-256 VAPID, OneSignal & Testing-Phase Delivery Lock tab panel."""
    return """
      <div id="u5PanelPush" class="u4-tab-panel" role="tabpanel" aria-labelledby="u5TabPushBtn" hidden="until-found">
        <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 mb-4">
          <div>
            <h6 class="mb-1" id="u5OsFormTitle">Web Push Foundation &middot; P-256 VAPID &amp; OneSignal Collect-Only</h6>
            <small class="text-body-secondary">Collects push subscribers while blocking campaign blasts; keeps Monetag <code>/sw.js</code> untouched</small>
          </div>
          <div role="toolbar" aria-label="Push Foundation Actions" focusgroup="toolbar wrap" class="d-flex flex-wrap align-items-center gap-2">
            <button type="button" class="btn btn-sm btn-outline-primary u4-tb-btn" id="u5BtnRotateVapid">
              <i class="icon-base ti tabler-key icon-16px me-1"></i>Rotate VAPID
            </button>
            <button type="button" class="btn btn-sm btn-primary u4-tb-btn" id="u5BtnInjectPush">
              <i class="icon-base ti tabler-code icon-16px me-1"></i>Sync Sites SW
            </button>
            <span role="separator" aria-orientation="vertical" class="u4-tb-sep d-none d-sm-inline-block"></span>
            <button type="button" class="btn btn-sm btn-outline-warning u4-tb-btn" id="u5BtnTestPushLock">
              <i class="icon-base ti tabler-shield-lock icon-16px me-1"></i>Verify Delivery Lock
            </button>
          </div>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-lg-6">
            <div class="border rounded p-3 h-100 d-flex flex-column justify-content-between gap-2">
              <div class="d-flex align-items-center justify-content-between gap-2">
                <label class="fw-semibold small mb-0" for="u5SwitchDeliveryLock">Testing-Phase Collect-Only Lock (<code>collect_only</code>)</label>
                <input
                  id="u5SwitchDeliveryLock"
                  type="checkbox"
                  switch
                  checked
                  disabled
                  aria-describedby="u5LockPolicyHelp"
                  class="u5-switch-control" />
              </div>
              <small id="u5LockPolicyHelp" class="text-body-secondary">
                Configured via <code>config.yaml</code> (<code>push_notifications.collect_only: true</code>) &mdash; prevents premature broadcasts during warmup.
              </small>
            </div>
          </div>

          <div class="col-lg-6">
            <div class="border rounded p-3 h-100">
              <div class="small text-body-secondary mb-1">Public ES256 / P-256 VAPID Key (Private key never exposed)</div>
              <div class="d-flex align-items-center justify-content-between gap-2">
                <code id="u5VapidPubCode" class="small u5-wrap-text">Loading VAPID public key...</code>
                <span class="u4-copy flex-shrink-0">
                  <button
                    type="button"
                    id="u5VapidCopyBtn"
                    class="btn btn-sm btn-icon btn-outline-secondary u4-copy-btn"
                    command="--copy"
                    commandfor="u5VapidPubCode"
                    aria-label="Copy public VAPID key">
                    <i class="icon-base ti tabler-copy icon-16px u4-icon-copy" aria-hidden="true"></i>
                    <i class="icon-base ti tabler-check icon-16px u4-icon-check" aria-hidden="true"></i>
                  </button>
                  <span class="u4-copy-tip" role="status" aria-live="polite" id="u5VapidCopyTip">Copied</span>
                </span>
              </div>
              <div class="small text-body-secondary mt-1">Fingerprint: <code id="u5VapidFp">--</code></div>
            </div>
          </div>
        </div>

        <details class="border rounded p-3 mb-4 bg-body-tertiary u5-acc-item" id="u5OsSetupDetails">
          <summary class="fw-semibold u5-acc-summary">
            <span>Optional OneSignal Web SDK v16 Configuration</span>
          </summary>
          <div class="u5-acc-body pt-3">
            <form id="u5OsForm" aria-labelledby="u5OsFormTitle" novalidate>
              <div class="row g-3 align-items-start">
                <div class="col-md-5 u25-field">
                  <label class="form-label" for="u5OsAppId">OneSignal App UUID <span aria-hidden="true">*</span></label>
                  <input
                    type="text"
                    id="u5OsAppId"
                    name="app_id"
                    class="form-control form-control-sm font-monospace"
                    required
                    pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                    autocomplete="off"
                    autocorrect="off"
                    autocapitalize="none"
                    spellcheck="false"
                    aria-describedby="u5OsAppIdErr"
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  <div id="u5OsAppIdErr" class="u25-error-msg">Enter a valid 36-character UUID OneSignal App ID.</div>
                </div>

                <div class="col-md-4 u25-field">
                  <label class="form-label" for="u5OsRestKey">REST API Key (Optional, write-only)</label>
                  <div class="input-group input-group-sm">
                    <input
                      type="password"
                      id="u5OsRestKey"
                      name="rest_api_key"
                      class="form-control font-monospace"
                      autocomplete="new-password"
                      aria-describedby="u5OsToggleWarn"
                      placeholder="Stored only in gitignored state/" />
                    <button
                      type="button"
                      id="u5BtnToggleOsKey"
                      class="btn btn-outline-secondary"
                      aria-pressed="false"
                      aria-label="Show OneSignal REST API Key">
                      <i class="icon-base ti tabler-eye icon-16px" aria-hidden="true"></i>
                    </button>
                  </div>
                  <span id="u5OsToggleWarn" class="visually-hidden">Toggling reveals your secret API key on screen.</span>
                </div>

                <div class="col-md-3 u25-field">
                  <label class="form-label" for="u5OsDomain">Scope Domain</label>
                  <input
                    type="text"
                    id="u5OsDomain"
                    name="domain"
                    class="form-control form-control-sm font-monospace"
                    autocorrect="off"
                    autocapitalize="none"
                    spellcheck="false"
                    placeholder="Blank = Global" />
                </div>
              </div>
              <div class="d-flex justify-content-end mt-3">
                <button type="submit" class="btn btn-sm btn-primary" id="u5BtnSaveOneSignal">
                  <i class="icon-base ti tabler-device-floppy icon-16px me-1"></i>Save OneSignal Config
                </button>
              </div>
            </form>
          </div>
        </details>

        <div tabindex="0" role="region" aria-labelledby="u5PushCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u5-push-table" id="u5PushTable">
            <caption id="u5PushCaption" class="visually-hidden">10-Domain Web Push collector and Service Worker audit</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Collector Script</th>
                <th scope="col"><code>/push-sw.js</code></th>
                <th scope="col"><code>OneSignalSW</code></th>
                <th scope="col">Monetag <code>/sw.js</code></th>
                <th scope="col" class="text-end">Subscribers</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody id="u5PushBody">
              <tr><td colspan="7" class="text-center text-body-secondary py-5">Loading Layer 6 Push foundation...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
"""


def _render_telegram_panel() -> str:
    """Render Layer 3 Telegram Bot, Daily Reports & Recent Alerts tab panel."""
    return """
      <div id="u5PanelTelegram" class="u4-tab-panel" role="tabpanel" aria-labelledby="u5TabTgBtn" hidden="until-found">
        <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 mb-4">
          <div>
            <h6 class="mb-1">Telegram Alert Bot &amp; Scheduled Fleet Reports</h6>
            <small class="text-body-secondary">Delivers 2-hour yield heartbeats, CTR warnings (&ge;4.4%), emergencies (&ge;5.0%), and 08:00 IST morning digests</small>
          </div>
          <div role="toolbar" aria-label="Telegram Dispatch Actions" focusgroup="toolbar wrap" class="d-flex flex-wrap align-items-center gap-2">
            <button type="button" class="btn btn-sm btn-outline-primary u4-tb-btn" id="u5BtnTgTest">
              <i class="icon-base ti tabler-send icon-16px me-1"></i>Send Test Ping
            </button>
            <button type="button" class="btn btn-sm btn-outline-info u4-tb-btn" id="u5BtnTgHeartbeat">
              <i class="icon-base ti tabler-heartbeat icon-16px me-1"></i>Push Heartbeat
            </button>
            <button type="button" class="btn btn-sm btn-primary u4-tb-btn" id="u5BtnTgDailyReport">
              <i class="icon-base ti tabler-news icon-16px me-1"></i>Send Daily Report
            </button>
          </div>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 h-100">
              <div class="small text-body-secondary">Alerts Today</div>
              <div class="h5 mb-0 mt-1 tabular-nums" id="u5TgTotal">0</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 h-100">
              <div class="small text-body-secondary">Heartbeats / Info</div>
              <div class="h5 mb-0 mt-1 text-success tabular-nums" id="u5TgInfo">0</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 h-100">
              <div class="small text-body-secondary">Warnings (&ge;4.4%)</div>
              <div class="h5 mb-0 mt-1 text-warning tabular-nums" id="u5TgWarn">0</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 h-100">
              <div class="small text-body-secondary">Emergencies (&ge;5.0%)</div>
              <div class="h5 mb-0 mt-1 text-danger tabular-nums" id="u5TgCrit">0</div>
            </div>
          </div>
        </div>

        <div tabindex="0" role="region" aria-labelledby="u5TgCaption" class="table-wrapper u3-table-region">
          <table class="table table-hover align-middle mb-0 u5-tg-table" id="u5TgTable">
            <caption id="u5TgCaption" class="visually-hidden">Recent Telegram alert dispatches</caption>
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Level</th>
                <th scope="col">Type</th>
                <th scope="col">Domain</th>
                <th scope="col">Notification Preview</th>
                <th scope="col">Delivered</th>
              </tr>
            </thead>
            <tbody id="u5TgBody">
              <tr><td colspan="6" class="text-center text-body-secondary py-5">Loading Telegram alert history...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
"""


def render_growth_view() -> str:
    """Render complete Component U5 Growth, GSC SEO, Push & Telegram workspace inside #view-growth."""
    return f"""
<section id="view-growth" class="crm-view">
  {_render_kpi_strip()}

  <div class="card">
    <div class="card-header pb-0">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-2 mb-3">
        <div>
          <h5 class="mb-0">Growth Engine &middot; Search Console, Web Push &amp; Telegram</h5>
          <small class="text-body-secondary">Switch modules with mouse or Left/Right arrow keys</small>
        </div>
        <button type="button" class="btn btn-sm btn-label-secondary" id="u5BtnRefreshGrowth">
          <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Refresh All
        </button>
      </div>

      <div id="u5GrowthStatusAlert" role="status" aria-live="polite" class="alert alert-secondary py-2 px-3 mb-3 small d-none"></div>

      <ul class="nav nav-tabs u25-profile-tabs" role="tablist" aria-label="Growth workspace modules" id="u5GrowthTabs">
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link active" id="u5TabGscBtn" role="tab" aria-selected="true" aria-controls="u5PanelGsc" data-u5-tab="gsc">
            <i class="icon-base ti tabler-brand-google icon-16px me-1"></i>Search Console (Layer 5)
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link" id="u5TabPushBtn" role="tab" aria-selected="false" aria-controls="u5PanelPush" data-u5-tab="push" tabindex="-1">
            <i class="icon-base ti tabler-bell-ringing icon-16px me-1"></i>Web Push &amp; VAPID (Layer 6)
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button type="button" class="nav-link" id="u5TabTgBtn" role="tab" aria-selected="false" aria-controls="u5PanelTelegram" data-u5-tab="telegram" tabindex="-1">
            <i class="icon-base ti tabler-brand-telegram icon-16px me-1"></i>Telegram Alerts (Layer 3)
          </button>
        </li>
      </ul>
    </div>

    <div class="card-body pt-4">
      {_render_gsc_panel()}
      {_render_push_panel()}
      {_render_telegram_panel()}
    </div>
  </div>
</section>
"""
