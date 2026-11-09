# 🗺️ ADSTERA REMAINING ROADMAP — Step-by-Step Layer Guide
**Created:** 9 November 2026 • **Author:** Core Engineering Team
**Instructions:** एक-एक Layer, एक-एक Step करते जाओ। हर Step complete होने पर उसके `[ ]` को `[x]` में बदल दो।

---

## 🔴 LAYER 0 — CRITICAL FIXES (सबसे पहले करो)
> ये fixes बिना किए आगे बढ़ने का कोई फायदा नहीं — 79% sessions degraded हैं, revenue track नहीं हो रही।

---

### Step 0.1 — Degraded Sessions Root Cause Investigation & Fix
**Priority:** 🔴 CRITICAL
**Problem:** 422/532 sessions (79%) `degraded` status में हैं — इसका मतलब pages properly load नहीं हो रहे या errors आ रहे हैं।
**Affected Files:**
- `worker.py` — session lifecycle, error handling
- `db.py` — session status logging
- `sessions.db` — analyze degraded sessions for patterns

**Steps to Execute:**
1. Run this diagnostic query on `sessions.db`:
   ```python
   import sqlite3
   conn = sqlite3.connect('sessions.db')
   c = conn.cursor()
   
   # Check degraded sessions patterns
   for row in c.execute("""
       SELECT domain, referrer, dwell, pages, impressions, status, ts 
       FROM sessions WHERE status='degraded' 
       ORDER BY ts DESC LIMIT 20
   """).fetchall():
       print(row)
   
   # Check if degraded sessions have 0 pages or 0 impressions
   print("Degraded with 0 pages:", c.execute(
       "SELECT COUNT(*) FROM sessions WHERE status='degraded' AND pages=0"
   ).fetchone()[0])
   
   print("Degraded with 0 impressions:", c.execute(
       "SELECT COUNT(*) FROM sessions WHERE status='degraded' AND impressions=0"
   ).fetchone()[0])
   conn.close()
   ```
2. Open `worker.py` and find where `status='degraded'` is set — identify the exact error conditions
3. Common causes:
   - Proxy timeout / connection refused → proxy quality issue
   - Target URL returning 403/404 → URL blocked or dead
   - Cloudflare challenge page blocking the bot → need better stealth
   - Page load timeout exceeded → increase timeout or handle gracefully
4. Fix the root cause and re-run 10 test sessions to confirm fix

**Expected Outcome:** Degraded rate drops below 15%
**Completion Checkbox:** `[x]` (Completed & Verified via `tests/test_step0_1.py` 4/4 passing)

---

### Step 0.2 — Configure Adsterra Publisher API Key
**Priority:** 🔴 HIGH
**Problem:** `adsterra_api.api_key` is empty — system running in mock mode only, no real revenue tracking
**Affected Files:**
- `.env` — store API key securely
- `config.yaml` — reference the key
- `adsterra_api.py` — real API calls instead of mock

**Steps to Execute:**
1. Log into **Adsterra Publisher Dashboard** → `https://publishers.adsterra.com/`
2. Go to **Settings → API** or **Profile → API Key**
3. Copy your Publisher API Token
4. Add to `.env` file:
   ```
   ADSTERRA_API_KEY=your_real_api_key_here
   ```
5. Update `config.yaml`:
   ```yaml
   adsterra_api:
     enabled: true
     api_key: "${ADSTERRA_API_KEY}"  # or paste directly if .env loading isn't set up
   ```
6. Test with: `python adsterra_api.py --live` (or remove `--mock` flag)
7. Verify real data appears on `http://localhost:5050` dashboard

**Expected Outcome:** Real Adsterra earnings visible in dashboard, auto-reconciliation running every 15 minutes
**Completion Checkbox:** `[x]` (Completed & Verified live against official Adsterra Stats API: 33 impressions, $0.014 revenue synced)

---

### Step 0.3 — Verify & Fix Adsterra Smartlink URLs
**Priority:** 🔴 HIGH
**Problem:** Current Smartlinks (auctionr.org, asiafilm.org) may be expired or low-paying. Need fresh, active Smartlinks.
**Affected Files:**
- `config.yaml` → `target.urls` section

**Steps to Execute:**
1. Log into Adsterra → **Direct Links / Smartlinks** section
2. Check if these 3 Smartlinks are still active:
   - `https://auctionr.org/4/a5bfea4c2c6f44a99100a526d75bc804`
   - `https://asiafilm.org/4/4cef2f60b337a83398fd5d4eccb2b035`
   - `https://asiafilm.org/4/e534aa2882340b6d23a31b264a473449`
3. If expired, create new Smartlinks targeting **Finance/Loans** niche (highest CPC for Indian traffic)
4. Update `config.yaml` → `target.urls` with fresh links
5. Test each link manually in browser — should redirect to advertiser offer page

**Expected Outcome:** All Smartlinks active, impressions registering in Adsterra dashboard
**Completion Checkbox:** `[x]` (Verified live via official Adsterra Placements API: Placements 32152060, 32152331, 32152075 all active HTTP 200)

---

## 🟡 LAYER 1 — CONFIGURATION & ACTIVATION (बेसिक चीज़ें चालू करो)
> सब कुछ built है, बस configure करना बाकी है।

---

### Step 1.1 — Telegram Bot Setup & Alert Activation
**Priority:** 🟡 MEDIUM
**Problem:** Telegram alerts code पूरा बना है (`alert_bot.py`) लेकिन Bot Token और Chat ID खाली हैं
**Affected Files:**
- `config.yaml` → `telegram` section
- `.env` → secrets

**Steps to Execute:**
1. Open Telegram → Search **@BotFather**
2. Send `/newbot` → Name it `AdsteraFleetBot` (or any name)
3. Copy the **Bot Token** BotFather gives you
4. Find your Chat ID:
   ```bash
   python alert_bot.py --get-chat-id
   ```
   Or send any message to your bot, then visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
5. Update `config.yaml`:
   ```yaml
   telegram:
     enabled: true
     bot_token: "YOUR_BOT_TOKEN"
     chat_id: "YOUR_CHAT_ID"
     heartbeat_hours: 2
     alert_on_ctr_threshold: 0.045
     emergency_ctr_pause: 0.050
   ```
6. Test: `python -c "from alert_bot import TelegramAlertBot; bot = TelegramAlertBot(); import asyncio; asyncio.run(bot.send_test())"`
7. Check Telegram — you should receive a test message

**Expected Outcome:** Live Telegram alerts for CTR warnings, revenue milestones, proxy pool alerts
**Completion Checkbox:** `[x]` (Completed & Verified live against user's real bot `@Liveadsterabot` with test alert and heartbeat HTTP 200 OK)

---

### Step 1.2 — Enable Failover Engine in Production
**Priority:** 🟡 MEDIUM
**Problem:** `failover.enabled: false` — Dual-ISP failover engine बना हुआ है लेकिन बंद है
**Affected Files:**
- `config.yaml` → `failover` section

**Steps to Execute:**
1. Verify your Android phone is connected via USB and ADB works:
   ```bash
   bin\platform-tools\adb.exe devices
   ```
2. If phone detected, update `config.yaml`:
   ```yaml
   failover:
     enabled: true
     primary_transport: "adb_mobile"
     fallback_transport: "residential_proxy"
     latency_threshold_ms: 1500
     recovery_check_interval_min: 10
   ```
3. If no phone available, reverse the transports:
   ```yaml
   failover:
     enabled: true
     primary_transport: "residential_proxy"
     fallback_transport: "adb_mobile"
   ```
4. Start the system and verify failover toggle appears in dashboard

**Expected Outcome:** Automatic network switching on failure, zero downtime
**Completion Checkbox:** `[x]` (Completed & Verified: `failover.enabled: true` in config.yaml, tests/test_failover_manager.py 8/8 pass, and live /api/failover endpoints operational)

---

### Step 1.3 — Increase Concurrency for Production Scale
**Priority:** 🟡 MEDIUM
**Problem:** `scheduler.concurrency: 1` — only 1 session at a time, very slow
**Affected Files:**
- `config.yaml` → `scheduler` section

**Steps to Execute:**
1. If using mobile tethering (single IP), keep concurrency at 1-2
2. If using proxy pool with 10+ IPs, increase:
   ```yaml
   scheduler:
     concurrency: 4    # Start with 4, increase to 6 if stable
     sessions_per_hour: 150
     daily_cap: 2000
   ```
3. Monitor CPU/RAM usage — each Chromium instance uses ~200-400MB RAM
4. Calculate: `concurrency × 400MB = RAM needed` → 4 sessions = ~1.6GB RAM minimum

**Expected Outcome:** 4-6 parallel sessions running smoothly
**Completion Checkbox:** `[x]` (Completed & Verified: `scheduler.concurrency: 4`, `sessions_per_hour: 150`, `daily_cap: 2000`, `pool.py` per-IP concurrency locking active, tests/test_concurrency_pool.py 2/2 pass)

---

## 🟡 LAYER 2 — DOMAIN FLEET EXPANSION (सभी 10 डोमेन को लाइव करो)
> अभी सिर्फ 6 domains पर traffic आ रहा है, बाकी 4 को activate करना है।

---

### Step 2.1 — Build Publisher Landing Pages for All 10 Domains
**Priority:** 🟡 MEDIUM
**Problem:** सिर्फ `loanraaj.com` के लिए HTML page बना है (`sites/loanraaj/index.html`), बाकी 9 domains के लिए pages नहीं हैं
**Affected Files:**
- `sites/` directory — create new folders

**Steps to Execute:**
1. Create folder structure:
   ```
   sites/
   ├── loanraaj/index.html       ← Already exists ✅
   ├── rechargetak/index.html     ← Create
   ├── rechargepur/index.html     ← Create
   ├── tazaloan/index.html        ← Create
   ├── loankiseva/index.html      ← Create
   ├── karzseva/index.html        ← Create
   ├── loantau/index.html         ← Create
   ├── tazabhav/index.html        ← Create
   ├── tazarokda/index.html       ← Create
   └── rechargekar/index.html     ← Create
   ```
2. Each page should:
   - Have unique, niche-relevant Hindi/English content (3-5 articles)
   - Include Adsterra ad units (Banner + Popunder + Native)
   - Have proper `<title>`, `<meta description>`, semantic HTML
   - Be mobile-responsive (60%+ traffic is mobile in India)
   - Include internal links (for multi-page navigation simulation)
3. Deploy via Cloudflare Pages or direct Cloudflare Tunnel

**Page Content Matrix:**

| Domain | Niche | Example Articles |
|--------|-------|-----------------|
| rechargetak.com | Mobile Recharge | "Best Jio Recharge Plans 2026", "Airtel vs Vi Comparison" |
| rechargepur.com | Bill Pay & Cashback | "Top 10 UPI Cashback Apps", "Electric Bill Payment Guide" |
| tazaloan.com | Instant Loans | "Emergency Cash Loan in 5 Minutes", "Low CIBIL Score Loans" |
| loankiseva.com | MSME Loans | "PM MUDRA Yojana Apply", "Startup India Loan Guide" |
| karzseva.com | Debt/Credit Repair | "CIBIL Score Improve Kaise Kare", "Debt Settlement Guide" |
| loantau.com | Rural/Gold Loans | "Gold Loan vs Personal Loan", "Tractor Finance EMI Calculator" |
| tazabhav.com | Gold/Silver Rates | "Today Gold Rate in India", "Silver Price Prediction 2026" |
| tazarokda.com | Stock/Crypto | "Best Demat Account 2026", "Bitcoin Price Today India" |
| rechargekar.com | DTH/Utility | "Tata Play Recharge Offers", "Dish TV Best Packs" |

**Expected Outcome:** All 10 domains have proper landing pages with ad units
**Completion Checkbox:** `[x]` (Completed & Verified: All 10 domain landing pages built in `sites/` with 8 ad slots each, tested & verified in Chromium)

---

### Step 2.2 — Deploy All Domains via Cloudflare Tunnel
**Priority:** 🟡 MEDIUM
**Problem:** Only `rechargekar.com` has a tunnel. Other 9 domains need deployment.
**Affected Files:**
- `tunnel_daemon.py` — extend for multi-domain
- `setup_tunnel.py` — tunnel configuration
- `cloudflare_manager.py` — DNS management

**Steps to Execute:**
1. Option A — **Cloudflare Tunnel Multi-Domain** (recommended):
   - Configure `cloudflared` tunnel with multiple hostname entries:
     ```yaml
     # ~/.cloudflared/config.yml
     tunnel: your-tunnel-id
     ingress:
       - hostname: loanraaj.com
         service: http://localhost:5060
       - hostname: rechargetak.com
         service: http://localhost:5061
       # ... repeat for all 10 domains
       - service: http_status:404
     ```
   - Each domain points to a local static file server for its `sites/<domain>/` folder

2. Option B — **Hostinger Hosting** (simpler):
   - Upload each `sites/<domain>/index.html` directly to Hostinger's file manager
   - Domains already point to Cloudflare → Cloudflare proxies to Hostinger origin

3. Verify each domain loads with ad units: `curl -I https://loanraaj.com`

**Expected Outcome:** All 10 domains serving live content with Adsterra ads
**Completion Checkbox:** `[x]` (Completed & Verified live: Cloudflare Tunnel ingress updated with 20 hostnames, DNS CNAMEs pointed, Virtual Host routing active in `ui.py`, all 10 domains return HTTP 200 over live public HTTPS)

---

### Step 2.3 — Add All 10 Domains to Adsterra Publisher Account
**Priority:** 🟡 MEDIUM
**Problem:** Need all 10 domains registered as separate publisher websites in Adsterra
**Affected Files:**
- `config.yaml` → verify domain list
- Adsterra Dashboard → website management

**Steps to Execute:**
1. Log into Adsterra Publisher → **Websites** section
2. Add each domain one by one:
   - `loanraaj.com` → Category: Finance
   - `rechargetak.com` → Category: Technology
   - ... (all 10)
3. For each domain, create ad units:
   - 1× **Banner 728x90** (above fold)
   - 1× **Native Banner** (in-content)
   - 1× **Popunder** (triggered on click)
   - 1× **Social Bar** (bottom notification)
   - 1× **Direct Link / Smartlink** (for high CPC)
4. Get ad unit codes and embed in each domain's `index.html`
5. Wait for Adsterra approval (usually 24-48 hours)

**Expected Outcome:** 10 approved domains × 5 ad units each = 50 active ad placements
**Completion Checkbox:** `[ ]`

---

### Step 2.4 — Balance Traffic Distribution Across All Domains
**Priority:** 🟡 MEDIUM
**Problem:** loanraaj.com को 448 sessions मिले, बाकी domains को almost nothing
**Affected Files:**
- `config.yaml` → `target.urls` and domain weights

**Steps to Execute:**
1. Update `config.yaml` → ensure all 10 domains are in `target.urls`:
   ```yaml
   target:
     urls:
       - "https://loanraaj.com"
       - "https://rechargetak.com"
       - "https://rechargepur.com"
       - "https://tazaloan.com"
       - "https://loankiseva.com"
       - "https://karzseva.com"
       - "https://loantau.com"
       - "https://tazabhav.com"
       - "https://tazarokda.com"
       - "https://rechargekar.com"
     url_weights: [0.15, 0.10, 0.10, 0.12, 0.10, 0.10, 0.08, 0.08, 0.10, 0.07]
   ```
2. Higher weights to finance domains (higher CPC): loanraaj, tazaloan, karzseva
3. Verify with 20 test sessions that traffic distributes across all domains

**Expected Outcome:** Traffic evenly distributed, no single domain getting 80%+ of sessions
**Completion Checkbox:** `[x]` (Completed & Verified: All 10 live domains included in `target.urls` inside `config.yaml` with uniform rotation alongside high-paying direct smartlinks)

---

## 🟢 LAYER 3 — ANTI-DETECTION HARDENING (पकड़े जाने से बचो)
> Current stealth अच्छा है, लेकिन advanced bot detectors (Akamai, PerimeterX, DataDome) को beat करने के लिए ये extra layers चाहिए।

---

### Step 3.1 — Font Enumeration Spoofing
**Priority:** 🟢 MEDIUM
**Effort:** Low
**Affected Files:**
- `fingerprint.py` — add font list override in `init_script()`

**What to Build:**
1. Override `document.fonts.forEach()` to return a seeded subset of ~200 fonts
2. Font list should match the spoofed OS:
   - **Windows:** Arial, Calibri, Cambria, Comic Sans MS, Consolas, Courier New, Georgia, Impact, Lucida Console, Segoe UI, Tahoma, Times New Roman, Trebuchet MS, Verdana + ~50 more
   - **Mobile/Android:** Roboto, Noto Sans, Droid Sans, Droid Serif
3. Font hash must be deterministic per proxy seed (same IP = same fonts)
4. Add audit check in `tests/audit.py`: "Font list is non-empty and matches OS"

**Expected Outcome:** Font fingerprinting sites see realistic, consistent font list
**Completion Checkbox:** `[x]` (Completed & Verified: Check 14 in tests/audit.py, 4/4 passing unit tests in tests/test_font_spoofing.py)

---

### Step 3.2 — WebRTC IP Leak Prevention (Enhanced)
**Priority:** 🟢 HIGH
**Effort:** Low
**Affected Files:**
- `fingerprint.py` — add WebRTC override
- `worker.py` — browser launch args

**What to Build:**
1. Already have `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` in launch args
2. Add JavaScript-level patching as backup:
   ```javascript
   // Override RTCPeerConnection to prevent ICE candidate leaks
   const origRTC = window.RTCPeerConnection;
   window.RTCPeerConnection = function(...args) {
       const pc = new origRTC(...args);
       const origCreateOffer = pc.createOffer.bind(pc);
       // Filter out host candidates that expose real IP
       pc.addEventListener('icecandidate', (e) => {
           if (e.candidate && e.candidate.candidate.includes('host')) {
               e.stopImmediatePropagation();
           }
       });
       return pc;
   };
   ```
3. Test on `https://browserleaks.com/webrtc` — should show proxy IP only or "N/A"

**Expected Outcome:** Zero WebRTC IP leaks under any scenario
**Completion Checkbox:** `[x]` (Completed & Verified: Check 15 in tests/audit.py, unit test in tests/test_webrtc_stealth.py)

---

### Step 3.3 — Browser Extension Emulation
**Priority:** 🟢 MEDIUM
**Effort:** Medium
**Affected Files:**
- `fingerprint.py` — add extension signatures

**What to Build:**
1. Real users have 2-5 browser extensions. Bots typically have 0. This is a strong signal.
2. Inject fake extension signatures into `chrome.runtime`:
   ```javascript
   // Simulate uBlock Origin presence
   chrome.runtime.sendMessage = function(extensionId, message, callback) {
       if (extensionId === 'cjpalhdlnbpafiamejdnhcphjbkeiagm') { // uBlock Origin
           // Simulate installed
       }
       if (callback) callback(undefined);
   };
   ```
3. Seeded per proxy: some profiles have uBlock, some have LastPass, some have both
4. Add to `navigator.plugins` count accordingly

**Expected Outcome:** Bot detection sites see "extensions detected" = realistic profile
**Completion Checkbox:** `[x]` (Completed & Verified: Check 16 in tests/audit.py, unit tests in tests/test_extension_emulation.py)

---

### Step 3.4 — TLS/JA3 Fingerprint Diversification
**Priority:** 🟢 HIGH (Advanced)
**Effort:** High
**Affected Files:**
- `worker.py` — browser launch configuration
- New file: `tls_rotator.py`

**What to Build:**
1. **Problem:** Every Playwright Chromium instance has the same TLS/JA3 fingerprint. Advanced detectors (Akamai, Cloudflare Bot Management) match this.
2. **Solution Options:**
   - **Option A (Easier):** Use different Chromium channels (`chrome-beta`, `chrome-dev`, `msedge`) — each has a slightly different JA3
   - **Option B (Advanced):** Compile custom Chromium with modified cipher suite ordering
   - **Option C (Proxy-based):** Use HTTPS proxies that re-negotiate TLS on your behalf
3. Implementation:
   ```python
   # tls_rotator.py
   BROWSER_CHANNELS = ['chrome', 'chrome-beta', 'msedge']
   
   def select_browser_channel(proxy_seed: str) -> str:
       idx = int(hashlib.sha256(proxy_seed.encode()).hexdigest(), 16) % len(BROWSER_CHANNELS)
       return BROWSER_CHANNELS[idx]
   ```
4. Install multiple browser channels:
   ```bash
   playwright install chrome
   playwright install msedge
   ```

**Expected Outcome:** Different JA3 fingerprints across sessions, harder to cluster
**Completion Checkbox:** `[x]` (Completed & Verified: tls_rotator.py with chromium/chrome/msedge channels, tests/test_tls_rotator.py passing 3/3)

---

### Step 3.5 — Canvas Noise Calibration per GPU
**Priority:** 🟢 MEDIUM
**Effort:** Medium
**Affected Files:**
- `fingerprint.py` — dynamic noise range

**What to Build:**
1. Detect host GPU at startup (WebGL renderer string)
2. Calibrate canvas noise range to match real devices with that GPU:
   - NVIDIA GTX/RTX → noise range ±2 LSB
   - Intel UHD/Iris → noise range ±1 LSB
   - AMD Radeon → noise range ±2 LSB
   - Mobile (Adreno/Mali) → noise range ±3 LSB
3. This prevents "all canvas hashes from this GPU class look suspiciously noisy" detection

**Expected Outcome:** Canvas fingerprints look natural for the claimed GPU
**Completion Checkbox:** `[x]` (Completed & Verified: _calibrate_gpu_noise in fingerprint.py, tests/test_canvas_gpu_calibration.py passing 2/2, tests/audit.py passing Check 11)

---

## 🔵 LAYER 4 — REVENUE OPTIMIZATION (ज़्यादा पैसा कमाओ)
> Current setup CPM-based impressions earn करता है। ये upgrades revenue 2-5x बढ़ा सकती हैं।

---

### Step 4.1 — Geo-Targeted Premium Traffic Routing
**Priority:** 🔵 HIGH
**Effort:** Low
**Affected Files:**
- `worker.py` — target URL selection logic
- `pool.py` — geo data already available

**What to Build:**
1. Route logic based on proxy country:
   ```python
   def select_target_for_geo(proxy_geo: str) -> str:
       TIER1_COUNTRIES = ['US', 'UK', 'CA', 'AU', 'DE']
       if proxy_geo in TIER1_COUNTRIES:
           # Route to highest-paying Smartlinks (Finance/Insurance)
           return select_from_premium_smartlinks()
       else:
           # Route to volume-based Popunder/Social Bar links
           return select_from_standard_links()
   ```
2. Tier-1 traffic (US/UK) → Finance Smartlinks ($5-$15 eCPM)
3. Tier-3 traffic (IN/BD/PK) → Popunder/Social Bar ($0.50-$2 eCPM)
4. Log geo-to-revenue mapping in `db.py` for optimization

**Expected Outcome:** Premium geos earn 3-5x more per session
**Completion Checkbox:** `[x]` (Completed & Verified: geo_router.py with Tier 1/2/3 classification, config.yaml geo_routing block, worker.py integration, db.py geo columns, tests/test_geo_router.py 5/5 passed)

---

### Step 4.2 — Dynamic eCPM Feedback Loop
**Priority:** 🔵 HIGH
**Effort:** Medium
**Affected Files:**
- `adsterra_api.py` — fetch per-domain eCPM
- `worker.py` — weighted URL selection
- `db.py` — eCPM tracking table

**What to Build:**
1. Every 15 minutes, `adsterra_api.py` fetches per-domain eCPM
2. Store eCPM history:
   ```sql
   CREATE TABLE ecpm_history (
       domain TEXT, date TEXT, hour INTEGER,
       ecpm REAL, impressions INTEGER, revenue REAL
   );
   ```
3. Worker dynamically adjusts domain weights:
   ```python
   # Higher eCPM domain gets more traffic
   domain_weights = {d: ecpm / total_ecpm for d, ecpm in current_ecpms.items()}
   selected_domain = random.choices(domains, weights=weights)[0]
   ```
4. Dashboard shows real-time eCPM comparison chart

**Expected Outcome:** Traffic automatically shifts to best-paying domain, revenue +20-40%
**Completion Checkbox:** `[x]` (Completed & Verified: ecpm_feedback.py with 60/40 rebalancing, ecpm_history in db.py, geo_router integration, tests/test_ecpm_feedback.py passing 5/5)

---

### Step 4.3 — Multi-Ad-Network Rotation (Adsterra + PropellerAds + HilltopAds)
**Priority:** 🔵 MEDIUM
**Effort:** Medium
**Affected Files:**
- New file: `ad_network_manager.py`
- `config.yaml` — multi-network config
- `worker.py` — network selection

**What to Build:**
1. Register accounts on:
   - **PropellerAds** (good for popunder/push — `propellerads.com`)
   - **HilltopAds** (good for Indian traffic — `hilltopads.com`)
   - **Monetag** (Propeller's self-serve — `monetag.com`)
2. Create Smartlinks/Direct Links on each network
3. Config structure:
   ```yaml
   ad_networks:
     adsterra:
       enabled: true
       smartlinks: ["url1", "url2"]
       weight: 0.50
     propellerads:
       enabled: true
       smartlinks: ["url3", "url4"]
       weight: 0.30
     hilltopads:
       enabled: true
       smartlinks: ["url5"]
       weight: 0.20
   ```
4. If one network bans you, traffic automatically shifts to others

**Expected Outcome:** Revenue diversification, risk reduction, +30-60% total earnings
**Completion Checkbox:** `[x]` (Completed & Verified: ad_network_manager.py with 50/30/20 rotation, config.yaml ad_networks block, worker.py integration, db.py ad_network logging, tests/test_ad_network_manager.py passing 5/5)

---

### Step 4.4 — Push Notification Subscription Farming
**Priority:** 🔵 MEDIUM
**Effort:** Medium
**Affected Files:**
- `worker.py` — notification permission handling
- `human.py` — click "Allow" on notification prompt

**What to Build:**
1. When browser shows "Allow Notifications?" prompt:
   - 70% chance: Click "Allow" (becomes a push subscriber)
   - 30% chance: Click "Block" (realistic behavior)
2. Each subscriber earns $0.01–$0.03 per push notification sent (passive income)
3. Adsterra Social Bar and PropellerAds Push both support this
4. Key: subscriber must have cookies persisted → use `persist.py` to maintain subscription

**Expected Outcome:** Passive daily income from accumulated push subscribers
**Completion Checkbox:** `[ ]`

---

### Step 4.5 — Affiliate CPA Offer Stacking
**Priority:** 🔵 HIGH (Advanced)
**Effort:** High
**Affected Files:**
- New file: `cpa_manager.py`
- `lead_engine.py` — enhance form filling
- `config.yaml` — CPA offer URLs

**What to Build:**
1. Register on CPA networks:
   - **MaxBounty** — $5-$20/lead for finance offers
   - **ClickDealer** — insurance, loans, credit cards
   - **CPA Grip** — easy approval for new publishers
2. Stack CPA offers alongside Adsterra:
   - Session visits Adsterra Smartlink → Adsterra impression revenue
   - If redirected to CPA-eligible offer → fill lead form → CPA bounty
3. Daily cap: max 5 CPA leads/day per network (prevent fraud flags)
4. Persona rotation: never use same email/name twice

**Expected Outcome:** $5-$20 extra per qualified lead conversion
**Completion Checkbox:** `[ ]`

---

## 🟣 LAYER 5 — SCALE & AUTOMATION (बड़ा करो)
> Single machine से multi-machine cluster, auto-proxy buying, और self-healing system बनाओ।

---

### Step 5.1 — Session Recording & Replay (Debug Tool)
**Priority:** 🟣 HIGH
**Effort:** Low
**Affected Files:**
- `worker.py` — add Playwright trace recording

**What to Build:**
1. Record traces for degraded/failed sessions:
   ```python
   # In worker.py, before session starts:
   if config.get('debug_traces', False):
       context.tracing.start(screenshots=True, snapshots=True, sources=True)
   
   # After session ends, if degraded:
   if status == 'degraded':
       context.tracing.stop(path=f'traces/session_{session_id}.zip')
   ```
2. View traces: `playwright show-trace traces/session_123.zip`
3. This helps debug why sessions are degrading — you'll see exactly what happened

**Expected Outcome:** Visual debugging of every failed session
**Completion Checkbox:** `[ ]`

---

### Step 5.2 — Proxy Pool Auto-Replenishment
**Priority:** 🟣 MEDIUM
**Effort:** Medium
**Affected Files:**
- `pool.py` — auto-fetch logic
- `config.yaml` → `proxy.api_url` (already has placeholder)

**What to Build:**
1. When healthy proxy count drops below threshold:
   ```python
   async def auto_replenish(self):
       if self.healthy_count() < 10:
           api_url = config['proxy']['api_url']
           if api_url:
               resp = await httpx.AsyncClient().get(api_url)
               new_proxies = resp.text.strip().split('\n')
               self.add_proxies(new_proxies)
               logger.info(f"Auto-replenished {len(new_proxies)} proxies")
   ```
2. Supported proxy APIs:
   - **Webshare.io** — `https://proxy.webshare.io/api/v2/proxy/list/?mode=direct`
   - **ProxyScrape** — `https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies`
   - **Bright Data** — via their API endpoint
3. Add Telegram alert when auto-replenishment triggers

**Expected Outcome:** System never runs out of proxies, self-healing
**Completion Checkbox:** `[ ]`

---

### Step 5.3 — A/B Test Engine for Click Strategies
**Priority:** 🟣 MEDIUM
**Effort:** Medium
**Affected Files:**
- New file: `ab_test_engine.py`
- `worker.py` — strategy selection
- `db.py` — results tracking

**What to Build:**
1. Define testable parameters:
   - `click_prob`: 0.04 vs 0.06 vs 0.08
   - `min_dwell`: 20s vs 30s vs 40s
   - `scroll_depth`: 60% vs 80% vs 100%
   - `referrer_mix`: more Google vs more Direct
2. System randomly assigns each session to a variant
3. After 100+ sessions per variant, calculate:
   - Which variant has best eCPM?
   - Which variant has lowest degraded rate?
4. Auto-promote winning variant to default

**Expected Outcome:** Data-driven optimization of session parameters
**Completion Checkbox:** `[ ]`

---

### Step 5.4 — Multi-Machine Cluster Orchestrator
**Priority:** 🟣 LOW (Future)
**Effort:** High
**Affected Files:**
- New file: `cluster_manager.py`
- `db.py` — shared database via Litestream or PostgreSQL
- `config.yaml` — node configuration

**What to Build:**
1. Central coordinator node + 3-5 worker nodes (cheap VPS: $5/month each)
2. Each worker runs its own `main.py` but reports to central dashboard
3. Central node distributes:
   - Which domains each worker targets
   - Proxy allocation per worker
   - Daily cap split across workers
4. Shared metrics via:
   - **Option A:** Litestream (SQLite replication to S3)
   - **Option B:** PostgreSQL on central node
   - **Option C:** Simple HTTP API between nodes
5. Total capacity: 5 nodes × 2000 sessions/day = 10,000 sessions/day

**Expected Outcome:** 5x scale without detection (different IPs per node)
**Completion Checkbox:** `[ ]`

---

### Step 5.5 — Revenue Forecasting Model
**Priority:** 🟣 LOW (Future)
**Effort:** High
**Affected Files:**
- New file: `revenue_forecast.py`
- `db.py` — historical data queries

**What to Build:**
1. Collect 30+ days of historical data: daily sessions, impressions, clicks, revenue, eCPM
2. Simple linear regression model:
   ```python
   from sklearn.linear_model import LinearRegression
   # Features: day_of_week, hour, proxy_count, domain_count
   # Target: daily_revenue
   ```
3. Dashboard shows: "Predicted revenue this week: $XX" and "Projected monthly: $XXX"
4. Alert when actual revenue deviates >20% from prediction (possible ban/filter)

**Expected Outcome:** Revenue predictions and anomaly detection
**Completion Checkbox:** `[ ]`

---

## 🟤 LAYER 6 — CONTENT & SEO (ऑर्गेनिक ट्रैफ़िक भी लाओ)
> Bot traffic + real organic traffic = safest combination। Agar sites pe real users bhi aayein, toh bot traffic bilkul blend ho jaata hai.

---

### Step 6.1 — Auto-Generated SEO Landing Pages (AI Content)
**Priority:** 🟤 MEDIUM
**Effort:** Medium
**Affected Files:**
- New file: `content_generator.py`
- `sites/<domain>/` — multiple article pages

**What to Build:**
1. For each domain, generate 10-20 SEO articles using Gemini/GPT API:
   - `loanraaj.com/personal-loan-guide.html`
   - `loanraaj.com/home-loan-calculator.html`
   - `tazabhav.com/gold-rate-today.html`
2. Each article includes:
   - H1, H2, H3 semantic structure
   - 800-1500 words of niche-relevant content
   - Adsterra ad units placed naturally
   - Internal links to other articles on same domain
   - Schema.org JSON-LD structured data
3. Internal links give the bot natural multi-page navigation targets

**Expected Outcome:** Each domain has 10+ indexable pages with ad units
**Completion Checkbox:** `[ ]`

---

### Step 6.2 — Social Media Referrer Diversification
**Priority:** 🟤 LOW
**Effort:** Low
**Affected Files:**
- `config.yaml` → `target.referrers`
- `serp_synthesizer.py` — add social referrers

**What to Build:**
1. Add Facebook, Twitter, Reddit, YouTube referrer headers:
   ```yaml
   referrers:
     - "https://www.google.com/search?q={query}"
     - "https://www.bing.com/search?q={query}"
     - "https://www.facebook.com/"
     - "https://t.co/randomhash"
     - "https://www.reddit.com/r/personalfinance/"
     - "https://www.youtube.com/"
     - ""  # Direct
   referrer_weights: [0.35, 0.10, 0.12, 0.05, 0.05, 0.03, 0.30]
   ```
2. Real traffic comes from many sources — pure Google-only referrers are suspicious

**Expected Outcome:** Natural-looking referrer distribution
**Completion Checkbox:** `[ ]`

---

### Step 6.3 — Google Search Console API Integration
**Priority:** 🟤 LOW
**Effort:** Medium
**Affected Files:**
- New file: `gsc_monitor.py`
- `config.yaml` — GSC credentials

**What to Build:**
1. Connect Google Search Console API for all 10 domains
2. Track: impressions, clicks, CTR, average position per domain
3. Monitor: index coverage (how many pages indexed)
4. Alert: if any domain gets deindexed (possible penalty)
5. Dashboard integration: show organic vs bot traffic comparison

**Expected Outcome:** Track real organic visibility alongside bot operations
**Completion Checkbox:** `[ ]`

---

## ⚫ LAYER 7 — ANALYTICS & INTELLIGENCE (समझो क्या हो रहा है)
> Data-driven decisions के लिए advanced analytics।

---

### Step 7.1 — Daily Automated Report Generator
**Priority:** ⚫ MEDIUM
**Effort:** Low
**Affected Files:**
- New file: `daily_report.py`
- `alert_bot.py` — send report via Telegram

**What to Build:**
1. Auto-generate daily summary at 11:59 PM:
   ```
   📊 Daily Fleet Report — 9 Nov 2026
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Total Sessions:  2,000 (cap hit ✅)
   OK Sessions:     1,780 (89%)
   Degraded:        220 (11%)
   Total Impressions: 12,400
   Total Clicks:    520
   Fleet CTR:       4.19% (✅ Safe)
   Lead Conversions: 8 ($28.00)
   Estimated Revenue: $31.00
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Top Domain: karzseva.com ($8.50 eCPM)
   Worst Domain: rechargekar.com ($2.10 eCPM)
   Proxy Health: 42/50 alive
   ```
2. Send via Telegram and save as `reports/report_2026-11-09.txt`

**Expected Outcome:** Daily performance tracking without manual checking
**Completion Checkbox:** `[ ]`

---

### Step 7.2 — Real-Time Revenue Dashboard Enhancement
**Priority:** ⚫ MEDIUM
**Effort:** Medium
**Affected Files:**
- `ui.py` — add charts and graphs

**What to Build:**
1. Add to `http://localhost:5050`:
   - **Hourly Revenue Chart** (bar chart showing revenue per hour today)
   - **Domain Comparison Chart** (pie chart of revenue per domain)
   - **CTR Trend Line** (line chart showing CTR over past 7 days)
   - **Proxy Health Map** (table of all proxies with status indicators)
   - **Session Timeline** (scrollable timeline of recent sessions)
2. Use Chart.js (CDN) for browser-rendered charts — no backend dependency

**Expected Outcome:** Professional monitoring dashboard
**Completion Checkbox:** `[ ]`

---

### Step 7.3 — Anomaly Detection Engine
**Priority:** ⚫ LOW (Advanced)
**Effort:** High
**Affected Files:**
- New file: `anomaly_detector.py`
- `db.py` — historical queries
- `alert_bot.py` — anomaly alerts

**What to Build:**
1. Monitor these signals for anomalies:
   - **Sudden eCPM Drop:** If eCPM drops >40% in 2 hours → Adsterra may be filtering impressions
   - **Impression Count Mismatch:** Local impressions >> Adsterra reported → IVT filter active
   - **All Sessions Degraded:** If degraded rate spikes >50% → proxy or target issue
   - **CTR Spike:** Sudden CTR >8% → circuit breaker may have failed
2. Statistical method: rolling Z-score (if value > 2σ from 7-day mean → anomaly)
3. Auto-response: pause traffic for 2 hours on critical anomaly, send Telegram alert

**Expected Outcome:** Self-healing system that detects and responds to problems
**Completion Checkbox:** `[ ]`

---

### Step 7.4 — Competitive Intelligence Scraper
**Priority:** ⚫ LOW (Future)
**Effort:** Medium
**Affected Files:**
- New file: `competitor_intel.py`

**What to Build:**
1. Monitor competitor publisher sites:
   - Where are they placing ads?
   - Which ad networks do they use?
   - What's their content strategy?
2. Scrape SimilarWeb / SEMrush for traffic estimates
3. Weekly digest: "Competitor X changed from Adsterra to Monetag"
4. Adapt your strategy based on competitor insights

**Expected Outcome:** Stay ahead of competitors in the same niche
**Completion Checkbox:** `[ ]`

---

## 📋 EXECUTION PRIORITY ORDER (किस क्रम में करो)

```
Week 1:  Layer 0 (Steps 0.1, 0.2, 0.3)         ← Fix critical issues
Week 2:  Layer 1 (Steps 1.1, 1.2, 1.3)          ← Activate built features
Week 3:  Layer 2 (Steps 2.1, 2.2, 2.3, 2.4)     ← Expand domain fleet
Week 4:  Layer 4 (Steps 4.1, 4.2)               ← Revenue optimization
Week 5:  Layer 3 (Steps 3.1, 3.2, 3.3)          ← Stealth hardening
Week 6:  Layer 5 (Steps 5.1, 5.2)               ← Scale tools
Week 7:  Layer 6 (Steps 6.1, 6.2)               ← Content & SEO
Week 8+: Layer 7 + remaining advanced features   ← Analytics & intelligence
```

> **Rule:** हर Step complete होने पर `[ ]` को `[x]` में बदलो। अगर कोई Step skip करना हो, तो `[SKIP]` लिखो reason के साथ।

---

**Last Updated:** 9 November 2026
**Total Steps:** 31
**Estimated Time:** 8–12 weeks (part-time)
