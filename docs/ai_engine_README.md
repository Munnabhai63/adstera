# AI Decision Engine — Phase 2 Architecture & Operations Guide

The **AI Decision Engine** is an intelligent, real-time autonomous decision and anomaly-control layer for high-precision traffic generation and ad interaction. It combines Bayesian machine learning (Linear Thompson Sampling contextual bandit), multi-layered statistical anomaly detection with automated fail-safes (EWMA + Isolation Forest + SAFE MODE), and multi-modal visual ad detection (ONNX computer vision + DOM/accessibility-tree rule fallback).

---

## 1. System Architecture

```
                                    +-----------------------------------------+
                                    |        Android Device / Emulator        |
                                    |    (Phase 1 Capture & Touch Protocol)   |
                                    +-----------------------------------------+
                                              | Screen Bytes         ^ Tap (x, y)
                                              v                      |
+----------------------------------------------------------------------------------------------------+
|                                    AI Engine Orchestrator                                         |
|                                                                                                    |
|   1. Screenshot Capture                                                                            |
|        │                                                                                           |
|        ▼                                                                                           |
|   2. A4 Visual Ad Detector                                                                         |
|        ├── ONNX Vision Model (ad_detector.onnx, confidence gate >= 0.55, timeout <= 300ms)         |
|        └── Fallback: RuleFallbackDetector (UIAutomator / DOM accessibility tree heuristic)         |
|        │                                                                                           |
|        ▼ DetectionResult (best BoundingBox, slot_type, source, confidence)                         |
|   3. A2 Anomaly Detector & Safe Mode Guard                                                         |
|        ├── MetricsBuffer (rolling Welford mean/std + EWMA smoothing)                               |
|        ├── Z-score thresholding (z >= 2.5) & Isolation Forest outlier detection                     |
|        ├── Absolute checks: CTR spike (>= 0.045), RPM floor (< 0.50), Empty ad spike (>= 0.40)      |
|        ├── AlertDispatcher (Telegram, Webhook, Email with 5-minute deduplication)                   |
|        └── SafeModeStateMachine (Suppresses clicks, throttles session rate to 30%, M-tick exit)    |
|        │                                                                                           |
|        ▼ AnomalyResult & Safe Mode Check                                                           |
|   4. A1 LinTS Contextual Bandit                                                                   |
|        ├── StateEncoder (Encodes 8-dim float32 vector: domain, slot, hour, CTR, RPM, device, age)  |
|        ├── CTRGuard (Thread-safe rolling window, hard cap 4.5%, soft cap 3.6%, auto-deferral)      |
|        ├── Bayesian Thompson Sampling: θ ~ N(A⁻¹b, α²A⁻¹) maximizing θᵀx                          |
|        └── WeightStore (Atomic persistence of precision matrix A and reward vector b)              |
|        │                                                                                           |
|        ▼ AdDecision: action ("click" | "paper_click" | "skip" | "defer"), timing, bbox             |
|   5. Execution & Reward Update                                                                     |
|        ├── If action == "click" & not paper: Touch.tap(bbox.random_click_point())                  |
|        ├── If action in ("click", "paper_click"): CTRGuard.record_click()                          |
|        ├── CTRGuard.record_impression()                                                            |
|        ├── Reward computation: R = (RPM / scale) + action_bonus                                    |
|        ├── A1.update(arm_id, reward, state)                                                        |
|        └── SQLite persistence (ai_decisions, ai_rewards, ai_anomalies, ai_safe_mode_log)           |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Core Modules

### A1 — Linear Thompson Sampling Contextual Bandit (`ai_engine/a1_linTS/`)

A1 balances exploration and exploitation across multiple ad slots (`banner`, `interstitial`, `popunder`, `native`, `none`) and domain arms.

- **`StateEncoder` (`state_encoder.py`)**:
  Deterministically encodes an `AgentState` dataclass into an `(8,)` float32 numpy vector normalized to `[0, 1]` or `[-1, 1]`:
  1. `domain_id`: hash mod 1000 / 1000
  2. `slot_type`: one-hot index / number of slots
  3. `time_of_day_h`: local hour / 24
  4. `recent_ctr`: rolling CTR
  5. `recent_rpm`: rolling RPM / `reward_rpm_scale`
  6. `device_id_hash`: device serial hash / 1e6
  7. `session_age_s`: elapsed session seconds / 3600
  8. `bbox_confidence`: visual detector confidence `[0, 1]`

- **`CTRGuard` (`ctr_guard.py`)**:
  Enforces traffic safety limits over a rolling window (default 200 events):
  * `hard_cap`: 0.045 (4.5% absolute CTR ceiling).
  * `soft_cap`: 0.036 (3.6% warning threshold).
  * `would_breach(hard_cap)`: evaluates whether 1 additional click would push window CTR above ceiling.
  * `set_defer(seconds)` / `is_deferred()`: pauses click actions when cap is threatened.

- **`LinTSBandit` (`bandit.py`)**:
  * Precision matrix $\mathbf{A} \in \mathbb{R}^{d \times d}$ (initialized to $\lambda \mathbf{I}$).
  * Reward accumulator vector $\mathbf{b} \in \mathbb{R}^d$.
  * Posterior mean $\boldsymbol{\mu} = \mathbf{A}^{-1}\mathbf{b}$ and covariance $\boldsymbol{\Sigma} = \alpha^2 \mathbf{A}^{-1}$.
  * Sample parameter $\boldsymbol{\theta} \sim \mathcal{N}(\boldsymbol{\mu}, \boldsymbol{\Sigma})$.
  * Selects arm maximizing $\boldsymbol{\theta}^T \mathbf{x}$.
  * Updates: $\mathbf{A} \leftarrow \mathbf{A} + \mathbf{x}\mathbf{x}^T$, $\mathbf{b} \leftarrow \mathbf{b} + r\mathbf{x}$.

- **`WeightStore` (`persistence.py`)**:
  Atomically saves and loads arm matrices $\mathbf{A}$ and $\mathbf{b}$ per ADB device and globally in `state/ai_engine/weights/` using base64-encoded binary buffers.

---

### A2 — Anomaly Detector & Safe Mode (`ai_engine/a2_anomaly/`)

Protects publisher accounts from abnormal spikes, policy violations, or invalid traffic penalties.

- **`MetricsBuffer` (`metrics.py`)**:
  Circular buffer maintaining rolling Welford online mean and standard deviation, alongside Exponentially-Weighted Moving Average (EWMA) with factor $\alpha=0.15$.
  Monitored metrics: `rpm`, `ctr`, `empty_ad_rate`, `load_time_ms`, `error_rate`, `repeated_creative_rate`.

- **`AnomalyDetector` (`detector.py`)**:
  1. **EWMA Z-score Check**: flags metric deviation $z = |x - \mu_{\text{ewma}}| / \sigma$. Triggers `WARNING` at $z \ge 2.5$, `CRITICAL` at $z \ge 3.75$.
  2. **Absolute Thresholds**:
     * CTR spike: $\text{CTR} \ge 0.045 \implies \text{CRITICAL}$.
     * RPM floor: $\text{RPM} < \$0.50 \implies \text{WARNING}$.
     * Empty ad rate: $\ge 40\% \implies \text{CRITICAL}$.
     * Load time: $> 8000\text{ms} \implies \text{WARNING}$.
     * Repeated creative: $\ge 60\% \implies \text{WARNING}$.
  3. **Isolation Forest**: optional unsupervised anomaly scoring via `sklearn.ensemble.IsolationForest`. Gracefully disabled when scikit-learn is uninstalled.

- **`AlertDispatcher` (`alerts.py`)**:
  Dispatches notifications to Telegram bot (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`), webhook endpoints, and logs. Includes a 5-minute deduplication window for repeated alerts.

- **`SafeModeStateMachine` (`safe_mode.py`)**:
  Autonomous operational circuit breaker:
  * Entered immediately upon any `CRITICAL` anomaly.
  * Click suppression: `is_active() == True` forces all ad decisions to `"skip"`.
  * Session rate throttling: multiplies scheduler rate by `throttle_session_rate` (0.3×).
  * State persisted to `state/ai_engine/safe_mode.json` to survive restarts.
  * Auto-exit requirement: requires $M=5$ consecutive clean monitoring windows before safely resuming normal operations.

---

### A4 — Visual Ad Detector (`ai_engine/a4_visual/`)

Detects ad placements and computes safe, human-like click coordinates.

- **`BoundingBox` & `DetectionResult` (`bbox.py`)**:
  * Represents bounding rectangle `(x, y, w, h)`, confidence score, label (`banner`, `interstitial`, `popunder`, `ad`, `none`), and network hint (`adsterra`, `propeller`, `hilltop`, `unknown`).
  * `random_click_point(seed)`: guarantees click coordinates land strictly within **[20%, 80%]** of box width and **[25%, 75%]** of box height, preventing edge misses and invalid touch telemetry.

- **`VisionModel` (`vision_model.py`)**:
  Lightweight ONNX Runtime inference engine. Operates within a hard time budget (default 300ms). If `onnxruntime` or model weights are unavailable, gracefully falls back to rules.

- **`RuleFallbackDetector` (`rule_fallback.py`)**:
  Parses ADB UIAutomator XML hierarchy dumps and accessibility node dicts. Evaluates resource IDs, classes, and text against network signatures (`adsterra`, `ad-`, `adv-`, `adunit`, `banner`), filtering out tiny widgets ($< 2000\text{px}^2$) or full-screen overlays ($> 60\%$).

- **`VisualAdDetector` (`detector.py`)**:
  Coordinates the vision model and rule detector with strict deadline enforcement.

---

## 3. Configuration Reference (`ai_engine_config.yaml`)

```yaml
ai_engine:
  paper_trading: false          # When true, decisions logged but NO touch executed
  log_level: INFO               # DEBUG | INFO | WARNING | ERROR
  state_dir: state/ai_engine    # Directory for weights, safe_mode.json, logs
  db_path: sessions.db          # SQLite database path

a1_linTS:
  alpha: 1.0                    # LinTS exploration coefficient
  lambda_reg: 1.0               # L2 regularization for precision matrix
  n_features: 8                 # Dimension of state feature vector
  domain_arms: []               # Dynamic publisher domain arms
  ad_slot_arms: [banner, interstitial, popunder, native, none]
  persist_every_n: 10           # Save model weights every N decisions
  reward_rpm_scale: 1000.0      # RPM divisor for reward normalization

ctr_guard:
  window_size: 200              # Number of events in rolling CTR window
  hard_cap: 0.045               # 4.5% CTR ceiling
  soft_cap: 0.036               # 3.6% CTR warning threshold
  defer_seconds: 30             # Cooldown period upon breach threat

a2_anomaly:
  ewma_alpha: 0.15              # EWMA smoothing factor
  z_threshold: 2.5              # Z-score anomaly threshold
  isolation_forest:
    enabled: true               # Enable unsupervised Isolation Forest
    contamination: 0.05
    n_estimators: 100
  safe_mode:
    exit_clean_windows: 5       # M consecutive clean windows to exit SAFE MODE
    window_seconds: 120         # Duration of each assessment window (seconds)
    pause_click_on_entry: true  # Suppress clicks immediately on entry
    throttle_session_rate: 0.3  # Fraction of normal session spawn rate (30%)
  metrics:
    - rpm
    - ctr
    - empty_ad_rate
    - load_time_ms
    - error_rate
    - repeated_creative_rate
  rpm_floor: 0.5                # Minimum acceptable RPM ($0.50)
  load_time_ceiling_ms: 8000    # Maximum acceptable load latency (8s)
  empty_ad_spike_rate: 0.4      # Max allowed empty ad fill fraction (40%)
  repeated_creative_threshold: 0.6 # Max allowed creative repetition (60%)
  alert:
    telegram_enabled: true      # Telegram Bot dispatch
    webhook_url: ""             # Optional HTTP POST JSON endpoint
    email_enabled: false

a4_visual:
  confidence_threshold: 0.55    # Minimum vision confidence before rule fallback
  inference_timeout_ms: 300     # Maximum total inference time budget
  model_path: state/ai_engine/ad_detector.onnx
  labels: [ad, banner, interstitial, popunder, none]
  ad_network_hints:
    adsterra: ["adsterra", "popunder", "araplhn"]
    propeller: ["propellerads", "propeller"]
    hilltop: ["hilltopads", "hilltop"]
  rule_fallback:
    enabled: true
    id_patterns: ["ad", "banner", "sponsor", "promoted"]
    class_patterns: ["ad-", "adv-", "adunit", "adsense", "adsterra"]
    min_area_px: 2000           # Minimum area filter
    max_area_ratio: 0.6         # Maximum area filter
```

---

## 4. Running Standalone Commands

Each module exposes a standalone CLI interface for isolated verification, diagnostics, and testing:

### 4.1 A1 LinTS Bandit Runner
Run a dry-run decision step, compute Bayesian arm selection, and update weights:
```bash
python -m ai_engine.a1_linTS.bandit --config ai_engine_config.yaml --dry-run
```
To test decision-making under paper-trading mode:
```bash
python -m ai_engine.a1_linTS.bandit --config ai_engine_config.yaml --paper
```

### 4.2 A2 Anomaly Detector
Evaluate point-in-time metrics against rolling EWMA and hard thresholds:
```bash
python -m ai_engine.a2_anomaly.detector --config ai_engine_config.yaml --rpm 1.5 --ctr 0.02
```
Test an anomalous CTR spike:
```bash
python -m ai_engine.a2_anomaly.detector --config ai_engine_config.yaml --rpm 0.8 --ctr 0.08
```

### 4.3 A4 Visual Ad Detector
Run visual ad detection over synthetic accessibility tree or screenshot frame:
```bash
python -m ai_engine.a4_visual.detector --config ai_engine_config.yaml
```

---

## 5. Running the Orchestrator

The orchestrator wires A4 Visual Detection $\to$ A2 Anomaly Detection $\to$ A1 LinTS Decision $\to$ Touch Execution $\to$ Reward Ingestion in an asynchronous loop.

### 5.1 Paper Trading Mode (Safe Verification)
Decisions are fully computed, logged to SQLite, and bandit weights updated, but **no physical or ADB touch events are executed**:
```bash
python -m ai_engine.orchestrator --config ai_engine_config.yaml --paper --steps 10
```

### 5.2 Normal Production Mode
Executes real touch actions via Phase 1 touch interface:
```bash
python -m ai_engine.orchestrator --config ai_engine_config.yaml --steps 100 --device emulator-5554
```

---

## 6. SAFE MODE Protocol

SAFE MODE is the automated circuit breaker defending network accounts from anomalies and bans.

### Entry Triggers
- Any anomaly evaluated with severity `CRITICAL`:
  - CTR $\ge 0.045$ (hard cap breach).
  * Empty ad response rate $\ge 40\%$.
  * EWMA z-score $\ge 3.75$ on any core metric.
  * Any unhandled module exception inside the orchestrator step.

### Actions While Active
1. **Ad Clicks Paused**: All decisions override to `action="skip"`.
2. **Session Throttling**: Session pace multiplied by `throttle_session_rate` (0.3×, reducing concurrency by 70%).
3. **Alert Fired**: Telegram and webhook notifications sent with root-cause diagnostic.
4. **State Persisted**: Written to `state/ai_engine/safe_mode.json`.

### Auto-Exit Criteria
- Clean window monitoring: Every window evaluated as clean (`is_clean=True`) increments `clean_window_count`.
- Automatic recovery: When $M=5$ (`exit_clean_windows`) consecutive clean windows are recorded, SAFE MODE automatically deactivates and normal clicking resumes.

---

## 7. Running Unit & Integration Tests

The test suite validates all mathematical invariants, edge cases, state transitions, and fallbacks:

```bash
python -m pytest tests/test_a2_anomaly.py tests/test_a4_visual.py tests/test_a1_bandit.py -v
```

### Test Coverage Summary:
- **`tests/test_a2_anomaly.py`**:
  * MetricsBuffer EWMA convergence and rolling Welford calculations.
  * Normal metrics baseline check (`ok=True, severity="OK"`).
  * CTR spike critical anomaly triggering (`severity="CRITICAL"`).
  * RPM floor breach warning triggering (`severity="WARNING"`).
  * SAFE MODE entry on CRITICAL anomaly (`is_active() == True`).
  * SAFE MODE auto-exit after $M=5$ clean ticks.
  * Graceful fallback when scikit-learn is absent.
  * AlertDispatcher 5-minute deduplication window.

- **`tests/test_a4_visual.py`**:
  * `BoundingBox.random_click_point()` boundary validation (strictly within [20%, 80%] width, [25%, 75%] height).
  * `RuleFallbackDetector` detecting banner nodes in UIAutomator accessibility tree dumps.
  * `RuleFallbackDetector` cleanly returning empty results on clean trees.
  * `VisualAdDetector` fallback when vision model weights are missing.
  * `VisualAdDetector` fallback when vision model times out ($> 300\text{ms}$).
  * `DetectionResult.best` returning highest-confidence non-none box.

- **`tests/test_a1_bandit.py`**:
  * `encode(AgentState)` deterministic `(8,)` float32 feature vector generation.
  * `CTRGuard`:
    - Zero impressions returning 0.0 CTR.
    - Accurate rolling CTR calculations across clicks and impressions.
    - `would_breach(hard_cap)` boundary detection.
    - `set_defer(seconds)` and `is_deferred()` state transitions.
  * `WeightStore` atomic save and load round-trip (identical matrices $\mathbf{A}$ and $\mathbf{b}$).
  * `LinTSBandit`:
    - `decide()` returns valid `AdDecision` actions (`click`, `skip`, `defer`, `paper_click`).
    - Defers on CTR guard breach.
    - Returns `paper_click` under paper trading mode.
    - `update()` modifies precision matrix $\mathbf{A}$ and vector $\mathbf{b}$.
    - Seed reproducibility across distinct instances.
