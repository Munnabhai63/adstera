"""
email_client.py — High-Performance Disposable & Verification Email Client with Sonjj API Integration.

Features:
- Connects to Sonjj / SmailPro API (https://app.sonjj.com) using X-Api-Key.
- Strict Credit-Guard System:
    * Hard daily quota cap to prevent accidental balance exhaustion.
    * SQLite persistence & email reuse cache (reuses active emails up to max_uses).
    * Automated fallback to high-intent synthetic personas from accounts_manager.py.
- Verification & OTP extraction from inboxes for high-payout CPL/CPA advertiser offers.
"""

from __future__ import annotations

import datetime
import logging
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

import db

logger = logging.getLogger(__name__)

SONJJ_API_BASE = "https://app.sonjj.com"


class SonjjEmailClient:
    """Production client for Sonjj / SmailPro email generation with rigorous credit guards."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.api_key = self._resolve_api_key()
        self.cached_domains: List[str] = []

        cfg = self.config.get("email_service", {})
        self.enabled = cfg.get("enabled", True)
        self.daily_limit = int(cfg.get("daily_limit", 10))
        self.max_uses_per_email = int(cfg.get("max_uses_per_email", 3))
        self.expiry_minutes = int(cfg.get("expiry_minutes", 1440))  # 24 hours default
        self.test_mode = bool(cfg.get("test_mode", False))

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config for email_client: %s", e)
        return {}

    def _resolve_api_key(self) -> str:
        # Priority 1: Environment variable
        env_key = os.environ.get("SONJJ_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

        # Priority 2: Check .env file directly
        env_file = Path(".env")
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("SONJJ_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
            except Exception:
                pass

        # Priority 3: config.yaml
        cfg_key = self.config.get("email_service", {}).get("api_key")
        if cfg_key and isinstance(cfg_key, str) and cfg_key.strip():
            return cfg_key.strip()

        return ""

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "LoanRaaj-EmailClient/1.0",
        }

    # =========================================================================
    # Credit-Guard & Caching Subsystem
    # =========================================================================

    def _count_creations_today(self) -> int:
        """Count how many real emails were created today from Sonjj API."""
        try:
            with db._conn() as con:
                row = con.execute(
                    """
                    SELECT COUNT(*) as cnt FROM email_cache 
                    WHERE provider = 'sonjj' 
                    AND date(created_at) = date('now', '+5 hours', '30 minutes')
                    """
                ).fetchone()
                return int(row["cnt"]) if row else 0
        except Exception as e:
            logger.error("Failed to query today's email creation count: %s", e)
            return 999  # Fail-safe: assume limit reached to protect credits

    def _get_active_cached_email(self) -> Optional[Dict[str, Any]]:
        """Find an active cached email that has not exceeded max reuse count and is not expired."""
        try:
            with db._conn() as con:
                row = con.execute(
                    """
                    SELECT id, email, domain, use_count, expires_at 
                    FROM email_cache 
                    WHERE is_active = 1 
                    AND use_count < ? 
                    AND datetime(expires_at) > datetime('now', '+5 hours', '30 minutes')
                    ORDER BY use_count ASC, id DESC LIMIT 1
                    """,
                    (self.max_uses_per_email,),
                ).fetchone()
                if row:
                    # Increment use count
                    con.execute(
                        """
                        UPDATE email_cache 
                        SET use_count = use_count + 1, 
                            last_used_at = datetime('now', '+5 hours', '30 minutes')
                        WHERE id = ?
                        """,
                        (row["id"],),
                    )
                    return dict(row)
        except Exception as e:
            logger.warning("Failed to retrieve cached email: %s", e)
        return None

    def _save_email_to_cache(self, email: str, domain: str, expiry_minutes: int) -> None:
        """Store newly provisioned email in local SQLite cache."""
        try:
            with db._conn() as con:
                expires_at = (
                    datetime.datetime.now() + datetime.timedelta(minutes=expiry_minutes)
                ).strftime("%Y-%m-%d %H:%M:%S")
                con.execute(
                    """
                    INSERT INTO email_cache (email, domain, provider, expires_at, use_count, is_active)
                    VALUES (?, ?, 'sonjj', ?, 0, 1)
                    ON CONFLICT(email) DO UPDATE SET 
                        use_count = 0,
                        expires_at = excluded.expires_at,
                        is_active = 1
                    """,
                    (email, domain, expires_at),
                )
        except Exception as e:
            logger.warning("Failed to cache email %s: %s", email, e)

    # =========================================================================
    # Domain & Email Provisioning
    # =========================================================================

    def get_allowed_domains(self) -> List[str]:
        """Fetch allowed domains from Sonjj API (cached in-memory)."""
        if self.cached_domains:
            return self.cached_domains

        if not self.api_key or self.test_mode:
            return ["momroad.org", "bussaco.com", "comproa.org", "brajraj.org"]

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{SONJJ_API_BASE}/v1/temp_email/domains", headers=self._get_headers())
                if res.status_code == 200:
                    domains = res.json().get("domains", [])
                    if domains:
                        self.cached_domains = domains
                        return domains
        except Exception as e:
            logger.warning("Sonjj get_allowed_domains failed: %s", e)

        return ["momroad.org", "bussaco.com", "comproa.org", "brajraj.org"]

    def create_or_reuse_email(
        self,
        prefix_hint: str = "",
        force_new: bool = False,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """
        Credit-Guarded Email Provisioner.
        1. Check active cache: if available and !force_new, reuse cached email (0 credit cost).
        2. Check daily credit limit: if today's creations >= daily_limit, return synthetic persona (0 credit cost).
        3. Call Sonjj API to create real temporary email, cache it, and return.
        """
        rng = rng or random.Random()

        # Step 0: Immediate test mode / disabled guard (guarantees zero real calls or side effects)
        if self.test_mode or not self.enabled or not self.api_key:
            from accounts_manager import AccountsManager
            acc_mgr = AccountsManager()
            acc = acc_mgr.generate_synthetic_account()
            return {
                "email": acc.email,
                "domain": acc.email.split("@")[-1],
                "source": "synthetic",
                "is_real": False,
                "persona": acc.persona,
                "name": acc.name,
            }

        # Step 1: Reuse existing active email if possible
        if not force_new:
            cached = self._get_active_cached_email()
            if cached:
                logger.info("[Sonjj Email] Reusing cached email '%s' (uses: %d/%d) — 0 credits spent", 
                            cached["email"], cached["use_count"], self.max_uses_per_email)
                return {
                    "email": cached["email"],
                    "domain": cached["domain"],
                    "source": "cache",
                    "is_real": True,
                }

        # Step 2: Check Daily Credit Cap Guard
        today_creations = self._count_creations_today()
        if today_creations >= self.daily_limit:
            logger.info("[Sonjj Email] Credit-Guard active (daily_limit_reached, today: %d/%d). Using synthetic persona email.", 
                        today_creations, self.daily_limit)
            from accounts_manager import AccountsManager
            acc_mgr = AccountsManager()
            acc = acc_mgr.generate_synthetic_account()
            return {
                "email": acc.email,
                "domain": acc.email.split("@")[-1],
                "source": "synthetic",
                "is_real": False,
                "persona": acc.persona,
                "name": acc.name,
            }

        # Step 3: Call Sonjj API safely
        try:
            domains = self.get_allowed_domains()
            chosen_domain = rng.choice(domains) if domains else "random.com"

            if prefix_hint:
                clean_prefix = re.sub(r"[^a-zA-Z0-9._-]", "", prefix_hint.lower())
                requested_email = f"{clean_prefix}@{chosen_domain}"
            else:
                requested_email = "random@random.com"

            params = {
                "email": requested_email,
                "expiry_minutes": self.expiry_minutes,
            }

            with httpx.Client(timeout=15.0) as client:
                res = client.get(
                    f"{SONJJ_API_BASE}/v1/temp_email/create",
                    headers=self._get_headers(),
                    params=params,
                )
                if res.status_code == 200:
                    data = res.json()
                    real_email = data.get("email") or requested_email
                    domain = real_email.split("@")[-1]
                    self._save_email_to_cache(real_email, domain, self.expiry_minutes)
                    logger.info("[Sonjj Email] Created real email: %s (Daily spent: %d/%d)", 
                                real_email, today_creations + 1, self.daily_limit)
                    return {
                        "email": real_email,
                        "domain": domain,
                        "source": "sonjj_api",
                        "is_real": True,
                        "raw": data,
                    }
                else:
                    logger.warning("[Sonjj Email] API returned status %d: %s", res.status_code, res.text)
        except Exception as e:
            logger.error("[Sonjj Email] Exception during API call: %s", e)

        # Fallback if API failed
        from accounts_manager import AccountsManager
        acc_mgr = AccountsManager()
        acc = acc_mgr.generate_synthetic_account()
        return {
            "email": acc.email,
            "domain": acc.email.split("@")[-1],
            "source": "synthetic_fallback",
            "is_real": False,
            "persona": acc.persona,
            "name": acc.name,
        }

    # =========================================================================
    # Inbox Polling & Verification / OTP Extraction
    # =========================================================================

    def check_inbox(self, email: str) -> List[Dict[str, Any]]:
        """Check messages in Sonjj inbox."""
        if not self.api_key or self.test_mode or "@" not in email:
            return []

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    f"{SONJJ_API_BASE}/v1/temp_email/inbox",
                    headers=self._get_headers(),
                    params={"email": email},
                )
                if res.status_code == 200:
                    data = res.json()
                    return data.get("messages", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        except Exception as e:
            logger.warning("[Sonjj Email] check_inbox error for %s: %s", email, e)
        return []

    def extract_otp_or_link(self, email: str) -> Dict[str, Optional[str]]:
        """Poll inbox and extract OTP or verification link from the latest message."""
        messages = self.check_inbox(email)
        if not messages:
            return {"otp": None, "link": None}

        latest = messages[0]
        content = str(latest.get("content") or latest.get("body") or latest.get("subject") or "")

        # Heuristic 4 to 6 digit OTP extraction
        otp_match = re.search(r"\b(\d{4,6})\b", content)
        otp = otp_match.group(1) if otp_match else None

        # Link extraction
        link_match = re.search(r"https?://[^\s'\"<>]+(?:verify|confirm|activate|token)[^\s'\"<>]*", content, re.IGNORECASE)
        link = link_match.group(0) if link_match else None

        return {"otp": otp, "link": link, "subject": latest.get("subject")}
