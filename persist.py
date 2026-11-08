"""
persist.py — Per-proxy storage_state (cookies + localStorage) carry-over.
"""
from __future__ import annotations

import logging
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
    if not path.exists():
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


def has_state(proxy_id: str) -> bool:
    """Check whether a saved state exists for this proxy."""
    return _state_path(proxy_id).exists()


def clear(proxy_id: str) -> None:
    """Delete the saved state for a proxy (e.g. after it's retired)."""
    path = _state_path(proxy_id)
    if path.exists():
        path.unlink()
        logger.debug("Cleared state for %s", proxy_id)

