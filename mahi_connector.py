"""
mahi_connector.py — Read-Only Bridge to MAHI Browser Anti-Detect Core.
Integrates 22+ active profiles and custom Chromium engine (138.0.7204.0) with zero tampering.
"""
from __future__ import annotations

import json
import logging
import os
import random
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Strict Host Paths (READ-ONLY ACCESS ONLY)
MAHI_APP_DIR = Path(r"C:\Users\munaf\AppData\Local\Programs\MAHI Browser")
MAHI_DATA_DIR = Path(r"C:\Users\munaf\AppData\Roaming\mahi-browser")
MAHI_CHROME_EXE = MAHI_APP_DIR / "resources" / "engines" / "138.0.7204.0" / "chrome-win" / "chrome.exe"
MAHI_SQLITE_PATH = MAHI_DATA_DIR / "mahi_browser.sqlite"

# Project-Isolated State Directory (ALL session writes happen here, never in MAHI dirs)
PROJECT_ROOT = Path(__file__).parent.resolve()
MAHI_STATE_DIR = PROJECT_ROOT / "state" / "mahi_bridge"
MAHI_PROFILES_STATE_DIR = MAHI_STATE_DIR / "profiles"
MAHI_COOKIES_STATE_DIR = MAHI_STATE_DIR / "cookies"


class MahiBridgeError(Exception):
    """Raised when MAHI Browser bridge encounters an unrecoverable condition."""
    pass


class MahiConnector:
    """Manages read-only profile retrieval and hardened Chromium launch arguments."""

    def __init__(self):
        self._ensure_isolated_dirs()

    def _ensure_isolated_dirs(self) -> None:
        """Create project-isolated directories for cookies and session states."""
        MAHI_STATE_DIR.mkdir(parents=True, exist_ok=True)
        MAHI_PROFILES_STATE_DIR.mkdir(parents=True, exist_ok=True)
        MAHI_COOKIES_STATE_DIR.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        """Check if MAHI custom Chromium and SQLite database are available on host."""
        return MAHI_CHROME_EXE.exists() and MAHI_SQLITE_PATH.exists()

    def get_chrome_executable_path(self) -> str:
        """Return the absolute path to MAHI's custom Chromium binary."""
        if not MAHI_CHROME_EXE.exists():
            raise MahiBridgeError(f"MAHI Chromium binary missing at: {MAHI_CHROME_EXE}")
        return str(MAHI_CHROME_EXE)

    def get_available_profiles(self) -> List[Dict[str, Any]]:
        """
        Reads active hardware profiles from MAHI SQLite in explicit Read-Only mode.
        Guarantees ZERO modifications to MAHI's database.
        """
        if not MAHI_SQLITE_PATH.exists():
            logger.warning("MAHI SQLite DB does not exist at: %s", MAHI_SQLITE_PATH)
            return []

        # Open SQLite with explicit ?mode=ro URI to guarantee zero writes
        uri = f"file:{MAHI_SQLITE_PATH.as_posix()}?mode=ro"
        conn = None
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""
                SELECT p.id, p.name, p.status, p.storage_path, ps.settings_json
                FROM profiles p
                LEFT JOIN profile_settings ps ON p.id = ps.profile_id
                WHERE p.deleted_at IS NULL
            """)
            rows = cur.fetchall()
            profiles = []
            for r in rows:
                settings_raw = r["settings_json"]
                settings = json.loads(settings_raw) if settings_raw else {}
                profiles.append({
                    "id": r["id"],
                    "name": r["name"],
                    "status": r["status"] or "active",
                    "storage_path": r["storage_path"],
                    "settings": settings,
                })
            return profiles
        except Exception as exc:
            logger.error("Failed to read MAHI profiles (read-only): %s", exc)
            return []
        finally:
            if conn:
                conn.close()

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific profile by its UUID."""
        profiles = self.get_available_profiles()
        for p in profiles:
            if p["id"] == profile_id:
                return p
        return None

    def get_random_profile(self, rng: Optional[random.Random] = None) -> Dict[str, Any]:
        """Select a random profile from available active profiles, or generate dynamically."""
        profiles = self.get_available_profiles()
        if not profiles:
            return self.get_dynamic_profile()
        chooser = rng if rng is not None else random
        return chooser.choice(profiles)

    def get_dynamic_profile(
        self,
        account: Optional[Any] = None,
        proxy: Optional[Any] = None,
        seed: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates an unlimited, mathematically coherent MAHI hardware profile on demand."""
        from profile_factory import ProfileFactory
        return ProfileFactory.generate_profile(account=account, proxy=proxy, seed=seed)

    def build_launch_args(
        self,
        proxy_config: Optional[Dict[str, str]] = None,
        lang: str = "en-US",
    ) -> List[str]:
        """
        Assemble hardened launch arguments including WebRTC and DNS leak shields.
        """
        args = [
            # 1. Anti-Automation Suppression
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-default-browser-check",
            "--no-first-run",

            # 2. WebRTC Strict IP Leak Shielding (Mandatory)
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",

            # 3. Language setting
            f"--lang={lang}",

            # 4. Rendering & Hardware Acceleration Integrity
            "--enable-webgl",
            "--enable-accelerated-2d-canvas",
            "--disable-dev-shm-usage",

            # 5. Background Throttling Prevention
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]

        # 6. DNS Leak Prevention: Route ALL DNS resolutions through the proxy
        if proxy_config and "server" in proxy_config:
            server_str = proxy_config["server"]
            parsed = urlparse(server_str if "://" in server_str else f"http://{server_str}")
            proxy_host = parsed.hostname
            if proxy_host:
                args.append(f'--host-resolver-rules="MAP * 0.0.0.0, EXCLUDE {proxy_host}"')

        return args

    def get_profile_context_kwargs(
        self,
        profile: Dict[str, Any],
        proxy_config: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Extract Playwright context parameters (viewport, UA, locale, timezone)
        from a MAHI profile configuration.
        """
        settings = profile.get("settings", {})
        display = settings.get("display", {})
        locale = settings.get("locale", {})
        browser = settings.get("browser", {})

        width = int(display.get("screenWidth", 1920))
        height = int(display.get("screenHeight", 1080))
        user_agent = browser.get("userAgent") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.7204.0 Safari/537.36"
        )
        lang = locale.get("language", "en-US")
        timezone = locale.get("timezone", "America/New_York")
        languages_list = locale.get("languagesList", ["en-US", "en"])

        kwargs: Dict[str, Any] = {
            "viewport": {"width": width, "height": height},
            "user_agent": user_agent,
            "locale": lang,
            "timezone_id": timezone,
            "extra_http_headers": {"Accept-Language": ",".join(languages_list)},
            "ignore_https_errors": True,
        }

        if proxy_config:
            kwargs["proxy"] = proxy_config

        return kwargs

    def get_isolated_user_data_dir(self, profile_id: str) -> Path:
        """Return the project-isolated user data dir for a profile session."""
        path = MAHI_PROFILES_STATE_DIR / profile_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_storage_state_path(self, profile_id: str) -> Path:
        """Return the path to the isolated storage_state (cookies/localStorage) file."""
        return MAHI_COOKIES_STATE_DIR / f"{profile_id}_state.json"

    def has_stored_state(self, profile_id: str) -> bool:
        """Check if an isolated storage state exists for this profile."""
        p = self.get_storage_state_path(profile_id)
        return p.exists() and p.stat().st_size > 10

    async def save_profile_state(self, context: Any, profile_id: str) -> Path:
        """Save the session's storage_state to the isolated project directory."""
        state_path = self.get_storage_state_path(profile_id)
        try:
            await context.storage_state(path=str(state_path))
            logger.debug("Saved isolated session state for profile %s to %s", profile_id, state_path)
        except Exception as exc:
            logger.warning("Could not save storage state for %s: %s", profile_id, exc)
        return state_path

