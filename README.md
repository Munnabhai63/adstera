# Adsterra QA Traffic Harness

A Playwright-based QA test harness that opens pages in Chromium through authenticated
HTTP proxies, sets a consistent viewport/locale/timezone per proxy, simulates human-like
scrolling and mouse movement with randomised dwell times, and writes each run to a SQLite
log. Designed to validate ad impression and click tracking on publisher sites.

---

## Requirements

- Python 3.11+
- Windows 10/11 or Linux (xvfb required for headless Linux)
- Chromium (installed automatically by Playwright)

---

## Install

```bash
cd f:\UserData\Downloads\adstera

# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# or: source .venv/bin/activate   # Linux/macOS

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Chromium
playwright install chromium
```

---

## Configure

Edit **`config.yaml`** before running:

```yaml
target:
  url: "https://your-publisher-site.com/article"   # ← change this
  min_dwell: 25        # minimum seconds per session
  max_dwell: 110       # maximum seconds per session

proxy:
  file: proxies.txt    # path to proxy list

scheduler:
  concurrency: 6       # parallel sessions
  sessions_per_hour: 150
  daily_cap: 2000      # hard stop per day
```

Edit **`proxies.txt`** with your real proxy credentials:

```
# Format: [user:pass@]host:port
user1:pass1@gw.yourprovider.com:8000
user2:pass2@mobile.yourprovider.com:9000
```

> **Important**: Use residential or mobile proxies only. Datacenter IPs
> (DigitalOcean, AWS, GCP, Hetzner, etc.) are automatically rejected.

---

## Run

### Localhost Web Dashboard (GUI Control Center)

Launch the interactive local control center to update target URLs, configure proxies, start/stop live runs, and inspect real-time metrics & session logs:

```bash
# Windows / Linux
py -3.12 ui.py
# Or specify a custom port:
py -3.12 ui.py 5050
```

Open your browser at: **`http://localhost:5050`**

- **Target Configuration**: Update Target URL, Min/Max Dwell, Click Probability, Daily Cap, Concurrency directly from the web interface.
- **Proxy Management**: Paste & save residential/mobile proxies with live format validation.
- **Run Controls**: Start/Stop `main.py` execution with 1 click.
- **Live Monitoring**: Real-time counter of sessions today, current CTR (%), live process stdout logs, and latest 20 sessions recorded in SQLite.

---

### Full production run (CLI)

```bash
# Windows
python main.py

# Linux (headless display required)
xvfb-run -a --server-args="-screen 0 1920x1080x24" python main.py
```

### Audit only (no sessions)

```bash
python tests/audit.py
```

### Smoke test (5 sessions against local fixture)

```bash
# Windows
python tests/smoke.py

# Linux
xvfb-run -a python tests/smoke.py
```

---

## Tune

| Parameter | File | Effect |
|-----------|------|--------|
| `scheduler.sessions_per_hour` | config.yaml | Base hourly rate (scaled by diurnal curve) |
| `scheduler.concurrency` | config.yaml | Max parallel browser sessions |
| `scheduler.daily_cap` | config.yaml | Hard stop, resets at midnight |
| `target.min_dwell` / `max_dwell` | config.yaml | Dwell time range (seconds) |
| `target.click_prob` | config.yaml | Per-session ad click probability |
| `target.ad_clicks_max` | config.yaml | Max ad clicks per session |
| `proxy.max_uses_per_ip` | config.yaml | Retire IP after N uses per day |
| `proxy.dead_ip_cooldown_min` | config.yaml | Cooldown after a dead IP |
| `browser.headless` | config.yaml | `false` = visible browser (required for anti-detect) |
| `cmp.accept_prob` | config.yaml | Probability of accepting consent banner |

### Diurnal curve

`scheduler.diurnal` is a 24-element array (index = hour 0–23) that scales traffic.
Values are relative (1.0 = peak). Flat traffic at all hours is a fraud signal.

---

## Verify

Check session log:

```bash
python -c "import db; db.init(); print(db.last_sessions(10))"
```

Check today's count and CTR:

```bash
python -c "import db; db.init(); print('Today:', db.today(), '| CTR:', db.ctr())"
```

SQLite database: `sessions.db` in the project root.

---

## Troubleshoot

| Problem | Cause | Fix |
|---------|-------|-----|
| `Proxy pool exhausted` | All IPs at daily cap or dead | Add more proxies or raise `max_uses_per_ip` |
| `HeadlessChrome in UA` | `headless: true` set | Set `headless: false` in config.yaml |
| `WebGL renderer: SwiftShader` | GPU not available | Install GPU drivers or run on a machine with real GPU |
| `Audit fails: datacenter ASN` | Proxy is a VPS/datacenter IP | Replace with residential/mobile proxies |
| `Sessions finish too fast` | `min_dwell` too low | Raise `min_dwell` and `max_dwell` |
| `SessionDB locked` | Multiple processes | Ensure only one `main.py` runs at a time |
| `playwright install` fails | Network issue | Try `playwright install chromium --with-deps` |

### Log level

Set `LOGLEVEL=DEBUG` for verbose output:

```bash
# Windows
set LOGLEVEL=DEBUG && python main.py

# Linux
LOGLEVEL=DEBUG python main.py
```

---

## Architecture

```
main.py         → Scheduler (diurnal rate, daily cap, concurrency)
pool.py         → Proxy rotation, geo lookup, health tracking
fingerprint.py  → Deterministic browser identity per proxy
worker.py       → Session lifecycle (navigate, dwell, ad interact)
nav.py          → Multi-page internal navigation
human.py        → Bezier mouse, eased scroll, typing simulation
cmp.py          → Consent banner detection and acceptance
persist.py      → Cookie/storage state persistence per proxy
db.py           → SQLite session logging
tests/audit.py  → Pre-flight invariant checks
tests/smoke.py  → 5-session end-to-end test
```

---

## File layout

```
adstera/
├── config.yaml          # All configuration
├── proxies.txt          # Proxy list (credentials here, never commit)
├── requirements.txt     # Python dependencies
├── sessions.db          # SQLite log (auto-created)
├── state/               # Per-proxy cookie storage (auto-created)
├── main.py
├── pool.py
├── fingerprint.py
├── human.py
├── worker.py
├── nav.py
├── persist.py
├── cmp.py
├── db.py
├── email_client.py      # Sonjj disposable email & OTP extraction client with credit guards
├── freellmapi_client.py # FreeLLMAPI AI content & high-intent persona inquiry client
├── freellmapi_daemon.py # Supervisor watchdog for local FreeLLMAPI service
├── tests/
│   ├── audit.py
│   ├── smoke.py
│   └── fixtures/
│       └── page.html
└── DECISIONS.md
```

