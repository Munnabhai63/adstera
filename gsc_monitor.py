"""
gsc_monitor.py — Layer 5: Real Google Search Console (GSC) API Monitor & Weekly Auto-Report

Monitors organic performance across all 10 publisher domains:
- Real Search Console API v3/v1 calls using OAuth2 / Service Account Bearer tokens (`gsc_auth.py`)
  * Sites List (`GET /webmasters/v3/sites`)
  * Search Analytics (`POST /webmasters/v3/sites/{siteUrl}/searchAnalytics/query`)
  * Sitemaps (`GET /webmasters/v3/sites/{siteUrl}/sitemaps`)
  * URL Inspection (`POST /v1/urlInspection/index:inspect`)
- Honest telemetry tagging (`data_source`: `google_search_console_api` vs `mock_estimate` / `api_error`)
- Automated deindexing detection (only alerts on verified non-mock results)
- Weekly automated GSC performance digest saved to reports/ and sent via Telegram
"""
from __future__ import annotations

import datetime
import hashlib
import html
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
import yaml

from gsc_auth import GSCAuthManager, SCOPE_WEBMASTERS, SCOPE_WEBMASTERS_RO

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
GSC_STATE_PATH = PROJECT_ROOT / "state" / "gsc_metrics.json"
WEEKLY_REPORT_STATE_PATH = PROJECT_ROOT / "state" / "gsc_weekly_report_state.json"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

GSC_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
GSC_SEARCH_ANALYTICS_BASE = "https://searchconsole.googleapis.com/webmasters/v3/sites"
GSC_SITEMAPS_BASE = "https://www.googleapis.com/webmasters/v3/sites"
GSC_URL_INSPECT_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

DEFAULT_DOMAINS = [
    "loanraaj.com", "rechargetak.com", "rechargepur.com", "tazaloan.com",
    "loankiseva.com", "karzseva.com", "loantau.com", "tazabhav.com",
    "tazarokda.com", "rechargekar.com",
]


def _clean_domain(domain: str) -> str:
    return domain.lower().replace("https://", "").replace("http://", "").strip().rstrip("/")


def _default_date_window(days: int = 7) -> tuple[str, str]:
    # GSC finalizes search analytics with a ~2-day delay; querying with dataState=all stays fresh.
    end_d = datetime.date.today() - datetime.timedelta(days=2)
    start_d = end_d - datetime.timedelta(days=max(1, int(days)) - 1)
    return start_d.isoformat(), end_d.isoformat()


class GSCMonitor:
    """Monitors Google Search Console metrics and index health across publisher domains."""

    def __init__(
        self,
        cfg: dict | None = None,
        service_account_json: Optional[str | dict[str, Any] | Path] = None,
        auth_manager: Optional[GSCAuthManager] = None,
        state_path: Optional[Path] = None,
        weekly_state_path: Optional[Path] = None,
    ):
        self.cfg = cfg if cfg is not None else self._read_default_cfg()
        gsc_cfg = self.cfg.get("gsc", {}) or {}
        self.enabled: bool = bool(gsc_cfg.get("enabled", True))
        self.service_account_path = service_account_json or gsc_cfg.get("service_account_json")
        self._explicit_state_path = Path(state_path) if state_path is not None else None
        self.weekly_state_path = Path(weekly_state_path) if weekly_state_path is not None else WEEKLY_REPORT_STATE_PATH
        self.domains: list[str] = self.cfg.get("target", {}).get("domains") or list(DEFAULT_DOMAINS)
        self.auth = auth_manager or GSCAuthManager(
            cfg=self.cfg,
            service_account_json=service_account_json,
            scopes=[SCOPE_WEBMASTERS_RO, SCOPE_WEBMASTERS],
        )
        self._verified_sites_cache: Optional[dict[str, tuple[str, str]]] = None
        self._cached_metrics: dict[str, dict[str, Any]] = {}
        self._load_cache()

    @staticmethod
    def _read_default_cfg() -> dict[str, Any]:
        if CONFIG_PATH.is_file():
            try:
                return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
        return {}

    @property
    def cache_path(self) -> Path:
        return self._explicit_state_path if self._explicit_state_path is not None else GSC_STATE_PATH

    def _mock_estimate(
        self,
        clean_dom: str,
        days: int,
        credentials_configured: bool,
        data_source: str = "mock_estimate",
        api_error: Optional[str] = None,
    ) -> dict[str, Any]:
        h = int(hashlib.md5(clean_dom.encode("utf-8")).hexdigest()[:8], 16)
        base_impressions = 150 + (h % 300)
        base_clicks = int(base_impressions * (0.025 + ((h % 20) / 1000.0)))
        ctr = round(base_clicks / base_impressions, 4) if base_impressions > 0 else 0.0
        avg_pos = round(14.2 + (h % 150) / 10.0, 1)

        return {
            "domain": clean_dom,
            "property_url": "",
            "period_days": days,
            "impressions": base_impressions,
            "clicks": base_clicks,
            "ctr": ctr,
            "avg_position": avg_pos,
            "indexed_pages": 3,
            "is_indexed": True,
            "top_queries": [],
            "quick_wins": [],
            "sitemaps": [],
            "credentials_configured": credentials_configured,
            "is_mock": True,
            "data_source": data_source,
            "api_error": api_error,
            "last_synced": datetime.datetime.now().isoformat(),
        }

    def list_verified_sites(self, client: Optional[httpx.Client] = None) -> list[dict[str, Any]]:
        """Query Google Search Console for all properties accessible to the authenticated identity."""
        token = self.auth.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)
        if not token:
            return []

        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.get(
                GSC_SITES_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.warning("GSC sites list failed (HTTP %s): %s", resp.status_code, resp.text[:200])
                return []
            entries = resp.json().get("siteEntry", []) or []
            domain_map: dict[str, tuple[str, str]] = {}
            for entry in entries:
                site_url = str(entry.get("siteUrl") or "")
                perm = str(entry.get("permissionLevel") or "")
                dom_key = site_url.replace("sc-domain:", "")
                dom_key = _clean_domain(dom_key).removeprefix("www.")
                if not dom_key:
                    continue
                prev = domain_map.get(dom_key)
                # Prefer sc-domain: over URL-prefix properties
                if prev is None or (site_url.startswith("sc-domain:") and not prev[0].startswith("sc-domain:")):
                    domain_map[dom_key] = (site_url, perm)
            self._verified_sites_cache = domain_map
            return entries
        finally:
            if own_client:
                http.close()

    def _candidate_site_urls(self, clean_dom: str, client: Optional[httpx.Client] = None) -> list[str]:
        candidates: list[str] = []
        if self._verified_sites_cache is None:
            try:
                self.list_verified_sites(client=client)
            except Exception as exc:
                logger.debug("Could not pre-fetch verified sites: %s", exc)
        if self._verified_sites_cache and clean_dom in self._verified_sites_cache:
            candidates.append(self._verified_sites_cache[clean_dom][0])
        for fallback in (f"sc-domain:{clean_dom}", f"https://{clean_dom}/", f"https://www.{clean_dom}/"):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def fetch_sitemaps(
        self,
        site_url: str,
        token: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> list[dict[str, Any]]:
        tok = token or self.auth.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)
        if not tok:
            return []
        encoded = quote(site_url, safe="")
        url = f"{GSC_SITEMAPS_BASE}/{encoded}/sitemaps"
        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.get(url, headers={"Authorization": f"Bearer {tok}"})
            if resp.status_code != 200:
                return []
            items = []
            for sm in resp.json().get("sitemap", []) or []:
                submitted_total = 0
                indexed_total = 0
                for content in sm.get("contents", []) or []:
                    submitted_total += int(content.get("submitted", 0) or 0)
                    indexed_total += int(content.get("indexed", 0) or 0)
                items.append({
                    "path": sm.get("path", ""),
                    "last_submitted": sm.get("lastSubmitted", ""),
                    "submitted": submitted_total,
                    "indexed": indexed_total,
                    "warnings": int(sm.get("warnings", 0) or 0),
                    "errors": int(sm.get("errors", 0) or 0),
                })
            return items
        except Exception as exc:
            logger.debug("Sitemap query failed for %s: %s", site_url, exc)
            return []
        finally:
            if own_client:
                http.close()

    def inspect_url(
        self,
        inspection_url: str,
        site_url: Optional[str] = None,
        token: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """Call Google URL Inspection API v1 for authoritative URL indexation truth."""
        tok = token or self.auth.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)
        if not tok:
            return {"status": "unconfigured", "is_indexed": None}
        if not site_url:
            clean = _clean_domain(str(httpx.URL(inspection_url).host or ""))
            site_url = f"sc-domain:{clean}" if clean else ""

        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.post(
                GSC_URL_INSPECT_ENDPOINT,
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                json={"inspectionUrl": inspection_url, "siteUrl": site_url, "languageCode": "en-US"},
            )
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "http_code": resp.status_code,
                    "error": resp.text[:200],
                    "is_indexed": None,
                }
            idx_res = resp.json().get("inspectionResult", {}).get("indexStatusResult", {}) or {}
            verdict = str(idx_res.get("verdict") or "VERDICT_UNSPECIFIED")
            return {
                "status": "ok",
                "verdict": verdict,
                "coverage_state": idx_res.get("coverageState", ""),
                "indexing_state": idx_res.get("indexingState", ""),
                "last_crawl_time": idx_res.get("lastCrawlTime", ""),
                "is_indexed": verdict == "PASS",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "is_indexed": None}
        finally:
            if own_client:
                http.close()

    def _query_search_analytics(
        self,
        http: httpx.Client,
        token: str,
        site_url: str,
        start_date: str,
        end_date: str,
    ) -> tuple[int, dict[str, Any], str]:
        encoded = quote(site_url, safe="")
        endpoint = f"{GSC_SEARCH_ANALYTICS_BASE}/{encoded}/searchAnalytics/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        totals_resp = None
        for attempt in range(2):
            try:
                totals_resp = http.post(
                    endpoint,
                    headers=headers,
                    json={
                        "startDate": start_date,
                        "endDate": end_date,
                        "searchType": "web",
                        "dataState": "all",
                    },
                )
                break
            except Exception as exc:
                if attempt == 1:
                    return 504, {}, f"{type(exc).__name__}: {exc}"[:250]
        if totals_resp is None or totals_resp.status_code != 200:
            code = totals_resp.status_code if totals_resp is not None else 504
            txt = totals_resp.text[:250] if totals_resp is not None else "Timeout"
            return code, {}, txt

        totals_rows = totals_resp.json().get("rows", []) or []
        totals = totals_rows[0] if totals_rows else {}

        detail_rows: list[dict[str, Any]] = []
        try:
            detail_resp = http.post(
                endpoint,
                headers=headers,
                json={
                    "startDate": start_date,
                    "endDate": end_date,
                    "dimensions": ["query", "page"],
                    "rowLimit": 25,
                    "searchType": "web",
                    "dataState": "all",
                },
            )
            if detail_resp.status_code == 200:
                detail_rows = detail_resp.json().get("rows", []) or []
        except Exception as exc:
            logger.debug("Detail query skipped for %s: %s", site_url, exc)
        return 200, {"totals": totals, "rows": detail_rows}, ""

    def fetch_domain_performance(
        self,
        domain: str,
        days: int = 7,
        mock_fallback: bool = True,
        inspect_homepage: bool = False,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """
        Fetch search performance (impressions, clicks, CTR, position) for a domain.
        Calls real Google Search Console APIs when OAuth2 / Service Account credentials are set;
        when unconfigured, honestly tags output as `mock_estimate` (or `unconfigured`).
        """
        clean_dom = _clean_domain(domain)

        try:
            token = self.auth.get_access_token(scopes=[SCOPE_WEBMASTERS_RO], client=client)
        except Exception as auth_exc:
            logger.warning("GSC auth error for %s: %s", clean_dom, auth_exc)
            if mock_fallback:
                res = self._mock_estimate(clean_dom, days, True, data_source="api_error_fallback", api_error=str(auth_exc))
            else:
                res = {
                    "domain": clean_dom,
                    "property_url": "",
                    "period_days": days,
                    "impressions": 0,
                    "clicks": 0,
                    "ctr": 0.0,
                    "avg_position": 0.0,
                    "indexed_pages": 0,
                    "is_indexed": False,
                    "top_queries": [],
                    "quick_wins": [],
                    "sitemaps": [],
                    "credentials_configured": True,
                    "is_mock": False,
                    "data_source": "api_error",
                    "api_error": str(auth_exc),
                    "last_synced": datetime.datetime.now().isoformat(),
                }
            self._cached_metrics[clean_dom] = res
            self._save_cache()
            return res

        if not token:
            if not mock_fallback:
                res = {
                    "domain": clean_dom,
                    "property_url": "",
                    "period_days": days,
                    "impressions": 0,
                    "clicks": 0,
                    "ctr": 0.0,
                    "avg_position": 0.0,
                    "indexed_pages": 0,
                    "is_indexed": None,
                    "top_queries": [],
                    "quick_wins": [],
                    "sitemaps": [],
                    "credentials_configured": False,
                    "is_mock": False,
                    "data_source": "unconfigured",
                    "api_error": "Google OAuth2 / Service Account credentials not configured",
                    "last_synced": datetime.datetime.now().isoformat(),
                }
            else:
                res = self._mock_estimate(clean_dom, days, credentials_configured=False, data_source="mock_estimate")
            self._cached_metrics[clean_dom] = res
            self._save_cache()
            return res

        # Real Google Search Console API Query
        start_date, end_date = _default_date_window(days)
        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            matched_site = ""
            payload: dict[str, Any] = {}
            last_code = 0
            last_err = ""

            for candidate_site in self._candidate_site_urls(clean_dom, client=http):
                code, data, err = self._query_search_analytics(http, token, candidate_site, start_date, end_date)
                last_code, last_err = code, err
                if code == 200:
                    matched_site = candidate_site
                    payload = data
                    break
                if code not in (403, 404):
                    break

            if not matched_site:
                err_msg = f"HTTP {last_code}: {last_err}".strip(": ")
                logger.warning("GSC live query error for %s: %s", clean_dom, err_msg)
                if mock_fallback:
                    res = self._mock_estimate(
                        clean_dom, days, credentials_configured=True, data_source="api_error_fallback", api_error=err_msg
                    )
                else:
                    res = {
                        "domain": clean_dom,
                        "property_url": "",
                        "period_days": days,
                        "impressions": 0,
                        "clicks": 0,
                        "ctr": 0.0,
                        "avg_position": 0.0,
                        "indexed_pages": 0,
                        "is_indexed": False,
                        "top_queries": [],
                        "quick_wins": [],
                        "sitemaps": [],
                        "credentials_configured": True,
                        "is_mock": False,
                        "data_source": "api_error",
                        "api_error": err_msg,
                        "last_synced": datetime.datetime.now().isoformat(),
                    }
                self._cached_metrics[clean_dom] = res
                self._save_cache()
                return res

            totals = payload.get("totals", {}) or {}
            detail_rows = payload.get("rows", []) or []

            impressions = int(round(float(totals.get("impressions", 0) or 0)))
            clicks = int(round(float(totals.get("clicks", 0) or 0)))
            raw_ctr = float(totals.get("ctr", 0.0) or 0.0)
            ctr = round(raw_ctr, 4) if impressions > 0 else 0.0
            avg_pos = round(float(totals.get("position", 0.0) or 0.0), 1)

            top_queries: list[dict[str, Any]] = []
            quick_wins: list[dict[str, Any]] = []
            unique_pages: set[str] = set()
            for r in detail_rows:
                keys = r.get("keys", []) or []
                q_str = str(keys[0]) if len(keys) > 0 else ""
                p_str = str(keys[1]) if len(keys) > 1 else ""
                if p_str:
                    unique_pages.add(p_str)
                q_entry = {
                    "query": q_str,
                    "page": p_str,
                    "clicks": int(round(float(r.get("clicks", 0) or 0))),
                    "impressions": int(round(float(r.get("impressions", 0) or 0))),
                    "ctr": round(float(r.get("ctr", 0.0) or 0.0), 4),
                    "position": round(float(r.get("position", 0.0) or 0.0), 1),
                }
                if len(top_queries) < 5:
                    top_queries.append(q_entry)
                if 5.0 <= q_entry["position"] <= 25.0 and q_entry["impressions"] > 0:
                    quick_wins.append(q_entry)

            quick_wins.sort(key=lambda x: x["impressions"], reverse=True)
            quick_wins = quick_wins[:5]

            sitemaps = self.fetch_sitemaps(matched_site, token=token, client=http)
            sm_indexed = sum(int(s.get("indexed", 0) or 0) for s in sitemaps)

            homepage_inspection: dict[str, Any] = {}
            if inspect_homepage or (sm_indexed == 0 and impressions == 0):
                homepage_inspection = self.inspect_url(f"https://{clean_dom}/", site_url=matched_site, token=token, client=http)

            indexed_pages = max(sm_indexed, len(unique_pages))
            if homepage_inspection.get("is_indexed") is True:
                indexed_pages = max(indexed_pages, 1)

            is_indexed = bool(
                indexed_pages > 0
                or impressions > 0
                or homepage_inspection.get("is_indexed") is True
                or any(s.get("submitted", 0) > 0 for s in sitemaps)
            )
            # Only classify explicitly deindexed if we actually inspected homepage and Google returned FAIL/NEUTRAL with 0 indexed/impressions
            if homepage_inspection.get("status") == "ok" and homepage_inspection.get("is_indexed") is False and indexed_pages == 0 and impressions == 0:
                is_indexed = False

            perm_level = ""
            if self._verified_sites_cache and clean_dom in self._verified_sites_cache:
                perm_level = self._verified_sites_cache[clean_dom][1]

            result = {
                "domain": clean_dom,
                "property_url": matched_site,
                "permission_level": perm_level,
                "period_days": days,
                "start_date": start_date,
                "end_date": end_date,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "avg_position": avg_pos,
                "indexed_pages": indexed_pages,
                "is_indexed": is_indexed,
                "top_queries": top_queries,
                "quick_wins": quick_wins,
                "sitemaps": sitemaps,
                "homepage_inspection": homepage_inspection,
                "credentials_configured": True,
                "is_mock": False,
                "data_source": "google_search_console_api",
                "api_error": None,
                "last_synced": datetime.datetime.now().isoformat(),
            }
            self._cached_metrics[clean_dom] = result
            self._save_cache()
            return result
        finally:
            if own_client:
                http.close()

    def audit_all_domains(
        self,
        days: int = 7,
        mock_fallback: bool = True,
        inspect_homepage: bool = False,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """Runs audit across all configured domains and detects any deindexed sites."""
        auth_status = self.auth.get_status()
        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            if auth_status["configured"]:
                try:
                    self.list_verified_sites(client=http)
                except Exception as exc:
                    logger.debug("Pre-audit verified sites lookup failed: %s", exc)

            fleet_metrics: dict[str, dict[str, Any]] = {}
            deindexed_domains: list[str] = []
            live_count = 0
            mock_count = 0
            error_domains: list[dict[str, str]] = []

            for dom in self.domains:
                dom_name = dom.get("domain", dom) if isinstance(dom, dict) else dom
                perf = self.fetch_domain_performance(
                    dom_name,
                    days=days,
                    mock_fallback=mock_fallback,
                    inspect_homepage=inspect_homepage,
                    client=http,
                )
                fleet_metrics[perf["domain"]] = perf
                if perf.get("data_source") == "google_search_console_api" and not perf.get("is_mock"):
                    live_count += 1
                else:
                    mock_count += 1
                if perf.get("api_error"):
                    error_domains.append({"domain": perf["domain"], "error": str(perf["api_error"])})
                if (
                    not perf.get("is_mock", False)
                    and perf.get("data_source") not in ("unconfigured", "api_error", "api_error_fallback", "mock_estimate")
                    and (not perf["is_indexed"] or perf["indexed_pages"] == 0)
                ):
                    deindexed_domains.append(perf["domain"])
        finally:
            if own_client:
                http.close()

        total_clicks = sum(int(m.get("clicks", 0) or 0) for m in fleet_metrics.values())
        total_impressions = sum(int(m.get("impressions", 0) or 0) for m in fleet_metrics.values())
        overall_ctr = round(total_clicks / total_impressions, 4) if total_impressions > 0 else 0.0

        report = {
            "audited_at": datetime.datetime.now().isoformat(),
            "period_days": days,
            "credentials_configured": auth_status["configured"],
            "auth_type": auth_status["auth_type"],
            "client_email": auth_status["client_email"],
            "live_domains_count": live_count,
            "mock_domains_count": mock_count,
            "total_domains": len(fleet_metrics),
            "deindexed_count": len(deindexed_domains),
            "deindexed_domains": deindexed_domains,
            "api_errors": error_domains,
            "total_organic_clicks_7d": total_clicks,
            "total_organic_impressions_7d": total_impressions,
            "fleet_organic_ctr": overall_ctr,
            "domains": fleet_metrics,
        }

        # Record per-domain metrics to state/autopublish.db (P3-7)
        self._record_db_metrics(fleet_metrics)

        if deindexed_domains:
            logger.critical("GSC ALERT: Domains deindexed by Google: %s", deindexed_domains)
            try:
                from alert_bot import TelegramAlertBot
                bot = TelegramAlertBot()
                bot.send_message(
                    f"🚨 <b>GSC DEINDEXING ALERT</b>\nDomains lost indexing: {', '.join(deindexed_domains)}",
                    alert_type="deindexed",
                    level="CRITICAL",
                )
            except Exception:
                pass

        return report

    def format_weekly_report_html(self, audit_report: dict[str, Any]) -> str:
        """Format fleet GSC audit into clean Telegram HTML weekly digest."""
        live_cnt = int(audit_report.get("live_domains_count", 0))
        tot_cnt = int(audit_report.get("total_domains", 0))
        is_live = bool(audit_report.get("credentials_configured")) and live_cnt > 0
        mode_line = (
            f"🟢 <b>LIVE Google Search Console API</b> ({live_cnt}/{tot_cnt} properties)"
            if is_live
            else f"🟡 <b>ESTIMATE MODE</b> (GSC OAuth2 credentials pending)"
        )

        ctr_pct = round(float(audit_report.get("fleet_organic_ctr", 0.0)) * 100, 2)
        domains_dict = audit_report.get("domains", {}) or {}
        ranked = sorted(
            domains_dict.values(),
            key=lambda d: (int(d.get("clicks", 0) or 0), int(d.get("impressions", 0) or 0)),
            reverse=True,
        )

        top_lines = []
        quick_wins_lines = []
        for item in ranked[:5]:
            dom = html.escape(str(item.get("domain", "")))
            imps = int(item.get("impressions", 0) or 0)
            clks = int(item.get("clicks", 0) or 0)
            pos = item.get("avg_position", 0.0)
            tag = "LIVE" if not item.get("is_mock") else "EST"
            q_list = item.get("top_queries") or []
            top_q = f" | top: <i>{html.escape(str(q_list[0].get('query', '')))}</i>" if q_list else ""
            top_lines.append(f"• <code>{dom}</code> [{tag}]: {clks:,} clicks / {imps:,} imps (pos #{pos}){top_q}")
            for qw in (item.get("quick_wins") or [])[:1]:
                quick_wins_lines.append(
                    f"• <code>{dom}</code>: \"{html.escape(str(qw.get('query', '')))}\" (#{qw.get('position')}, {qw.get('impressions')} imps)"
                )

        deindexed = audit_report.get("deindexed_domains") or []
        deidx_line = "✅ None (0 deindexed)" if not deindexed else f"🚨 {', '.join(html.escape(str(x)) for x in deindexed)}"

        msg = (
            f"📈 <b>WEEKLY GOOGLE SEARCH CONSOLE REPORT</b>\n"
            f"📅 <b>Generated:</b> {html.escape(str(audit_report.get('audited_at', ''))[:10])}\n"
            f"🔌 <b>Source:</b> {mode_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👁️ <b>Organic Impressions (7d):</b> {int(audit_report.get('total_organic_impressions_7d', 0)):,}\n"
            f"🖱️ <b>Organic Clicks (7d):</b> {int(audit_report.get('total_organic_clicks_7d', 0)):,}\n"
            f"🎯 <b>Fleet Organic CTR:</b> {ctr_pct}%\n"
            f"🛡️ <b>Deindexed Domains:</b> {deidx_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>Top Domains:</b>\n"
            + ("\n".join(top_lines) if top_lines else "• No domain data")
        )
        if quick_wins_lines:
            msg += "\n━━━━━━━━━━━━━━━━━━━━━\n💡 <b>Quick-Win Keywords (Pos #5–#25):</b>\n" + "\n".join(quick_wins_lines[:5])
        if audit_report.get("api_errors"):
            msg += f"\n━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>API Notices:</b> {len(audit_report['api_errors'])} domain(s) need property verification"
        return msg

    def generate_weekly_report(
        self,
        days: int = 7,
        report_date: Optional[str] = None,
        reports_dir: Optional[Path] = None,
        send_telegram: bool = False,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """Run full 7-day GSC audit, write .txt/.json artifacts, and optionally send Telegram digest."""
        out_dir = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = report_date or datetime.date.today().isoformat()

        audit = self.audit_all_domains(days=days, client=client)
        html_msg = self.format_weekly_report_html(audit)

        txt_path = out_dir / f"weekly_gsc_report_{date_str}.txt"
        json_path = out_dir / f"weekly_gsc_report_{date_str}.json"
        txt_path.write_text(html_msg, encoding="utf-8")
        json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

        telegram_sent = False
        if send_telegram:
            try:
                from alert_bot import TelegramAlertBot
                bot = TelegramAlertBot()
                res = bot.send_message(html_msg, alert_type="gsc_weekly_report", level="INFO")
                telegram_sent = bool(res.get("ok") or res.get("status") == "standby_logged")
            except Exception as exc:
                logger.warning("Weekly GSC Telegram dispatch failed: %s", exc)

        return {
            "date": date_str,
            "txt_path": str(txt_path),
            "json_path": str(json_path),
            "telegram_sent": telegram_sent,
            "audit": audit,
            "message_html": html_msg,
        }

    def maybe_send_scheduled_weekly_report(
        self,
        now: Optional[datetime.datetime] = None,
        weekly_day: Optional[int] = None,
        weekly_hour: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send weekly GSC report once per ISO week when scheduled weekday/hour is reached."""
        gsc_cfg = self.cfg.get("gsc", {}) or {}
        if not bool(gsc_cfg.get("weekly_report_enabled", True)):
            return {"sent": False, "reason": "disabled"}

        current = now or datetime.datetime.now()
        target_day = int(gsc_cfg.get("weekly_report_day", 0)) if weekly_day is None else int(weekly_day)
        target_hour = int(gsc_cfg.get("weekly_report_hour", 9)) if weekly_hour is None else int(weekly_hour)
        if current.weekday() < target_day or (current.weekday() == target_day and current.hour < target_hour):
            return {"sent": False, "reason": "before_schedule"}

        iso = current.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        state_file = self.weekly_state_path
        state: dict[str, Any] = {}
        if state_file.is_file():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                state = {}

        if state.get("last_sent_week") == week_key:
            return {"sent": False, "reason": "already_sent_this_week", "week": week_key}

        report = self.generate_weekly_report(
            days=int(gsc_cfg.get("default_days", 7)),
            report_date=current.date().isoformat(),
            send_telegram=True,
        )
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(
                json.dumps(
                    {
                        "last_sent_week": week_key,
                        "last_sent_date": current.date().isoformat(),
                        "sent_at": current.isoformat(),
                        "credentials_configured": report["audit"]["credentials_configured"],
                        "live_domains_count": report["audit"]["live_domains_count"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Could not persist weekly GSC state: %s", exc)

        return {"sent": True, "week": week_key, "report": report}

    def _save_cache(self) -> None:
        try:
            p = self.cache_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._cached_metrics, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to cache GSC metrics: %s", exc)

    def _record_db_metrics(self, fleet_metrics: dict[str, dict[str, Any]]) -> None:
        """Record per-domain GSC performance and indexing health to state/autopublish.db (P3-7)."""
        db_path = PROJECT_ROOT / "state" / "autopublish.db"
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)

        now_iso = datetime.datetime.now().isoformat()
        try:
            with sqlite3.connect(db_path, timeout=10.0) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gsc_domain_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain TEXT NOT NULL,
                        published_pages INTEGER DEFAULT 0,
                        indexed_pages INTEGER DEFAULT 0,
                        impressions INTEGER DEFAULT 0,
                        clicks INTEGER DEFAULT 0,
                        ctr REAL DEFAULT 0.0,
                        indexing_ratio REAL DEFAULT 0.0,
                        is_mock INTEGER DEFAULT 1,
                        data_source TEXT,
                        recorded_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS ix_gsc_metrics_domain ON gsc_domain_metrics(domain, recorded_at)"
                )

                for dom, perf in fleet_metrics.items():
                    clean_dom = _clean_domain(dom)
                    short_dom = clean_dom.replace(".com", "")
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM published_posts WHERE domain = ? OR domain = ? OR domain = ?",
                        (clean_dom, short_dom, f"{short_dom}.com"),
                    )
                    row = cur.fetchone()
                    published_count = row[0] if row and row[0] else 0

                    if published_count == 0:
                        site_folder = PROJECT_ROOT / "sites" / f"{short_dom}.com"
                        if site_folder.is_dir():
                            published_count = len([
                                p for p in site_folder.glob("*/index.html")
                                if p.parent.name not in ("img", "css", "js")
                            ])

                    indexed_pages = int(perf.get("indexed_pages", 0) or 0)
                    impressions = int(perf.get("impressions", 0) or 0)
                    clicks = int(perf.get("clicks", 0) or 0)
                    ctr = float(perf.get("ctr", 0.0) or 0.0)
                    is_mock = 1 if perf.get("is_mock", True) else 0
                    data_source = str(perf.get("data_source", "mock_estimate"))
                    indexing_ratio = round(indexed_pages / published_count, 4) if published_count > 0 else 1.0

                    conn.execute(
                        """
                        INSERT INTO gsc_domain_metrics
                        (domain, published_pages, indexed_pages, impressions, clicks, ctr, indexing_ratio, is_mock, data_source, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (clean_dom, published_count, indexed_pages, impressions, clicks, ctr, indexing_ratio, is_mock, data_source, now_iso),
                    )
                conn.commit()
        except Exception as exc:
            logger.debug("Failed to record GSC metrics to autopublish.db: %s", exc)

    def _load_cache(self) -> None:
        try:
            p = self.cache_path
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for dom, entry in raw.items():
                        if isinstance(entry, dict) and "data_source" not in entry:
                            entry["data_source"] = "mock_estimate"
                            entry["is_mock"] = True
                            entry["credentials_configured"] = False
                    self._cached_metrics = raw
        except Exception:
            pass


def build_from_config(cfg: dict) -> GSCMonitor:
    return GSCMonitor(cfg=cfg)


def maybe_send_scheduled_weekly_report() -> dict[str, Any]:
    return GSCMonitor().maybe_send_scheduled_weekly_report()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google Search Console API Monitor CLI")
    parser.add_argument("--audit", action="store_true", help="Run GSC audit across all domains")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly GSC report")
    parser.add_argument("--send", action="store_true", help="Also dispatch weekly report to Telegram")
    args = parser.parse_args()

    mon = GSCMonitor()
    if args.weekly:
        out = mon.generate_weekly_report(send_telegram=args.send)
        print(out["message_html"])
    else:
        print(json.dumps(mon.audit_all_domains(), indent=2))
