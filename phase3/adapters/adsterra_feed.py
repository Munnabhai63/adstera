"""Adsterra publisher feed adapter wrapping root ``adsterra_api.py``.

Reads ``ADSTERRA_API_KEY`` strictly from environment variables configured in
``phase3/config.yaml``. Provides TTL caching and offline/mock fallback.
"""
from __future__ import annotations

import datetime
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.logging_utils import log_event

# ASSUMPTION: Root `adsterra_api` exposes `AdsterraApiClient`,
# `load_local_adsterra_ZeroWaste_maps`, and `diagnose_domain_metrics`.
try:
    import adsterra_api  # type: ignore
except Exception:  # pragma: no cover
    adsterra_api = None  # type: ignore[assignment]

logger = logging.getLogger("phase3.adapters.adsterra_feed")

_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv_into_environ(
    env_path: Optional[str | Path] = None,
    *,
    force: Optional[bool] = None,
) -> Dict[str, str]:
    """Load key=value pairs from repo ``.env`` into ``os.environ`` without overwriting.

    Under pytest (``PYTEST_CURRENT_TEST`` set), automatic loading is skipped unless
    ``force=True`` is explicitly passed so tests using ``monkeypatch.delenv`` stay isolated.
    """
    should_load = (not bool(os.environ.get("PYTEST_CURRENT_TEST"))) if force is None else bool(force)
    if not should_load:
        return {}

    path = Path(env_path) if env_path is not None else _DEFAULT_ENV_PATH
    if not path.is_file():
        return {}

    loaded: Dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            if key not in os.environ:
                os.environ[key] = val
                loaded[key] = val
    except Exception as exc:
        log_event(logger, logging.WARNING, "dotenv_load_failed", path=str(path), error=str(exc))
    return loaded


class AdsterraFeedAdapter:
    """Adapter around ``adsterra_api.AdsterraApiClient`` with TTL cache and fail-safe defaults."""

    def __init__(
        self,
        cfg: Optional[Phase3Config] = None,
        *,
        client: Optional[Any] = None,
        auto_load_env: Optional[bool] = None,
        env_path: Optional[str | Path] = None,
    ) -> None:
        load_dotenv_into_environ(env_path, force=auto_load_env)
        self.cfg = cfg or load_phase3_config()
        self._client = client
        self._cache: Dict[str, Tuple[float, Any]] = {}

    @property
    def client(self) -> Any:
        if self._client is None and adsterra_api is not None:
            api_key = self.cfg.resolve_env_secret(self.cfg.adsterra.api_key_env_var)
            # ASSUMPTION: AdsterraApiClient(api_key=..., config_path=...) falls back to mock if api_key=="".
            self._client = adsterra_api.AdsterraApiClient(
                api_key=api_key,
                config_path=self.cfg.phase3.legacy_config,
            )
        return self._client

    def has_live_credentials(self) -> bool:
        """Return True when a non-empty, non-dummy API key is present in env."""
        key = self.cfg.resolve_env_secret(self.cfg.adsterra.api_key_env_var)
        if not key:
            return False
        if self.client is not None and hasattr(self.client, "is_mock_mode"):
            return not bool(self.client.is_mock_mode())
        return True

    def _get_cached(self, cache_key: str) -> Optional[Any]:
        ttl = max(0, int(self.cfg.adsterra.cache_ttl_seconds))
        entry = self._cache.get(cache_key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts <= ttl:
            return value
        self._cache.pop(cache_key, None)
        return None

    def _set_cached(self, cache_key: str, value: Any) -> Any:
        self._cache[cache_key] = (time.time(), value)
        return value

    def _fallback_stats(self, start_date: str, finish_date: str) -> Dict[str, Any]:
        default_ecpm = float(self.cfg.adsterra.default_ecpm_usd)
        default_ctr = float(self.cfg.adsterra.default_ctr)
        imps = 100
        clicks = max(1, int(round(imps * default_ctr)))
        return {
            "status": "ok",
            "mode": "phase3_fallback",
            "items": [
                {
                    "domain": "default",
                    "date": start_date,
                    "impression": imps,
                    "impressions": imps,
                    "clicks": clicks,
                    "ctr": round(default_ctr * 100.0, 2),
                    "cpm": default_ecpm,
                    "revenue": round((imps / 1000.0) * default_ecpm, 4),
                }
            ],
        }

    async def fetch_domain_stats(
        self,
        start_date: Optional[str] = None,
        finish_date: Optional[str] = None,
        *,
        force_mock: bool = False,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch daily domain stats from Adsterra API or mock fallback."""
        today = datetime.date.today().isoformat()
        start = start_date or today
        finish = finish_date or today
        use_mock = bool(
            force_mock or (not self.has_live_credentials() and self.cfg.adsterra.fallback_mock_on_missing_key)
        )
        cache_key = f"stats:{start}:{finish}:{use_mock}"

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        if self.client is None:
            return self._set_cached(cache_key, self._fallback_stats(start, finish))

        try:
            # ASSUMPTION: AdsterraApiClient.fetch_daily_stats is async and returns {"items": [...], ...}.
            data = await self.client.fetch_daily_stats(
                start_date=start,
                finish_date=finish,
                group_by="domain",
                force_mock=use_mock,
            )
            if not isinstance(data, dict) or (data.get("status") == "error" and self.cfg.adsterra.fallback_mock_on_missing_key):
                log_event(
                    logger,
                    logging.WARNING,
                    "adsterra_stats_fallback",
                    reason=str(data.get("error") if isinstance(data, dict) else "invalid_response"),
                )
                return self._set_cached(cache_key, self._fallback_stats(start, finish))
            return self._set_cached(cache_key, data)
        except Exception as exc:
            log_event(logger, logging.WARNING, "adsterra_stats_exception", error=str(exc))
            if self.cfg.adsterra.fallback_mock_on_missing_key:
                return self._set_cached(cache_key, self._fallback_stats(start, finish))
            return {"status": "error", "error": str(exc), "items": []}

    async def get_domain_metrics(self, domain: str = "default", *, force_mock: bool = False) -> Dict[str, Any]:
        """Return normalized metrics dict `{domain, impressions, clicks, ctr, ecpm, revenue, rpm, source}`."""
        stats = await self.fetch_domain_stats(force_mock=force_mock)
        items = stats.get("items", []) if isinstance(stats, dict) else []
        clean = (domain or "default").lower().strip()

        dom_map, _ = self.get_placement_maps()
        matched: Optional[Dict[str, Any]] = None
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_dom = str(item.get("domain", "")).strip()
            resolved_dom = str(dom_map.get(raw_dom, raw_dom)).lower().strip()
            item_dom = raw_dom.lower()
            if (
                resolved_dom == clean
                or item_dom == clean
                or (clean != "default" and (clean in resolved_dom or clean in item_dom))
            ):
                matched = item
                break
        if matched is None and items and isinstance(items[0], dict):
            matched = items[0]

        if matched is None:
            ecpm = float(self.cfg.adsterra.default_ecpm_usd)
            ctr = float(self.cfg.adsterra.default_ctr)
            return {
                "domain": domain,
                "impressions": 0,
                "clicks": 0,
                "ctr": ctr,
                "ecpm": ecpm,
                "revenue": 0.0,
                "rpm": ecpm,
                "source": "config_default",
            }

        imps = int(matched.get("impressions") or matched.get("impression") or 0)
        clicks = int(matched.get("clicks") or 0)
        raw_ctr = float(matched.get("ctr") or 0.0)
        # Adsterra API returns CTR in percent (e.g., 3.8); normalize to [0.0, 1.0].
        ctr = raw_ctr / 100.0 if raw_ctr > 1.0 else raw_ctr
        if ctr <= 0.0 and imps > 0:
            ctr = clicks / imps
        ecpm = float(matched.get("cpm") or matched.get("ecpm") or self.cfg.adsterra.default_ecpm_usd)
        revenue = float(matched.get("revenue") or 0.0)
        rpm = (revenue / imps * 1000.0) if imps > 0 and revenue > 0 else ecpm
        return {
            "domain": domain,
            "impressions": imps,
            "clicks": clicks,
            "ctr": round(ctr, 6),
            "ecpm": round(ecpm, 4),
            "revenue": round(revenue, 6),
            "rpm": round(rpm, 4),
            "source": str(stats.get("mode") or "adsterra_api"),
        }

    async def get_revenue_series(self, days: int = 14, *, force_mock: bool = False) -> List[Dict[str, Any]]:
        """Build a chronological list of daily revenue/eCPM dicts for A3 forecasting."""
        n_days = max(1, int(days))
        end_d = datetime.date.today()
        series: List[Dict[str, Any]] = []
        for offset in range(n_days - 1, -1, -1):
            day_str = (end_d - datetime.timedelta(days=offset)).isoformat()
            stats = await self.fetch_domain_stats(start_date=day_str, finish_date=day_str, force_mock=force_mock)
            items = stats.get("items", []) if isinstance(stats, dict) else []
            total_rev = sum(float(it.get("revenue") or 0.0) for it in items if isinstance(it, dict))
            total_imps = sum(int(it.get("impressions") or it.get("impression") or 0) for it in items if isinstance(it, dict))
            avg_ecpm = (
                (total_rev / total_imps) * 1000.0
                if total_imps > 0
                else float(self.cfg.adsterra.default_ecpm_usd)
            )
            series.append(
                {
                    "date": day_str,
                    "revenue": round(total_rev, 4),
                    "total_revenue": round(total_rev, 4),
                    "impressions": total_imps,
                    "ecpm": round(avg_ecpm, 4),
                }
            )
        return series

    def get_placement_maps(self) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        """Return `(domain_id_map, placement_map)` from local Adsterra state."""
        if adsterra_api is None:
            return {}, {}
        try:
            # ASSUMPTION: load_local_adsterra_ZeroWaste_maps returns (dom_map, placement_map).
            return adsterra_api.load_local_adsterra_ZeroWaste_maps()
        except Exception as exc:
            log_event(logger, logging.WARNING, "adsterra_placement_map_failed", error=str(exc))
            return {}, {}

    def diagnose(
        self,
        api_impressions: int,
        api_clicks: int,
        api_ctr: float,
        api_cpm: float,
        verified_beacons: int = 0,
    ) -> Dict[str, str]:
        """Delegate health diagnosis to ``adsterra_api.diagnose_domain_metrics``."""
        if adsterra_api is None:
            return {"health": "UNKNOWN", "diagnosis": "adsterra_api unavailable", "auto_action": "none"}
        # ASSUMPTION: diagnose_domain_metrics returns {health, diagnosis, auto_action}.
        return adsterra_api.diagnose_domain_metrics(
            api_impressions,
            api_clicks,
            api_ctr,
            api_cpm,
            verified_beacons,
        )
