# ROUND 21 — BRANDED LANDING PAGE + DENY-BY-DEFAULT AUTH GUARD

**Repo:** `Munnabhai63/adstera`
**Base branch:** `arena/7a0464cb-adstera` (also present on `round20-purge` @ `20a9a49c`)
**Create branch:** `round21-admin-auth`

---

## 0. WHAT YOU ARE BEING ASKED TO DO

Two things, in this order:

1. **Wire in a finished, pre-built landing page** that already exists in this repo.
   You do **not** design it. You do **not** restyle it. You copy it and connect it.
2. **Add a deny-by-default auth guard** so that all 63 API routes require a session,
   not the current 4.

That is the entire round. Everything else is out of scope.

---

## 1. THE DESIGN IS ALREADY DONE — DO NOT CHANGE IT

The final, approved design lives in this repo at:

```
design_preview/login_branded.py     <- the real module (already tested, renders correctly)
design_preview/landing.html         <- the same page as static HTML (for reference only)
design_preview/SETUP_STEPS.md       <- the human's copy of these steps
```

**Read `design_preview/login_branded.py` first. It is complete and working.** It exports:

```python
render_login_branded(profile: dict, error_msg: str = "", next_url: str = "") -> str
```

It already has:
- Inline CSS only (`_CSS` constant) — zero external requests, zero `<img>`, system fonts
- 8 integration cards + 8 curved SVG wires + glowing orb (`_cards()`, `_wires_svg()`)
- Error alert block, rendered only when `error_msg` is non-empty
- HTML-escaped interpolation (`_esc()`) — XSS-safe, verified
- Password reveal, pointer-tilt parallax, `prefers-reduced-motion` handling
- Renders in 24,902 bytes, gzip ~7.8 KB

### ABSOLUTE DESIGN RULES

```
✅ COPY design_preview/login_branded.py to admin_ui/views/login_branded.py VERBATIM
❌ DO NOT change any colour, spacing, size, font, layout or SVG path
❌ DO NOT "improve", "modernise", "optimise" or refactor the CSS
❌ DO NOT add a logo image, a font link, an icon library or a CSS framework
❌ DO NOT add any visible number (article counts, domain counts, traffic, revenue)
❌ DO NOT add a "Protected by ..." footer, a sign-up link, or a "Need help?" link
❌ DO NOT touch admin_ui/assets/** — the existing panel's Vuexy skin is untouched
❌ DO NOT touch admin_ui/shell.py or any existing view in admin_ui/views/ except
   pointing the /crm/login route at the new renderer
```

If you believe the design needs a change, **stop and report it** — do not make it.

The heavy CSS you will see referenced by the old login page — `core.css` (713,576 B)
and `iconify-icons.css` (2,819,085 B) — must **not** be linked by the new page. That
3.5 MB is precisely what this round removes from the login path.

---

## 2. STEP-BY-STEP IMPLEMENTATION

### 2.1 Copy the module

```bash
cp design_preview/login_branded.py admin_ui/views/login_branded.py
```

Confirm it imports cleanly:

```bash
python -c "from admin_ui.views.login_branded import render_login_branded; \
           print(len(render_login_branded({}).encode()))"
```
Expected: `24902` (± a few bytes). If it errors, fix the import path only.

### 2.2 Export it

Edit `admin_ui/views/__init__.py`. **Add** — do not remove anything:

```python
from admin_ui.views.login_branded import render_login_branded
```
and add `"render_login_branded",` to `__all__`.

### 2.3 Swap the renderer — exactly 2 lines in `ui.py`

At the `/crm/login` branch (around line 3108):

```python
        if path in ("/crm/login", "/crm/login/"):
            from admin_ui import profile_auth
            from admin_ui.views import render_login_view            # <- OLD
```

Change the import to:
```python
            from admin_ui.views import render_login_branded         # <- NEW
```

Then, a few lines below, change the call:
```python
            self._send_html(render_login_view(prof, error_msg=err), extra_headers=[("Cache-Control", "no-store")])
```
to:
```python
            self._send_html(render_login_branded(prof, error_msg=err), extra_headers=[("Cache-Control", "no-store")])
```

**Leave `admin_ui/views/login.py` on disk, untouched.** It is the fallback.

### 2.4 Add the deny-by-default guard — `admin_ui/auth_guard.py` (NEW file)

Measured state today:

```
/api/ routes defined in ui.py        : 63
_require_crm_unlocked() call sites   :  4
_redirect_if_crm_locked() call sites :  4
=> 59 endpoints answer with no session cookie
```

```python
"""Deny-by-default authentication guard for the whole admin surface."""

PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",       # the only API a signed-out browser may call
})

PUBLIC_GET_PATHS = frozenset({
    "/crm/login", "/crm/login/",
    "/login", "/login/",
    "/favicon.ico", "/healthz",
})

PUBLIC_PREFIXES = ("/crm-assets/",)   # existing panel assets must keep loading

def is_public_path(path: str) -> bool: ...
def guard_request(handler) -> bool:
    """True  -> request may proceed.
       False -> a 401 or redirect was already sent; caller must return."""

def note_failed_login(ip: str) -> None: ...
def is_rate_limited(ip: str, window_s: int = 900, max_attempts: int = 5) -> bool: ...
```

Behaviour:
- Path is public → allow
- Valid session cookie → allow
- Otherwise `/api/*` → `{"ok": false, "locked": true, "error": "unauthorized"}`, HTTP 401
- Otherwise HTML → 302 to `/crm/login?next=<urlencoded original path>`
- Rate limit: 5 failures per IP per 15 min → 401 `too_many_attempts`, **even if the
  password is correct**. State in `state/login_attempts.json`, pruned on read.
- **Must honour `PHASE4_FIRST_RUN_SETUP=1`** exactly like
  `profile_auth.is_crm_locked` (profile_auth.py:387), otherwise
  `tests/test_layer_u7_phase4_unified_crm.py` breaks.

### 2.5 Wire the guard — 2 call sites in `ui.py`

```python
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        from admin_ui.auth_guard import guard_request
        if not guard_request(self):
            return
        # ... existing code unchanged ...

    def do_POST(self) -> None:
        from admin_ui.auth_guard import guard_request
        if not guard_request(self):
            return
        # ... existing code unchanged ...
```

Do **not** delete the existing `_require_crm_unlocked` / `_redirect_if_crm_locked`
calls. They are defence in depth and run after the new guard.

**Total `ui.py` change budget: ≤ 20 lines.** If you are changing more, you are
editing route blocks — stop and use the central guard instead.

### 2.6 First-run credentials — `scripts/setup_admin.py` (NEW file)

Add to `.env.example` (blank values):
```
ADMIN_EMAIL=
ADMIN_PASSWORD=
```

`setup_admin.py` reads them from `.env` or argv, refuses a password < 12 chars or an
email without `@`, then calls the **existing** helpers:

```python
profile_auth.set_password(new_password, confirm_password=new_password, require_login=True)
profile_auth.save_profile({"email": email})
```

Prints `ADMIN READY: <email> / password not echoed`. Never echoes or writes the
password. Confirm `.env` is in `.gitignore` before touching it.

### 2.7 Do NOT rebuild auth

`admin_ui/profile_auth.py` already provides everything. Verified in code:

```python
verify_credentials(identifier, password)          # line 201
# accepts email, display_name, "admin", "operator"  (lines 214-219)
create_session_token(...)                          # line 324
validate_session_cookie(...)                       # line 346
is_crm_locked(...)                                 # line 384
set_password(...) / set_require_login(...)         # lines 224 / 270
```

PBKDF2-HMAC-SHA256 + per-user salt + `hmac.compare_digest` are all present.
**Do not add a users table. Do not add JWT. Do not rewrite hashing.**

---

## 3. TESTS — `tests/test_round21_admin_auth.py`

```
1.  every "/api/..." literal in ui.py is protected (parse the file; none may be
    public except the whitelist)                                  <- load-bearing
2.  deny-by-default: invented path /api/zzz_unlisted -> 401       <- load-bearing
3.  GET /api/autopublish/stats, no cookie -> 401, body has "locked": true
4.  GET /api/adsterra/funnel, no cookie   -> 401
5.  GET /api/config, no cookie            -> 401
6.  GET /crm, no cookie                   -> 302 to /crm/login
7.  GET /crm/login, no cookie             -> 200, contains "Sign in"
8.  GET /crm-assets/<real file>, no cookie-> 200
9.  POST /api/auth/login correct creds    -> 200 + Set-Cookie
10. same with wrong identifier            -> 302 ?error=invalid
11. login, then GET a protected route WITH cookie -> 200
12. 6 bad logins -> the 6th is too_many_attempts
13. landing page has ZERO external requests (regex src=/href=/@import for http)
14. landing page has ZERO <img> and ZERO external <script src>
15. landing page contains <meta name="robots" content="noindex
16. landing page renders in <= 26 KB
17. landing page works as a plain form POST with JS disabled
18. PHASE4_FIRST_RUN_SETUP=1 still bypasses the lock
19. design unchanged: admin_ui/assets/** and shell.py have an empty git diff
20. render_login_branded output still shows 8 integration cards
```

### Must not break
```
python -m pytest --collect-only -q        -> 557 collected or more
python -m pytest -q -m "not live"         -> all pass
python scripts/verify_round_claims.py     -> EXIT=0
python scripts/seo_onpage_audit.py        -> 15 rows at 100.0%
tests/test_layer_u7_phase4_unified_crm.py -> passes
```

---

## 4. ACCEPTANCE — real command output only, no summaries

```
CHECK 1  route coverage
    required: "protected: 63 / 63 | public: 1 (/api/auth/login)"

CHECK 2  unauthenticated sweep over all 63
    required: "401: 62 | 200: 0"  (login itself excluded)

CHECK 3  authenticated sweep
    required: "200: 63 | 401: 0"

CHECK 4  landing page weight
    required: "render_login_branded bytes: <N>"
    required: "external requests: 0 | img tags: 0 | external scripts: 0"
    required: "cards: 8 | wires: 8"

CHECK 5  rate limit
    required: "attempt 6 -> too_many_attempts"

CHECK 6  design untouched
    command: git diff --stat <base>..HEAD
    required: admin_ui/shell.py        -> NO diff
    required: admin_ui/assets/**       -> NO diff
    required: admin_ui/views/          -> only __init__.py + the new file
    required: "ui.py lines changed: <= 20"
    required: design_preview/login_branded.py vs admin_ui/views/login_branded.py
              -> byte-identical (diff must be empty)

CHECK 7  regression
    required: pytest green, 557+ collected, verify_round_claims EXIT=0,
              15 audit rows at 100.0%
```

---

## 5. INSTANT REJECT LIST

1. Any change to `admin_ui/assets/**` or `admin_ui/shell.py`
2. Any restyle of the existing admin panel
3. The landing page CSS being modified in any way from `design_preview/login_branded.py`
4. Any `<img>`, external font, CDN or icon library on the landing page
5. Any visible number on the landing page
6. Reconstituting "Protected by Cloudflare Tunnel", a sign-up link or "Need help?"
7. Guard implemented per-route instead of one central call
8. Any `/api/*` route left public that is not `/api/auth/login`
9. Password echoed to stdout, a log, or a committed file
10. `ADMIN_PASSWORD` hardcoded anywhere, including tests
11. Deleting or weakening `test_layer_u7_phase4_unified_crm.py`
12. Any skip/xfail added to make the suite green
13. A number in the report you did not get from a command in this session

---

## 6. COMMITS

Keep mechanical and functional changes separate:

```
1. feat(auth): deny-by-default guard + rate limiting + sweep tests
2. feat(admin): branded landing page (verbatim copy + renderer swap)
3. feat(scripts): setup_admin.py + .env.example keys
```

Push only `round21-admin-auth`. **Never push to `master`.**

---

## 7. WHAT THIS ROUND DOES NOT DO

State this in the report so nobody is surprised:

- ❌ Does not redesign or restyle the panel — deliberately untouched
- ❌ Does not add an article list / edit / delete workspace (Round 22)
- ❌ Does not add a deploy button (Round 22)
- ❌ Does not initialise `state/` databases (Round 23)
- ❌ Does not fix `set_require_login(False)` leaving `locked_now: true` — known bug,
     report it, do not silently change behaviour
- ❌ Does not start the Cloudflare tunnel. **The operator must not open
     `admin.rechargekar.com` until this round is verified green**, because today 59 of
     63 endpoints answer without a session.

---

## 8. REPORT CONTRACT

Numbers only, each from a command run in this session.

```
ROUND 21
branch: round21-admin-auth    head: <sha>
files added: <n>   files modified: <n>   ui.py lines changed: <n>

routes total: <n>   protected: <n>/<n>   public: <n> (must be 1)
unauth sweep: 401=<n> 200=<n>
auth sweep:   200=<n> 401=<n>

render_login_branded bytes: <n>
external requests: <n>   img tags: <n>   external scripts: <n>
cards: <n>   wires: <n>
design file byte-identical to design_preview: YES/NO

rate limit trips at attempt: <n>
tests added: <n>   passed: <n>   failed: <n>
pytest collected: <n>
verify_round_claims: EXIT=<n>
seo_onpage_audit rows at 100.0%: <n>

shell.py diff: NONE/<n>
assets/ diff: NONE/<n>
views/ touched: <list — must be __init__.py + login_branded.py only>
password leaked: NEVER
set_require_login(False) bug: still present (reported, not changed)
```
