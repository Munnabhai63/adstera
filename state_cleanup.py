"""
state_cleanup.py — Layer 4: Safe state/ cleanup, session reset, and test-pollution purge.

Removes stale per-proxy test session files (mobile_*.json, 10.0.x.1_8080*.json,
127.0.0.1_8080*.json, empty 0-byte state/sessions.db, empty mahi_bridge test artifacts),
resets circuit_breaker.json (unlocking loanraaj.com) and active_ua.json, verifies
state/accounts/registry.json & autopublish.db remain intact, and removes synthetic
test rows from sessions.db while keeping real alerts & verification logs.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from anomaly_detector import AnomalyDetector

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.resolve()
DEFAULT_STATE_DIR = PROJECT_ROOT / "state"
DEFAULT_SESSIONS_DB = PROJECT_ROOT / "sessions.db"

PROTECTED_STATE_FILES = frozenset({
    "adsterra_banners.json",
    "autopublish.db",
    "autopublish.db-shm",
    "autopublish.db-wal",
    "active_ua.json",
    "circuit_breaker.json",
    "cluster_state.json",
    "daily_report_state.json",
    "dynamic_ecpm_weights.json",
    "gsc_metrics.json",
    "gsc_submissions.json",
})

PROXY_STATE_RE = re.compile(
    r"^(?:\d{1,3}(?:\.\d{1,3}){3}|localhost|[a-z0-9.-]*trustsource\.live)_\d+(?:_meta)?\.json$",
    re.IGNORECASE,
)

IDLE_ACTIVE_UA: dict[str, Any] = {
    "active": False,
    "proxy_id": "—",
    "user_agent": "Ready — Click Start Live Run to rotate",
    "device_label": "⚪ Waiting for session start…",
    "is_mobile": False,
    "platform": "—",
    "timezone": "—",
    "target_url": "—",
    "updated_at": "—",
}

SYNTHETIC_DOMAINS = (
    "this-domain-definitely-does-not-exist-123456789.com",
    "asiafilm.org",
    "auctionr.org",
    "healthy.com",
    "risky.com",
    "insurancenet.com",
    "cloudhoster.com",
)

SYNTHETIC_PROXIES = (
    "10.0.0.1:8080",
    "10.0.1.1:8080",
    "10.0.2.1:8080",
    "127.0.0.1:8080",
    "mobile:direct",
    "test:127.0.0.1",
)


def _is_stale_proxy_state_file(path: Path) -> bool:
    """Return True if path is a top-level persist.py cookie/meta file safe to purge."""
    if not path.is_file() or path.name in PROTECTED_STATE_FILES:
        return False
    name = path.name
    if name.startswith("mobile_") and name.endswith(".json"):
        return True
    return bool(PROXY_STATE_RE.match(name))


def _is_empty_storage_state(path: Path) -> bool:
    """Return True if a Playwright storage_state JSON has zero cookies and zero origins."""
    try:
        if path.stat().st_size == 0:
            return True
        data = json.loads(path.read_text(encoding="utf-8"))
        return not data.get("cookies") and not data.get("origins")
    except Exception:
        return False


def clean_state_dir(state_dir: Path | None = None, apply: bool = True) -> dict[str, Any]:
    """Purge stale proxy session files & empty test artifacts while protecting critical state."""
    root = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    root.mkdir(parents=True, exist_ok=True)

    deleted_proxy_files: list[str] = []
    deleted_other: list[str] = []
    deleted_empty_cookies: list[str] = []
    preserved_warmed_cookies: list[str] = []

    for item in sorted(root.iterdir(), key=lambda p: p.name):
        if _is_stale_proxy_state_file(item):
            deleted_proxy_files.append(item.name)
            if apply:
                item.unlink(missing_ok=True)
        elif item.is_file() and item.name == "sessions.db" and item.stat().st_size == 0:
            deleted_other.append("sessions.db (0B orphan)")
            if apply:
                item.unlink(missing_ok=True)

    mahi_test_profile = root / "mahi_bridge" / "profiles" / "test-uuid-1234"
    if mahi_test_profile.exists() and mahi_test_profile.is_dir():
        deleted_other.append("mahi_bridge/profiles/test-uuid-1234")
        if apply:
            shutil.rmtree(mahi_test_profile, ignore_errors=True)

    mahi_cookies_dir = root / "mahi_bridge" / "cookies"
    if mahi_cookies_dir.is_dir():
        for cfile in sorted(mahi_cookies_dir.glob("*_state.json")):
            if _is_empty_storage_state(cfile):
                deleted_empty_cookies.append(cfile.name)
                if apply:
                    cfile.unlink(missing_ok=True)
            else:
                preserved_warmed_cookies.append(cfile.name)

    accounts_count = 0
    reg_path = root / "accounts" / "registry.json"
    if reg_path.is_file():
        try:
            reg_data = json.loads(reg_path.read_text(encoding="utf-8"))
            accounts_count = len(reg_data)
        except Exception:
            accounts_count = -1

    return {
        "apply": apply,
        "deleted_proxy_files_count": len(deleted_proxy_files),
        "deleted_proxy_files": deleted_proxy_files,
        "deleted_empty_cookies_count": len(deleted_empty_cookies),
        "deleted_empty_cookies": deleted_empty_cookies,
        "preserved_warmed_cookies": preserved_warmed_cookies,
        "deleted_other": deleted_other,
        "accounts_registry_intact": reg_path.is_file(),
        "accounts_count": accounts_count,
        "autopublish_db_intact": (root / "autopublish.db").is_file(),
        "banners_vault_intact": (root / "adsterra_banners.json").is_file(),
    }


def reset_circuit_breaker(state_dir: Path | None = None, apply: bool = True) -> dict[str, Any]:
    """Reset state/circuit_breaker.json to unlock paused domains such as loanraaj.com."""
    root = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    cb_path = root / "circuit_breaker.json"
    detector = AnomalyDetector(state_file=cb_path)
    before = detector._load_state()
    paused_before = sorted((before.get("paused_domains") or {}).keys())
    history_before = len(before.get("history") or [])

    if apply:
        detector.reset_all()

    return {
        "apply": apply,
        "path": str(cb_path),
        "paused_before": paused_before,
        "history_before": history_before,
        "paused_after": [] if apply else paused_before,
    }


def reset_active_ua_file(state_dir: Path | None = None, apply: bool = True) -> dict[str, Any]:
    """Reset state/active_ua.json to neutral idle standby payload."""
    root = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    ua_path = root / "active_ua.json"
    prev_proxy = ""
    if ua_path.is_file():
        try:
            prev_proxy = str(json.loads(ua_path.read_text(encoding="utf-8")).get("proxy_id", ""))
        except Exception:
            prev_proxy = "corrupt"

    if apply:
        root.mkdir(parents=True, exist_ok=True)
        ua_path.write_text(json.dumps(IDLE_ACTIVE_UA, indent=2), encoding="utf-8")

    return {
        "apply": apply,
        "path": str(ua_path),
        "previous_proxy_id": prev_proxy,
        "reset_to_idle": apply,
    }


def clean_test_sessions_db(db_path: Path | None = None, apply: bool = True) -> dict[str, Any]:
    """Purge synthetic smoke/unit-test sessions and fake domain_stats while preserving alerts."""
    target = Path(db_path) if db_path is not None else DEFAULT_SESSIONS_DB
    if not target.is_file():
        return {"exists": False, "sessions_removed": 0, "domain_stats_removed": 0}

    with sqlite3.connect(target, timeout=15.0) as con:
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "sessions" not in tables:
            return {"exists": True, "sessions_removed": 0, "domain_stats_removed": 0}

        dom_ph = ",".join("?" for _ in SYNTHETIC_DOMAINS)
        px_ph = ",".join("?" for _ in SYNTHETIC_PROXIES)
        sess_where = (
            f"domain IN ({dom_ph}) "
            f"OR proxy_id IN ({px_ph}) "
            "OR proxy_id LIKE 'mobile:1.39.%' "
            "OR proxy_id LIKE 'mobile:49.36.%'"
        )
        sess_params = (*SYNTHETIC_DOMAINS, *SYNTHETIC_PROXIES)

        before_sessions = int(con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        matched_sessions = int(con.execute(f"SELECT COUNT(*) FROM sessions WHERE {sess_where}", sess_params).fetchone()[0])

        ds_before = int(con.execute("SELECT COUNT(*) FROM domain_stats").fetchone()[0]) if "domain_stats" in tables else 0
        ds_removed = 0
        daily_removed = 0

        if apply:
            con.execute(f"DELETE FROM sessions WHERE {sess_where}", sess_params)
            remaining_sessions = int(con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

            if "domain_stats" in tables:
                if remaining_sessions == 0:
                    ds_removed = ds_before
                    con.execute("DELETE FROM domain_stats")
                else:
                    cur_ds = con.execute(
                        f"DELETE FROM domain_stats WHERE domain IN ({dom_ph}) "
                        "OR (domain = 'tazaloan.com' AND sessions = 150 AND ad_clicks = 6 AND impressions = 160)",
                        SYNTHETIC_DOMAINS,
                    )
                    ds_removed = cur_ds.rowcount

            if "daily_stats" in tables and remaining_sessions == 0:
                daily_removed = int(con.execute("SELECT COUNT(*) FROM daily_stats").fetchone()[0])
                con.execute("DELETE FROM daily_stats")

            con.commit()
        else:
            remaining_sessions = before_sessions - matched_sessions

    return {
        "exists": True,
        "apply": apply,
        "sessions_before": before_sessions,
        "sessions_removed": matched_sessions,
        "sessions_remaining": remaining_sessions,
        "domain_stats_removed": ds_removed,
        "daily_stats_removed": daily_removed,
    }


def run_layer4_cleanup(
    state_dir: Path | None = None,
    sessions_db_path: Path | None = None,
    apply: bool = True,
) -> dict[str, Any]:
    """Execute the full Layer 4 state cleanup, circuit breaker reset, and DB test purge."""
    return {
        "state_files": clean_state_dir(state_dir=state_dir, apply=apply),
        "circuit_breaker": reset_circuit_breaker(state_dir=state_dir, apply=apply),
        "active_ua": reset_active_ua_file(state_dir=state_dir, apply=apply),
        "sessions_db": clean_test_sessions_db(db_path=sessions_db_path, apply=apply),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 4 state/ cleanup & session reset")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup (default is dry-run preview)")
    args = parser.parse_args()

    result = run_layer4_cleanup(apply=args.apply)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not args.apply:
        print("\n[Dry-Run] Re-run with --apply to execute cleanup.")


if __name__ == "__main__":
    main()
