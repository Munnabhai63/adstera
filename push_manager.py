"""
push_manager.py — Layer 6: Real Push Notification Foundation & Collection Engine

Integrates:
1. Pure-Python NIST P-256 VAPID keys (`vapid_keys.py`) for W3C Web Push subscription collection
2. Optional OneSignal Web SDK v16 + REST API (`OneSignalPushClient`) with global & per-domain App IDs
3. Testing-phase safety lock (`collect_only=True`, `delivery_enabled=False`):
   - Collects real PushSubscription / permission events
   - Blocks outbound push delivery campaigns while testing mode is active
4. Playwright session permission & browser PushManager subscription capture (GDPR EU/UK safe)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

import vapid_keys

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_NETWORK_STATE_PATH = PROJECT_ROOT / "state" / "push_network.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
ONESIGNAL_API_BASE = "https://api.onesignal.com"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DUMMY_IDS = {
    "00000000-0000-0000-0000-000000000000",
    "11111111-1111-1111-1111-111111111111",
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
}

# EU/UK country codes — skip push prompts in GDPR zones unless CMP was accepted
_EU_UK_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK", "GB", "NO", "IS", "LI",
}


def _clean_domain(domain: str) -> str:
    clean = (domain or "").strip().lower()
    clean = clean.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    if clean.startswith("www."):
        clean = clean[4:]
    return clean


def _read_yaml_cfg() -> dict[str, Any]:
    if DEFAULT_CONFIG_PATH.is_file():
        try:
            return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}


def is_valid_onesignal_app_id(app_id: str) -> bool:
    cand = (app_id or "").strip()
    if not _UUID_RE.match(cand):
        return False
    return cand.lower() not in _DUMMY_IDS


class OneSignalPushClient:
    """
    Manages OneSignal Web SDK v16 credentials and REST API interactions.
    Outbound notification delivery is strictly gated by `delivery_enabled=False`
    / `collect_only=True` during the testing phase.
    """

    def __init__(
        self,
        cfg: Optional[dict[str, Any]] = None,
        state_path: Optional[Path | str] = None,
        app_id: Optional[str] = None,
        rest_api_key: Optional[str] = None,
    ) -> None:
        self.cfg = cfg if cfg is not None else _read_yaml_cfg()
        pn_cfg = self.cfg.get("push_notifications", {}) or {}
        os_cfg = pn_cfg.get("onesignal", {}) or {}

        self.state_path = Path(state_path or pn_cfg.get("network_state_path") or DEFAULT_NETWORK_STATE_PATH)
        self.collect_only: bool = bool(pn_cfg.get("collect_only", True))
        self.delivery_enabled: bool = bool(pn_cfg.get("delivery_enabled", False))
        self.enabled: bool = bool(os_cfg.get("enabled", True))

        saved = self._load_state()
        cfg_domains = os_cfg.get("domain_app_ids") or {}
        saved_domains = saved.get("domain_app_ids") or {}
        merged_domains: dict[str, str] = {}
        for src in (cfg_domains, saved_domains):
            if isinstance(src, dict):
                for k, v in src.items():
                    if is_valid_onesignal_app_id(str(v)):
                        merged_domains[_clean_domain(str(k))] = str(v).strip()

        raw_app = (
            app_id
            or os.getenv("ONESIGNAL_APP_ID", "")
            or saved.get("app_id", "")
            or os_cfg.get("app_id", "")
        ).strip()
        self.app_id: str = raw_app if is_valid_onesignal_app_id(raw_app) else ""
        self.rest_api_key: str = (
            rest_api_key
            or os.getenv("ONESIGNAL_REST_API_KEY", "")
            or saved.get("rest_api_key", "")
        ).strip()
        self.domain_app_ids: dict[str, str] = merged_domains

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception as exc:
                logger.warning("Could not load push network state %s: %s", self.state_path, exc)
        return {}

    def _save_state(self, data: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_app_id(self, domain: str = "") -> str:
        clean = _clean_domain(domain)
        if clean and clean in self.domain_app_ids:
            return self.domain_app_ids[clean]
        return self.app_id

    def is_configured(self, domain: str = "") -> bool:
        return bool(self.get_app_id(domain))

    def save_credentials(
        self,
        app_id: str = "",
        rest_api_key: str = "",
        domain: str = "",
        domain_app_ids: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Validate and persist OneSignal App IDs / REST API Key into gitignored state/."""
        existing = self._load_state()
        dom_map = dict(existing.get("domain_app_ids") or {})

        clean_app = (app_id or "").strip()
        clean_dom = _clean_domain(domain)
        if clean_app:
            if not is_valid_onesignal_app_id(clean_app):
                raise ValueError("Invalid OneSignal App ID (expected non-dummy UUID v4 format).")
            if clean_dom:
                dom_map[clean_dom] = clean_app
            else:
                existing["app_id"] = clean_app
                self.app_id = clean_app

        if domain_app_ids:
            for k, v in domain_app_ids.items():
                val = str(v or "").strip()
                if not val:
                    continue
                if not is_valid_onesignal_app_id(val):
                    raise ValueError(f"Invalid OneSignal App ID for {k}: expected UUID v4.")
                dom_map[_clean_domain(str(k))] = val

        clean_rest = (rest_api_key or "").strip()
        if clean_rest:
            lower_rest = clean_rest.lower()
            if len(clean_rest) < 16 or "placeholder" in lower_rest or "dummy" in lower_rest:
                raise ValueError("Invalid OneSignal REST API key.")
            existing["rest_api_key"] = clean_rest
            self.rest_api_key = clean_rest

        if not existing.get("app_id") and not dom_map:
            raise ValueError("Provide a valid OneSignal App ID (global or per-domain).")

        existing["domain_app_ids"] = dom_map
        existing["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.domain_app_ids = dom_map
        self._save_state(existing)
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        """Return safe OneSignal configuration status (never returns raw rest_api_key)."""
        configured = bool(self.app_id or self.domain_app_ids)
        return {
            "provider": "onesignal+vapid" if configured else "vapid_local",
            "configured": configured,
            "app_id": self.app_id,
            "domain_app_ids": dict(self.domain_app_ids),
            "domain_overrides_count": len(self.domain_app_ids),
            "rest_api_key_configured": bool(self.rest_api_key),
            "collect_only": self.collect_only,
            "delivery_enabled": self.delivery_enabled,
            "delivery_locked": bool(self.collect_only or not self.delivery_enabled),
            "state_path": str(self.state_path),
        }

    def fetch_app_stats(
        self,
        domain: str = "",
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """Fetch real subscriber totals from OneSignal API if App ID & REST key exist."""
        target_app = self.get_app_id(domain)
        if not target_app:
            return {"configured": False, "data_source": "unconfigured", "players": 0, "messageable_players": 0}
        if not self.rest_api_key:
            return {
                "configured": True,
                "app_id": target_app,
                "data_source": "sdk_collection_only",
                "players": 0,
                "messageable_players": 0,
                "note": "OneSignal Web SDK App ID active; add REST API Key to sync remote player counts.",
            }

        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.get(
                f"{ONESIGNAL_API_BASE}/apps/{target_app}",
                headers={"Authorization": f"Key {self.rest_api_key}", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return {
                    "configured": True,
                    "app_id": target_app,
                    "data_source": "api_error",
                    "http_code": resp.status_code,
                    "error": resp.text[:200],
                    "players": 0,
                    "messageable_players": 0,
                }
            body = resp.json()
            return {
                "configured": True,
                "app_id": target_app,
                "data_source": "onesignal_api",
                "name": body.get("name", ""),
                "players": int(body.get("players", 0) or 0),
                "messageable_players": int(body.get("messageable_players", 0) or 0),
            }
        except Exception as exc:
            return {
                "configured": True,
                "app_id": target_app,
                "data_source": "api_error",
                "error": str(exc),
                "players": 0,
                "messageable_players": 0,
            }
        finally:
            if own_client:
                http.close()

    def send_campaign(
        self,
        title: str,
        message: str,
        url: str,
        domain: str = "",
        collect_only: Optional[bool] = None,
        delivery_enabled: Optional[bool] = None,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """
        Send a push campaign via OneSignal REST API.
        HARD LOCKED during testing phase (`collect_only=True` or `delivery_enabled=False`):
        refuses outbound push delivery so we only collect subscriptions cleanly.
        """
        is_collect_only = self.collect_only if collect_only is None else bool(collect_only)
        is_delivery_on = self.delivery_enabled if delivery_enabled is None else bool(delivery_enabled)
        if is_collect_only or not is_delivery_on:
            logger.info("Push delivery blocked by testing-phase collect-only lock (domain=%s).", domain or "fleet")
            return {
                "ok": False,
                "delivered": False,
                "status": "blocked_testing_phase",
                "collect_only": is_collect_only,
                "delivery_enabled": is_delivery_on,
                "reason": "Testing phase collect-only lock active: subscriptions are collected, delivery is disabled.",
            }

        target_app = self.get_app_id(domain)
        if not target_app or not self.rest_api_key:
            return {
                "ok": False,
                "delivered": False,
                "status": "unconfigured",
                "reason": "OneSignal App ID and REST API Key are required for live push delivery.",
            }

        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            payload = {
                "app_id": target_app,
                "included_segments": ["Subscribed Users"],
                "headings": {"en": title},
                "contents": {"en": message},
                "url": url,
            }
            resp = http.post(
                f"{ONESIGNAL_API_BASE}/notifications",
                headers={
                    "Authorization": f"Key {self.rest_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code in (200, 201):
                body = resp.json()
                return {
                    "ok": True,
                    "delivered": True,
                    "status": "sent",
                    "id": body.get("id", ""),
                    "recipients": int(body.get("recipients", 0) or 0),
                }
            return {
                "ok": False,
                "delivered": False,
                "status": "api_error",
                "http_code": resp.status_code,
                "error": resp.text[:200],
            }
        finally:
            if own_client:
                http.close()


class PushManager:
    """
    Manages push notification subscription collection for a browser session.

    Attributes:
        trigger_prob: Probability (0-1) a session will trigger push handling (default 0.175 = 17.5%)
        allow_prob:   Given trigger, probability of granting (Allow) vs blocking (default 0.78)
        min_delay_s:  Minimum seconds on page before triggering prompt (default 7.0)
        max_delay_s:  Maximum seconds on page before triggering prompt (default 25.0)
        collect_only: Testing-phase flag (True = collect subscriptions only, block delivery)
        delivery_enabled: Must be False during testing phase
    """

    def __init__(
        self,
        trigger_prob: float = 0.175,
        allow_prob: float = 0.78,
        min_delay_s: float = 7.0,
        max_delay_s: float = 25.0,
        collect_only: bool = True,
        delivery_enabled: bool = False,
        vapid_public_key: str = "",
        onesignal_client: Optional[OneSignalPushClient] = None,
    ) -> None:
        self.trigger_prob = trigger_prob
        self.allow_prob = allow_prob
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self.collect_only = bool(collect_only)
        self.delivery_enabled = bool(delivery_enabled)
        self.vapid_public_key = vapid_public_key
        self.onesignal = onesignal_client

    def _resolve_vapid_public_key(self) -> str:
        if self.vapid_public_key:
            return self.vapid_public_key
        try:
            return vapid_keys.load_or_create_vapid_keys()["public_key"]
        except Exception:
            return ""

    def should_trigger(self, rng: random.Random) -> bool:
        """Returns True if this session should handle push notification prompt."""
        return rng.random() < self.trigger_prob

    def should_allow(self, rng: random.Random) -> bool:
        """Returns True if the simulated user should click Allow (vs Block/Dismiss)."""
        return rng.random() < self.allow_prob

    def dispatch_campaign_guarded(
        self,
        title: str,
        message: str,
        url: str,
        domain: str = "",
    ) -> dict[str, Any]:
        """Guarded campaign helper — strictly blocks delivery while collect_only=True or delivery_enabled=False."""
        client = self.onesignal or OneSignalPushClient()
        return client.send_campaign(
            title=title,
            message=message,
            url=url,
            domain=domain,
            collect_only=self.collect_only,
            delivery_enabled=self.delivery_enabled,
        )

    async def handle(
        self,
        context,
        page,
        rng: random.Random,
        proxy_country: str = "",
        cmp_accepted: bool = True,
        domain: str = "loanraaj.com",
    ) -> dict[str, Any]:
        """
        Handle push notification permission collection for this session.

        Returns a result dict preserving backwards compatibility and carrying
        Layer 6 subscription metadata (`subscription`, `collect_only`).
        """
        result: dict[str, Any] = {
            "triggered": False,
            "action": "skipped",
            "delay_s": 0.0,
            "timestamp": time.time(),
            "domain": domain,
            "collect_only": self.collect_only,
            "subscription": None,
        }

        country_up = (proxy_country or "").upper()
        if country_up in _EU_UK_COUNTRIES and not cmp_accepted:
            result["action"] = "eu_skip"
            logger.debug("Push: Skipping EU/UK geo (%s) without CMP accept", country_up)
            return result

        if not self.should_trigger(rng):
            result["action"] = "skipped"
            return result

        delay = rng.uniform(self.min_delay_s, self.max_delay_s)
        result["triggered"] = True
        result["delay_s"] = delay

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            result["action"] = "skipped"
            return result

        if self.should_allow(rng):
            result["action"] = "allow"
            try:
                await context.grant_permissions(["notifications"])
                logger.info(
                    "Push: Granted notification permission on %s (delay=%.1fs, collect_only=%s)",
                    domain,
                    delay,
                    self.collect_only,
                )
                sub_info = await _trigger_push_subscription_js(
                    page,
                    rng,
                    domain,
                    vapid_public_key=self._resolve_vapid_public_key(),
                )
                if isinstance(sub_info, dict) and sub_info.get("subscription"):
                    result["subscription"] = sub_info["subscription"]
            except Exception as exc:
                logger.debug("Push: grant_permissions failed: %s", exc)
                result["action"] = "allow_failed"
        else:
            result["action"] = "block"
            try:
                await context.clear_permissions()
                logger.debug("Push: Blocked notification permission on %s (delay=%.1fs)", domain, delay)
            except Exception as exc:
                logger.debug("Push: clear_permissions failed: %s", exc)

        result["timestamp"] = time.time()
        return result


async def _trigger_push_subscription_js(
    page,
    rng: random.Random,
    domain: str,
    vapid_public_key: str = "",
) -> dict[str, Any]:
    """
    After granting notification permission, inspect or create the browser's W3C PushSubscription
    (or OneSignal subscription metadata) using our VAPID `applicationServerKey` without dispatching
    any outbound notification messages.
    """
    try:
        await asyncio.sleep(rng.uniform(0.2, 0.8))

        result = await page.evaluate(
            """
            async (vapidPubKey) => {
                try {
                    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') {
                        return { ok: false, reason: 'permission_not_granted' };
                    }
                    if (!('serviceWorker' in navigator)) {
                        return { ok: false, reason: 'no_sw' };
                    }
                    const cfg = window.__ADSTERRA_PUSH__ || {};
                    const appKey = vapidPubKey || cfg.vapidPublicKey || '';
                    let sub = window.__PUSH_SUBSCRIPTION__ || null;

                    if (!sub && appKey && navigator.serviceWorker.getRegistration) {
                        try {
                            const reg = (await navigator.serviceWorker.getRegistration('/'))
                                || (await navigator.serviceWorker.getRegistration());
                            if (reg && reg.pushManager) {
                                let existing = await reg.pushManager.getSubscription();
                                if (!existing && appKey.length >= 80) {
                                    const pad = '='.repeat((4 - (appKey.length % 4)) % 4);
                                    const b64 = (appKey + pad).replace(/-/g, '+').replace(/_/g, '/');
                                    const raw = atob(b64);
                                    const bytes = new Uint8Array(raw.length);
                                    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                                    existing = await reg.pushManager.subscribe({
                                        userVisibleOnly: true,
                                        applicationServerKey: bytes
                                    });
                                }
                                if (existing && existing.toJSON) {
                                    const j = existing.toJSON();
                                    sub = {
                                        provider: cfg.onesignalAppId ? 'onesignal' : 'vapid_local',
                                        endpoint: j.endpoint || existing.endpoint || '',
                                        p256dh: (j.keys && j.keys.p256dh) || '',
                                        auth: (j.keys && j.keys.auth) || '',
                                        subscription_id: cfg.onesignalAppId || ''
                                    };
                                    window.__PUSH_SUBSCRIPTION__ = sub;
                                }
                            }
                        } catch (_subErr) {
                            // Expected in headless/fixture origins without FCM push service connectivity
                        }
                    }

                    return {
                        ok: true,
                        permission: Notification.permission,
                        swReady: true,
                        subscription: sub,
                    };
                } catch (e) {
                    return { ok: false, reason: String(e) };
                }
            }
            """,
            vapid_public_key or "",
        )
        logger.debug("Push JS eval result for %s: %s", domain, result)
        return result if isinstance(result, dict) else {"ok": False}
    except Exception as exc:
        logger.debug("Push JS trigger failed for %s: %s", domain, exc)
        return {"ok": False, "reason": str(exc)}


def build_from_config(cfg: dict) -> PushManager:
    """Build a PushManager from the config.yaml push_notifications block."""
    pn_cfg = (cfg or {}).get("push_notifications", {}) or {}
    vapid_path = pn_cfg.get("vapid_keys_path") or vapid_keys.DEFAULT_VAPID_STATE_PATH
    vapid_pub = ""
    try:
        vapid_pub = vapid_keys.load_or_create_vapid_keys(
            state_path=vapid_path,
            subject=pn_cfg.get("vapid_subject") or vapid_keys.DEFAULT_VAPID_SUBJECT,
        )["public_key"]
    except Exception as exc:
        logger.debug("Could not preload VAPID public key: %s", exc)

    return PushManager(
        trigger_prob=float(pn_cfg.get("trigger_prob", 0.175)),
        allow_prob=float(pn_cfg.get("allow_prob", 0.78)),
        min_delay_s=float(pn_cfg.get("min_delay_s", 7.0)),
        max_delay_s=float(pn_cfg.get("max_delay_s", 25.0)),
        collect_only=bool(pn_cfg.get("collect_only", True)),
        delivery_enabled=bool(pn_cfg.get("delivery_enabled", False)),
        vapid_public_key=vapid_pub,
        onesignal_client=OneSignalPushClient(cfg=cfg),
    )
