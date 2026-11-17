"""Deny-by-default authentication guard for the whole admin surface."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote, urlparse

PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",       # the only API a signed-out browser may call
})

PUBLIC_GET_PATHS = frozenset({
    "/crm/login", "/crm/login/",
    "/login", "/login/",
    "/favicon.ico", "/healthz",
})

PUBLIC_PREFIXES = ("/crm-assets/",)   # existing panel assets must keep loading


def is_public_path(path: str) -> bool:
    if path in PUBLIC_API_PATHS or path in PUBLIC_GET_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _get_attempts_file() -> Path:
    from admin_ui import profile_auth
    sdir = getattr(profile_auth, "DEFAULT_STATE_DIR", Path("state"))
    return Path(sdir) / "login_attempts.json"


def _get_client_ip(handler) -> str:
    hdr = handler.headers.get("X-Forwarded-For")
    if hdr:
        return hdr.split(",")[0].strip()
    if hasattr(handler, "client_address") and handler.client_address:
        return str(handler.client_address[0])
    return "127.0.0.1"


def is_rate_limited(ip: str, window_s: int = 900, max_attempts: int = 5) -> bool:
    p = _get_attempts_file()
    if not p.exists():
        return False
    now = time.time()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        attempts = data.get("attempts", []) if isinstance(data, dict) else []
    except Exception:
        return False

    active = [
        item for item in attempts
        if isinstance(item, dict) and now - float(item.get("ts", 0)) < window_s
    ]
    if len(active) != len(attempts):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"attempts": active}, indent=2), encoding="utf-8")
        except Exception:
            pass

    ip_count = sum(1 for item in active if item.get("ip") == ip)
    return ip_count >= max_attempts


def note_failed_login(ip: str) -> None:
    p = _get_attempts_file()
    now = time.time()
    active = []
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            attempts = data.get("attempts", []) if isinstance(data, dict) else []
            active = [
                item for item in attempts
                if isinstance(item, dict) and now - float(item.get("ts", 0)) < 900
            ]
        except Exception:
            active = []
    active.append({"ip": ip, "ts": now})
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"attempts": active}, indent=2), encoding="utf-8")
    except Exception:
        pass


def guard_request(handler) -> bool:
    """True  -> request may proceed.
       False -> a 401 or redirect was already sent; caller must return."""
    from admin_ui import profile_auth

    parsed = urlparse(handler.path)
    path = parsed.path

    # Check rate limit on login attempts
    if path == "/api/auth/login":
        client_ip = _get_client_ip(handler)
        if is_rate_limited(client_ip):
            handler.send_response(401)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(json.dumps({
                "ok": False,
                "locked": True,
                "error": "too_many_attempts",
            }).encode("utf-8"))
            return False
        return True

    # Public paths & prefixes
    if is_public_path(path):
        return True

    # Check Virtual Host publisher domains (loanraaj.com, etc.)
    host_header = (handler.headers.get("Host") or "").split(":")[0].lower()
    if host_header.startswith("www."):
        host_header = host_header[4:]
    try:
        from ui import DOMAIN_FOLDERS
        if (
            host_header in DOMAIN_FOLDERS
            and not path.startswith("/api/")
            and not path.startswith("/crm")
            and not (host_header == "rechargekar.com" and path in ("/admin", "/dashboard"))
        ):
            return True
    except ImportError:
        pass

    # Must honour PHASE4_FIRST_RUN_SETUP=1 bypass
    if os.environ.get("PHASE4_FIRST_RUN_SETUP") == "1":
        return True

    # Check session cookie / CRM lock
    cookie_hdr = handler.headers.get("Cookie")
    if not profile_auth.is_crm_locked(cookie_hdr):
        return True

    # Locked / Unauthorized
    if path.startswith("/api/"):
        handler.send_response(401)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "ok": False,
            "locked": True,
            "error": "unauthorized",
        }).encode("utf-8"))
        return False

    # HTML routes -> 302 to /crm/login
    login_url = "/crm/login" if path in ("/", "/crm", "/crm/") else f"/crm/login?next={quote(handler.path, safe='')}"
    handler.send_response(302)
    handler.send_header("Location", login_url)
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    return False
