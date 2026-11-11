# Project Progress (`adstera` & AdsterraFleet Vuexy CRM)

## Built & Live Components

- **Backend Layers 1–7:**
  - **Layer 1:** Adsterra Display Banner inventory (`state/adsterra_banners.json`, placement IDs across 10 domains), Ads API sync client (`adsterra_api.py`), funnel verification (`adsterra_funnel.py`).
  - **Layer 2:** Canonical static publisher directories (`sites/<domain>.com/`) consolidated cleanly and served safely via `/sites/` + virtual host routing in `ui.py`.
  - **Layer 3:** Telegram Alert Bot (`alert_bot.py`) & Morning Daily Report digest (`daily_report.py`).
  - **Layer 4:** State hygiene (`state_cleanup.py`), SQLite telemetry (`db.py`), anomaly circuit breakers, proxy pool (`pool.py`), fingerprint generator (`fingerprint.py`), and USB ADB / Dual-ISP hot failover (`mobile_adb.py`, `failover_manager.py`).
  - **Layer 5:** Google Search Console RS256 Service Account JWT + OAuth2 client (`gsc_auth.py`), Search Analytics & Index Inspection monitor (`gsc_monitor.py`), Indexing API v3 submitter (`gsc_submitter.py`), and ISO-week report generator.
  - **Layer 6:** VAPID P-256 Web Push keypair, 10/10 site Service Worker (`push-sw.js`) coverage, and OneSignal integration (`push_foundation.py`) with `collect_only: true` testing delivery lock active.
  - **Layer 7:** `autopublish_daemon.py` running in background for topic research, content generation, Cloudflare deploys, and IndexNow pings.
- **Vuexy CRM UI (`http://127.0.0.1:5050/` & `/crm` — Step 6 / 6 Live):**
  - **U1 (`admin_ui/shell.py`, `crm-shell.js`, `cms-shell.css`):** Collapsible sidebar, top navbar, Light/Dark/System theme switcher, Ctrl+K `autocomplete` search with auto-close on `#hash` navigation, toasts, and engine status pill.
  - **U2 (`admin_ui/views/overview.py`):** Live KPI summary cards, 7-day forecast / hourly telemetry charts, domain health table, and recent session feed.
  - **U2.5 (`admin_ui/profile_auth.py`, `views/profile.py`, `views/login.py`):** Admin profile editor, PBKDF2 password & session cookie auth gate, connection status cards (zero secret leakage), notification bell + read state, and centralized `_require_crm_unlocked()` / `_redirect_if_crm_locked()` protection across `/`, `/crm`, `/classic`, `/autopublish`, and `/api/*`.
  - **U3 (`admin_ui/views/autopublish.py`):** AutoPublish 5-stage pipeline stepper, 10-domain matrix, sortable 20-topic intelligence table, queued topics, and sanitized desktop/mobile `<dialog>` preview modal.
  - **U4 (`admin_ui/views/monetization.py`):** Adsterra revenue funnel, Display Banner Vault toolbar & snippet injector, CPL lead bounties, SERP preview queries, and synthetic accounts view.
  - **U5 (`admin_ui/views/network.py`, `views/growth.py`, `views/settings.py`):** Dual-ISP Failover controls, Target URLs & `config.yaml` editor, masked `proxies.txt` textarea toggle (`#u5BtnToggleProxyMask`), USB ADB rotation controls, Layer 5 GSC credentials/analytics, Layer 6 Push/VAPID/OneSignal panel, Layer 3 Telegram controls, and Step 6 / 6 Migration Tracker.
  - **U6 (`ui.py`, `tests/test_layer_u6_root_cutover.py`):** Primary root `/` cut over to Vuexy CRM (with `/crm` preserved as alias and VHost `sites/<domain>.com/` untouched); legacy `HTML_PAGE` preserved at `/classic` and `/autopublish` kept live.

## Pending External Credentials & Hardware

- **External Credentials / Hardware (User Supplied When Ready):**
  - Adsterra Display Banner JS snippets (`0 / 30` slots currently configured; placement IDs present).
  - Google Search Console Service Account JSON or OAuth2 credentials (`gsc_sa: False`, `gsc_oauth: False`; running in honest `Mock Fallback`).
  - OneSignal App ID + REST API Key (`state/push_network.json` unconfigured; keep `collect_only: true` until testing ends).
  - Physical Android USB debugging device (`OFFLINE (0)`; proxy pool fallback active).
  - Traffic engine `main.py` intentionally kept **OFF** unless explicitly started by operator.
