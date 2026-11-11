"""Component U2.5 — Operator Profile, Security & Sign-In Gate, API Connections & Alerts View."""

from __future__ import annotations

from admin_ui.profile_auth import ALLOWED_AVATARS


def render_profile_view() -> str:
    """Return the Vuexy User Profile, Security, Connections & Alerts workspace."""
    avatar_buttons = "\n".join(
        f'''<button type="button" class="btn p-1 border rounded u25-avatar-choice" data-avatar="{url}" aria-label="Select avatar {idx + 1}" aria-pressed="{"true" if idx == 0 else "false"}">
              <img src="{url}" alt="Operator avatar option {idx + 1}" width="44" height="44" class="rounded" />
            </button>'''
        for idx, url in enumerate(ALLOWED_AVATARS)
    )

    return f"""
<section id="view-profile" class="crm-view">
  <!-- Vuexy Profile Banner Header -->
  <div class="row mb-5">
    <div class="col-12">
      <div class="card">
        <div class="user-profile-header-banner">
          <img src="/crm-assets/img/pages/profile-banner.png" alt="Operator banner" class="rounded-top w-100" />
        </div>
        <div class="user-profile-header d-flex flex-column flex-lg-row text-sm-start text-center mb-4">
          <div class="flex-shrink-0 mt-n2 mx-sm-0 mx-auto">
            <img
              src="/crm-assets/img/avatars/1.png"
              alt="Operator avatar"
              id="u25ProfileBannerAvatar"
              width="120"
              height="120"
              class="d-block ms-0 ms-sm-6 rounded user-profile-img"
            />
          </div>
          <div class="flex-grow-1 mt-3 mt-lg-5">
            <div class="d-flex align-items-md-end align-items-sm-start align-items-center justify-content-md-between justify-content-start mx-5 flex-md-row flex-column gap-4">
              <div class="user-profile-info">
                <div class="d-flex flex-wrap align-items-center justify-content-sm-start justify-content-center gap-2 mt-lg-4 mb-2">
                  <h4 class="mb-0" id="u25ProfileBannerName">Master Operator</h4>
                  <span class="badge bg-label-success" id="u25LockStateBadge">Unlocked · Localhost Open</span>
                </div>
                <ul class="list-inline mb-0 d-flex align-items-center flex-wrap justify-content-sm-start justify-content-center gap-4 my-2">
                  <li class="list-inline-item d-flex gap-2 align-items-center">
                    <i class="icon-base ti tabler-crown icon-lg text-primary"></i>
                    <span class="fw-medium" id="u25ProfileBannerRole">Lead Publisher Admin</span>
                  </li>
                  <li class="list-inline-item d-flex gap-2 align-items-center">
                    <i class="icon-base ti tabler-building icon-lg text-info"></i>
                    <span class="fw-medium" id="u25ProfileBannerOrg">10-Domain Publisher Hub</span>
                  </li>
                  <li class="list-inline-item d-flex gap-2 align-items-center">
                    <i class="icon-base ti tabler-map-pin icon-lg text-success"></i>
                    <span class="fw-medium" id="u25ProfileBannerLocation">India (IST / UTC+5:30)</span>
                  </li>
                </ul>
              </div>
              <button type="button" class="btn btn-outline-danger mb-1" id="u25LockNowBtn">
                <i class="icon-base ti tabler-logout icon-sm me-1"></i> Sign Out &amp; Lock CRM
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Single-Row Profile Tabs -->
  <ul class="nav nav-pills flex-nowrap overflow-x-auto gap-2 mb-5 u25-profile-tabs" id="u25ProfileTabs" role="tablist" aria-label="Profile and security sections">
    <li class="nav-item" role="presentation">
      <button type="button" class="nav-link active" id="u25-tab-account-btn" role="tab" aria-selected="true" aria-controls="u25TabAccount" data-u25-tab="account">
        <i class="icon-base ti tabler-user-check icon-sm me-1"></i> Account Profile
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button type="button" class="nav-link" id="u25-tab-security-btn" role="tab" aria-selected="false" aria-controls="u25TabSecurity" data-u25-tab="security" tabindex="-1">
        <i class="icon-base ti tabler-shield-lock icon-sm me-1"></i> Security &amp; Sign-In
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button type="button" class="nav-link" id="u25-tab-connections-btn" role="tab" aria-selected="false" aria-controls="u25TabConnections" data-u25-tab="connections" tabindex="-1">
        <i class="icon-base ti tabler-plug-connected icon-sm me-1"></i> Connected APIs
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button type="button" class="nav-link" id="u25-tab-alerts-btn" role="tab" aria-selected="false" aria-controls="u25TabAlerts" data-u25-tab="alerts" tabindex="-1">
        <i class="icon-base ti tabler-bell icon-sm me-1"></i> Alerts &amp; Notifications
        <span class="badge text-bg-danger rounded-pill ms-1 d-none" id="u25TabAlertCount">0</span>
      </button>
    </li>
  </ul>

  <!-- Tab 1: Account Profile -->
  <div id="u25TabAccount" role="tabpanel" aria-labelledby="u25-tab-account-btn">
    <div class="row g-5">
      <div class="col-12 col-lg-8">
        <div class="card">
          <div class="card-header">
            <h5 class="mb-0" id="u25ProfileFormTitle">Operator Identity Details</h5>
            <p class="card-subtitle mb-0">Synced across the CRM Navbar, Audit Profile &amp; Active Sessions.</p>
          </div>
          <div class="card-body">
            <div class="mb-5">
              <span class="form-label d-block mb-2">Choose Operator Avatar</span>
              <div class="d-flex flex-wrap gap-2" id="u25AvatarPicker" role="group" aria-label="Choose avatar">
                {avatar_buttons}
              </div>
            </div>

            <form id="u25ProfileForm" aria-labelledby="u25ProfileFormTitle" novalidate>
              <input type="hidden" id="u25AvatarInput" name="avatar" value="/crm-assets/img/avatars/1.png" />
              <div class="row g-4">
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25DisplayName">Display Name <span aria-hidden="true">*</span></label>
                  <input type="text" class="form-control" id="u25DisplayName" name="display_name" autocomplete="name" required minlength="2" maxlength="60" data-error="u25DisplayNameErr" />
                  <div id="u25DisplayNameErr" class="u25-error-msg">Enter a display name between 2 and 60 characters.</div>
                </div>
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25Email">Operator Email <span aria-hidden="true">*</span></label>
                  <input type="email" class="form-control" id="u25Email" name="email" autocomplete="email" spellcheck="false" required maxlength="120" data-error="u25EmailErr" />
                  <div id="u25EmailErr" class="u25-error-msg">Enter a valid email address (for example operator@domain.com).</div>
                </div>
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25Role">Role Title</label>
                  <input type="text" class="form-control" id="u25Role" name="role" autocomplete="organization-title" maxlength="60" />
                </div>
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25Organization">Workspace / Hub</label>
                  <input type="text" class="form-control" id="u25Organization" name="organization" autocomplete="organization" maxlength="80" />
                </div>
                <div class="col-12 u25-field">
                  <label class="form-label" for="u25Location">Timezone &amp; Location</label>
                  <input type="text" class="form-control" id="u25Location" name="location" maxlength="80" />
                </div>
                <div class="col-12 u25-field">
                  <label class="form-label" for="u25Bio">Operator Notes / Bio</label>
                  <textarea class="form-control" id="u25Bio" name="bio" rows="3" maxlength="280"></textarea>
                </div>
                <div class="col-12 d-flex flex-wrap gap-2 pt-2">
                  <button type="submit" class="btn btn-primary" id="u25SaveProfileBtn">
                    <i class="icon-base ti tabler-device-floppy icon-sm me-1"></i> Save Profile Changes
                  </button>
                  <button type="button" class="btn btn-label-secondary" id="u25ReloadProfileBtn">Reset Changes</button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>

      <div class="col-12 col-lg-4">
        <div class="card h-100">
          <div class="card-header">
            <h5 class="mb-0">Operator Summary</h5>
          </div>
          <div class="card-body">
            <ul class="list-unstyled mb-5">
              <li class="d-flex justify-content-between py-2 border-bottom">
                <span class="text-body-secondary">Auth Mode</span>
                <span class="fw-semibold" id="u25SummaryAuthMode">Open Localhost</span>
              </li>
              <li class="d-flex justify-content-between py-2 border-bottom">
                <span class="text-body-secondary">Password Hash</span>
                <span class="fw-semibold" id="u25SummaryPasswordStatus">Not Set</span>
              </li>
              <li class="d-flex justify-content-between py-2 border-bottom">
                <span class="text-body-secondary">Active Web Sessions</span>
                <span class="fw-semibold tabular-nums" id="u25SummarySessionsCount">0</span>
              </li>
              <li class="d-flex justify-content-between py-2">
                <span class="text-body-secondary">Last Profile Save</span>
                <span class="fw-semibold tabular-nums" id="u25SummaryUpdatedAt">--</span>
              </li>
            </ul>
            <div class="alert alert-info mb-0 small" role="note">
              <i class="icon-base ti tabler-info-circle me-1"></i>
              Stored safely inside gitignored <code>state/admin_profile.json</code>. Zero secrets are ever checked into Git.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Tab 2: Security & Authentication -->
  <div id="u25TabSecurity" role="tabpanel" aria-labelledby="u25-tab-security-btn" hidden>
    <div class="row g-5">
      <div class="col-12 col-lg-7">
        <div class="card">
          <div class="card-header">
            <h5 class="mb-0" id="u25PasswordFormTitle">Operator Password &amp; Lock Credentials</h5>
            <p class="card-subtitle mb-0">Salted PBKDF2-HMAC-SHA256 (200,000 iterations) with HttpOnly session cookies.</p>
          </div>
          <div class="card-body">
            <form id="u25PasswordForm" aria-labelledby="u25PasswordFormTitle" novalidate>
              <div class="mb-4 p-3 rounded border bg-body-tertiary">
                <div class="fw-semibold small mb-1">Password Requirements:</div>
                <ul class="small text-body-secondary ps-4 mb-0">
                  <li>Minimum 8 characters long</li>
                  <li>At least one lowercase letter (a-z)</li>
                  <li>At least one number or symbol</li>
                </ul>
              </div>

              <div class="mb-4 d-none u25-field" id="u25CurrentPwWrap">
                <label class="form-label" for="u25CurrentPassword">Current Password <span aria-hidden="true">*</span></label>
                <div class="input-group input-group-merge">
                  <input type="password" class="form-control" id="u25CurrentPassword" name="current_password" autocomplete="current-password" />
                  <button type="button" class="input-group-text cursor-pointer u25-pw-toggle" data-target="u25CurrentPassword" aria-pressed="false" aria-label="Show current password">
                    <i class="icon-base ti tabler-eye-off icon-18px"></i>
                  </button>
                </div>
              </div>

              <div class="row g-4 mb-4">
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25NewPassword">New Password <span aria-hidden="true">*</span></label>
                  <div class="input-group input-group-merge">
                    <input type="password" class="form-control" id="u25NewPassword" name="new_password" autocomplete="new-password" required minlength="8" pattern="(?=.*[a-z])(?=.*[\\d\\W_]).{{8,}}" data-error="u25NewPasswordErr" />
                    <button type="button" class="input-group-text cursor-pointer u25-pw-toggle" data-target="u25NewPassword" aria-pressed="false" aria-label="Show new password">
                      <i class="icon-base ti tabler-eye-off icon-18px"></i>
                    </button>
                  </div>
                  <div id="u25NewPasswordErr" class="u25-error-msg">Use 8+ chars with at least 1 lowercase letter and 1 number/symbol.</div>
                </div>
                <div class="col-12 col-md-6 u25-field">
                  <label class="form-label" for="u25ConfirmPassword">Confirm New Password <span aria-hidden="true">*</span></label>
                  <div class="input-group input-group-merge">
                    <input type="password" class="form-control" id="u25ConfirmPassword" name="confirm_password" autocomplete="new-password" required minlength="8" data-error="u25ConfirmPasswordErr" />
                    <button type="button" class="input-group-text cursor-pointer u25-pw-toggle" data-target="u25ConfirmPassword" aria-pressed="false" aria-label="Show confirm password">
                      <i class="icon-base ti tabler-eye-off icon-18px"></i>
                    </button>
                  </div>
                  <div id="u25ConfirmPasswordErr" class="u25-error-msg">Both password fields must match.</div>
                </div>
              </div>

              <div class="d-flex flex-wrap gap-2">
                <button type="submit" class="btn btn-primary" id="u25SavePasswordBtn">
                  <i class="icon-base ti tabler-key icon-sm me-1"></i> Save Operator Password
                </button>
                <button type="button" class="btn btn-label-danger d-none" id="u25ClearPasswordBtn">
                  <i class="icon-base ti tabler-lock-open icon-sm me-1"></i> Remove Password Lock
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <div class="col-12 col-lg-5 d-flex flex-column gap-5">
        <div class="card">
          <div class="card-header">
            <h5 class="mb-0">Dashboard Access Gate</h5>
            <p class="card-subtitle mb-0">Choose whether CRM sign-in is required on every browser session.</p>
          </div>
          <div class="card-body">
            <div class="form-check form-switch mb-4">
              <input class="form-check-input" type="checkbox" id="u25RequireLoginSwitch" />
              <label class="form-check-label fw-medium" for="u25RequireLoginSwitch">
                Require Password Sign-In on every CRM visit
              </label>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button type="button" class="btn btn-primary" id="u25ApplyGateBtn">Apply Access Policy</button>
              <button type="button" class="btn btn-outline-danger" id="u25LockSessionBtn2">
                <i class="icon-base ti tabler-logout icon-sm me-1"></i> Sign Out / Lock Now
              </button>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h5 class="mb-0">Active CRM Sessions</h5>
          </div>
          <div class="card-body" id="u25ActiveSessionsList">
            <div class="text-body-secondary small">No cookie sessions created yet (open localhost mode).</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Tab 3: Connected Integrations -->
  <div id="u25TabConnections" role="tabpanel" aria-labelledby="u25-tab-connections-btn" hidden>
    <div class="card">
      <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
        <div>
          <h5 class="mb-0">Connected Services &amp; API Key Vault Status</h5>
          <p class="card-subtitle mb-0">Live configuration audit from <code>.env</code> and <code>config.yaml</code> (secret values remain hidden).</p>
        </div>
        <button type="button" class="btn btn-sm btn-label-primary" id="u25RefreshConnectionsBtn">
          <i class="icon-base ti tabler-refresh icon-16px me-1"></i> Re-check Status
        </button>
      </div>
      <div class="card-body">
        <div class="row g-4" id="u25ConnectionsGrid">
          <div class="col-12 text-body-secondary small">Checking connected APIs...</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Tab 4: Alerts & Notifications History -->
  <div id="u25TabAlerts" role="tabpanel" aria-labelledby="u25-tab-alerts-btn" hidden>
    <div class="card">
      <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-3">
        <div>
          <h5 class="mb-0">Notification &amp; Alert History</h5>
          <p class="card-subtitle mb-0">Unified stream from <code>alert_logs</code>, CTR Circuit Breakers &amp; Adsterra API syncs.</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-sm btn-label-secondary" id="u25TestAlertBtn">
            <i class="icon-base ti tabler-bell-plus icon-16px me-1"></i> Trigger Test Alert
          </button>
          <button type="button" class="btn btn-sm btn-primary" id="u25MarkAllReadBtn2">
            <i class="icon-base ti tabler-mail-opened icon-16px me-1"></i> Mark All Read
          </button>
        </div>
      </div>
      <div class="card-body p-0">
        <ul class="list-group list-group-flush" id="u25FullAlertsList">
          <li class="list-group-item py-4 text-body-secondary small">Loading alerts...</li>
        </ul>
      </div>
    </div>
  </div>
</section>
"""
