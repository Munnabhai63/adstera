# Project Progress (`adstera` & AdsterraFleet Vuexy CRM)

## Built & Live Components

- **Backend Layers 1–7:**
  - **Layer 1:** Adsterra Display Banner inventory (`state/adsterra_banners.json` now `30 / 30` configured across all 10 domains), anti-adblock `bauval.org` tag parser & selector support (`adsterra_links.py`, `worker.py`), Ads API sync (`adsterra_api.py`), funnel verification (`adsterra_funnel.py`), injected across `687` HTML pages and deployed live to Cloudflare Pages (`10 / 10`).
  - **Layer 2:** Canonical static publisher directories (`sites/<domain>.com/`) consolidated cleanly and served safely via `/sites/` + virtual host routing in `ui.py`.
  - **Layer 3:** Telegram Alert Bot (`alert_bot.py`) & Morning Daily Report digest (`daily_report.py`).
  - **Layer 4:** State hygiene (`state_cleanup.py`), SQLite telemetry (`db.py`), anomaly circuit breakers, proxy pool (`pool.py`), fingerprint generator (`fingerprint.py`), and USB ADB / Dual-ISP hot failover (`mobile_adb.py`, `failover_manager.py`).
  - **Layer 5:** Google Search Console RS256 Service Account JWT (`state/gsc_service_account.json` configured, `10 / 10` domains `siteOwner` live) + OAuth2 client (`gsc_auth.py`), Search Analytics & Index Inspection monitor (`gsc_monitor.py`), Indexing API v3 submitter (`gsc_submitter.py`), and ISO-week report generator.
  - **Layer 6:** VAPID P-256 Web Push keypair, 10/10 site Service Worker (`push-sw.js`) coverage, and OneSignal integration (`push_foundation.py`) with `collect_only: true` testing delivery lock active.
  - **Layer 7:** `autopublish_daemon.py` running in **5-Wave 24-Hour Sequential Quality Mode** (`07:00`, `11:30`, `16:00`, `20:00`, `00:00` IST — `5` articles/domain/day × `10` domains = `50` articles/day, 1 domain at a time) powered by the **3-Layer 24×7 FreeLLMAPI Gateway** (`https://loanraaj.com/v1` Cloudflare Serverless Edge + Direct Cloud Multi-Provider Failover + `http://127.0.0.1:3001` Local Watchdog), running full 5-Stage pipeline (`20-Topic Discovery` -> `Top-5 Selection` -> `2-Part Deep AI Writing 1,500–2,000+ words` -> `Anti-AI Gate 100/100 + Adsterra 3-Slot Injection` -> `Cloudflare Pages Deploy + GSC Indexing API`).
- **Vuexy CRM UI (`http://127.0.0.1:5050/` & `/crm` — Step 6 / 6 Live):**
  - **U1 (`admin_ui/shell.py`, `crm-shell.js`, `cms-shell.css`):** Collapsible sidebar, top navbar, Light/Dark/System theme switcher, Ctrl+K `autocomplete` search with auto-close on `#hash` navigation, toasts, and engine status pill.
  - **U2 (`admin_ui/views/overview.py`):** Live KPI summary cards, 7-day forecast / hourly telemetry charts, domain health table, and recent session feed.
  - **U2.5 (`admin_ui/profile_auth.py`, `views/profile.py`, `views/login.py`):** Admin profile editor, PBKDF2 password & session cookie auth gate, connection status cards (zero secret leakage), notification bell + read state, and centralized `_require_crm_unlocked()` / `_redirect_if_crm_locked()` protection across `/`, `/crm`, `/classic`, `/autopublish`, and `/api/*`.
  - **U3 (`admin_ui/views/autopublish.py`):** AutoPublish 5-stage pipeline stepper, 10-domain matrix, sortable 20-topic intelligence table, queued topics, and sanitized desktop/mobile `<dialog>` preview modal.
  - **U4 (`admin_ui/views/monetization.py`):** Adsterra revenue funnel, Display Banner Vault toolbar & snippet injector, CPL lead bounties, SERP preview queries, and synthetic accounts view.
  - **U5 (`admin_ui/views/network.py`, `views/growth.py`, `views/settings.py`):** Dual-ISP Failover controls, Target URLs & `config.yaml` editor, masked `proxies.txt` textarea toggle (`#u5BtnToggleProxyMask`), USB ADB rotation controls, Layer 5 GSC credentials/analytics, Layer 6 Push/VAPID/OneSignal panel, Layer 3 Telegram controls, and Step 6 / 6 Migration Tracker.
  - **U6 (`ui.py`, `tests/test_layer_u6_root_cutover.py`):** Primary root `/` cut over to Vuexy CRM (with `/crm` preserved as alias and VHost `sites/<domain>.com/` untouched); legacy `HTML_PAGE` preserved at `/classic` and `/autopublish` kept live.

## Remaining Setup & Verification

- **Completed User Inputs & Part A Production Rollout:**
  - Adsterra Display Banner JS snippets: **`30 / 30` slots configured** (`bauval.org` anti-adblock + `/invoke.js` supported), injected across `687` HTML files, and deployed live to Cloudflare Pages (`10 / 10` HTTP `200 OK`).
  - Google Search Console & Indexing API: **Service Account configured & live verified (`10 / 10` `siteOwner`, `live_domains_count: 10`, `mock_domains_count: 0`)**.
  - Canonical & Sitemap Audit (Part A): **Normalized `48` `<link rel="canonical">` tags**, rebuilt all `10` `sitemap.xml` files (`374` total clean URLs), deployed to Cloudflare Pages (`10 / 10`), submitted all `10 / 10` sitemaps (`PUT`) + homepages (`Indexing API HTTP 200`), and configured Cloudflare Zone Dynamic Redirect Rulesets so `https://www.<domain>/*` returns **`301` -> `https://<domain>/*` (`10 / 10` verified)**.
- **Pending User Confirmation (Part B — Proxy / Mobile ADB Network Transport):**
  - Network transport setup for live traffic testing (`proxies.txt` currently returns `407 Proxy Authentication Required` on `global.rotgb.trustsource.live:10000`, and no Android 4G USB `adb` device is attached).
  - Final live end-to-end traffic verification run once Part B proxy credentials or USB ADB device are connected.
  - Optional OneSignal App ID + REST API Key (`state/push_network.json` unconfigured; keep `collect_only: true` until testing ends).
  - Traffic engine `main.py` intentionally kept **OFF** until Part B transport is ready.
