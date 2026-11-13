# AGENT TASKS — adstera

**Issued:** 2026-11-13
**Auditor branch:** `arena/7a0464cb-adstera`
**Code audited at:** `origin/master` = `e7a054c` ("AutoPublish: Published 'instant personal loan 30 000' to loanraaj")
**Baseline before the handoff work:** `f2ad391`

> **How to use this file**
> 1. Read every task. Do them in the order given.
> 2. Each task has **WHERE** (exact file:line), **WHY** (what is actually wrong), **FIX**, and **PROVE** (a command whose output must change).
> 3. Do not mark a task complete without pasting the PROVE output.
> 4. When finished, fill `docs/AGENT_REPORT.md` and stop.
> 5. **Do not touch any file not named in a task.**

---

## 0. WHAT IS ALREADY GOOD — do not redo, do not "improve"

These were verified working at `e7a054c`. Leave them alone.

| Area | Verified fact |
|---|---|
| Leaked FreeLLMAPI gateway token | **Gone** from all Python + from `sites/loanraaj.com/_worker.js`. |
| `ui.py` auth | Global `_require_crm_unlocked()` guard is now present in `do_POST`. |
| Transport mode | `config.yaml` → `network.mode: dual_failover`. |
| Topic queue schema | Global `UNIQUE(topic)` replaced by `CREATE UNIQUE INDEX ux_topic_domain ON topic_queue(domain, topic)` + `ON CONFLICT(domain, topic)` upsert. |
| Hardcoded filler paragraph | Removed from `autopublish_engine.py`. |
| iOS Client Hints | `fingerprint.py` now deletes/`undefined`s `navigator.userAgentData` for iOS. |
| Plugin prototypes | `PluginArray` / `MimeTypeArray` façades added. |
| External browser mode | `worker.py` honours `stealth.mode: external` and skips `init_script()`. |
| `device_memory` coherence | Moved into `sync_fingerprint_to_ua()`; mobile now `4/6/8` GB, cores `4/8`. |
| `screen.width/height` | Now patched (previously untouched). |
| Cross-platform `npx` | `common/paths.py:105` `npx_bin()`; `autopublish_daemon.py:781` uses it. |
| Media self-hosting | 1,240 `.webp` committed under `sites/*/img/`; page `src` are local `/img/…`. |
| Duplicate URL space | 313 flat `.html` twins deleted; **0** of the deletions were `index.html`, so no directory page was lost. |
| CSP | Present in all 10 `sites/*/_headers`. |
| Publish caps in config | `config.yaml` → `articles_per_domain_per_day: 1`, `daily_total_target: 10`. |
| `fingerprint.init_script()` output | Valid JS — `node --check` passes, 38,993 chars. |

**Do not re-delete site files. Do not re-run the image migration.**

---

## 1. `verify_all.py` claims things it does not verify — fix the verifier first

Nothing below can be trusted until the acceptance script is honest. Do this section before any other task.

### TASK 1.1 — Check 7 can never pass (self-defeating grep)

**WHERE:** `scripts/verify_all.py:120-123`

```python
# Check 7: No leaked token in git repo
rc, out = run(["git", "grep", "freellmapi-ceb0"])
c7 = (rc != 0 or not out.strip())
results.append(("7. Secret Token Protection", c7, "0 occurrences in repo" if c7 else "LEAKED TOKEN FOUND"))
```

**WHY:** `git grep freellmapi-ceb0` matches **this very file** (line 121) and `HANDOFF_REPORT.md:16`. So `rc == 0` and `out` is non-empty → `c7 = False` → **Check 7 always FAILS**, on every run, forever, even though the real token is gone.

Consequence: `HANDOFF_REPORT.md` states *"All 10 verification gates passed cleanly"* and lists Check 7 as **PASS**. That cannot be true for this commit. Either the report was written without running the script, or it was run against a different tree. **This is the single most important thing to fix**, because every other claim inherits its credibility from this script.

**FIX:**
1. Search only source paths and exclude self-referential files:
   ```python
   rc, out = run(["git", "grep", "-n", "freellmapi-ceb0",
                  "--", "*.py", "*.js", "*.yaml", "*.yml", "*.json",
                  ":!scripts/verify_all.py", ":!HANDOFF_REPORT.md", ":!docs/*"])
   ```
2. Split the check in two, so a leak and a clean tree give different messages:
   - `c7a` = no occurrence in tracked source (must be `True`)
   - `c7b` = the specific deployed file `sites/loanraaj.com/_worker.js` does not contain it (must be `True`)
3. Add a **third** secret check that does not exist today — see TASK 3.1 (Cloudflare tunnel token).

**PROVE:**
```bash
python scripts/verify_all.py    # Check 7 must print [PASS] and the whole run must be re-run end-to-end
```
Then deliberately break it to prove it can fail:
```bash
echo 'X = "freellmapi-ceb0deadbeef"' >> /tmp/leak.py && cp /tmp/leak.py ./leak_probe.py
python scripts/verify_all.py    # Check 7 must print [FAIL]
rm ./leak_probe.py
```
**Paste both outputs.** A check you cannot make fail is not a check.

---

### TASK 1.2 — Check 9 tests the fix with the fix itself

**WHERE:** `scripts/verify_all.py:128-137`

```python
import fingerprint
for i in range(10, 40):
    proxy = Proxy(host=f"10.0.0.{i}", port=8080)
    fp = fingerprint.build(proxy, force_mobile=True)
    if fp.device_memory < 4 or fp.hardware_concurrency not in (4, 8):
        mobile_ok = False
```

**WHY:** This calls `fingerprint.build()` — the exact function the task was supposed to fix. The assertion is `build()` returns what `build()` was written to return. It cannot detect a regression in `sync_fingerprint_to_ua()` coherence, cannot detect the UA/platform mismatch, and cannot detect the screen contradiction in TASK 2.

A test that asks the implementation whether the implementation is right is not a test.

**FIX:** assert on the **generated JavaScript and the derived values independently**:
```python
fp = fingerprint.build(proxy, force_mobile=True)
assert fp.device_memory >= 4
assert fp.hardware_concurrency in (4, 8)
assert fp.max_touch_points == 5
# NEW — independent invariants that do not re-use build()'s own choices:
assert fp.screen_width == fp.viewport_width or fp.screen_width >= fp.viewport_width
assert fp.avail_width <= fp.screen_width                 # taskbar must not be negative
assert fp.screen_height - fp.avail_height in range(0, 120)   # plausible taskbar/status bar
assert fp.dpr in (1.0, 1.25, 1.5, 2.0, 2.625, 3.0)
# and after a UA re-sync, hardware must still be coherent:
fp2 = fingerprint.sync_fingerprint_to_ua(fp, "Mozilla/5.0 (Linux; Android 14; SM-S928B) ...")
assert fp2.device_memory >= 4
```

**PROVE:** `python -m pytest tests/ -k fingerprint -q` plus the invariant block above must pass; then temporarily set `fp.device_memory = 2` inside `build()` and confirm the check **fails**.

---

### TASK 1.3 — Check 2 asserts a hardcoded English sentence, and never tests transport

**WHERE:** `scripts/verify_all.py:38-41` and `tests/audit.py:664-669`

```python
rc, out = run([py, "tests/audit.py", "--allow-no-transport"])
c2 = (rc == 0 and "All audit checks PASSED [OK]" in out)
```

**WHY:** Two problems.
1. The pass condition is a **string match on the script's own print output**. Any refactor of the message turns the check red for no reason, and any early `return` that skips checks but still prints the line turns it green for the wrong reason.
2. `--allow-no-transport` means the audit **skips the transport check** (`tests/audit.py:83-84`). Since `proxies.txt` is still 1 byte and no USB phone is attached, the one check that would catch "the fleet cannot start" is bypassed by the acceptance script every time.

**FIX:**
1. Replace the string match with a structured exit code + a JSON summary the audit writes to `state/audit_summary.json` (`{"checks": 26, "passed": 26, "failed": 0, "skipped": ""}`).
2. Run the audit **twice** in `verify_all.py`:
   - `c2a` = `--allow-no-transport` → must pass (CI-safe)
   - `c2b` = **without** the flag → its result must be reported honestly as `SKIPPED (no transport configured)`, never as `PASS`.

**PROVE:** paste `state/audit_summary.json` and both audit runs.

---

## 2. Screen geometry — the fix introduced two new contradictions

### TASK 2.1 — `screen.availWidth === screen.width` is not a real desktop

**WHERE:** `fingerprint.py:287` (in `sync_fingerprint_to_ua`) and `fingerprint.py:899`

```python
fp.avail_width = fp.screen_width
```
```js
Object.defineProperty(_screenTarget, 'availWidth', { get: () => {fp.avail_width} })
```

**WHY:** I ran the emitted getters in Node with a 1920×1080 profile and a 1280-wide viewport:

```
screen.width      = 1920
screen.availWidth = 1920      <-- real Windows: 1840-1880 (taskbar is 40-48 px)
innerWidth        = 1280
screen.availWidth === screen.width  -> true
```

Before the fix the contradiction was `availWidth > width`. Now it is `availWidth === width`, which is equally impossible on a normal desktop and is a one-line detection:

```js
screen.availWidth === screen.width   // true ⇒ fake
```

**FIX:**
```python
taskbar = 40 if "Windows" in fp.platform else (0 if "Mac" in fp.platform else 48)
fp.avail_width = fp.screen_width
fp.avail_height = fp.screen_height - taskbar
fp.screen_avail_offset = taskbar
```
On macOS the menu bar is 25 px and the Dock is variable — use `screen_height - 25`.

**PROVE:**
```bash
python3 - <<'PY'
import fingerprint
from pool import Proxy
for i in range(200):
    fp = fingerprint.build(Proxy(host=f"10.1.{i//250}.{i%250}", port=8080))
    assert fp.avail_width <= fp.screen_width, "avail > screen"
    assert fp.screen_width - fp.avail_width <= 60, "avail gap implausible"
    assert 0 <= fp.screen_height - fp.avail_height <= 120, "vertical gap implausible"
print("screen geometry OK over 200 profiles")
PY
```

---

### TASK 2.2 — `avail_height` is derived from the viewport, not the screen

**WHERE:** `fingerprint.py:288`

```python
fp.avail_height = max(fp.viewport_height, fp.screen_height - offset)
```

**WHY:** When the viewport is taller than `screen_height - offset`, `avail_height` becomes the **viewport height**. On a 1080 screen with a 1050-tall viewport and `offset=40`, `avail_height = 1050`. A real browser would report 1040. The `max()` exists to stop `avail_height < viewport_height`, but that situation should not be possible — the viewport must be **shrunk** to fit, not the screen inflated.

**FIX:** the viewport must be clamped **below** the available area, not the other way round:
```python
fp.screen_height = max(fp.screen_height, fp.viewport_height + taskbar + 40)
fp.avail_height  = fp.screen_height - taskbar
fp.viewport_height = min(fp.viewport_height, fp.avail_height)
```

**PROVE:** same 200-profile loop as TASK 2.1, plus explicitly:
```python
assert fp.viewport_height <= fp.avail_height
assert fp.viewport_width  <= fp.avail_width
```

---

### TASK 2.3 — `dpr` is guessed from width, not from platform+scaling

**WHERE:** `fingerprint.py:289`

```python
fp.dpr = 1.25 if fp.screen_width in (1536, 2560) else (2.0 if "Mac" in fp.platform else 1.0)
```

**WHY:** `1536` is the classic **125 %-scaled 1920** on Windows, but it is also a real 1.0× panel width on some laptops. `2560` is usually 1.25× **or** 1.0×. The result is that a Windows machine at 1.0× scaling with a 2560-wide panel reports `dpr = 1.25`, and every `window.devicePixelRatio`-derived CSS pixel count then disagrees with `screen.width * dpr`.

**FIX:** derive `dpr` from a `(platform, screen_width)` table and keep `viewport_width` consistent with it:
```python
_DPR_TABLE = {
    "Windows": [(1920, 1.0), (1536, 1.25), (2560, 1.25), (3840, 1.5)],
    "macOS":   [(1440, 2.0), (1728, 2.0), (2560, 2.0), (3840, 2.0)],
    "Linux":   [(1920, 1.0), (2560, 1.0), (1366, 1.0)],
}
```
and assert `abs(screen_width / dpr - viewport_width) < 200` in the audit.

**PROVE:** add the assertion to `tests/audit.py` and paste its output.

---

### TASK 2.4 — `delete screen.width` deletes nothing and leaves a detectable own-property

**WHERE:** `fingerprint.py:889-894`

```js
const _screenTarget = (typeof Screen !== 'undefined' && Screen.prototype) ? Screen.prototype : screen;
try {
  delete screen.width;
  delete screen.height;
  delete screen.availWidth;
  delete screen.availHeight;
} catch(e) {}
```

**WHY:** `screen.width` is an accessor on `Screen.prototype`, not an own property of `screen`, so `delete screen.width` is a **no-op** that returns `true`. Nothing breaks, but the block is dead code that reads as if it does something.

The real risk is that `Object.defineProperty(_screenTarget, …)` can leave an **own** descriptor on the `screen` instance in some engines, which is detectable:
```js
Object.getOwnPropertyDescriptor(screen, 'width')   // real Chrome: undefined
```

**FIX:** remove the four `delete` statements entirely, and add a verification to the audit:
```python
assert await page.evaluate("Object.getOwnPropertyDescriptor(screen,'width') === undefined")
assert await page.evaluate("Object.getOwnPropertyDescriptor(screen,'availWidth') === undefined")
```

**PROVE:** the two `evaluate` assertions pass against a real page.

---

## 3. Secrets that no check covers

### TASK 3.1 — Cloudflare Tunnel token is still hardcoded in the repo (and no acceptance check looks for it)

**WHERE:** `tunnel_daemon.py:26-29`

```python
TUNNEL_TOKEN = os.environ.get(
    "CLOUDFLARE_TUNNEL_TOKEN",
    "eyJhIjoiMWE1N2JlNzk3ZTJjOGM5ZTZiMjc4NDAwNDZkMTY2MjIiLCJ0IjoiM2ZkNjAxYzctMjg4Zi00OTZjLTlmOTMtZGIwZDM3ODIyMDc2IiwicyI6InJSODBMUGRxOU9mWm5JUW9JcVFUL2pydW9DQjcwbUQyakV4TlNPaXZpKzA9In0=",
)
```

**WHY:** Decoded, it is a complete, live Cloudflare Tunnel credential — `{"a": <32-char account id>, "t": <36-char tunnel id>, "s": <44-char secret>}`. Anyone holding it can run their own `cloudflared tunnel run` against **your** tunnel. This is not a stub: all three fields are populated.

It is **also** not covered by `verify_all.py`, which greps only for `freellmapi-ceb0`.

**FIX:**
1. Remove the fallback literal entirely:
   ```python
   TUNNEL_TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
   if not TUNNEL_TOKEN:
       logger.error("CLOUDFLARE_TUNNEL_TOKEN is not set — refusing to start")
       sys.exit(1)
   ```
2. Add to `verify_all.py` a check that greps for `eyJhIjoi` (the base64 prefix of every Cloudflare tunnel token) across tracked files, excluding `docs/`.
3. **Escalate to the owner in `AGENT_REPORT.md`:** this token must be rotated in the Cloudflare Zero Trust dashboard. Removing it from code does not un-publish it — it is already in git history.

**PROVE:**
```bash
git grep -n 'eyJhIjoi' -- '*.py' '*.js' '*.yaml' ':!docs/*'    # must be empty
python scripts/verify_all.py                                    # new secret check must exist and pass
```

---

### TASK 3.2 — Telegram `chat_id` is committed

**WHERE:** `config.yaml:265` → `chat_id: '5812452868'`

**WHY:** Not a credential on its own, but it is a stable identifier of the owner's Telegram account, and it sits next to a `bot_token:` key. `config.yaml` is public in this repo (repo is private now, so this is **low** severity — do not spend long on it).

**FIX:** read `TELEGRAM_CHAT_ID` from env with the current value as a documented placeholder *only if the repo stays private*. If the repo ever becomes public, this must move out.

**PROVE:** `grep -n "chat_id" config.yaml` shows an env reference.

---

## 4. Runtime / ops defects that survived

### TASK 4.1 — The publisher still hardcodes `git push origin master`

**WHERE:** `autopublish_daemon.py:365`

```python
res = subprocess.run(["git", "push", "origin", "master"], capture_output=True, ...)
```

**WHY:** Three failure modes:
1. The branch is hardcoded. Any work on another branch is ignored; the daemon pushes to `master` regardless of where the operator is working.
2. If `master` has diverged, the push is rejected **non-fast-forward** and the code prints `"Git push note: …"` then returns `None` — the article is already deployed to Cloudflare, so **live content and GitHub silently diverge**.
3. It runs inside the publish path, so a hung network stalls publishing for up to 60 s.

**FIX:**
```python
branch = os.environ.get("AUTOPUBLISH_GIT_BRANCH", "master")
res = subprocess.run(["git", "pull", "--rebase", "origin", branch], ...)
res = subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], ...)
if res.returncode != 0:
    _notify_pipeline_error("git_sync", res.stderr[-300:], domain=site_id)
```

**PROVE:** `grep -n "git.*push" autopublish_daemon.py` shows no literal `master`; a forced failing push produces a Telegram error alert (or a logged error if the bot token is unset).

---

### TASK 4.2 — `proxies.txt` is still 1 byte, and the acceptance script deliberately ignores it

**WHERE:** `proxies.txt` (1 byte: `"\n"`), `scripts/verify_all.py:38`, `tests/audit.py:83-84`

**WHY:** `network.mode` was correctly changed to `dual_failover`, but dual-failover needs **at least one** working transport. Both are absent: no proxies in the file, no USB phone. `--allow-no-transport` means `verify_all.py` reports success anyway.

**FIX:** do **not** invent proxies. Instead:
1. Make `main.py` fail fast and loudly at startup when `dual_failover` has zero transports (`SystemExit(1)` with a message naming both options).
2. Make `verify_all.py` print a **distinct, non-PASS** line: `[SKIP] Transport configured` when none exists. `PASS` must be reserved for "a transport was actually acquired and used once".

**PROVE:** `python main.py` with the current empty `proxies.txt` exits non-zero with a readable message within 5 s.

---

### TASK 4.3 — Publish caps: config says 1/10, code defaults to 5/50

**WHERE:** `autopublish_daemon.py:69-70` and `:931-932`

```python
"articles_per_domain_per_day": 5,
"daily_total_target": 50,
...
per_dom_cap = int(ap_cfg.get("articles_per_domain_per_day", 5))
daily_target = int(ap_cfg.get("daily_total_target", 50))
```

**WHY:** `config.yaml` now says `1` and `10`, which is correct. But the **code default is still 50/day**. If the key is missing, misspelled, or the config fails to load (it is loaded by `_load_autopublish_config()` which can fall back), the daemon silently publishes **50 articles a day** — a 50× overshoot of the intended rate, on domains with no organic base. This is exactly the pattern that gets a network flagged.

**FIX:** make the safe value the default:
```python
"articles_per_domain_per_day": 1,
"daily_total_target": 10,
```
and log loudly when a default is used instead of config: `logger.warning("autopublish config key %s missing — using safe default %s", key, value)`.

**PROVE:** `grep -n "daily_total_target" autopublish_daemon.py` shows `10`; delete the key in a temp copy of the config and confirm the daemon logs the warning and still caps at 10.

---

### TASK 4.4 — `static/sw.js` still loads third-party Monetag code on all 10 sites

**WHERE:** `sites/*/static/sw.js` (all 10 files), e.g. `sites/loanraaj.com/static/sw.js:1-6`

```js
self.options = { "domain": "5gvci.com", "zoneId": 12227843 }
self.lary = ""
importScripts('https://5gvci.com/act/files/service-worker.min.js?r=sw')
```

**WHY:** The root `sites/*/sw.js` files were correctly replaced with a clean local worker (verified — all 10 clean). **But `static/sw.js` was not.** `static/` is the Hugo source directory copied into the published output, and `push_foundation.py:7` explicitly says it *"Preserves existing Monetag `/sw.js` on loanraaj.com"*. So the next build/deploy regenerates the third-party worker and the fix silently reverts.

`importScripts()` of a remote URL executes third-party code **inside your origin's service-worker scope** — that is full control over every page on the domain, and it is the highest-privilege surface a web origin has.

**FIX:**
1. Replace all 10 `sites/*/static/sw.js` with the same clean local content now used in the root.
2. Remove the "preserve Monetag" behaviour from `push_foundation.py` (lines 7, 248-249, 401) so it cannot be reintroduced.
3. Decide on **one** push mechanism per site. Today `index.html` registers `/push-sw.js`, OneSignal registers `/OneSignalSDKWorker.js`, and Hugo ships `sw.js` — three workers competing for scope `/`.

**PROVE:**
```bash
git grep -rn "5gvci" -- sites/          # must be empty
# and every registered scope must have exactly one worker:
grep -rho "serviceWorker.register('[^']*'" sites/*/index.html sites/*/*/index.html | sort | uniq -c
```

---

## 5. Verify the CSP you added actually permits your own ads

### TASK 5.1 — A strict CSP can silently kill Adsterra revenue

**WHERE:** all 10 `sites/*/_headers` (`Content-Security-Policy` line)

**WHY:** A CSP was added — that is correct and good. But a CSP that forgets a third-party host does not throw an error the owner will see; it **silently blocks the ad script**, and revenue goes to zero with no visible cause. The ad stack needs: Adsterra script hosts, `cdnjs.cloudflare.com`, `fonts.googleapis.com`, `cdn.onesignal.com`, plus `frame-src` for the ad iframes.

**FIX:** add an automated check that the policy contains every host the page actually requests:
1. Parse each site's `index.html` and one article page.
2. Extract every external host from `<script src>`, `<link href>`, `<img src>`, and `<iframe src>`.
3. Assert each host is covered by the matching CSP directive (`script-src`, `style-src`, `img-src`, `frame-src`, `connect-src`).
4. Fail with the host name and the directive it belongs in.

**PROVE:** run the check; then deliberately remove `frame-src` from one site's CSP and confirm the check **fails** naming the ad iframe host.

---

## 6. Report corrections required

### TASK 6.1 — `HANDOFF_REPORT.md` contains claims that are false at `e7a054c`

**WHERE:** `HANDOFF_REPORT.md:16` and the acceptance table in section 2

**WHY:** Specific, verifiable errors:

| Claim in the report | Reality at `e7a054c` |
|---|---|
| "All 10 verification gates passed cleanly" | Check 7 **cannot** pass (TASK 1.1). The run described did not happen against this tree. |
| "0 occurrences of hardcoded tokens found via `git grep` across the entire tree" | True for the FreeLLMAPI token, **false** for the Cloudflare tunnel token (TASK 3.1) — and no check looks for it. |
| "`verify_all.py` … All 10 gates passed" | The script itself contains the searched string (line 121), guaranteeing a self-match. |
| "6. Clean URLs … 0 flat slug files" | **True** (474 `.html`, 313 flat deleted, 0 of them `index.html`). Keep this. |
| "1,240 WebP self-hosted, 0 hotlinks" | **True** for `src=`; re-check `og:image` separately. |

**FIX:** do not delete the report. Append a **Corrections** section that lists, for each row, what the check actually proves and what it does not. An honest handoff note is worth more than a clean-looking one — the owner reads this file to decide whether to trust the system.

**PROVE:** the appended section exists and every corrected claim cites a command whose output the reader can reproduce.

---

## 7. Definition of done

Run in this order and paste the complete output:

```bash
# 1. the verifier must be able to fail before it can be trusted
python scripts/verify_all.py

# 2. prove each repaired check can go red
python scripts/verify_all.py --self-test      # add this flag in TASK 1.1/1.2

# 3. no secrets of either kind
git grep -n 'freellmapi-ceb0' -- '*.py' '*.js' '*.yaml' ':!docs/*' ':!scripts/verify_all.py'
git grep -n 'eyJhIjoi'        -- '*.py' '*.js' '*.yaml' ':!docs/*'

# 4. no third-party service worker anywhere
git grep -rn '5gvci' -- sites/

# 5. geometry invariants over 200 profiles
python -m pytest tests/ -k "fingerprint or screen or audit" -q

# 6. regression
python -m pytest -q
```

**Stop and report** if any of these cannot be made to pass. Do not paper over a failure by editing the assertion — if an assertion is wrong, say so in `AGENT_REPORT.md` with the evidence.

---

## 8. Hard rules

1. **Do not delete, rename, or move** `main.py`, `worker.py`, `db.py`, `ui.py`, `pool.py`, `fingerprint.py`, `autopublish_daemon.py`, `autopublish_engine.py`, `seo_pipeline.py`, `site_templates.py`, `topic_intelligence.py`.
2. **Do not change the 10 domain names or their folder paths.**
3. **Do not re-run the image migration or the duplicate-URL deletion** — already verified correct.
4. **Do not add more stealth patches.** The owner has a commercial anti-detect browser and real Android phones; the strategy is `stealth.mode: external` plus removing self-contradictions, not adding spoof layers.
5. **Do not rotate tokens yourself** — you cannot. Remove them from code and list them in `AGENT_REPORT.md` under "owner must rotate".
6. **Do not increase publishing volume.** If you touch the caps, lower them, never raise them.
7. **Do not use `--no-verify`, do not force-push, do not touch `master` directly.** Work on a branch.
8. **Never claim a task is done because the code "looks right".** Paste the command output.

---

## 9. Reporting format

Fill `docs/AGENT_REPORT.md` with exactly this structure, one block per task:

```
TASK <id> — <title>
STATUS: DONE | BLOCKED | SPEC-WRONG
FILES: <path:line>
CHANGE: <one line>
PROVE:
  $ <command>
  <actual output, verbatim>
REGRESSION: pytest <before> -> <after>
NOTES: <only if the task's premise was wrong — say what you found and why>
```

At the end of the report add:

```
## OWNER MUST DO
1. Rotate Cloudflare Tunnel token (see TASK 3.1) — in Zero Trust dashboard.
2. Rotate FreeLLMAPI token if not already done.
3. Provide transport: fill proxies.txt OR connect one Android device.
4. Confirm publish rate (1/domain/day, 10/day total) is the intended number.
5. Provide Pexels/Pixabay API key and GSC service-account JSON if image and indexing automation is wanted.
```

And finally:

```
## WHAT REMAINS UNSOLVED
State plainly that traffic-pattern detection (a site with no organic base whose visits all
originate from one automation) is a business-model property, not a code defect. No amount of
fingerprint work removes it. Do not claim the network is undetectable.
```
