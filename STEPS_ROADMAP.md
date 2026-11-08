# Browser Automation & Realism Enhancement Roadmap

This document outlines the systematic engineering upgrades for the Chromium automation suite. Each phase is designed to ensure maximum realism, browser coherence, and behavioral plausibility for developer load testing and QA environments.

---

## Phase 1: Client Hints Synchronization (`navigator.userAgentData`)
- **Objective:** Prevent discrepancies between the legacy `navigator.userAgent` string and modern Chromium Client Hints.
- **Key Tasks:**
  - Mock `navigator.userAgentData.brands` matching the selected Chrome / Edge major version.
  - Implement `getHighEntropyValues(["architecture", "model", "platformVersion", "fullVersionList", "bitness"])`.
  - Dynamically align mobile model names (e.g. `SM-S928B`, `Pixel 8`) with Client Hints `model` attribute.
  - Set `mobile: true/false` consistently across both layers.

---

## Phase 2: Canvas & WebGL Pixel Buffer Consistency
- **Objective:** Ensure 2D Canvas and WebGL buffer reads match the deterministic fingerprint seed.
- **Key Tasks:**
  - Patch `CanvasRenderingContext2D.prototype.getImageData` with deterministic micro-jitter derived from the proxy/session seed.
  - Patch `WebGLRenderingContext.prototype.readPixels` and `WebGL2RenderingContext.prototype.readPixels`.
  - Maintain pixel data integrity across multiple reads within the same session.

---

## Phase 3: Hardware Peripherals & Power API Simulation
- **Objective:** Eliminate empty hardware signatures typical of default headless environments.
- **Key Tasks:**
  - Implement mock `navigator.mediaDevices.enumerateDevices()` returning realistic audio input and video input hardware descriptors.
  - Implement mock `navigator.getBattery()` for mobile device profiles (realistic battery levels between 55%–95%, realistic charging states).
  - Ensure hardware concurrency and device memory values correspond strictly to real consumer devices.

---

## Phase 4: Ergonomic Pre-Click Settlement & Micro-Tremors
- **Objective:** Simulate real human neuromuscular reaction latency and micro-motion before interaction.
- **Key Tasks:**
  - Add pre-click hover dwell of 120ms–240ms after moving to the target bounding box.
  - Implement 1–2 pixel natural micro-tremor jitter during hover pause.
  - Randomize click point distribution (20%–80% width, 25%–75% height) across interactive targets.

---

## Phase 5: Multi-Target URL Distribution Pool
- **Objective:** Distribute sessions across multiple target URLs and internal articles rather than a single static link.
- **Key Tasks:**
  - Update `config.yaml` to support a pool of target URLs with optional weights.
  - Update dashboard UI to allow adding, editing, and managing multiple target URLs.
  - Distribute incoming sessions probabilistically across the pool to avoid unnatural single-page clustering.

---

## Phase 6: Hybrid Keyboard & Scroll Interaction
- **Objective:** Replicate authentic navigation methods used by real visitors.
- **Key Tasks:**
  - Introduce keyboard navigation events (Spacebar, PageDown, ArrowDown) for 20%–30% of scroll cycles.
  - Add realistic keydown/keyup timing delays (60ms–140ms).
  - Combine keyboard scrolling with mouse wheel scrolling throughout the session dwell.

---

## Implementation Progress Tracker

| Phase | Description | Status | Target File |
|---|---|---|---|
| **Phase 1** | Client Hints (`navigator.userAgentData`) | Completed (Verified) | `fingerprint.py` |
| **Phase 2** | Canvas & WebGL Buffer Jitter (`getImageData`) | Planned | `fingerprint.py` |
| **Phase 3** | Hardware APIs & Battery Simulation | Planned | `fingerprint.py` |
| **Phase 4** | Pre-Click Settle & Micro-Tremors | Planned | `human.py` |
| **Phase 5** | Multi-URL Distribution Pool | Planned | `config.yaml`, `ui.py` |
| **Phase 6** | Keyboard Scroll & Tab Navigation | Planned | `human.py` |
