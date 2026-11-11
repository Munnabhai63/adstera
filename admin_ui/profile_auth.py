"""Profile, salted PBKDF2 authentication, integrations audit, and live notifications state."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html as html_lib
import json
import os
import re
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import db

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = BASE_DIR / "state"
COOKIE_NAME = "adsterra_crm_session"
PBKDF2_ITERATIONS = 200_000

ALLOWED_AVATARS = (
    "/crm-assets/img/avatars/1.png",
    "/crm-assets/img/avatars/2.png",
    "/crm-assets/img/avatars/3.png",
    "/crm-assets/img/avatars/4.png",
    "/crm-assets/img/avatars/10.png",
    "/crm-assets/img/avatars/12.png",
    "/crm-assets/img/avatars/14.png",
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[\d\W_]).{8,}$")
_TAG_RE = re.compile(r"<[^>]+>")
_RULE_LINE_RE = re.compile(r"[─━─\-]{4,}")


def _clean_alert_text(raw_text: str) -> str:
    txt = html_lib.unescape(str(raw_text or ""))
    txt = _TAG_RE.sub("", txt)
    txt = _RULE_LINE_RE.sub(" ", txt)
    parts = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    return re.sub(r"\s{2,}", " ", " · ".join(parts))[:220]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utc_iso(when: dt.datetime | None = None) -> str:
    return (when or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(ts_str: str) -> dt.datetime | None:
    if not ts_str:
        return None
    norm = ts_str.strip().replace("Z", "+00:00")
    if " " in norm and "T" not in norm:
        norm = norm.replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(norm)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _default_record() -> dict[str, Any]:
    return {
        "display_name": "Master Operator",
        "role": "Lead Publisher Admin",
        "email": "operator@adsterrafleet.local",
        "organization": "10-Domain Publisher Hub",
        "location": "India (IST / UTC+5:30)",
        "bio": "Autonomous Adsterra traffic, 20-topic AutoPublish CMS, and multi-domain monetization operator.",
        "avatar": ALLOWED_AVATARS[0],
        "joined_label": "Active Fleet v3",
        "updated_at": _utc_iso(),
        "auth": {
            "require_login": False,
            "locked_now": False,
            "password_hash": "",
            "password_salt": "",
            "password_updated_at": "",
        },
        "notifications": {
            "read_ids": [],
            "read_all_before": "",
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, path)


def _load_raw_profile(state_dir: Path | None = None) -> dict[str, Any]:
    sdir = state_dir or DEFAULT_STATE_DIR
    path = sdir / "admin_profile.json"
    base = _default_record()
    if not path.exists():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return base
    except (OSError, json.JSONDecodeError):
        return base

    for k in ("display_name", "role", "email", "organization", "location", "bio", "avatar", "joined_label", "updated_at"):
        if isinstance(raw.get(k), str) and raw[k].strip():
            base[k] = raw[k]
    if base["avatar"] not in ALLOWED_AVATARS:
        base["avatar"] = ALLOWED_AVATARS[0]
    if isinstance(raw.get("auth"), dict):
        base["auth"].update({k: raw["auth"][k] for k in base["auth"] if k in raw["auth"]})
    if isinstance(raw.get("notifications"), dict):
        notifs = raw["notifications"]
        if isinstance(notifs.get("read_ids"), list):
            base["notifications"]["read_ids"] = [str(x) for x in notifs["read_ids"]][-200:]
        if isinstance(notifs.get("read_all_before"), str):
            base["notifications"]["read_all_before"] = notifs["read_all_before"]
    return base


def _save_raw_profile(data: dict[str, Any], state_dir: Path | None = None) -> None:
    sdir = state_dir or DEFAULT_STATE_DIR
    _atomic_write_json(sdir / "admin_profile.json", data)


def _public_profile(raw: dict[str, Any]) -> dict[str, Any]:
    auth = raw.get("auth", {})
    has_pw = bool(auth.get("password_hash") and auth.get("password_salt"))
    return {
        "display_name": raw["display_name"],
        "role": raw["role"],
        "email": raw["email"],
        "organization": raw["organization"],
        "location": raw["location"],
        "bio": raw["bio"],
        "avatar": raw["avatar"],
        "joined_label": raw["joined_label"],
        "updated_at": raw["updated_at"],
        "require_login": bool(auth.get("require_login", False)) and has_pw,
        "locked_now": bool(auth.get("locked_now", False)),
        "has_password": has_pw,
        "password_updated_at": auth.get("password_updated_at", ""),
        "available_avatars": list(ALLOWED_AVATARS),
    }


def load_profile(state_dir: Path | None = None) -> dict[str, Any]:
    """Return non-sensitive operator profile and auth posture metadata."""
    return _public_profile(_load_raw_profile(state_dir))


def save_profile(updates: dict[str, Any], state_dir: Path | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Validate and persist editable operator profile details."""
    raw = _load_raw_profile(state_dir)
    display_name = str(updates.get("display_name", raw["display_name"])).strip()
    email = str(updates.get("email", raw["email"])).strip()
    role = str(updates.get("role", raw["role"])).strip() or raw["role"]
    org = str(updates.get("organization", raw["organization"])).strip() or raw["organization"]
    location = str(updates.get("location", raw["location"])).strip() or raw["location"]
    bio = str(updates.get("bio", raw["bio"])).strip() or raw["bio"]
    avatar = str(updates.get("avatar", raw["avatar"])).strip()

    if not (2 <= len(display_name) <= 60):
        return False, "Display name must be between 2 and 60 characters.", _public_profile(raw)
    if not _EMAIL_RE.match(email) or len(email) > 120:
        return False, "Enter a valid operator email address (e.g. name@domain.com).", _public_profile(raw)
    if avatar not in ALLOWED_AVATARS:
        return False, "Select one of the verified operator avatars.", _public_profile(raw)

    raw.update({
        "display_name": display_name,
        "email": email,
        "role": role[:60],
        "organization": org[:80],
        "location": location[:80],
        "bio": bio[:280],
        "avatar": avatar,
        "updated_at": _utc_iso(),
    })
    _save_raw_profile(raw, state_dir)
    return True, "Operator profile updated.", _public_profile(raw)


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_credentials(identifier: str, password: str, state_dir: Path | None = None) -> bool:
    """Timing-safe verification of operator identifier and PBKDF2 password."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    stored_hash = auth.get("password_hash", "")
    stored_salt = auth.get("password_salt", "")
    if not stored_hash or not stored_salt or not password:
        return False

    ident = (identifier or "").strip().lower()
    valid_idents = {
        raw["email"].strip().lower(),
        raw["display_name"].strip().lower(),
        "admin",
        "operator",
    }
    if ident and ident not in valid_idents:
        return False

    candidate_hash, _ = _hash_password(password, stored_salt)
    return hmac.compare_digest(candidate_hash, stored_hash)


def set_password(
    new_password: str,
    confirm_password: str = "",
    current_password: str = "",
    require_login: bool | None = None,
    state_dir: Path | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Set or rotate salted PBKDF2 operator password and optional login gate."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    has_pw = bool(auth.get("password_hash") and auth.get("password_salt"))

    if has_pw and not verify_credentials("", current_password, state_dir):
        return False, "Current password is incorrect.", _public_profile(raw)
    if not _PASSWORD_RE.match(new_password or ""):
        return False, "Password must be at least 8 chars with 1 lowercase letter and 1 number/symbol.", _public_profile(raw)
    if confirm_password and new_password != confirm_password:
        return False, "New password and confirmation do not match.", _public_profile(raw)

    pw_hash, pw_salt = _hash_password(new_password)
    auth["password_hash"] = pw_hash
    auth["password_salt"] = pw_salt
    auth["password_updated_at"] = _utc_iso()
    if require_login is not None:
        auth["require_login"] = bool(require_login)
    _save_raw_profile(raw, state_dir)
    return True, "Operator password updated securely.", _public_profile(raw)


def clear_password(current_password: str, state_dir: Path | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Remove configured password (after verifying current) and disable login gate."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    if auth.get("password_hash") and not verify_credentials("", current_password, state_dir):
        return False, "Current password is required to disable password lock.", _public_profile(raw)
    auth["password_hash"] = ""
    auth["password_salt"] = ""
    auth["password_updated_at"] = ""
    auth["require_login"] = False
    auth["locked_now"] = False
    _save_raw_profile(raw, state_dir)
    return True, "Password lock removed; CRM returned to open localhost mode.", _public_profile(raw)


def set_require_login(enabled: bool, state_dir: Path | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Toggle strict /crm sign-in gate cleanly."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    has_pw = bool(auth.get("password_hash") and auth.get("password_salt"))
    if enabled and not has_pw:
        return False, "Set an operator password first before enabling Sign-In Gate.", _public_profile(raw)
    auth["require_login"] = bool(enabled)
    _save_raw_profile(raw, state_dir)
    msg = "Sign-In Gate enabled for /crm." if enabled else "Sign-In Gate disabled (open localhost mode)."
    return True, msg, _public_profile(raw)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_sessions(state_dir: Path | None = None) -> list[dict[str, Any]]:
    sdir = state_dir or DEFAULT_STATE_DIR
    path = sdir / "admin_sessions.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []

    now = _utc_now()
    active = []
    for item in sessions:
        exp = _parse_iso(str(item.get("expires_at", "")))
        if exp and exp > now and item.get("token_digest"):
            active.append(item)
    return active


def _save_sessions(sessions: list[dict[str, Any]], state_dir: Path | None = None) -> None:
    sdir = state_dir or DEFAULT_STATE_DIR
    _atomic_write_json(sdir / "admin_sessions.json", {"sessions": sessions[-10:]})


def extract_cookie_token(cookie_header: str | None) -> str:
    if not cookie_header:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return ""
    morsel = jar.get(COOKIE_NAME)
    return morsel.value if morsel else ""


def create_session_token(user_agent: str = "", remember: bool = True, state_dir: Path | None = None) -> str:
    """Issue fresh session cookie token, clear locked_now, and store only token SHA-256 digest."""
    token = secrets.token_urlsafe(32)
    ttl = dt.timedelta(days=30 if remember else 0, hours=0 if remember else 12)
    now = _utc_now()
    sessions = _load_sessions(state_dir)
    sessions.append({
        "id": secrets.token_hex(4),
        "token_digest": _token_digest(token),
        "user_agent": (user_agent or "Browser Session")[:120],
        "created_at": _utc_iso(now),
        "expires_at": _utc_iso(now + ttl),
    })
    _save_sessions(sessions, state_dir)

    raw = _load_raw_profile(state_dir)
    if raw["auth"].get("locked_now"):
        raw["auth"]["locked_now"] = False
        _save_raw_profile(raw, state_dir)
    return token


def validate_session_cookie(cookie_header: str | None, state_dir: Path | None = None) -> dict[str, Any] | None:
    token = extract_cookie_token(cookie_header)
    if not token:
        return None
    digest = _token_digest(token)
    for item in _load_sessions(state_dir):
        if hmac.compare_digest(str(item.get("token_digest", "")), digest):
            return {"id": item["id"], "user_agent": item["user_agent"], "created_at": item["created_at"]}
    return None


def revoke_session_and_lock(cookie_header: str | None = None, state_dir: Path | None = None) -> None:
    """Sign out current token (or all tokens if forced) and lock /crm until unlock/login."""
    token = extract_cookie_token(cookie_header)
    sessions = _load_sessions(state_dir)
    if token:
        digest = _token_digest(token)
        sessions = [s for s in sessions if not hmac.compare_digest(str(s.get("token_digest", "")), digest)]
    else:
        sessions = []
    _save_sessions(sessions, state_dir)

    raw = _load_raw_profile(state_dir)
    raw["auth"]["locked_now"] = True
    _save_raw_profile(raw, state_dir)


def unlock_without_password(state_dir: Path | None = None) -> tuple[bool, str]:
    """Allow instant dev unlock ONLY when no password hash is set."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    if auth.get("password_hash") and auth.get("password_salt"):
        return False, "Password is configured; enter your password to sign in."
    auth["locked_now"] = False
    _save_raw_profile(raw, state_dir)
    return True, "CRM session unlocked."


def is_crm_locked(cookie_header: str | None, state_dir: Path | None = None) -> bool:
    """Return True if /crm must present the Vuexy Sign-In / Lock screen."""
    raw = _load_raw_profile(state_dir)
    auth = raw["auth"]
    has_pw = bool(auth.get("password_hash") and auth.get("password_salt"))
    if auth.get("locked_now"):
        return True
    if has_pw and auth.get("require_login"):
        return validate_session_cookie(cookie_header, state_dir) is None
    return False


def list_active_sessions(cookie_header: str | None = None, state_dir: Path | None = None) -> list[dict[str, Any]]:
    token = extract_cookie_token(cookie_header)
    cur_digest = _token_digest(token) if token else ""
    out = []
    for s in reversed(_load_sessions(state_dir)):
        is_cur = bool(cur_digest and hmac.compare_digest(str(s.get("token_digest", "")), cur_digest))
        out.append({
            "id": s.get("id", ""),
            "user_agent": s.get("user_agent", "Session"),
            "created_at": s.get("created_at", ""),
            "expires_at": s.get("expires_at", ""),
            "is_current": is_cur,
        })
    return out


def _read_env_keys(base_dir: Path) -> set[str]:
    keys: set[str] = set()
    env_path = base_dir / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if v.strip():
                keys.add(k.strip())
    for k, v in os.environ.items():
        if v:
            keys.add(k)
    return keys


def get_connections_summary(base_dir: Path | None = None, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Inspect .env key presence (never returning values) & config.yaml subsystem readiness."""
    bdir = base_dir or BASE_DIR
    env_keys = _read_env_keys(bdir)
    c = cfg or {}
    gsc_cfg = c.get("google_search_console", {}) or {}
    gsc_new_cfg = c.get("gsc", {}) or {}
    gsc_sa_exists = (bdir / str(gsc_new_cfg.get("service_account_json", "state/gsc_service_account.json"))).exists()
    gsc_token_exists = (bdir / str(gsc_new_cfg.get("oauth_token_json", gsc_cfg.get("token_path", "state/gsc_token.json")))).exists()
    gsc_active = gsc_sa_exists or gsc_token_exists
    gsc_status = "Service Account Active" if gsc_sa_exists else ("OAuth Token Active" if gsc_token_exists else "Setup Pending")
    push_cfg = c.get("push_notifications", {}) or {}
    vapid_exists = (bdir / str(push_cfg.get("vapid_keys_path", "state/vapid_keys.json"))).exists()
    net_mode = str((c.get("network") or {}).get("mode", "")).strip().lower()
    proxies_file = bdir / str((c.get("proxy", {}) or {}).get("file", "proxies.txt"))
    proxy_count = 0
    if proxies_file.exists():
        proxy_count = sum(1 for ln in proxies_file.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip() and not ln.strip().startswith("#"))
    is_mobile_tether = (net_mode == "mobile_tether")
    net_configured = is_mobile_tether or (proxy_count > 0)
    net_status = (
        ("Mobile ADB Tether Active" if proxy_count == 0 else f"Mobile ADB + {proxy_count} Proxies")
        if is_mobile_tether
        else f"{proxy_count} Proxy Lines"
    )

    return [
        {
            "id": "adsterra",
            "name": "Adsterra Stats API",
            "category": "Monetization",
            "icon": "tabler-currency-dollar",
            "color": "success",
            "configured": "ADSTERRA_API_KEY" in env_keys,
            "status_label": "Key Set (.env)" if "ADSTERRA_API_KEY" in env_keys else "Mock Mode",
            "detail": "Official revenue & eCPM hourly telemetry",
            "target_view": "monetization",
        },
        {
            "id": "freellmapi",
            "name": "FreeLLM / Gemini AI Writer",
            "category": "AutoPublish CMS",
            "icon": "tabler-sparkles",
            "color": "primary",
            "configured": ("FREELLMAPI_KEY" in env_keys or "GEMINI_API_KEY" in env_keys),
            "status_label": "Gateway Ready" if ("FREELLMAPI_KEY" in env_keys or "GEMINI_API_KEY" in env_keys) else "Fallback / Missing Key",
            "detail": "20-topic content synthesis & SEO schema",
            "target_view": "autopublish",
        },
        {
            "id": "cloudflare",
            "name": "Cloudflare Workers Fleet",
            "category": "10 Domains",
            "icon": "tabler-cloud-bolt",
            "color": "warning",
            "configured": ("CLOUDFLARE_API_TOKEN" in env_keys and "CLOUDFLARE_ACCOUNT_ID" in env_keys),
            "status_label": "Account & Token Set" if ("CLOUDFLARE_API_TOKEN" in env_keys and "CLOUDFLARE_ACCOUNT_ID" in env_keys) else "Partial Config",
            "detail": "Parallel edge publishing & domain bindings",
            "target_view": "autopublish",
        },
        {
            "id": "telegram",
            "name": "Telegram Alert Bot",
            "category": "Alerts",
            "icon": "tabler-brand-telegram",
            "color": "info",
            "configured": ("TELEGRAM_BOT_TOKEN" in env_keys and "TELEGRAM_CHAT_ID" in env_keys),
            "status_label": "Live Delivery Ready" if ("TELEGRAM_BOT_TOKEN" in env_keys and "TELEGRAM_CHAT_ID" in env_keys) else "Not Configured",
            "detail": "Layer 3 morning revenue & CTR safety digests",
            "target_view": "growth",
        },
        {
            "id": "gsc",
            "name": "Google Search Console",
            "category": "SEO & Indexing",
            "icon": "tabler-brand-google",
            "color": "danger",
            "configured": gsc_active,
            "status_label": gsc_status,
            "detail": "Layer 5 sitemap push & URL inspection",
            "target_view": "growth",
        },
        {
            "id": "push",
            "name": "OneSignal & WebPush VAPID",
            "category": "Retention",
            "icon": "tabler-bell-ringing",
            "color": "secondary",
            "configured": vapid_exists or ("ONESIGNAL_APP_ID" in env_keys),
            "status_label": "VAPID / SDK Ready" if (vapid_exists or "ONESIGNAL_APP_ID" in env_keys) else "Needs Keys",
            "detail": "Layer 6 prompt allow-rate & subscriber growth",
            "target_view": "growth",
        },
        {
            "id": "proxies",
            "name": "Proxy Pool & Mobile ADB",
            "category": "Network",
            "icon": "tabler-network",
            "color": "dark",
            "configured": net_configured,
            "status_label": net_status,
            "detail": "Residential / 4G pool & ADB IP rotation",
            "target_view": "network",
        },
    ]


def get_notifications(state_dir: Path | None = None, limit: int = 20) -> dict[str, Any]:
    """Aggregate real alerts from alert_logs, CTR safety breakers, and Adsterra syncs."""
    raw = _load_raw_profile(state_dir)
    notif_state = raw.get("notifications", {})
    read_ids = set(notif_state.get("read_ids", []))
    read_before = _parse_iso(notif_state.get("read_all_before", ""))

    items: list[dict[str, Any]] = []
    today_summary = {"INFO": 0, "WARNING": 0, "CRITICAL": 0, "SUCCESS": 0, "total": 0}

    try:
        today_summary = db.get_alert_summary_today()
        for row in db.get_recent_alerts(limit=limit):
            nid = f"alert:{row['id']}"
            items.append({
                "id": nid,
                "level": str(row.get("level") or "INFO").upper(),
                "type": str(row.get("alert_type") or "SYSTEM"),
                "domain": str(row.get("domain") or "fleet"),
                "title": str(row.get("alert_type") or "System Alert").replace("_", " ").title(),
                "message": _clean_alert_text(str(row.get("message") or "")),
                "ts": str(row.get("ts") or _utc_iso()),
                "sent_live": bool(row.get("sent_live")),
            })
    except Exception:
        pass

    try:
        for dom in db.all_domains_summary():
            if dom.get("tripped") or (dom.get("ctr_pct", 0) >= 4.4 and dom.get("impressions", 0) >= 5):
                lvl = "CRITICAL" if dom.get("tripped") else "WARNING"
                nid = f"breaker:{dom['domain']}:{dom.get('impressions', 0)}"
                items.append({
                    "id": nid,
                    "level": lvl,
                    "type": "CIRCUIT_BREAKER",
                    "domain": dom["domain"],
                    "title": f"{dom['domain']} CTR Safety {lvl.title()}",
                    "message": f"CTR at {dom.get('ctr_pct', 0):.2f}% across {dom.get('impressions', 0)} impressions.",
                    "ts": _utc_iso(),
                    "sent_live": False,
                })
    except Exception:
        pass

    try:
        for sync_row in db.get_latest_adsterra_sync(limit=2):
            nid = f"sync:{sync_row['id']}"
            rev = float(sync_row.get("revenue_usd") or 0)
            items.append({
                "id": nid,
                "level": "SUCCESS",
                "type": "ADSTERRA_SYNC",
                "domain": str(sync_row.get("domain") or "all"),
                "title": f"Adsterra Sync ({sync_row.get('domain') or 'fleet'})",
                "message": f"${rev:.2f} reported · eCPM ${float(sync_row.get('cpm') or 0):.2f}",
                "ts": str(sync_row.get("synced_at") or _utc_iso()),
                "sent_live": False,
            })
    except Exception:
        pass

    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    items = items[:limit]

    unread = 0
    for it in items:
        parsed_ts = _parse_iso(str(it.get("ts", "")))
        marked_by_cutoff = bool(read_before and parsed_ts and parsed_ts <= read_before)
        is_read = (it["id"] in read_ids) or marked_by_cutoff
        it["read"] = is_read
        if not is_read:
            unread += 1

    return {"items": items, "unread_count": unread, "today_summary": today_summary}


def mark_notifications_read(
    notif_ids: list[str] | None = None,
    mark_all: bool = False,
    state_dir: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Persist notification read acknowledgements and return fresh notification state."""
    raw = _load_raw_profile(state_dir)
    nstate = raw["notifications"]
    if mark_all:
        nstate["read_all_before"] = _utc_iso()
        cur = get_notifications(state_dir, limit=limit)
        merged = list(dict.fromkeys([*nstate["read_ids"], *[x["id"] for x in cur["items"]]]))
        nstate["read_ids"] = merged[-200:]
    elif notif_ids:
        merged = list(dict.fromkeys([*nstate["read_ids"], *[str(i) for i in notif_ids if i]]))
        nstate["read_ids"] = merged[-200:]
    _save_raw_profile(raw, state_dir)
    return get_notifications(state_dir, limit=limit)
