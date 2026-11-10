"""
freellmapi_client.py — High-Performance Free LLM API Client for Autonomous Content & Lead Realism.

Connects to the local FreeLLMAPI aggregator daemon (http://localhost:3001/v1) powered by
7.4 billion monthly tokens across 34 free providers (Kilo, OVH, AIHorde, Google, Groq, etc.).

Use Cases:
- Hyper-realistic persona inquiry/notes generation for high-payout CPL/CPA lead forms.
- Dynamic search query generation for organic referrer emulation.
- SEO content & article enhancement across the 10 publisher sites.
- Resilient fallback to local heuristic generators if daemon is offline.
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "http://localhost:3001"
DEFAULT_MODEL = "auto"


class FreeLLMClient:
    """Client for FreeLLMAPI OpenAI-compatible router on localhost:3001."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.api_url, self.api_key = self._resolve_credentials()
        self.enabled = bool(self.config.get("freellm", {}).get("enabled", True))
        self.timeout = float(self.config.get("freellm", {}).get("timeout", 20.0))
        self.default_model = self.config.get("freellm", {}).get("model", DEFAULT_MODEL)

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config for FreeLLMClient: %s", e)
        return {}

    def _resolve_credentials(self) -> tuple[str, str]:
        url = os.environ.get("FREELLMAPI_URL", "").strip()
        key = os.environ.get("FREELLMAPI_KEY", "").strip()

        if not url or not key:
            env_file = Path(".env")
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("FREELLMAPI_URL=") and not url:
                            url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("FREELLMAPI_KEY=") and not key:
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass

        url = url or DEFAULT_API_URL
        key = key or "freellmapi-ceb04983702628b4439a5a1d9e9bf34484f948c29dbe8b4f"
        return url, key

    def is_available(self) -> bool:
        """Ping FreeLLMAPI service status."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.api_url}/v1/models", headers={"Authorization": f"Bearer {self.api_key}"})
                return res.status_code == 200
        except Exception:
            return False

    def generate_completion(
        self,
        prompt: str,
        system_prompt: str = "You are a professional assistant.",
        max_tokens: int = 120,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Send chat completion request to FreeLLMAPI router."""
        if not self.enabled or not self.is_available():
            return None

        chosen_model = model or self.default_model
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.api_url}/v1/chat/completions", headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"].get("content", "").strip()
                else:
                    logger.warning("[FreeLLMClient] API status %d: %s", res.status_code, res.text[:160])
        except Exception as e:
            logger.warning("[FreeLLMClient] Request failed (%s) — using fallback.", e)

        return None

    # =========================================================================
    # High-Value Domain Domain-Specific Realism Synthesizers
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

        result = self.generate_completion(prompt, system_prompt=system_prompt, max_tokens=50, temperature=0.8)
        if result and len(result) > 10:
            return result.replace('"', '').strip()

        # Heuristic fallback
        fallbacks = [
            "Need urgent funds for medical emergency and hospital bill clearance.",
            "Applying for business loan to purchase working capital inventory before festive season.",
            "Looking for lowest interest personal loan to consolidate existing high-cost debts.",
            "Need immediate personal loan for house renovation and urgent civil repairs.",
            "Urgent short-term salary advance loan required for sibling college fee payment."
        ]
        return rng.choice(fallbacks)

    def generate_search_query_variation(self, base_keyword: str, domain: str, rng: Optional[random.Random] = None) -> str:
        """Generate natural organic long-tail search query to mimic organic Google/Bing referral."""
        rng = rng or random.Random()
        prompt = (
            f"Given keyword '{base_keyword}' for site '{domain}', generate one natural, authentic Google search query "
            "that a real person in India would type in 2026. Return ONLY the search query text, no quotes, no explanation."
        )
        result = self.generate_completion(prompt, max_tokens=30, temperature=0.85)
        if result and len(result) > 5 and len(result) < 80:
            return result.replace('"', '').strip()

        suffixes = ["low cibil score fast approval", "best interest rates 2026", "online apply without document", "eligibility check direct bank"]
        return f"{base_keyword} {rng.choice(suffixes)}"
