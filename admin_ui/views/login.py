"""Component U2.5 — Vuexy Sign-In & CRM Lock Screen Renderer (/crm/login)."""

from __future__ import annotations

import html
from typing import Any


def render_login_view(profile: dict[str, Any], error_msg: str = "") -> str:
    """Render standalone Vuexy auth-login-basic sign-in / lock screen."""
    has_pw = bool(profile.get("has_password"))
    prefill_email = html.escape(str(profile.get("email") or "operator@adsterrafleet.local"))
    operator_name = html.escape(str(profile.get("display_name") or "Master Operator"))
    avatar = html.escape(str(profile.get("avatar") or "/crm-assets/img/avatars/1.png"))
    safe_err = html.escape(error_msg or "")

    mode_value = "login" if has_pw else "setup"
    heading = "CRM Session Locked" if has_pw else "First-Time Operator Lock"
    subtext = (
        f"Signed out as {operator_name}. Enter your password to unlock the command center."
        if has_pw
        else "No password is configured yet. Create an operator password to lock & protect the CRM, or unlock open localhost mode."
    )
    pw_label = "Password" if has_pw else "Create Operator Password (8+ chars)"
    pw_autocomplete = "current-password" if has_pw else "new-password"
    submit_label = "Sign In & Unlock CRM" if has_pw else "Set Password & Unlock CRM"

    dev_unlock_html = "" if has_pw else """
        <button type="button" class="btn btn-label-secondary w-100 mt-3" id="u25DevUnlockBtn">
          <i class="icon-base ti tabler-lock-open me-1"></i> Unlock Open Localhost Mode (No Password Yet)
        </button>"""

    return f"""<!doctype html>
<html
  lang="en"
  class="layout-wide customizer-hide"
  dir="ltr"
  data-skin="default"
  data-bs-theme="system"
  data-assets-path="/crm-assets/"
  data-template="adstera-crm">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="color-scheme" content="light dark" />
    <script>
      (function () {{
        try {{
          var tName = document.documentElement.getAttribute("data-template") || "adstera-crm";
          var stored = localStorage.getItem("templateCustomizer-" + tName + "--Theme") || "system";
          var resolved = stored === "system"
            ? (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
            : stored;
          document.documentElement.setAttribute("data-bs-theme", resolved);
        }} catch (_) {{}}
      }})();
    </script>
    <title>Sign In | AdsterraFleet CRM</title>
    <link rel="icon" type="image/x-icon" href="/crm-assets/img/favicon/favicon.ico" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/crm-assets/vendor/fonts/iconify-icons.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/core.css" />
    <link rel="stylesheet" href="/crm-assets/vendor/css/pages/page-auth.css" />
    <link rel="stylesheet" href="/crm-assets/css/cms-shell.css" />
  </head>
  <body>
    <div class="container-xxl">
      <div class="authentication-wrapper authentication-basic container-p-y">
        <div class="authentication-inner py-6">
          <div class="card">
            <div class="card-body">
              <div class="app-brand justify-content-center mb-5">
                <a href="/crm/login" class="app-brand-link">
                  <span class="app-brand-logo demo text-primary">
                    <svg width="32" height="22" viewBox="0 0 32 22" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" clip-rule="evenodd" d="M0.00172773 0V6.85398C0.00172773 6.85398 -0.133178 9.01207 1.98092 10.8388L13.6912 21.9964L19.7809 21.9181L18.8042 9.88248L16.4951 7.17289L9.23799 0H0.00172773Z" fill="currentColor" />
                      <path fill-rule="evenodd" clip-rule="evenodd" d="M7.77295 16.3566L23.6563 0H32V6.88383C32 6.88383 31.8262 9.17836 30.6591 10.4057L19.7824 22H13.6938L7.77295 16.3566Z" fill="currentColor" />
                    </svg>
                  </span>
                  <span class="app-brand-text demo text-heading fw-bold ms-2">AdsterraFleet CRM</span>
                </a>
              </div>

              <div class="d-flex align-items-center gap-3 p-3 rounded border bg-body-tertiary mb-4">
                <img src="{avatar}" alt="Operator avatar" width="44" height="44" class="rounded-circle flex-shrink-0" />
                <div class="min-w-0">
                  <h4 class="mb-0 fs-5 text-truncate">{heading}</h4>
                  <p class="mb-0 small text-body-secondary">{subtext}</p>
                </div>
              </div>

              <div id="u25LoginAlert" class="alert alert-danger {"" if safe_err else "d-none"}" role="alert">{safe_err}</div>

              <form id="u25LoginForm" method="POST" action="/api/auth/login" novalidate>
                <input type="hidden" name="mode" value="{mode_value}" />
                <div class="mb-4 u25-field">
                  <label for="u25LoginEmail" class="form-label">Operator Email or Name</label>
                  <input
                    type="text"
                    class="form-control"
                    id="u25LoginEmail"
                    name="identifier"
                    value="{prefill_email}"
                    autocomplete="username"
                    spellcheck="false"
                    autocapitalize="none"
                    enterkeyhint="next"
                    required
                  />
                </div>

                <div class="mb-4 u25-field">
                  <label class="form-label" for="u25LoginPassword">{pw_label}</label>
                  <div class="input-group input-group-merge">
                    <input
                      type="password"
                      id="u25LoginPassword"
                      name="password"
                      class="form-control"
                      autocomplete="{pw_autocomplete}"
                      placeholder="Enter password"
                      minlength="8"
                      enterkeyhint="done"
                      required
                      autofocus
                      data-error="u25LoginPwErr"
                    />
                    <button type="button" class="input-group-text cursor-pointer" id="u25LoginPwToggle" aria-pressed="false" aria-label="Show password">
                      <i class="icon-base ti tabler-eye-off icon-18px"></i>
                    </button>
                  </div>
                  <div id="u25LoginPwErr" class="u25-error-msg">Enter at least 8 characters.</div>
                </div>

                <div class="mb-4 d-flex justify-content-between align-items-center">
                  <div class="form-check mb-0">
                    <input class="form-check-input" type="checkbox" id="u25RememberMe" name="remember" value="1" checked />
                    <label class="form-check-label" for="u25RememberMe">Keep signed in (30 days)</label>
                  </div>
                  <a href="/classic" class="small text-body-secondary">Classic UI (/classic)</a>
                </div>

                <button type="submit" class="btn btn-primary d-grid w-100" id="u25LoginSubmitBtn">
                  {submit_label}
                </button>
                {dev_unlock_html}
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      (function () {{
        var form = document.getElementById("u25LoginForm");
        var pw = document.getElementById("u25LoginPassword");
        var toggle = document.getElementById("u25LoginPwToggle");
        var alertEl = document.getElementById("u25LoginAlert");
        var btn = document.getElementById("u25LoginSubmitBtn");
        var devBtn = document.getElementById("u25DevUnlockBtn");

        if (toggle && pw) {{
          toggle.addEventListener("click", function () {{
            var show = pw.type === "password";
            pw.type = show ? "text" : "password";
            toggle.setAttribute("aria-pressed", String(show));
            toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
            var ic = toggle.querySelector("i");
            if (ic) ic.className = show ? "icon-base ti tabler-eye icon-18px" : "icon-base ti tabler-eye-off icon-18px";
          }});
        }}

        if (devBtn) {{
          devBtn.addEventListener("click", async function () {{
            devBtn.disabled = true;
            try {{
              var r = await fetch("/api/auth/unlock-dev", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: "{{}}" }});
              var d = await r.json();
              if (d.ok) window.location.href = d.redirect || "/";
              else if (alertEl) {{ alertEl.textContent = d.error || "Unlock failed"; alertEl.classList.remove("d-none"); }}
            }} finally {{ devBtn.disabled = false; }}
          }});
        }}

        if (pw) {{
          pw.setAttribute("aria-invalid", "false");
          pw.addEventListener("input", function () {{
            if (pw.validity.valid) pw.setAttribute("aria-invalid", "false");
          }});
          pw.addEventListener("blur", function () {{
            if (pw.value && !pw.validity.valid) pw.setAttribute("aria-invalid", "true");
          }});
        }}

        if (form) {{
          form.addEventListener("submit", async function (e) {{
            e.preventDefault();
            if (!form.checkValidity()) {{
              if (pw && !pw.validity.valid) pw.setAttribute("aria-invalid", "true");
              var firstBad = form.querySelector(":invalid");
              if (firstBad) firstBad.focus();
              return;
            }}
            if (alertEl) alertEl.classList.add("d-none");
            if (btn) btn.disabled = true;
            try {{
              var payload = {{
                mode: form.elements.mode.value,
                identifier: form.elements.identifier.value,
                password: pw.value,
                remember: Boolean(form.elements.remember && form.elements.remember.checked)
              }};
              var res = await fetch("/api/auth/login", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(payload)
              }});
              var data = await res.json();
              if (data.ok) {{
                window.location.href = data.redirect || "/";
              }} else {{
                if (alertEl) {{
                  alertEl.textContent = data.error || "Invalid credentials.";
                  alertEl.classList.remove("d-none");
                }}
                pw.focus();
                pw.select();
              }}
            }} catch (err) {{
              if (alertEl) {{
                alertEl.textContent = "Sign-in request failed: " + String(err);
                alertEl.classList.remove("d-none");
              }}
            }} finally {{
              if (btn) btn.disabled = false;
            }}
          }});
        }}
      }})();
    </script>
  </body>
</html>
"""
