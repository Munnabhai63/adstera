"""
freellmapi_client.py — 3-Layer 24x7 Always-On FreeLLMAPI & Cloudflare Edge Router Client.

Architecture (Zero Single-Point-of-Failure):
  Layer 1 — Cloudflare 24x7 Serverless Edge Gateway (https://loanraaj.com/v1)
  Layer 2 — Local FreeLLMAPI Daemon (http://127.0.0.1:3001/v1) with Auto-Start Watchdog
  Layer 3 — Direct Multi-Provider Cloud Failover (OVH AI Endpoints & Kilo Gateway)

Fast Instruct Model Chain (avoids slow reasoning token starvation):
  1. Qwen2.5-VL-72B-Instruct (OVH — 72B fast instruct, zero <think> overhead)
  2. Mistral-Small-3.2-24B-Instruct-2506 (OVH — fast structured HTML)
  3. gpt-oss-120b (OVH — 120B high-depth model)
  4. cohere/north-mini-code:free (Kilo — 1.2s TTFB ultra-fast instruct)
  5. nvidia/nemotron-3.5-lightning:free (Kilo)
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

CLOUDFLARE_EDGE_URL = "https://loanraaj.com"
LOCAL_DAEMON_URL = "http://127.0.0.1:3001"
DEFAULT_API_URL = CLOUDFLARE_EDGE_URL
DEFAULT_MODEL = "llama-3.3-70b"
FREELLMAPI_SERVER_DIR = Path(r"F:\UserData\Downloads\ai-power-tools\freellmapi\server")

FAST_INSTRUCT_CHAIN: List[Dict[str, str]] = [
    {
        "provider": "ovh",
        "model": "Qwen/Qwen2.5-VL-72B-Instruct",
        "url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
    },
    {
        "provider": "ovh",
        "model": "Mistral-Small-3.2-24B-Instruct-2506",
        "url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
    },
    {
        "provider": "ovh",
        "model": "gpt-oss-120b",
        "url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
    },
    {
        "provider": "kilo",
        "model": "cohere/north-mini-code:free",
        "url": "https://api.kilo.ai/api/gateway/v1/chat/completions",
    },
    {
        "provider": "kilo",
        "model": "nvidia/nemotron-3.5-lightning:free",
        "url": "https://api.kilo.ai/api/gateway/v1/chat/completions",
    },
]

_LAST_WATCHDOG_ATTEMPT = 0.0


def ensure_local_daemon_running(api_key: str = "") -> bool:
    """Check if localhost:3001 is up; if not, auto-spawn FreeLLMAPI server in background."""
    global _LAST_WATCHDOG_ATTEMPT
    token = api_key or os.environ.get("FREELLMAPI_TOKEN") or os.environ.get("FREELLMAPI_KEY")
    if not token:
        raise ValueError("FREELLMAPI_TOKEN environment variable is not set")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=2.5) as client:
            res = client.get(f"{LOCAL_DAEMON_URL}/v1/models", headers=headers)
            if res.status_code == 200:
                return True
    except Exception:
        pass

    now = time.time()
    if (now - _LAST_WATCHDOG_ATTEMPT) < 30.0:
        return False
    _LAST_WATCHDOG_ATTEMPT = now

    entry_js = FREELLMAPI_SERVER_DIR / "dist" / "index.js"
    if not entry_js.exists():
        return False

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            ["node", "dist/index.js"],
            cwd=str(FREELLMAPI_SERVER_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        for _ in range(10):
            time.sleep(0.5)
            try:
                with httpx.Client(timeout=2.0) as client:
                    res = client.get(f"{LOCAL_DAEMON_URL}/v1/models", headers=headers)
                    if res.status_code == 200:
                        logger.info("[FreeLLMClient] Auto-started local FreeLLMAPI daemon on 127.0.0.1:3001")
                        return True
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[FreeLLMClient] Watchdog spawn warning: %s", exc)
    return False


class FreeLLMClient:
    """3-Layer 24x7 Client for Cloudflare Edge Gateway + Local Daemon + Direct Cloud Providers."""

    def __init__(self, config_path: str = "config.yaml", api_key: str = ""):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        explicit = api_key.strip() if api_key else ""
        if explicit:
            self.api_key = explicit
            self.api_url = self._resolve_url_only()
        else:
            self.api_url, self.api_key = self._resolve_credentials()
        freellm_cfg = self.config.get("freellm", {}) or {}
        self.enabled = bool(freellm_cfg.get("enabled", True))
        self.timeout = float(freellm_cfg.get("timeout", 150.0))
        self.fallback_models: List[str] = list(freellm_cfg.get("fallback_models") or [
            "llama-3.3-70b",
            "auto",
            "kilo-auto",
            "free-router",
            "gpt-oss-120b",
        ])
        cfg_model = str(freellm_cfg.get("model", "llama-3.3-70b")).strip()
        if cfg_model in ("claude-sonnet-4-5", "") and self.fallback_models:
            self.default_model = self.fallback_models[0]
        else:
            self.default_model = cfg_model or (self.fallback_models[0] if self.fallback_models else DEFAULT_MODEL)
        self.edge_url = str(freellm_cfg.get("edge_url", CLOUDFLARE_EDGE_URL)).rstrip("/")
        self.local_url = str(freellm_cfg.get("local_url", LOCAL_DAEMON_URL)).rstrip("/")

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config for FreeLLMClient: %s", e)
        return {}

    def _resolve_url_only(self) -> str:
        """Resolve API URL from environment or .env without requiring a token."""
        url = os.environ.get("FREELLMAPI_URL", "").strip()
        if not url:
            env_file = Path(".env")
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("FREELLMAPI_URL="):
                            url = line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
        return (url or DEFAULT_API_URL).rstrip("/")

    def _resolve_credentials(self) -> tuple[str, str]:
        explicit_empty = ("FREELLMAPI_TOKEN" in os.environ and not os.environ["FREELLMAPI_TOKEN"].strip()) or \
                         ("FREELLMAPI_KEY" in os.environ and not os.environ["FREELLMAPI_KEY"].strip())
        url = os.environ.get("FREELLMAPI_URL", "").strip()
        key = os.environ.get("FREELLMAPI_TOKEN", "").strip() or os.environ.get("FREELLMAPI_KEY", "").strip()

        if not explicit_empty and (not url or not key):
            env_file = Path(".env")
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("FREELLMAPI_URL=") and not url:
                            url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("FREELLMAPI_KEY=") and not key:
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("FREELLMAPI_TOKEN=") and not key:
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass

        url = (url or DEFAULT_API_URL).rstrip("/")
        if not key:
            raise ValueError("FREELLMAPI_TOKEN environment variable is not set")
        return url, key

    def is_available(self) -> bool:
        """Verify whether Cloudflare 24x7 Edge Gateway, Local Daemon, or Direct Cloud is reachable."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for base in (self.edge_url, self.api_url, self.local_url):
            if not base:
                continue
            try:
                with httpx.Client(timeout=4.0) as client:
                    res = client.get(f"{base}/v1/models", headers=headers)
                    if res.status_code == 200 and '"object"' in res.text:
                        return True
            except Exception:
                continue
        return ensure_local_daemon_running(self.api_key)

    @staticmethod
    def _extract_message_text(data: dict) -> Optional[str]:
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return None
        msg = choices[0].get("message") or {}
        text = (msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
        return text if text else None

    def generate_completion(
        self,
        prompt: str,
        system_prompt: str = "You are a professional assistant.",
        max_tokens: int = 2500,
        temperature: float = 0.7,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """
        Send chat completion across multi-model fallback list and 3-Layer Failover:
          - Automatically retries across fallback models if primary model fails (429/500/timeout).
          - Logs explicit warning on every fallback switch.
        """
        if not self.enabled:
            return None

        req_timeout = float(timeout or self.timeout or 150.0)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        auth_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build ordered list of models to try from config
        effective_fallbacks = [fb for fb in self.fallback_models if fb not in ("auto", "fusion", "claude-sonnet-4-5")]
        primary_fallback = effective_fallbacks[0] if effective_fallbacks else DEFAULT_MODEL

        models_to_try: List[str] = []
        primary_candidate = model or self.default_model
        if primary_candidate in ("auto", "fusion", "claude-sonnet-4-5", ""):
            primary_candidate = primary_fallback

        if primary_candidate:
            models_to_try.append(primary_candidate)
        for fb in self.fallback_models:
            if fb not in models_to_try:
                models_to_try.append(fb)

        gateways_to_try: List[str] = []
        if self.api_url and self.api_url != self.edge_url:
            gw = f"{self.api_url}/chat/completions" if "/v1" in self.api_url else f"{self.api_url}/v1/chat/completions"
            if gw not in gateways_to_try:
                gateways_to_try.append(gw)
        if self.local_url and f"{self.local_url}/v1/chat/completions" not in gateways_to_try:
            gateways_to_try.append(f"{self.local_url}/v1/chat/completions")
        if self.edge_url and f"{self.edge_url}/v1/chat/completions" not in gateways_to_try:
            gateways_to_try.append(f"{self.edge_url}/v1/chat/completions")

        for idx, candidate_model in enumerate(models_to_try):
            chosen_model = candidate_model
            if chosen_model in ("claude-sonnet-4-5", "fusion"):
                chosen_model = primary_fallback

            last_failure_reason = None

            # 1. Configured / Edge Gateways
            for gw_url in gateways_to_try:
                try:
                    with httpx.Client(timeout=min(req_timeout, 90.0)) as client:
                        res = client.post(
                            gw_url,
                            headers=auth_headers,
                            json={
                                "model": chosen_model,
                                "messages": messages,
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                            },
                        )
                        if res.status_code == 200:
                            text = self._extract_message_text(res.json())
                            if text:
                                return text
                        else:
                            last_failure_reason = f"HTTP {res.status_code}"
                except Exception as exc:
                    last_failure_reason = f"{type(exc).__name__}: {exc}"
                    logger.debug("[FreeLLMClient] Gateway %s notice: %s", gw_url, exc)

            # 2. Direct Fast-Instruct Cloud Failover Chain (OVH & Kilo)
            ordered_routes = sorted(
                FAST_INSTRUCT_CHAIN,
                key=lambda r: 0 if r["model"] == chosen_model else 1,
            )
            for route in ordered_routes:
                try:
                    with httpx.Client(timeout=min(req_timeout, 20.0)) as client:
                        res = client.post(
                            route["url"],
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "Mozilla/5.0 FreeLLMAPI-CloudRouter/2.0",
                            },
                            json={
                                "model": route["model"],
                                "messages": messages,
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                            },
                        )
                        if res.status_code == 200:
                            text = self._extract_message_text(res.json())
                            if text:
                                return text
                        else:
                            last_failure_reason = f"HTTP {res.status_code}"
                except Exception as exc:
                    last_failure_reason = f"{type(exc).__name__}: {exc}"
                    logger.debug("[FreeLLMClient] Direct route %s/%s failed: %s", route["provider"], route["model"], exc)

            # 3. Local FreeLLMAPI Daemon (with Auto-Start Watchdog)
            if ensure_local_daemon_running(self.api_key):
                try:
                    with httpx.Client(timeout=req_timeout) as client:
                        res = client.post(
                            f"{self.local_url}/v1/chat/completions",
                            headers=auth_headers,
                            json={
                                "model": chosen_model,
                                "messages": messages,
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                            },
                        )
                        if res.status_code == 200:
                            text = self._extract_message_text(res.json())
                            if text:
                                return text
                        else:
                            last_failure_reason = f"HTTP {res.status_code}"
                except Exception as exc:
                    last_failure_reason = f"{type(exc).__name__}: {exc}"
                    logger.warning("[FreeLLMClient] Local daemon fallback failed: %s", exc)

            # If all layers failed for this model, log fallback switch if another model exists
            if idx + 1 < len(models_to_try):
                next_model = models_to_try[idx + 1]
                logger.warning(
                    f"[FreeLLMClient] Model '{candidate_model}' failed ({last_failure_reason or 'empty response'}), switching to fallback model '{next_model}'"
                )

        return None

    # =========================================================================
    # High-Value Domain-Specific Realism Synthesizers
    # =========================================================================

    def generate_loan_inquiry_purpose(self, domain: str, niche: str, rng: Optional[random.Random] = None) -> str:
        """Generate high-intent user comment/reason for loan/credit card applications."""
        rng = rng or random.Random()
        prompt = (
            f"Generate a realistic 1-sentence borrower note/purpose for a loan application on {domain} ({niche}). "
            "Write in natural Indian English or Hinglish context (e.g. urgent home renovation, medical bill, MSME stock purchase). "
            "Keep it under 25 words, realistic and high commercial intent."
        )
        system_prompt = "You simulate real loan applicants in India submitting online inquiry forms."

        result = self.generate_completion(prompt, system_prompt=system_prompt, max_tokens=120, temperature=0.8, timeout=25.0)
        if result and len(result) > 10:
            return result.replace('"', "").strip()

        fallbacks = [
            "Need urgent funds for medical emergency and hospital bill clearance.",
            "Applying for business loan to purchase working capital inventory before festive season.",
            "Looking for lowest interest personal loan to consolidate existing high-cost debts.",
            "Need immediate personal loan for house renovation and urgent civil repairs.",
            "Urgent short-term salary advance loan required for sibling college fee payment.",
        ]
        return rng.choice(fallbacks)

    def generate_search_query_variation(self, base_keyword: str, domain: str, rng: Optional[random.Random] = None) -> str:
        """Generate natural organic long-tail search query to mimic organic Google/Bing referral."""
        rng = rng or random.Random()
        prompt = (
            f"Given keyword '{base_keyword}' for site '{domain}', generate one natural, authentic Google search query "
            "that a real person in India would type in 2026. Return ONLY the search query text, no quotes, no explanation."
        )
        result = self.generate_completion(prompt, max_tokens=80, temperature=0.85, timeout=25.0)
        if result and 5 < len(result) < 80:
            return result.replace('"', "").strip()

        suffixes = [
            "low cibil score fast approval",
            "best interest rates 2026",
            "online apply without document",
            "eligibility check direct bank",
        ]
        return f"{base_keyword} {rng.choice(suffixes)}"
