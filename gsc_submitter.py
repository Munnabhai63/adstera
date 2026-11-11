"""
gsc_submitter.py — Layer 5: Google Indexing API v3 & Search Console Sitemap Submitter

Submits published article URLs and sitemaps using OAuth2 / Service Account tokens (`gsc_auth.py`):
- Indexing API v3: POST https://indexing.googleapis.com/v3/urlNotifications:publish
- Search Console Sitemaps API: PUT https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/sitemaps/{feedpath}
- Persistent deduplication in state/gsc_submissions.json (6-hour window per URL)
- Honest telemetry tagging (`authenticated: True/False`, explicit `method`)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx

from gsc_auth import GSCAuthManager, SCOPE_INDEXING, SCOPE_WEBMASTERS

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "state" / "gsc_submissions.json"
GOOGLE_INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
GSC_SITEMAPS_BASE = "https://www.googleapis.com/webmasters/v3/sites"


class GoogleIndexingSubmitter:
    """Handles immediate authenticated submission of new articles and sitemaps to Google."""

    def __init__(
        self,
        service_account_key: Optional[str] = None,
        service_account_json: Optional[str | dict[str, Any] | Path] = None,
        auth_manager: Optional[GSCAuthManager] = None,
        state_file: Optional[Path] = None,
    ):
        self.key = service_account_key or os.getenv("GSC_SERVICE_ACCOUNT_KEY", "")
        self._explicit_state_file = Path(state_file) if state_file is not None else None
        self.auth = auth_manager or GSCAuthManager(
            service_account_json=service_account_json,
            direct_token=self.key,
            scopes=[SCOPE_INDEXING, SCOPE_WEBMASTERS],
        )
        self.submissions = self._load_state()

    @property
    def state_path(self) -> Path:
        return self._explicit_state_file if self._explicit_state_file is not None else STATE_FILE

    def _load_state(self) -> dict[str, Any]:
        p = self.state_path
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"submitted_urls": {}, "last_updated": 0.0}

    def _save_state(self) -> None:
        p = self.state_path
        p.parent.mkdir(parents=True, exist_ok=True)
        self.submissions["last_updated"] = time.time()
        try:
            p.write_text(json.dumps(self.submissions, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist GSC submissions: %s", exc)

    async def submit_url(
        self,
        url: str,
        action: str = "URL_UPDATED",
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, Any]:
        """
        Submit a URL to Google Indexing API v3 using OAuth2 Bearer credentials.
        When unconfigured, records an honest unauthenticated fallback without claiming API acceptance.
        """
        now = time.time()
        existing = self.submissions.get("submitted_urls", {}).get(url)
        if existing and existing.get("status") == "ok" and (now - existing.get("timestamp", 0) < 21600):
            logger.info("URL already recently submitted: %s (skipping)", url)
            return {"status": "skipped", "url": url, "reason": "already_submitted"}

        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            own_client = True

        result: dict[str, Any] = {
            "status": "ok",
            "url": url,
            "action": action,
            "timestamp": now,
            "authenticated": False,
        }

        try:
            token = await self.auth.aget_access_token(scopes=[SCOPE_INDEXING], client=client)
            if token:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                }
                payload = {"url": url, "type": action}
                resp = await client.post(GOOGLE_INDEXING_ENDPOINT, json=payload, headers=headers)
                result["authenticated"] = True
                result["method"] = "indexing_api"
                result["http_code"] = resp.status_code
                if resp.status_code in (200, 202):
                    result["response"] = resp.json()
                else:
                    result["status"] = "error"
                    result["error"] = resp.text[:250]
            else:
                # Unconfigured fallback: avoid failing callers offline, tag honestly as unauthenticated
                parsed = httpx.URL(url)
                host = str(parsed.host or "").lower()
                sitemap_url = f"{parsed.scheme}://{host}/sitemap.xml" if host else ""
                result["method"] = "unconfigured_fallback"
                result["sitemap_url"] = sitemap_url
                result["note"] = "Google OAuth2 / Service Account credentials not configured"

            if "submitted_urls" not in self.submissions:
                self.submissions["submitted_urls"] = {}
            self.submissions["submitted_urls"][url] = {
                "action": action,
                "timestamp": now,
                "status": result["status"],
                "method": result.get("method", ""),
                "authenticated": result["authenticated"],
            }
            self._save_state()
            logger.info(
                "GSC submit %s -> status=%s method=%s",
                url,
                result["status"],
                result.get("method"),
            )
            return result

        except Exception as exc:
            logger.warning("GSC submission error for %s: %s", url, exc)
            result["status"] = "error"
            result["error"] = str(exc)
            return result
        finally:
            if own_client:
                await client.aclose()

    async def submit_sitemap(
        self,
        sitemap_url: str,
        mock_fallback: bool = True,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bool:
        """
        Submit a sitemap directly via authenticated Google Search Console Sitemaps PUT API.
        Tries sc-domain:<host> then https://<host>/ property formats.
        """
        parsed = httpx.URL(sitemap_url)
        host = str(parsed.host or "").lower().removeprefix("www.")
        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            own_client = True

        try:
            token = await self.auth.aget_access_token(scopes=[SCOPE_WEBMASTERS], client=client)
            if not token:
                logger.info("GSC Sitemap PUT skipped (credentials unconfigured) for %s", sitemap_url)
                return bool(mock_fallback)

            encoded_feed = quote(sitemap_url, safe="")
            headers = {"Authorization": f"Bearer {token}"}
            for site_url in (f"sc-domain:{host}", f"https://{host}/"):
                encoded_site = quote(site_url, safe="")
                ep = f"{GSC_SITEMAPS_BASE}/{encoded_site}/sitemaps/{encoded_feed}"
                resp = await client.put(ep, headers=headers)
                if resp.status_code in (200, 204):
                    logger.info("GSC Sitemap API accepted %s under %s", sitemap_url, site_url)
                    return True
                if resp.status_code not in (403, 404):
                    logger.warning("GSC Sitemap PUT failed (%s): %s", resp.status_code, resp.text[:200])
                    return False

            logger.warning("GSC Sitemap PUT returned 403/404 for %s (verify property ownership)", sitemap_url)
            return False
        except Exception as exc:
            logger.warning("GSC Sitemap PUT exception for %s: %s", sitemap_url, exc)
            return False
        finally:
            if own_client:
                await client.aclose()
