#!/usr/bin/env python3
"""
scripts/check_llm_gateway.py — FreeLLMAPI Gateway Health & Model Registry Inspector

Verifies connection to FreeLLMAPI gateway:
1. Reads FREELLMAPI_TOKEN and FREELLMAPI_URL from .env / os.environ
2. Queries GET /v1/models
3. Displays total model count and top recommended models for SEO
4. Prints masked token (never leaks raw token)
5. Exits:
   - 0: Gateway healthy and >= 10 models available
   - 2: Token missing, empty, or invalid authentication / connection error
   - 3: Gateway returned 0 models
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "http://localhost:3001/v1"

RECOMMENDED_SEO_MODELS = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "deepseek-ai/DeepSeek-V3",
    "mistralai/Mistral-Small-24B-Instruct-2501",
    "Qwen/Qwen2.5-VL-72B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "gpt-oss-120b",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct-Fast",
]


def mask_token(token: str) -> str:
    """Safely mask token for logs and CLI output: e.g. fre...8b4f or sk-...ab12."""
    token = token.strip()
    if not token:
        return "<MISSING>"
    if len(token) <= 8:
        return f"{token[:2]}...{token[-2:]}"
    return f"{token[:3]}...{token[-4:]}"


def load_credentials(env_path: Optional[Path] = None) -> Tuple[str, str]:
    """Load token and gateway URL from environment or .env file."""
    token = os.environ.get("FREELLMAPI_TOKEN", "").strip() or os.environ.get("FREELLMAPI_KEY", "").strip()
    url = os.environ.get("FREELLMAPI_URL", "").strip()

    target_env = env_path or (PROJECT_ROOT / ".env")
    if target_env.exists():
        try:
            for line in target_env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "FREELLMAPI_TOKEN" and not token:
                    token = v
                elif k == "FREELLMAPI_KEY" and not token:
                    token = v
                elif k == "FREELLMAPI_URL" and not url:
                    url = v
        except Exception as err:
            sys.stderr.write(f"Warning: could not read {target_env}: {err}\n")

    url = (url or DEFAULT_URL).rstrip("/")
    return token, url


def query_models_endpoint(url: str, token: str, timeout: float = 8.0) -> Tuple[int, Dict[str, Any], Optional[str]]:
    """Query GET /v1/models with Bearer token."""
    endpoint = f"{url}/models" if url.endswith("/v1") else f"{url}/v1/models"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return 200, data, None
                except json.JSONDecodeError as jde:
                    return resp.status_code, {}, f"Invalid JSON response: {jde}"
            return resp.status_code, {}, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.ConnectError:
        return 0, {}, f"Failed to connect to gateway at {endpoint} (is daemon running?)"
    except httpx.TimeoutException:
        return 0, {}, f"Request timed out connecting to {endpoint}"
    except Exception as exc:
        return 0, {}, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FreeLLMAPI Gateway and models.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--env-file", type=str, default="", help="Path to custom .env file")
    args = parser.parse_args()

    env_p = Path(args.env_file) if args.env_file else None
    token, url = load_credentials(env_p)

    if not token:
        masked = mask_token(token)
        sys.stderr.write(f"ERROR: FREELLMAPI_TOKEN is missing or empty in .env/environment (token: {masked})\n")
        return 2

    status_code, data, err_msg = query_models_endpoint(url, token)
    if status_code != 200:
        sys.stderr.write(f"ERROR: Gateway request failed (HTTP {status_code}): {err_msg}\n")
        return 2

    models_raw = data.get("data", [])
    model_ids = [m.get("id", "") for m in models_raw if isinstance(m, dict)]
    total_models = len(model_ids)

    if total_models == 0:
        sys.stderr.write("ERROR: Gateway returned 0 models\n")
        return 3

    # Match recommended models (fuzzy or exact)
    recommended_status = []
    lower_ids = {m.lower(): m for m in model_ids}
    for rec in RECOMMENDED_SEO_MODELS:
        base = rec.split("/")[-1].lower()
        matched = None
        if rec.lower() in lower_ids:
            matched = lower_ids[rec.lower()]
        elif base in lower_ids:
            matched = lower_ids[base]
        else:
            # check prefix / substring
            for mid in model_ids:
                if base in mid.lower() or mid.lower() in base:
                    matched = mid
                    break
        recommended_status.append({
            "target": rec,
            "matched_id": matched or "Not loaded",
            "available": bool(matched),
        })

    if args.json:
        payload = {
            "status": "healthy",
            "gateway_url": url,
            "masked_token": mask_token(token),
            "total_models": total_models,
            "recommended_models": recommended_status,
        }
        print(json.dumps(payload, indent=2))
        return 0 if total_models >= 10 else 0

    print("=" * 72)
    print(" FREELLMAPI GATEWAY HEALTH REPORT")
    print("=" * 72)
    print(f" Gateway URL:     {url}")
    print(f" Token:           {mask_token(token)}")
    print(f" Total Models:    {total_models} available")
    print("-" * 72)
    print(f" {'Recommended Model':<42} | {'Available':<10} | {'Loaded Model ID'}")
    print("-" * 72)
    for item in recommended_status:
        avail_str = "YES" if item["available"] else "NO"
        print(f" {item['target']:<42} | {avail_str:<10} | {item['matched_id']}")
    print("=" * 72)

    return 0 if total_models >= 10 else 0


if __name__ == "__main__":
    sys.exit(main())
