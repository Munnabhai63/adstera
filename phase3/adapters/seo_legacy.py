"""Legacy SEO, GSC, and content quality adapter.

Wraps root ``seo_pipeline.py``, ``gsc_monitor.py``, and ``content_quality_gate.py``
read-only without modifying them.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import log_event

# ASSUMPTION: Root `seo_pipeline` exposes `generate_seo_brief`,
# `score_with_claude_seo_qrg`, and `humanize_with_claude_seo`.
# Catching SystemExit as well because optional external claude-seo scripts may call sys.exit(1)
# when optional dependencies such as bs4 are absent.
try:
    import seo_pipeline  # type: ignore
except (Exception, SystemExit):  # pragma: no cover
    seo_pipeline = None  # type: ignore[assignment]

# ASSUMPTION: Root `gsc_monitor` exposes `GSCMonitor` with `fetch_domain_performance`
# and `audit_all_domains`.
try:
    import gsc_monitor  # type: ignore
except (Exception, SystemExit):  # pragma: no cover
    gsc_monitor = None  # type: ignore[assignment]

# ASSUMPTION: Root `content_quality_gate` exposes `ContentQualityFinishGate` with
# `sanitize_raw_html` and `format_editorial_layout`.
try:
    import content_quality_gate  # type: ignore
except (Exception, SystemExit):  # pragma: no cover
    content_quality_gate = None  # type: ignore[assignment]

logger = logging.getLogger("phase3.adapters.seo_legacy")


class SEOLegacyAdapter:
    """Safe wrapper over ``seo_pipeline``, ``gsc_monitor``, and ``content_quality_gate``."""

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        monitor: Optional[Any] = None,
    ) -> None:
        self.cfg = cfg or load_phase3_config()
        self._monitor = monitor

    @property
    def monitor(self) -> Any:
        if self._monitor is None and gsc_monitor is not None:
            try:
                self._monitor = gsc_monitor.GSCMonitor()
            except Exception as exc:
                log_event(logger, logging.WARNING, "gsc_monitor_init_failed", error=str(exc))
        return self._monitor

    def get_gsc_domain_metrics(
        self,
        domain: str,
        *,
        days: int = 7,
        mock_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Fetch GSC performance metrics for *domain* with mock fallback if unconfigured."""
        if self.monitor is None:
            return {
                "domain": domain,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0.0,
                "avg_position": 20.0,
                "is_mock": True,
                "data_source": "unavailable",
            }
        try:
            # ASSUMPTION: GSCMonitor.fetch_domain_performance returns a metrics dict.
            return dict(
                self.monitor.fetch_domain_performance(
                    domain,
                    days=days,
                    mock_fallback=mock_fallback,
                )
            )
        except Exception as exc:
            log_event(logger, logging.WARNING, "gsc_fetch_domain_failed", domain=domain, error=str(exc))
            return {
                "domain": domain,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0.0,
                "avg_position": 20.0,
                "is_mock": True,
                "data_source": "error_fallback",
                "api_error": str(exc),
            }

    def audit_gsc_fleet(self, *, days: int = 7, mock_fallback: bool = True) -> Dict[str, Any]:
        """Run GSC audit across all configured domains."""
        if self.monitor is None:
            return {"total_domains": 0, "domains": {}, "deindexed_domains": []}
        try:
            # ASSUMPTION: GSCMonitor.audit_all_domains returns fleet report dict.
            return dict(self.monitor.audit_all_domains(days=days, mock_fallback=mock_fallback))
        except Exception as exc:
            log_event(logger, logging.WARNING, "gsc_fleet_audit_failed", error=str(exc))
            return {"total_domains": 0, "domains": {}, "deindexed_domains": [], "error": str(exc)}

    def generate_brief(self, domain_key: str, seed_topic: Optional[str] = None) -> Dict[str, Any]:
        """Generate keyword brief via ``seo_pipeline.generate_seo_brief``."""
        if seo_pipeline is None:
            return {"domain": domain_key, "primary_keyword": seed_topic or domain_key, "lsi_keywords": []}
        try:
            return dict(seo_pipeline.generate_seo_brief(domain_key, seed_topic=seed_topic))
        except Exception as exc:
            log_event(logger, logging.WARNING, "seo_brief_failed", domain=domain_key, error=str(exc))
            return {"domain": domain_key, "primary_keyword": seed_topic or domain_key, "lsi_keywords": []}

    def score_content_qrg(self, text_or_html: str) -> Dict[str, Any]:
        """Score content using ``seo_pipeline.score_with_claude_seo_qrg``."""
        if seo_pipeline is None:
            return {"score": 0.0, "available": False}
        try:
            res = seo_pipeline.score_with_claude_seo_qrg(text_or_html)
            return dict(res) if isinstance(res, dict) else {"raw": res}
        except Exception as exc:
            log_event(logger, logging.WARNING, "seo_qrg_score_failed", error=str(exc))
            return {"score": 0.0, "error": str(exc)}

    def sanitize_html(self, raw_html: str) -> str:
        """Sanitize generated HTML via ``ContentQualityFinishGate.sanitize_raw_html``."""
        if content_quality_gate is None:
            return raw_html
        try:
            return str(content_quality_gate.ContentQualityFinishGate.sanitize_raw_html(raw_html))
        except Exception as exc:
            log_event(logger, logging.WARNING, "content_sanitize_failed", error=str(exc))
            return raw_html

    def format_layout(
        self,
        clean_html: str,
        title: str,
        domain_key: str,
        primary_kw: str,
        *,
        category: str = "",
        site_name: str = "",
        cluster_links: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        """Format editorial layout via ``ContentQualityFinishGate.format_editorial_layout``."""
        if content_quality_gate is None:
            return clean_html, [], {}
        return content_quality_gate.ContentQualityFinishGate.format_editorial_layout(
            clean_html,
            title,
            domain_key,
            primary_kw,
            category=category,
            site_name=site_name,
            cluster_links=cluster_links,
        )
