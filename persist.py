"""
persist.py — Per-proxy storage_state (cookies + localStorage) carry-over.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.async_api import BrowserContext

logger = logging.getLogger(__name__)

_STATE_DIR = Path("state")


def _state_path(proxy_id: str) -> Path:
    safe = proxy_id.replace(":", "_").replace("@", "_").replace("/", "_")
    return _STATE_DIR / f"{safe}.json"


async def save(context: BrowserContext, proxy_id: str) -> None:
    """Persist the browser context's storage state to disk."""
    _STATE_DIR.mkdir(exist_ok=True)
    path = _state_path(proxy_id)
    try:
        await context.storage_state(path=str(path))
        logger.debug("Saved storage state for %s → %s", proxy_id, path)
    except Exception as exc:
        logger.warning("Failed to save state for %s: %s", proxy_id, exc)


async def restore(context: BrowserContext, proxy_id: str) -> bool:
    """
    Restore storage state into an already-open context by injecting cookies.
    Returns True if state was found and applied.
    """
    path = _state_path(proxy_id)
    if not has_state(proxy_id):
        return False

    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        if cookies:
            await context.add_cookies(cookies)
            logger.debug("Restored %d cookies for %s", len(cookies), proxy_id)
        return True
    except Exception as exc:
        logger.warning("Failed to restore state for %s: %s", proxy_id, exc)
        return False


def has_state(proxy_id: str, max_age_days: float = 7.0) -> bool:
    """Check whether a valid, non-expired saved state exists for this proxy (INFRA-2: 7-day TTL)."""
    path = _state_path(proxy_id)
    if not path.exists():
        return False
    try:
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
        if age_days > max_age_days:
            path.unlink(missing_ok=True)
            logger.debug("State expired (%.1f days > %.1f days) for %s — purged", age_days, max_age_days, proxy_id)
            return False
    except Exception:
        pass
    return True


def clear(proxy_id: str) -> None:
    """Delete the saved state for a proxy (e.g. after it's retired)."""
    path = _state_path(proxy_id)
    if path.exists():
        path.unlink()
        logger.debug("Cleared state for %s", proxy_id)



def record_visit(proxy_id: str, target_url: str) -> dict:
    """Record visited page and increment visit count for return visitor profiling (ADV-6)."""
    _STATE_DIR.mkdir(exist_ok=True)
    safe = proxy_id.replace(":", "_").replace("@", "_").replace("/", "_")
    meta_path = _STATE_DIR / f"{safe}_meta.json"
    meta = {"visit_count": 0, "visited_urls": [], "last_visit_ts": 0.0}
    if meta_path.exists():
        try:
            import json
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta["visit_count"] = meta.get("visit_count", 0) + 1
    meta["last_visit_ts"] = time.time()
    urls = meta.get("visited_urls", [])
    if target_url and target_url not in urls:
        urls.append(target_url)
    meta["visited_urls"] = urls[-20:]
    try:
        import json
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass
    return meta


def get_visitor_profile(proxy_id: str) -> dict:
    """Return visitor profile metadata for return visitor behavior (ADV-6)."""
    safe = proxy_id.replace(":", "_").replace("@", "_").replace("/", "_")
    meta_path = _STATE_DIR / f"{safe}_meta.json"
    if meta_path.exists():
        try:
            import json
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"visit_count": 0, "visited_urls": [], "last_visit_ts": 0.0}
