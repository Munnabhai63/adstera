# Phase 3 — Multi-Device Farm, Mathematical Scheduling, SEO/Revenue Intelligence & Live Wiring

> **Notice:** automated clicking may violate ad-network ToS; `--paper` is the safe default.

Phase 3 layers production-grade scheduling, subnet collision tracking, quantile forecasting, SEO/anti-AI quality gating, Android accessibility gesture execution, and multi-device USB farm orchestration on top of Phase 1 (`mobile_adb.py`, `android_cdp_bridge.py`) and Phase 2 (`ai_engine/`), without modifying Phase 1 or Phase 2 source files.

---

## 1. Installation

Use Python 3.11+ with the repository virtual environment:

```bash
pip install -r requirements.txt
playwright install chromium
```

Optional tooling for physical Android device execution:
- **ADB (`adb`)**: Android Platform Tools on `PATH` or `bin/platform-tools/adb.exe`.
- **Android SDK 34 + Gradle** (optional): Only needed if compiling the native B1 APK under `phase3/b1_android/apk/`. Host-side Python client and ADB fallback work without the Android SDK.

---

## 2. Configuration (`phase3/config.yaml`)

All runtime thresholds, caps, diurnal curves, CGNAT cooldowns, quantile settings, SEO gate bounds, and USB port mappings live in `phase3/config.yaml` and are loaded via `phase3.config_loader.load_phase3_config()`.

**Secrets and device serials are never stored in YAML or source files.** Configure secrets exclusively via environment variables:

| Environment Variable | Purpose | Required For |
| --- | --- | --- |
| `PHASE3_LIVE_CONFIRM_TOKEN` | Must equal `CONFIRM_LIVE_EXECUTION` | `--live` mode |
| `ADSTERRA_API_KEY` | Adsterra Publisher API key (falls back to mock stats if unset) | Live Adsterra feed |
| `TELEGRAM_BOT_TOKEN` | Optional Telegram alert bot token | Alert dispatch |
| `TELEGRAM_CHAT_ID` | Optional Telegram alert target chat | Alert dispatch |
| `PHASE3_ALERT_WEBHOOK_URL` | Optional webhook endpoint for A2 anomalies | Webhook alerts |

---

## 3. `--paper` vs `--live` Execution

`--paper` is always the default mode.

- **Paper mode (`--paper`, default):**
  Runs the full pipeline (`capture -> A4 visual/rule detection -> A2 anomaly check -> A1 LinTS decision -> reward update -> SQLite + JSON-lines logging`), emits `paper_click` / `skip` / `defer` decisions, and **never executes a real tap or swipe**.
  ```bash
  python -m phase3.wiring.live_orchestrator --paper --steps 5
  ```
- **Live mode (`--live`, dual-gated):**
  Requires **both** the `--live` CLI flag (or `live=True`) **and** `PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION` in the environment. If the environment token is missing or mismatches, the CLI refuses live execution with exit code `2` and the orchestrator remains safely in paper mode.
  ```bash
  PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION \
    python -m phase3.wiring.live_orchestrator --live --steps 5
  ```

### Safety Guardrails

1. **A4 BBox Gate (`safety.require_a4_bbox_for_gesture`):** No click gesture is allowed unless A4 returns a valid bounding box meeting `confidence_threshold`.
2. **A2 Anomaly & SAFE MODE Gate (`safety.require_a2_ok_for_gesture`):** A `CRITICAL` anomaly from A2 (or any unhandled step exception) immediately enters `SAFE MODE`, suppresses all clicks, and throttles session cadence to `safe_mode_throttle_factor` until `safe_mode_exit_clean_windows` consecutive clean windows pass.
3. **CTR Caps:** `aggregate_ctr_hard_cap` and `per_device_ctr_hard_cap` (default `0.045`) prevent excessive click-through rates via A1 `CTRGuard` and farm-level enforcement.
4. **Correlation IDs & Audit Trail:** Every step binds a unique `correlation_id`, emits structured JSON-lines logs (`phase3.logging_utils`), and persists rows to `p3_sessions` and `p3_decisions_rewards` in SQLite (`phase3.db.Phase3Store`).

---

## 4. Module Overview

- **`phase3/adapters/`** — Clean wrappers around Phase 1 & Phase 2 modules (`phase1_device.py`, `adsterra_feed.py`, `phase2_ai.py`, `seo_legacy.py`, `revenue_legacy.py`).
- **`phase3/wiring/live_orchestrator.py`** — Async orchestrator and CLI wiring `capture -> A4 -> A2 -> A1 -> (paper | live) -> reward -> SQLite/JSON logs`.
- **`phase3/a3_forecaster/` (A3)** — Pure-Python Iteratively Reweighted Least Squares (IRLS) quantile regression (`P10 / P50 / P90` daily revenue and eCPM bands) with median + IQR fallback for `< 7` days of history, persisted to `p3_forecasts`.
- **`phase3/a5_seo_gate/` (A5)** — Gamma-Poisson hierarchical RPM keyword predictor combining GSC and Adsterra signals, plus an Anti-AI SEO content quality gate measuring sentence-length burstiness (CV) and Zipf token entropy/slope.
- **`phase3/a6_scheduler/` (A6)** — Lewis-Shedler thinning Non-Homogeneous Poisson Process (`NHPPScheduler`) driven by the 24-hour diurnal curve and weekday multipliers, paired with `CGNATTracker` to prevent `/24` and `/20` carrier subnet collisions across `p3_cgnat_slots`.
- **`phase3/b1_android/` (B1)** — Native Android Accessibility + Foreground Service APK (`phase3/b1_android/apk/`) exposing a localhost RFC 6455 WebSocket server (`127.0.0.1:8765`) for `dispatchGesture()` taps/scrolls over stock Chrome, plus `PhoneAgentClient.py` with ADB fallback (`mobile_adb.run_adb`).
- **`phase3/b2_farm/` (B2)** — Multi-device USB farm manager (`1–10` phones) isolating per-device ADB/CDP/B1 ports and A1 weights, enforcing farm-wide CTR caps, CGNAT slot isolation, health quarantine/auto-recovery (`p3_farm_devices`), and farm-wide SAFE MODE propagation.

---

## 5. Tests

Run all Phase 3 unit and end-to-end paper-farm tests:

```bash
python -m pytest phase3/tests/ -v
```

Run just the adapter, database, and live-wiring tests:

```bash
python -m pytest phase3/tests/test_adapters_and_db.py phase3/tests/test_live_wiring.py -v
```
