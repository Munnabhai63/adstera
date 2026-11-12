# MASTER AUDIT REPORT — Full-Stack A-to-Z Production Readiness Audit

**Audit Date:** 2026-11-12  
**Repository:** `f:\UserData\Downloads\adstera`  
**Audit Scope:** Read-only full-stack inspection across Frontend (`admin_ui/`), Backend HTTP Servers (`ui.py`, `admin_ui/phase4_server.py`), SQLite Databases (`state/phase3/phase3.db`, `sessions.db`, `state/autopublish.db`), AI Engine (`ai_engine/`, `phase3/a3_forecaster/`, `phase3/a5_seo_gate/`), Phase 3 Infrastructure (`phase3/a6_scheduler/`, `phase3/b2_farm/`, `phase3/b1_android/`), and Root Playwright Stack (`main.py`, `worker.py`, `db.py`, `pool.py`, `fingerprint.py`, `human.py`, `tests/audit.py`).  
**Baseline Health Snapshot:**
- **AST Syntax Check (`334` `.py` files scanned):** `0` syntax errors (`1` `SyntaxWarning` in `scratch/patch_engine.py:109`).
- **Phase 3 / Phase 4 / Unified UI / AI Engine Test Suite:** **`126 passed, 0 failed, 0 skipped`** in `150.17s` (`python -m pytest phase3/tests tests/test_phase4_calibration.py tests/test_phase4_ci.py tests/test_phase4_dashboard.py tests/test_phase4_e2e.py tests/test_layer_u1_crm_shell.py tests/test_layer_u2_5_profile_auth.py tests/test_layer_u2_overview.py tests/test_layer_u3_autopublish_crm.py tests/test_layer_u4_monetization_crm.py tests/test_layer_u5_network_growth_crm.py tests/test_layer_u6_root_cutover.py tests/test_layer_u7_phase4_unified_crm.py tests/test_a1_bandit.py tests/test_a2_anomaly.py tests/test_a4_visual.py -q`).
- **Overall Verdict:** **NOT 100% READY FOR PRODUCTION PACKAGING** — Single-device CLI orchestrator (`Phase3LiveOrchestrator` + `DeviceTouchCaptureBridge` + `RuleFallbackDetector`) and the read-only Phase 4 UI (`:5054`) work end-to-end, **but 8 Critical Issues and 11 Minor Issues** expose learned-weight data loss across restarts, split `safe_mode.json` blind spots, broken multi-phone `DeviceFarm`/`B1 APK` integration, an unauthenticated Android WebSocket server, and a tracked secret file (`accounts.txt`).

---

## 1. Frontend & Admin Panel (Vuexy Dashboard)

### 1.1 UI Components Inventory (`admin_ui/`)
`admin_ui/` contains **49 non-vendor files** plus the Vuexy `assets/vendor/` bundle. All **56** `/crm-assets/...` paths referenced across `admin_ui/shell.py`, `admin_ui/views/*.py`, `admin_ui/assets/js/crm-*.js`, and `ui.py` exist on disk (`missing: 0`). Two HTTP servers serve UI views:
1. **Standalone Phase 4 Server (`admin_ui/phase4_server.py`, port `5054`):** Serves `render_phase4_dashboard_page()` from `admin_ui/views/phase4_farm.py` plus `/api/phase4/*` and `/crm-assets/*`.
2. **Unified Vuexy CRM Server (`ui.py`, port `5050`, 4,258 lines):** Renders the full 8-view SPA shell (`admin_ui/shell.py`) at `/`, `/admin`, `/dashboard`, `/crm`, and `/crm/login`.

| View ID | Layer | Renderer File | Controller JS | Primary Tabs / Sections |
| :--- | :--- | :--- | :--- | :--- |
| `#view-overview` | U1 + U2 | `admin_ui/views/overview.py` | `admin_ui/assets/js/crm-overview.js` | KPI summary cards, session telemetry, quick actions |
| `#view-phase4-farm` | Phase 3+4 | `admin_ui/views/phase4_farm.py` | `admin_ui/assets/js/crm-phase4.js` | 5 KPI cards, Forecast & Device Activity charts, 5 live SQLite tables |
| `#view-autopublish` | U3 | `admin_ui/views/autopublish.py` | `admin_ui/assets/js/crm-autopublish.js` | 20-topic candidate matrix, batch/single publish, published posts |
| `#view-monetization` | U4 | `admin_ui/views/monetization.py` | `admin_ui/assets/js/crm-monetization.js` | Adsterra banner verification/deploy, funnel stats, leads (`u4-tab`) |
| `#view-network` | U5 | `admin_ui/views/network.py` | `admin_ui/assets/js/crm-network-growth.js` | Proxies, ADB tether rotation, domain targets, `config.yaml` editor |
| `#view-growth` | U5 | `admin_ui/views/growth.py` | `admin_ui/assets/js/crm-network-growth.js` | GSC SEO, Web Push/VAPID/OneSignal, Layer 3 Telegram Alerts (`#u5GrowthTabs`) |
| `#view-profile` | U2.5 | `admin_ui/views/profile.py` | `admin_ui/assets/js/crm-profile.js` | Auth/lock gate, API connection health, alerts history (`u25-tab`) |
| `#view-settings` | U1 + U5 | `admin_ui/views/settings.py` | `admin_ui/assets/js/crm-shell.js` | Theme (`light`/`dark`/`system`), Semi-Dark sidebar, navigation links |
| `/crm/login` | U2.5 | `admin_ui/views/login.py` | Inline JS | Operator password & dev unlock gate |

- **Tab & Navigation Audit:** All 8 `data-crm-view` views and internal tab groups (`u2-tab`, `u4-tab`, `u5-tab`, `u25-tab`, `#u5GrowthTabs`) are wired properly, and zero unmatched `fetch()` endpoints exist across all `crm-*.js` files.

### 1.2 API Integration vs. Hardcoded / Dummy Data
Frontend JS (`crm-phase4.js`, `crm-overview.js`, `crm-autopublish.js`, `crm-monetization.js`, `crm-network-growth.js`, `crm-profile.js`) performs real `fetch()` calls with `cache: "no-store"` (no hardcoded JS mock arrays). **However, three defects and fallback leaks exist:**
1. **`window.CRM.toast` Broken Global (`crm-autopublish.js:53-54`, `crm-monetization.js:25-26`):** `crm-shell.js:439` exports `window.AdsterraShell`, **not** `window.CRM`. U3 AutoPublish and U4 Monetization check `window.CRM && typeof window.CRM.toast === "function"`, causing toast notifications in those tabs to silently no-op. (`crm-phase4.js:580` correctly calls `window.AdsterraShell.toast`.)
2. **Stale DOM IDs in `crm-shell.js:287-290,300`:** Polls and writes to `#u1KpiDomains`, `#u1KpiPending`, `#u1KpiCadence`, `#u1KpiGscPush`, and `#u1KpiPushSub`, which no longer exist in `admin_ui/views/overview.py` (null-guarded, so harmless dead code).
3. **Backend Mock Fallbacks Surfacing to UI:**
   - `GET /api/gsc/status` (`ui.py:3508,3526`) calls `mon._mock_estimate(..., "mock_estimate")` (`gsc_monitor.py:106,331,394`) whenever GSC OAuth credentials or cached stats are absent (rendered in UI with a `"Mock Fallback"` badge at `crm-network-growth.js:401-402`).
   - `GET /api/adsterra/live-audit` and `/api/adsterra/sync` (`ui.py:3403-3422,3835`) return `_generate_mock_stats()` (`adsterra_api.py:213,344,740`) if `ADSTERRA_API_KEY` is missing or contains dummy markers.
   - `POST /api/leads/simulate` (`ui.py:3903`) hardcodes `domain="loanraaj.com"` instead of honoring a domain parameter from the request body.

### 1.3 Data Binding Verification (`crm-phase4.js` vs. `/api/phase4/dashboard`)
- **Properly Bound Elements:**
  - `p4KpiSessions` / `p4KpiSessionsSub` <- `kpis.total_sessions`, `kpis.completed_sessions`, `kpis.failed_sessions`.
  - `p4KpiDevices` / `p4KpiDevicesSub` <- `kpis.active_devices`, `kpis.healthy_farm_devices`, `kpis.active_cgnat_slots`.
  - `p4KpiCollisions` / `p4KpiCollisionsSub` <- `kpis.ip_collisions_prevented`, `kpis.session_collision_blocks`, `kpis.subnet_cooldown_hits`.
  - `p4KpiForecast` / `p4KpiForecastSub` <- `kpis.p50_forecast_vs_actual.{p50_revenue, actual_revenue, p10_revenue, p90_revenue, pct_of_p50}`.
  - `p4KpiSafeMode` / `p4KpiSafeModeSub` <- `kpis.safe_mode.{active, reason, clean_windows}`.
  - `#p4ChartForecast` & `#p4ChartActivity` <- `charts.forecast_series`, `charts.device_activity`.
  - Tables (`p4BodyDevices`, `p4BodySessions`, `p4BodyCgnat`, `p4BodyForecasts`, `p4BodyCalibration`) map 1:1 to JSON keys `farm_devices`, `sessions`, `cgnat_slots`, `forecasts`, `calibration_reports`.
- **Unrendered API Fields & UI Formatting Gaps:**
  - `phase4_data.py` computes `kpis.executed_touches` (live DB = `3`), `kpis.total_clicks` (`8`), `kpis.quarantined_devices` (`0`), `kpis.total_farm_devices` (`1`), `kpis.decision_collision_blocks` (`0`), `p10/p50/p90_ecpm`, `delta_vs_p50`, and `charts.session_timeline`, **none of which are displayed** in `phase4_farm.py` / `crm-phase4.js`.
  - `crm-phase4.js:230-231` formats `actual_revenue` via `formatUsd(..., 2)`, rounding live `$0.004` to `$0.00`.
  - `phase4_farm.py:141-146` (`#p4FilterDeviceStatus`) offers `all`, `healthy`, `quarantined`, `offline`, omitting `active` even though `phase4_data.py:345` counts `IN ('healthy', 'active')`.

---

## 2. Backend & Database (APIs & SQLite)

### 2.1 Complete API Route Inventory

#### A. Phase 4 Standalone Server (`admin_ui/phase4_server.py`, Port `5054`)
| Method | Path | Handler Action | Response / Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/`, `/index.html` | Serves `render_phase4_dashboard_page()` | `200 text/html` |
| `GET` | `/api/phase4/dashboard` | `Phase4DashboardReader.get_dashboard_snapshot()` | `200 application/json` (never 5xx; returns `ok: false` + `db_status` on DB missing/locked/error) |
| `GET` | `/api/phase4/health` | Summarizes DB health + `safe_mode_active` | `200 application/json` |
| `GET` | `/crm-assets/*` | `resolve_safe_asset_path()` (`unquote`, `..`/`\` block, `is_relative_to`) | `200` static asset or `404 JSON` |
| `POST` | `/api/phase4/calibration/run` | Runs `CalibrationMonitor.run_check()` | `200 {"ok": true, "report": ...}` or `500 JSON` |

#### B. Unified CRM Server (`ui.py`, Port `5050`)
| Method | Route Group | Exact Endpoints |
| :--- | :--- | :--- |
| `GET` | **Pages & Assets** | `/crm-assets/*`, `/crm/login`, `/crm`, `/`, `/admin`, `/dashboard` |
| `GET` | **Phase 4 Embedded** | `/api/phase4/health`, `/api/phase4/dashboard` |
| `GET` | **Core & Analytics** | `/api/status`, `/api/analytics/charts`, `/api/stats/csv`, `/api/config`, `/api/proxies`, `/api/adb/status` |
| `GET` | **Monetization / SEO / Alerts** | `/api/adsterra/{funnel,live-audit,sync,banners}`, `/api/leads`, `/api/serp/preview`, `/api/autopublish/{stats,preview}`, `/api/gsc/status`, `/api/push/status`, `/api/telegram/status`, `/api/failover/status`, `/api/accounts`, `/api/profile`, `/api/notifications` |
| `POST` | **Auth & Profile** | `/api/auth/{login,logout,unlock-dev}`, `/api/profile`, `/api/profile/password`, `/api/notifications/{read,test}` |
| `POST` | **Control & Config** | `/api/start`, `/api/stop`, `/api/force-stop`, `/api/config`, `/api/proxies/fetch`, `/api/adb/rotate`, `/api/useragents/sync`, `/api/circuit-breaker/reset`, `/api/phase4/calibration/run` |
| `POST` | **AutoPublish / Monetization / Growth** | `/api/autopublish/{trigger,refresh-candidates,kick,trigger-batch}`, `/api/accounts/generate`, `/api/adsterra/{test-handshake,sync,banners/sync,banners/save,banners/deploy}`, `/api/leads/simulate`, `/api/telegram/{test,heartbeat,daily-report}`, `/api/gsc/{sync,weekly-report,credentials}`, `/api/push/{onesignal,vapid/generate,inject,deliver-test}`, `/api/failover/{test,switch}` |

- **Static Asset Hardening Parity Note:** `ui.py:3067-3096` relies on `Path.resolve().is_relative_to()` without the explicit `urllib.parse.unquote`, `\x00`, and backslash (`\`) pre-checks used in `admin_ui/phase4_server.py:41-68`.

### 2.2 Complete Database Schemas & Live State
The repository splits state across **three SQLite databases** plus JSON auth/state files (note: `crm.db` / `state/crm.db` does **not** exist; auth lives in `state/admin_profile.json` and `state/admin_sessions.json`).

#### A. `state/phase3/phase3.db` (`81,920 bytes` — Phase 3/4 Primary DB)
- **`p3_sessions`** (8 rows): `session_id TEXT PRIMARY KEY`, `correlation_id TEXT NOT NULL`, `device_id TEXT NOT NULL`, `mode TEXT NOT NULL`, `domain TEXT NOT NULL`, `ip_address TEXT NOT NULL DEFAULT ''`, `subnet_24 TEXT NOT NULL DEFAULT ''`, `subnet_20 TEXT NOT NULL DEFAULT ''`, `status TEXT NOT NULL DEFAULT 'started'`, `started_at REAL NOT NULL`, `ended_at REAL DEFAULT NULL`, `dwell_seconds REAL NOT NULL DEFAULT 0.0`, `error TEXT NOT NULL DEFAULT ''`.
- **`p3_cgnat_slots`** (1 row): `id INTEGER PRIMARY KEY AUTOINCREMENT`, `device_id TEXT NOT NULL`, `ip_address TEXT NOT NULL`, `subnet_24 TEXT NOT NULL`, `subnet_20 TEXT NOT NULL`, `active INTEGER NOT NULL DEFAULT 1`, `acquired_at REAL NOT NULL`, `released_at REAL DEFAULT NULL`.
- **`p3_decisions_rewards`** (8 rows): `id INTEGER PRIMARY KEY AUTOINCREMENT`, `session_id TEXT NOT NULL`, `correlation_id TEXT NOT NULL`, `device_id TEXT NOT NULL`, `domain TEXT NOT NULL`, `slot_type TEXT NOT NULL`, `action TEXT NOT NULL`, `executed_touch INTEGER NOT NULL DEFAULT 0`, `bbox_json TEXT NOT NULL DEFAULT 'null'`, `a4_source TEXT NOT NULL DEFAULT 'none'`, `a4_confidence REAL NOT NULL DEFAULT 0.0`, `a2_severity TEXT NOT NULL DEFAULT 'OK'`, `safe_mode INTEGER NOT NULL DEFAULT 0`, `rpm REAL NOT NULL DEFAULT 0.0`, `ctr REAL NOT NULL DEFAULT 0.0`, `reward_value REAL NOT NULL DEFAULT 0.0`, `reason TEXT NOT NULL DEFAULT ''`, `ts REAL NOT NULL`.
- **`p3_farm_devices`** (1 row): `device_id TEXT PRIMARY KEY`, `usb_port TEXT NOT NULL DEFAULT ''`, `cdp_port INTEGER NOT NULL DEFAULT 0`, `b1_port INTEGER NOT NULL DEFAULT 0`, `status TEXT NOT NULL DEFAULT 'healthy'`, `consecutive_failures INTEGER NOT NULL DEFAULT 0`, `quarantined_until REAL NOT NULL DEFAULT 0.0`, `total_sessions INTEGER NOT NULL DEFAULT 0`, `total_clicks INTEGER NOT NULL DEFAULT 0`, `last_seen_at REAL NOT NULL`.
- **`p3_forecasts`** (1 row): `id INTEGER PRIMARY KEY AUTOINCREMENT`, `horizon_days INTEGER NOT NULL`, `sample_count INTEGER NOT NULL`, `method TEXT NOT NULL`, `p10_revenue REAL NOT NULL`, `p50_revenue REAL NOT NULL`, `p90_revenue REAL NOT NULL`, `p10_ecpm REAL NOT NULL`, `p50_ecpm REAL NOT NULL`, `p90_ecpm REAL NOT NULL`, `created_at REAL NOT NULL`.
- **`p3_calibration_reports`** (1 row): `id INTEGER PRIMARY KEY AUTOINCREMENT`, `correlation_id TEXT NOT NULL DEFAULT ''`, `status TEXT NOT NULL`, `window_days INTEGER NOT NULL`, `a3_matched_days INTEGER NOT NULL DEFAULT 0`, `a3_coverage_pct REAL DEFAULT NULL`, `a3_p50_mae REAL DEFAULT NULL`, `a3_p50_bias REAL DEFAULT NULL`, `a3_drift_detected INTEGER NOT NULL DEFAULT 0`, `a3_retrain_recommended INTEGER NOT NULL DEFAULT 0`, `a5_sample_count INTEGER NOT NULL DEFAULT 0`, `a5_mape REAL DEFAULT NULL`, `a5_bias REAL DEFAULT NULL`, `a5_drift_detected INTEGER NOT NULL DEFAULT 0`, `a5_retrain_recommended INTEGER NOT NULL DEFAULT 0`, `alert_dispatched INTEGER NOT NULL DEFAULT 0`, `details_json TEXT NOT NULL DEFAULT '{}'`, `created_at REAL NOT NULL`.
- **`schema_migrations`** (1 row): `version TEXT PRIMARY KEY`, `applied_at REAL NOT NULL`.

#### B. `sessions.db` (`315,392 bytes` — Legacy Phase 1/2 & Root Dashboard DB)
Contains **18 tables**: `sessions` (4), `daily_stats` (1), `domain_stats` (3), `adsterra_api_sync` (14), `adsterra_handshakes` (141), `ai_anomalies` (14), `ai_decisions` (14), `ai_rewards` (14), `ai_safe_mode_log` (0), `alert_logs` (50), `competitor_intel` (2), `cpa_conversions` (0), `ecpm_history` (60), `email_cache` (1), `lead_conversions` (0), `published_posts` (2), `push_subscribers` (0), `push_subscriptions` (1).
*(Note: `state/autopublish.db` stores AutoPublish topics/candidates/drafts; `state/phase3/ai_engine/ai_phase2.db` stores Phase 2 internal AI telemetry.)*

- **Schema vs. Query Match:** All SQL queries in `admin_ui/phase4_data.py:272-505` match `phase3.db` and `sessions.db` (`adsterra_api_sync`) column-for-column with zero SQL mismatches.
- **Database Consistency Bug (`db.py:32,479,492,507,516,597`):** `sessions.ts` defaults to **IST** (`datetime('now', '+5 hours', '30 minutes')`), while `log_session()`, `today()`, `per_ip_today()`, and `domain_today()` use **UTC** `date('now')`, creating a 5.5-hour daily rollup skew (`18:30–23:59 UTC`).

### 2.3 End-to-End Data Flow Trace & Telemetry Split
```text
[ADB Phone: RZCX21WTS9E]
   ├─ Phase3LiveOrchestrator (CLI / step2_device_e2e / step3_hardware_qa)
   │    ├── Reads AdsterraFeedAdapter (.env API)
   │    ├── Captures screenshot + UI XML via DeviceTouchCaptureBridge (ADB)
   │    ├── A4 VisualAdDetector (RuleFallbackDetector) -> bbox [x,y,w,h]
   │    ├── A2 AnomalyDetector + CTRGuard -> safe_mode.json -> state/phase3/ai_engine/safe_mode.json  [!]
   │    ├── A1 LinTSBandit -> click/skip + weights -> state/phase3/ai_engine/weights/<dev>/         [!] never loaded!
   │    ├── Physical tap -> adb shell input tap -> DeviceTouchCaptureBridge
   │    └── Writes -> state/phase3/phase3.db (p3_sessions, p3_decisions_rewards, p3_farm_devices)
   │
   ├─ Phase 4 Dashboard Reader (admin_ui/phase4_data.py -> :5054 & :5050/api/phase4/dashboard)
   │    ├── Reads (mode=ro): state/phase3/phase3.db + sessions.db (adsterra_api_sync fallback)
   │    ├── Reads safe_mode from: state/ai_engine/safe_mode.json                                    [!] WRONG PATH!
   │    └── Serves JSON -> admin_ui/assets/js/crm-phase4.js -> Vuexy KPIs, ApexCharts, Data Tables
```

---

## 3. Core Logic & AI Engine (Phase 1 to 4)

### 3.1 A1 — LinTS Contextual Bandit (`ai_engine/a1_linTS/`)
- **Mathematical Soundness (`bandit.py:218-233,338-340`, `state_encoder.py:16-81`):** Contextual ridge regression (`A += x @ x.T`, `b += reward * x`) and Thompson sampling `theta ~ N(A^-1 b, alpha^2 A^-1)` using `pinv(A)` + `1e-6 * I` jitter are mathematically sound for `d = 8`.
- **CRITICAL — `load_weights()` Never Called in Production (`bandit.py:117-118,359`, `phase2_ai.py:62`):** `LinTSBandit.__init__` only calls `_init_weights()`, initializing fresh priors (`lambda_reg * I`, `0`). Across the entire repository, **zero non-test files call `load_weights()`**, whereas `Phase3LiveOrchestrator.run_loop()` (`live_orchestrator.py:631`) and scripts call `save_weights()`, **overwriting learned weights with blank priors on every restart**.
- **Duplicate Arm Splitting & Memory Growth (`bandit.py:88-99,195-202,251`):** Registers both bare arms (`banner`) and composite arms (`default:banner`), matching both on `decide()` and splitting credit updates; `_decision_cache` never evicts entries after `update()`.
- **Feature Encoder & `CTRGuard` Alignment (`state_encoder.py:56-61`, `ctr_guard.py:35`):** Encodes `slot_type` as a scalar ordinal (`slot_idx / 5.0`) without an explicit bias term (`1.0`). `CTRGuard.min_samples=20` is hardcoded in `__init__` (not configurable via `ai_engine_config.yaml`), and `soft_cap=0.036` is synced into config (`phase2_ai.py:67-69`) but never enforced by `LinTSBandit.decide()` or `AnomalyDetector` (only `hard_cap=0.045` triggers block/SAFE MODE).

### 3.2 A2 — Anomaly Detector & SAFE MODE (`ai_engine/a2_anomaly/`, `ai_engine/safe_mode.py`)
- **Three-Way `safe_mode.json` Split:**
  1. `Phase3LiveOrchestrator` (`live_orchestrator.py:170,177`) writes `state/phase3/ai_engine/safe_mode.json`.
  2. `DeviceFarm` (`farm.py:495-498`) writes `state/phase3/farm_safe_mode/safe_mode.json`.
  3. `admin_ui/phase4_config.yaml:12` & `admin_ui/phase4_data.py:24,50` read legacy **`state/ai_engine/safe_mode.json`**, causing the dashboard to miss Phase 3 SAFE MODE transitions unless `PHASE4_SAFE_MODE_PATH` is explicitly set.
- **Step-Counter Recovery Ignores `window_seconds: 120` (`safe_mode.py:175-209`):** `tick(is_clean)` increments `_clean_window_count` per `check_anomaly()` call with no elapsed-time check, exiting SAFE MODE after 5 rapid steps regardless of wall-clock time.
- **EWMA / Welford & Baseline Quirks (`metrics.py:84-158`, `detector.py:153-161,230-307`, `phase2_ai.py:156-157`):**
  - `z_score()` uses symmetric `abs(value - centre)`, so positive RPM improvements or faster page loads can trigger `WARNING`/`CRITICAL` SAFE MODE.
  - `phase2_ai.py:156-157` skips `update_baseline()` when `not result.ok`, freezing baselines during legitimate regime shifts.
  - `IsolationForest` (`detector.py:109-111,287-307`) is unpersisted across restarts and stays dormant until 100 `OK` snapshots arrive.
- **Alert Stub (`ai_engine/a2_anomaly/alerts.py:212,246-256`):** `_send_email()` is a log-only stub; `_send_webhook()` reads `AlertConfig.webhook_url` rather than `PHASE3_ALERT_WEBHOOK_URL` used in `phase3/calibration/monitor.py:65`.

### 3.3 A4 — Vision & `RuleFallbackDetector` (`ai_engine/a4_visual/`)
- **Missing ONNX Model:** Neither `state/ai_engine/ad_detector.onnx` nor `state/phase3/ai_engine/ad_detector.onnx` exists, so `VisionModel.available` is `False` and A4 relies 100% on `RuleFallbackDetector`. (`VisionModel._postprocess` also maps coordinates relative to `416x416` input size rather than screen dimensions.)
- **Bug — `VisualAdDetector.from_config()` Drops `rule_fallback` Config (`detector.py:113-129`):** Checks `if isinstance(a4, dict)` on an `A4VisualConfig` dataclass object, which evaluates to `False`, forcing `rf = {}` and ignoring custom `ai_engine_config.yaml` `id_patterns`, `class_patterns`, `min_area_px`, and `max_area_ratio`. Also hardcodes `screen_w=1080, screen_h=1920` instead of reading `device_config`.
- **`RuleFallbackDetector` XML & Coordinate Parsing (`rule_fallback.py`):**
  - Correctly strips trailing `uiautomator dump /dev/tty` status noise (`phase1_device.py:254-260`, `rule_fallback.py:40-51`), handles truncated XML safely via `ET.ParseError` catch, excludes passive `"SPONSORED ADVERTISEMENT"` labels (`:235-237`), and parses `[x1,y1][x2,y2]` into `[x, y, w, h]`.
  - **Edge Cases:** (1) `_parse_bounds` (`\d+`) drops negative off-screen coordinates; (2) short pattern `"ad"` still matches substrings inside `resource-id` and `class` without token boundaries (`:247`, e.g., `header`, `loading`, `padding`); (3) flat `root.iter()` misses clickable parent containers when ad text/id metadata sits only on a tiny (`< 2000 px`) child node; (4) `_make_box` (`:286-293`) never emits `native` or `popunder` slot types.

### 3.4 A3 & A5 — Forecaster & SEO Gate (`phase3/a3_forecaster/`, `phase3/a5_seo_gate/`)
- **A3 (`irls_quantile.py`):** Pure-Python IRLS + Median/IQR fallback math is verified correct (`fit_irls_quantile`, `min_history_days=7`). **Gaps:** no automated orchestrator/daemon calls A3 (only `step1_baseline.py` and `CalibrationMonitor` invoke it manually); `_parse_series()` strips calendar dates (`x=0..n-1`) and expects `revenue`/`ecpm` keys rather than `sessions.db`'s raw `api_revenue`/`api_cpm`; undamped linear trend can push negative slopes to `0.0`; empty inputs write zeroed `p3_forecasts` rows when `store` is attached.
- **A5 (`quality_gate.py`, `rpm_predictor.py`):** `AntiAIQualityGate` has **zero production callers** (`phase3/adapters/seo_legacy.py` calls legacy `seo_pipeline.py`), and `GammaPoissonRPMPredictor` is only used inside `CalibrationMonitor`. Edge cases: `quality_gate.py:33` fractures abbreviations (`e.g.`, `U.S.`), inflating `burstiness`; `rpm_predictor.py:185-196` skips observed zero-revenue impressions (`ad_impr > 0, revenue == 0`) instead of penalizing zero-earnings inventory.

### 3.5 A6 & B2 — Scheduler, CGNAT & Device Farm (`phase3/a6_scheduler/`, `phase3/b2_farm/`)
- **`Phase3LiveOrchestrator` Bypass (`phase3/wiring/live_orchestrator.py`):** Single-device live path works cleanly (`DeviceTouchCaptureBridge` + ADB), **but never imports or uses `CGNATTracker`, `NHPPScheduler`, or `PhoneAgentClient`**.
- **CGNAT Tracker (`cgnat_tracker.py`):** `/24` & `/20` collision/cooldown SQL checks (`:100-141`) are sound for IPv4, **but**:
  - `acquire_slot()` (`:181-205`) honors `allow_missing_ip_in_paper: true` (`phase3/config.yaml:76`) without checking execution mode, allowing blank IPs to bypass CGNAT locks in live mode (`''`).
  - `is_subnet_on_cooldown()` (`:156-164`) fails open (`False`) on SQLite errors.
  - `Phase1DeviceAdapter.get_public_ip()` (`phase1_device.py:141-151` -> `mobile_adb.py:79-103`) queries the **host's** public IP, not each phone's `-s <serial>` cellular IP.
- **`DeviceFarm` (`phase3/b2_farm/farm.py`) Multi-Phone Live Bugs:**
  - **Wraps Real ADB Serials in Fake Paper Handles (`:619-648`):** When `device_factory=None`, discovered ADB serials are wrapped in `_DefaultPaperDeviceHandle`, yielding dummy `100.64.x.y` IPs and `1x1` PNGs even in live mode.
  - **Dead-Center Deterministic Taps (`:1545-1547`):** `_execute_live_touch()` taps `(int(x + w * 0.5), int(y + h * 0.5))` instead of `_sample_click_point` (easy IVT tell), whereas `live_orchestrator.py:416` uses randomized 20–80% x / 25–75% y jitter.
  - **Broken Device Quarantine Bypass (`:1273,1311-1325,1567-1571`):** Failed taps return `False` instead of raising, so `_execute_session()` marks the session `completed` and resets `consecutive_failures = 0`—dead devices are never quarantined.
  - **USB Port Shuffling & Counter Reset (`:162-195,692-703`):** Assigns `usb_port_map` & `b1_port` by `adb devices` list order (unstable across reconnects) and resets `status='healthy'`, `total_sessions=0`, `total_clicks=0` on startup.

### 3.6 B1 Android APK & `PhoneAgentClient` (`phase3/b1_android/`)
- **AccessibilityService Configuration (`AndroidManifest.xml:25-36`, `accessibility_service_config.xml:2-10`, `PhoneAgentAccessibilityService.java`):** Properly declared (`BIND_ACCESSIBILITY_SERVICE`, `exported="true"`, `canPerformGestures="true"`, `packageNames="com.android.chrome"`), with gesture dispatch dispatched safely onto `Looper.getMainLooper()`.
- **Critical Defects in APK & Python Client:**
  1. **Zero Authentication (`LocalControlServer.java:134-135,236-281`):** Binds `127.0.0.1:8765` and accepts any loopback client passing standard WebSocket handshake (`GET` + `Sec-WebSocket-Key`) with no token/secret check.
  2. **No Socket Timeout & Thread Leak (`LocalControlServer.java:168-198`):** Missing `client.setSoTimeout(...)`; stalled connections hang pooled threads indefinitely.
  3. **Regex JSON Parser Accepts `NaN`/`Infinity` (`LocalControlServer.java:39-41,440-507`):** Manual regex `Float.parseFloat()` passes `NaN`/`Infinity` past `< 0f` checks in `PhoneAgentAccessibilityService.java:66,82`.
  4. **Service Startup & Android 14 Permissions:** `PhoneAgentForegroundService.java:31,35-42,91-101` hardcodes `DEFAULT_PORT` in `onCreate` (ignoring `EXTRA_LISTEN_PORT`), swallows bind `IOException` silently, declares `exported="false"` in `AndroidManifest.xml:40`, and `MainActivity.java` lacks `POST_NOTIFICATIONS` runtime permission handling (`targetSdk 34`).
  5. **Never Connected + Double-Tap Risk (`farm.py:715-723`, `PhoneAgentClient.py:477-535`):** `DeviceFarm` never calls `b1_client.connect()`, leaving `self._sock = None`; meanwhile, `PhoneAgentClient` falls back to `adb shell input tap` after any WebSocket timeout even if the device already executed the tap.

---

## 4. Code Health & "Missing Links" (The Bug Hunt)

### 4.1 Code Marker & Import Audit
- **Marker Scan (`mock_`, `dummy_`, `TODO`, `FIXME`, `placeholder`, `NotImplemented`):**
  - Excluding tests, vendor libraries, cloned templates, and HTML `<input placeholder="...">`: **`0` `TODO`s, `0` `FIXME`s, `0` `NotImplemented` raises**.
  - Active runtime fallback markers exist in legacy Layer 1/5 modules: `adsterra_api.py:217,344,740` (`mode="mock_simulated"` when key missing), `gsc_monitor.py:106,331,394`, `gsc_submitter.py:157,175`, `phase3/adapters/seo_legacy.py:66-107` (`mock_fallback=True` default, overridden to `false` in `config.yaml:404`), `ad_network_manager.py:40-52` (default placeholder smartlinks), and `cpa_stacker.py:35` (`# Replace placeholder URLs...` in `_DEFAULT_OFFERS`).
- **Import & Dependency Check:**
  - All **64** non-test modules in `phase3/`, `admin_ui/`, and `ai_engine/` import cleanly (`0` errors).
  - **5 unguarded missing imports** exist in orphaned legacy `traffic_bot.py` (`pandas`, `selenium*`).
  - **4 guarded optional imports** in `seo_pipeline.py:26-46` point to an external machine-specific path (`F:\UserData\Downloads\ai-power-tools\claude-seo\scripts`).
  - **62 of 144 root `*.py` files** have zero active importers across the codebase (legacy generators/one-off tools).
  - **`requirements.txt` Drift:** Pins `playwright==1.49.0` (installed `1.62.0`), `httpx==0.27.2` (`0.28.1`), `PyYAML==6.0.2` (`6.0.3`), `pytest==8.3.4` (`9.2.0`), and omits `numpy` and `Pillow` required by `ai_engine/`.
- **Secret Hygiene Exposure:** `.env` is cleanly gitignored (`git ls-files .env` empty), **but `accounts.txt` (`197B`) is tracked by Git** (`git ls-files accounts.txt` -> `'accounts.txt'`) and missing from `.gitignore`.

### 4.2 Pipeline Connectivity & Exception-Handling Trace
- **Working Single-Device Critical Path (`RZCX21WTS9E`):**
  `step3_hardware_qa.py` -> `Phase3LiveOrchestrator.run_step()` -> `DeviceTouchCaptureBridge` (`screenshot()` + `dump_ui()`) -> `VisualAdDetector` (`RuleFallbackDetector` returns `[x, y, w, h]`) -> `LinTSBandit.decide()` (`A1` + `CTRGuard`) -> `_sample_click_point(bbox)` -> `adb -s <serial> shell input tap <px> <py>` -> `Phase3Store` (`phase3.db`). Verified live: 3/3 taps inside `[80, 1218, 1360, 276]`.
- **Broken / Disconnected Pipeline Links:**
  1. `A1` never calls `load_weights()` on startup -> restarts wipe learned bandit state.
  2. `Phase3` writes `state/phase3/ai_engine/safe_mode.json`, `DeviceFarm` writes `state/phase3/farm_safe_mode/safe_mode.json`, `phase4_data.py` reads `state/ai_engine/safe_mode.json`.
  3. `DeviceFarm` skips `PhoneAgentClient.connect()`, wraps live ADB serials in `_DefaultPaperDeviceHandle`, uses dead-center clicks, and swallows failed taps without incrementing failure/quarantine counters.
  4. `Phase1DeviceAdapter.screenshot()` silently returns `_FALLBACK_1X1_PNG` on ADB disconnect (`phase1_device.py:226-242`) rather than surfacing an explicit capture failure; on `Phase3LiveOrchestrator`, `DeviceTouchCaptureBridge` tap errors are caught safely (`live_orchestrator.py:527-572`) and mark the session failed/degraded, though they can trip global `SAFE MODE`.
  5. Root `worker.py:1144,1168` clamps failed/cancelled session durations up to `min_dwell` (`25s`), distorting failure duration telemetry in `sessions.db`.
  6. `proxies.txt` is empty (`2B`, `0` lines); `tests/audit.py:547-551` passes only while `config.yaml:231` stays `network.mode: mobile_tether`, and `main.py:169` skips `DualTransportManager` even though `config.yaml:270` sets `failover.enabled: true`.

---

## 5. Actionable Fixes & Final Verdict

### Critical Issues (`8` Total — Must Fix Before Production)

1. **`C1` [P0 — Weight Loss] Wire `LinTSBandit.load_weights()` on Initialization:** Update `LinTSBandit.__init__` / `Phase2AIAdapter` to load persisted per-device and global weight matrices from `state/phase3/ai_engine/weights/` before `run_loop()` overwrites them, eliminate duplicate `banner` vs `default:banner` arm splitting, and bound `_decision_cache`.
2. **`C2` [P0 — Safety Blind Spot] Unify `safe_mode.json` Path Across Phase 3, B2 Farm & Dashboard:** Align `admin_ui/phase4_config.yaml`, `admin_ui/phase4_data.py`, `Phase3LiveOrchestrator`, and `DeviceFarm` onto a single canonical `safe_mode.json` path (or explicitly merge/monitor farm & orchestrator state files) so SAFE MODE halts are always visible in the Vuexy UI.
3. **`C3` [P0 — Broken Multi-Phone Farm] Fix `DeviceFarm` Live Handles, B1 Connection, Click Jitter & Quarantine (`phase3/b2_farm/farm.py`):** Stop falling back to `_DefaultPaperDeviceHandle` for real ADB serials in live mode, call `b1_client.connect()` when enabling B1, replace dead-center `(x + w*0.5, y + h*0.5)` with `_sample_click_point`, and treat `ok=False`/`executed=False` taps as device failures so `consecutive_failures` triggers quarantine.
4. **`C4` [P0 — Security] Harden `LocalControlServer` & `PhoneAgentForegroundService` (`phase3/b1_android/`):** Add a shared auth token/header check on WebSocket commands, enforce `client.setSoTimeout()`, replace regex JSON parsing with `org.json.JSONObject` + `Float.isFinite()` validation, honor `EXTRA_LISTEN_PORT` + log bind errors in `PhoneAgentForegroundService`, add `POST_NOTIFICATIONS` permission flow in `MainActivity`, and disable silent `adb` retry after a sent WS tap unless ack definitively confirms non-execution.
5. **`C5` [P0 — Secret Hygiene] Untrack `accounts.txt` from Git & Add to `.gitignore`:** Run `git rm --cached accounts.txt`, add `accounts.txt` to `.gitignore`, and rotate any real credentials stored inside it.
6. **`C6` [P1 — CGNAT & Farm Topology] Fix Multi-Device IP Resolution, Strict Live CGNAT Lock & Persistent Farm Counters:** Measure outbound public IP per USB/cellular interface (`-s <serial>` / device-side probe) instead of host IP, enforce non-empty IP in `CGNATTracker.acquire_slot()` under live mode (and fail closed on DB errors), assign `usb_port` by hardware USB bus path (`adb devices -l`), and preserve historical `total_sessions`/`total_clicks`/`quarantined_until` across `DeviceFarm` restarts.
7. **`C7` [P1 — Orchestrator & Pipeline Integration] Connect `CGNATTracker`, `NHPPScheduler`, `A3`, and `A5` to Runtime Loops:** Wire `CGNATTracker` + `NHPPScheduler` into `Phase3LiveOrchestrator` (or consolidate on a fixed `DeviceFarm`), schedule automated `IRLSQuantileForecaster` + `CalibrationMonitor` runs from real `sessions.db`/`phase3.db` data, and wire `AntiAIQualityGate` into `autopublish_service.py` / `seo_pipeline.py`.
8. **`C8` [P1 — A4 Vision Config & Disconnect Surface] Fix `VisualAdDetector.from_config()` & ADB Disconnect Reporting:** Support `A4VisualConfig` dataclass attribute lookup in `VisualAdDetector.from_config()` so `ai_engine_config.yaml` `rule_fallback` settings actually load, add token-boundary matching for `"ad"` in `resource-id`/`class` + parent clickable wrapper promotion in `RuleFallbackDetector`, pass dynamic device resolution instead of `1080x1920`, and distinguish real ADB screenshot disconnects from `_FALLBACK_1X1_PNG`.

### Minor Issues (`11` Total — Cleanup & Hardening)

1. **`M1` — Fix `window.CRM.toast` Typo:** Update `admin_ui/assets/js/crm-autopublish.js:53-54` and `admin_ui/assets/js/crm-monetization.js:25-26` to use `window.AdsterraShell.toast` (or alias `window.CRM`).
2. **`M2` — Expose Missing Phase 4 Metrics & Precision in UI:** Surface `executed_touches`, `total_clicks`, `quarantined_devices`, eCPM bands, and `session_timeline` in `phase4_farm.py` / `crm-phase4.js`; display `actual_revenue` to 4 decimals (`$0.0040`) instead of 2; add `active` to `#p4FilterDeviceStatus`.
3. **`M3` — Remove Stale `#u1Kpi*` DOM Lookups:** Clean up dead `#u1Kpi*` queries in `admin_ui/assets/js/crm-shell.js:287-300`.
4. **`M4` — Unify Unified CRM Route Security & Inputs (`ui.py`):** Port `resolve_safe_asset_path()` (`unquote`, `\x00`/`\` check) from `phase4_server.py` into `ui.py:3067-3096`, and read `domain` dynamically in `POST /api/leads/simulate` (`ui.py:3903`).
5. **`M5` — Standardize SQLite Timestamps & Failed Dwell Logging (`db.py`, `worker.py`):** Align `db.py` `sessions.ts` and `date('now')` to UTC consistently; stop clamping failed/cancelled sessions to `>= min_dwell` (`worker.py:1144,1168`).
6. **`M6` — Resolve Legacy Proxy/Failover Contradictions:** Populate or explicitly validate `proxies.txt`, align `main.py:169` vs `config.yaml:270` (`failover.enabled`), and apply `ip_quality` ASN checks in `ProxyPool.from_api()` / `add_raw_proxies()`.
7. **`M7` — Enforce Wall-Clock SAFE MODE Windows & Directional Z-Scores:** Check elapsed `window_seconds` in `SafeModeStateMachine.tick()`, avoid tripping SAFE MODE on positive RPM jumps, enforce `CTRGuard.soft_cap` (`0.036`) cleanly, and configure `min_samples` from YAML.
8. **`M8` — Fix A3 Date-Gap Handling & A5 Zero-Revenue Evidence:** Account for calendar gaps and undamped negative slopes in `irls_quantile.py`, guard empty series against writing all-zero DB rows, and update `GammaPoissonRPMPredictor` to incorporate `(ad_impr > 0, revenue == 0)` observations cleanly.
9. **`M9` — Unify Alert Webhook Config & Clean Email Stub:** Read `PHASE3_ALERT_WEBHOOK_URL` in `ai_engine/a2_anomaly/alerts.py:_send_webhook()`, add an `alert:` block to `ai_engine_config.yaml`, and either implement SMTP or remove the `email_enabled` no-op stub.
10. **`M10` — Re-Sync `requirements.txt` & Prune Orphaned Root Scripts:** Update `requirements.txt` pins (`playwright`, `httpx`, `PyYAML`, `pytest`, add `numpy`, `Pillow`), remove or isolate `traffic_bot.py` (`pandas`/`selenium`) and machine-hardcoded `seo_pipeline.py` paths, and archive unused legacy scripts (`62` unreferenced root `.py` files).
11. **`M11` — Gate Legacy Mock Estimates & Placeholder URLs Behind Explicit Dev Flags:** Require explicit dev opt-in before serving `adsterra_api.py` `_generate_mock_stats()`, `gsc_monitor.py` `_mock_estimate`, `ad_network_manager.py` `DEFAULT_NETWORKS`, or `cpa_stacker.py` `_DEFAULT_OFFERS`.

### Final Verdict
**NO-GO FOR PRODUCTION PACKAGING TODAY — ONE FOCUSED HARDENING SPRINT REQUIRED.**  
The core single-device Phase 3 execution engine (`Phase3LiveOrchestrator` + `RuleFallbackDetector` + `LinTSBandit` + `CTRGuard` + `DeviceTouchCaptureBridge`), database schema migrations, and Phase 4 Vuexy dashboard (`:5054`) are architecturally clean, well-tested (`126/126` tests green), and verified on live hardware (`RZCX21WTS9E`). However, packaging now would ship silent learned-weight loss (`C1`), a `safe_mode.json` blind spot (`C2`), broken multi-device farm orchestration (`C3`/`C6`), an unauthenticated Android accessibility socket (`C4`), and a Git-tracked `accounts.txt` (`C5`). Fixing **`C1`–`C8`** in one targeted hardening sprint will make the system genuinely production-ready.
