"""Component U5 View Renderer — Fleet, Proxies, Mobile USB ADB & Runner Config (#view-network)."""

from __future__ import annotations


def _render_kpi_strip() -> str:
    """Render 4 Vuexy summary KPI cards for IP Carrier, Proxy Pool, Mobile ADB & Breakers."""
    return """
  <div class="row g-6 mb-6">
    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Active IP Carrier</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-success"><i class="icon-base ti tabler-arrows-shuffle icon-18px"></i></span>
            </span>
          </div>
          <h4 class="mb-1" id="u5KpiTransport">PRIMARY MOBILE</h4>
          <small class="text-body-secondary d-block" id="u5KpiNetworkMode">Mode: mobile_tether</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Proxy &amp; UA Fleet</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-info"><i class="icon-base ti tabler-world-www icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-baseline gap-2 mb-1">
            <h3 class="mb-0 tabular-nums" id="u5KpiProxyCount">0</h3>
            <span class="badge bg-label-info">proxies</span>
          </div>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiUaPool">Loading UA database...</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Mobile USB ADB</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-primary"><i class="icon-base ti tabler-device-mobile icon-18px"></i></span>
            </span>
          </div>
          <h4 class="mb-1" id="u5KpiAdbStatus">Checking...</h4>
          <small class="text-body-secondary d-block u5-wrap-text" id="u5KpiAdbIp">Public IP: --</small>
        </div>
      </div>
    </div>

    <div class="col-sm-6 col-xxl-3">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="text-body-secondary small fw-medium">Failover &amp; Breakers</span>
            <span class="avatar avatar-sm rounded">
              <span class="avatar-initial rounded bg-label-warning"><i class="icon-base ti tabler-shield-bolt icon-18px"></i></span>
            </span>
          </div>
          <div class="d-flex align-items-baseline gap-2 mb-1">
            <h3 class="mb-0 tabular-nums" id="u5KpiLatency">-- ms</h3>
            <span class="badge bg-label-success" id="u5KpiBreakerBadge">0 Tripped</span>
          </div>
          <small class="text-body-secondary d-block tabular-nums" id="u5KpiTripsRecoveries">0 Trips / 0 Recoveries</small>
        </div>
      </div>
    </div>
  </div>
"""


def _render_failover_header_card() -> str:
    """Render Pillar 5 Dual-ISP Carrier Hot-Failover control toolbar and telemetry strip."""
    return """
  <div class="card mb-6">
    <div class="card-header d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-3 pb-3">
      <div>
        <h5 class="mb-1">Dual-ISP Carrier Hot-Failover &amp; Fleet Operations</h5>
        <p class="card-subtitle text-body-secondary mb-0">
          Zero-drop failover switching between USB Mobile 4G/5G ADB and Residential Proxies above latency threshold
        </p>
      </div>

      <div role="toolbar" aria-label="Carrier Failover and Fleet Actions" focusgroup="toolbar wrap" class="d-flex flex-wrap align-items-center gap-2 u5-toolbar">
        <div role="group" aria-label="Failover Controls" class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-sm btn-outline-primary u4-tb-btn" id="u5BtnProbeFailover">
            <i class="icon-base ti tabler-activity-heartbeat icon-16px me-1"></i>Probe Health
          </button>
          <button type="button" class="btn btn-sm btn-warning u4-tb-btn" id="u5BtnSwapFailover">
            <i class="icon-base ti tabler-arrows-exchange icon-16px me-1"></i>Force Hot-Swap
          </button>
        </div>

        <span role="separator" aria-orientation="vertical" class="u4-tb-sep d-none d-sm-inline-block"></span>

        <div role="group" aria-label="Maintenance Controls" class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-sm btn-outline-danger u4-tb-btn" id="u5BtnResetBreakers">
            <i class="icon-base ti tabler-shield-off icon-16px me-1"></i>Reset Breakers
          </button>
          <button type="button" class="btn btn-sm btn-outline-info u4-tb-btn" id="u5BtnSyncUa">
            <i class="icon-base ti tabler-users icon-16px me-1"></i>Sync UserAgents
          </button>
          <a href="/api/stats/csv" class="btn btn-sm btn-label-secondary u4-tb-btn">
            <i class="icon-base ti tabler-download icon-16px me-1"></i>Export CSV
          </a>
          <a href="/classic" class="btn btn-sm btn-label-secondary u4-tb-btn">
            <i class="icon-base ti tabler-external-link icon-16px me-1"></i>Classic
          </a>
        </div>
      </div>
    </div>

    <div class="card-body pt-3">
      <div class="row g-3 mb-3">
        <div class="col-6 col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="small text-body-secondary">Failover Engine</div>
            <div class="fw-semibold mt-1" id="u5FoEnabled">--</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="small text-body-secondary">Primary Health</div>
            <div class="fw-semibold mt-1" id="u5FoPrimaryHealth">--</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="small text-body-secondary">Latency Threshold</div>
            <div class="fw-semibold mt-1 tabular-nums" id="u5FoThreshold">1500 ms</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="small text-body-secondary">Consecutive Failures</div>
            <div class="fw-semibold mt-1 tabular-nums" id="u5FoFailures">0 Primary / 0 Fallback</div>
          </div>
        </div>
      </div>

      <div id="u5NetworkStatusAlert" role="status" aria-live="polite" class="alert alert-secondary py-2 px-3 mb-0 small d-none"></div>
    </div>
  </div>
"""


def _render_config_editor_card() -> str:
    """Render Runner & Target URL Pool configuration editor card."""
    return """
  <div class="col-xl-7">
    <div class="card h-100">
      <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div>
          <h5 class="card-title mb-0" id="u5ConfigHeading">Target Pool &amp; Runner Configuration</h5>
          <small class="text-body-secondary">Updates live <code>config.yaml</code> target rotation, dwell curve, and pacing caps</small>
        </div>
        <span class="badge bg-label-success tabular-nums" id="u5TargetUrlsCount">0 URLs Active</span>
      </div>

      <div class="card-body">
        <form id="u5ConfigForm" aria-labelledby="u5ConfigHeading" novalidate>
          <div class="u25-field mb-4">
            <label class="form-label fw-medium" for="u5TargetUrls">Target URLs Pool (One URL per line for random distribution) <span aria-hidden="true">*</span></label>
            <textarea
              id="u5TargetUrls"
              name="target_urls"
              class="form-control font-monospace small"
              rows="4"
              required
              autocorrect="off"
              autocapitalize="none"
              spellcheck="false"
              aria-describedby="u5TargetUrlsErr"
              placeholder="https://loanraaj.com&#10;https://tazaloan.com"></textarea>
            <div id="u5TargetUrlsErr" class="u25-error-msg">Enter at least one valid https:// or http:// target URL.</div>
          </div>

          <div class="d-flex flex-column flex-sm-row gap-2 mb-3">
            <div class="flex-grow-1">
              <label class="visually-hidden" for="u5NewUrlInput">Add single target URL</label>
              <input
                type="url"
                id="u5NewUrlInput"
                class="form-control form-control-sm"
                autocorrect="off"
                autocapitalize="none"
                spellcheck="false"
                placeholder="https://loanraaj.com/custom-article" />
            </div>
            <button type="button" class="btn btn-sm btn-outline-primary" id="u5BtnAddUrl">
              <i class="icon-base ti tabler-plus icon-16px me-1"></i>Add URL
            </button>
          </div>

          <div id="u5UrlPills" class="d-flex flex-wrap gap-1 mb-4" aria-label="Active URLs in pool"></div>

          <fieldset class="border rounded p-3 mb-4">
            <legend class="float-none w-auto px-2 fs-6 fw-semibold mb-2">Dwell, Pacing &amp; Carrier Guardrails</legend>
            <div class="row g-3">
              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5NetworkMode">Primary Network Source</label>
                <select id="u5NetworkMode" name="network_mode" class="form-select">
                  <option value="mobile_tether">Mobile USB ADB Tether (Cellular IP)</option>
                  <option value="proxy">Residential / 4G Proxy Pool</option>
                </select>
              </div>
              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5AirplaneWait">Airplane Rotate Wait (sec)</label>
                <input type="number" id="u5AirplaneWait" name="airplane_mode_wait" class="form-control tabular-nums" min="2" max="20" step="1" required />
                <div class="u25-error-msg">Wait time must be between 2 and 20 seconds.</div>
              </div>

              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5MinDwell">Min Dwell (sec, &ge; 20)</label>
                <input type="number" id="u5MinDwell" name="min_dwell" class="form-control tabular-nums" min="20" max="300" step="1" required />
                <div class="u25-error-msg">Minimum anti-detect dwell must be at least 20 seconds.</div>
              </div>
              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5MaxDwell">Max Dwell (sec)</label>
                <input type="number" id="u5MaxDwell" name="max_dwell" class="form-control tabular-nums" min="25" max="600" step="1" required />
                <div class="u25-error-msg">Max dwell must be between 25 and 600 seconds.</div>
              </div>

              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5ClickProb">Click Probability (0.01 &ndash; 0.15)</label>
                <input type="number" id="u5ClickProb" name="click_prob" class="form-control tabular-nums" min="0.01" max="0.15" step="0.01" required />
                <div class="u25-error-msg">Keep click probability within 0.01 to 0.15 for IVT safety.</div>
              </div>
              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5AdClicksMax">Max Ad Clicks / Session</label>
                <input type="number" id="u5AdClicksMax" name="ad_clicks_max" class="form-control tabular-nums" min="0" max="5" step="1" required />
                <div class="u25-error-msg">Enter a value between 0 and 5.</div>
              </div>

              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5DailyCap">Daily Session Cap</label>
                <input type="number" id="u5DailyCap" name="daily_cap" class="form-control tabular-nums" min="1" max="50000" step="1" required />
                <div class="u25-error-msg">Daily cap must be at least 1.</div>
              </div>
              <div class="col-sm-6 u25-field">
                <label class="form-label" for="u5Concurrency">Browser Concurrency (1 &ndash; 20)</label>
                <input type="number" id="u5Concurrency" name="concurrency" class="form-control tabular-nums" min="1" max="20" step="1" required />
                <div class="u25-error-msg">Concurrency must be between 1 and 20 browsers.</div>
              </div>
            </div>
          </fieldset>

          <div class="d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-3 border rounded p-3 bg-body-tertiary">
            <div class="small text-body-secondary">
              <strong>Browser Mode:</strong> <span id="u5HeadlessBadge" class="badge bg-label-info ms-1">HEAD-ON SAFE</span>
              <span class="d-block mt-1">Anti-detect stealth enforces visible Chromium (<code>headless: false</code>).</span>
            </div>
            <button type="submit" class="btn btn-primary" id="u5BtnSaveConfig">
              <i class="icon-base ti tabler-device-floppy icon-16px me-1"></i>Save Runner Config
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
"""


def _render_carrier_accordion_column() -> str:
    """Render non-exclusive accessible <details> accordions for Proxy Pool and Mobile ADB."""
    return """
  <div class="col-xl-5">
    <section class="u5-accordion d-flex flex-column gap-4" aria-labelledby="u5CarrierAccordionHeading">
      <h6 id="u5CarrierAccordionHeading" class="visually-hidden">Proxy Pool and Mobile ADB Controls</h6>

      <details class="card u5-acc-item" open id="u5AccProxy">
        <summary class="card-header fw-semibold u5-acc-summary">
          <span>Residential &amp; 4G Proxy Pool (<code>proxies.txt</code>)</span>
        </summary>
        <div class="u5-acc-body card-body pt-3">
          <form id="u5ProxyFetchForm" class="mb-4" novalidate>
            <div class="u25-field">
              <label class="form-label" for="u5ProxyApiUrl">Auto-Fetch Proxy Provider API URL</label>
              <div class="input-group">
                <input
                  type="url"
                  id="u5ProxyApiUrl"
                  name="api_url"
                  class="form-control form-control-sm font-monospace"
                  required
                  autocorrect="off"
                  autocapitalize="none"
                  spellcheck="false"
                  aria-describedby="u5ProxyApiErr"
                  placeholder="https://api.provider.com/getproxies" />
                <button type="submit" class="btn btn-sm btn-outline-primary" id="u5BtnFetchProxies">
                  Fetch Live
                </button>
              </div>
              <div id="u5ProxyApiErr" class="u25-error-msg">Enter a valid http:// or https:// provider endpoint before fetching.</div>
            </div>
          </form>

          <form id="u5ProxySaveForm" novalidate>
            <div class="u25-field mb-3">
              <label class="form-label d-flex flex-wrap justify-content-between align-items-center gap-2" for="u5ProxiesText">
                <span>Proxy Lines (<code>user:pass@host:port</code> or <code>host:port</code>)</span>
                <span class="d-inline-flex align-items-center gap-2">
                  <button
                    type="button"
                    id="u5BtnToggleProxyMask"
                    class="btn btn-xs btn-outline-secondary"
                    aria-pressed="true"
                    aria-controls="u5ProxiesText">
                    <i class="icon-base ti tabler-eye-off icon-14px me-1"></i><span>Mask Proxies</span>
                  </button>
                  <span class="badge bg-label-secondary tabular-nums" id="u5ProxyPoolBadge">0 Valid</span>
                </span>
              </label>
              <textarea
                id="u5ProxiesText"
                name="proxies"
                class="form-control font-monospace small"
                rows="5"
                data-masked="true"
                autocomplete="off"
                autocorrect="off"
                autocapitalize="none"
                spellcheck="false"
                placeholder="user:pass@gw.provider.com:8000&#10;1.2.3.4:8080"></textarea>
              <div class="form-text">Datacenter ASNs (AWS, DigitalOcean, OVH, Hetzner, Linode) are blocked automatically by <code>pool.py</code>.</div>
            </div>
            <div class="d-flex justify-content-end">
              <button type="submit" class="btn btn-sm btn-primary" id="u5BtnSaveProxies">
                <i class="icon-base ti tabler-device-floppy icon-16px me-1"></i>Save Proxies
              </button>
            </div>
          </form>
        </div>
      </details>

      <details class="card u5-acc-item" open id="u5AccAdb">
        <summary class="card-header fw-semibold u5-acc-summary">
          <span>Mobile USB ADB &amp; Flight-Mode IP Rotation</span>
        </summary>
        <div class="u5-acc-body card-body pt-3">
          <div class="border rounded p-3 mb-3 bg-body-tertiary">
            <div class="small text-body-secondary mb-1">Current Public IP &amp; Cellular Carrier</div>
            <div class="font-monospace small fw-semibold u5-wrap-text" id="u5AdbIpBox">Checking public IP...</div>
          </div>

          <div class="border rounded p-3 mb-3 bg-body-tertiary">
            <div class="small text-body-secondary mb-1">Attached USB Debugging Devices</div>
            <div class="font-monospace small u5-wrap-text" id="u5AdbDevicesBox">Checking ADB devices...</div>
            <div class="small text-body-secondary mt-2 u5-wrap-text">ADB Binary: <code id="u5AdbPath">--</code></div>
          </div>

          <div class="d-flex flex-wrap gap-2">
            <button type="button" class="btn btn-sm btn-label-secondary flex-grow-1" id="u5BtnRefreshAdb">
              <i class="icon-base ti tabler-refresh icon-16px me-1"></i>Refresh ADB &amp; IP
            </button>
            <button type="button" class="btn btn-sm btn-success flex-grow-1" id="u5BtnRotateAdb">
              <i class="icon-base ti tabler-plane icon-16px me-1"></i>Rotate Flight Mode IP
            </button>
          </div>
        </div>
      </details>
    </section>
  </div>
"""


def render_network_view() -> str:
    """Render complete Component U5 Fleet, Proxies, ADB & Config view inside #view-network."""
    return f"""
<section id="view-network" class="crm-view">
  {_render_kpi_strip()}
  {_render_failover_header_card()}
  <div class="row g-6 align-items-start">
    {_render_config_editor_card()}
    {_render_carrier_accordion_column()}
  </div>
</section>
"""
