# Owner Action Guide & Operational Playbook

This document is the unified owner action guide. For Step 1 specific setup (Cloudflare Tunnel, FreeLLMAPI Token, Google Search Console), see [STEP1_OWNER_ACTIONS.md](STEP1_OWNER_ACTIONS.md).

---

## 8. FreeLLMAPI Gateway Health Check & Multi-Model Fallback Configuration

### Why It Is Needed
The content generation pipeline connects to an unmetered FreeLLMAPI gateway hosting 330 open-weights models (including Qwen 2.5 72B, Llama 3.3 70B, DeepSeek V3, and Mistral Small). To guarantee 100% uptime and prevent generation stalls if any individual model faces provider rate limits (HTTP 429) or timeouts, the engine employs automated multi-model failover.

### 8.1 Run Gateway Health Check
Verify your gateway connection, token authentication, and model availability:
```bash
python scripts/check_llm_gateway.py
```
This script:
- Safely reads `FREELLMAPI_TOKEN` and `FREELLMAPI_URL` from `.env`
- Masks your token in all terminal output (e.g. `fre...8b4f`)
- Queries `GET /v1/models` and prints a health table of recommended SEO models
- Exits `0` if >= 10 models are available, `2` if token is invalid or gateway down, `3` if 0 models

### 8.2 Configure Multi-Model Fallback List
In `config.yaml`, the `freellm` section allows defining primary and fallback models:
```yaml
freellm:
  enabled: true
  url: https://loanraaj.com
  edge_url: https://loanraaj.com
  local_url: http://127.0.0.1:3001
  model: "auto"
  fallback_models:
    - "Qwen/Qwen2.5-72B-Instruct"
    - "meta-llama/Llama-3.3-70B-Instruct"
    - "mistralai/Mistral-Small-24B-Instruct-2501"
  timeout: 150.0
```
When `freellmapi_client.py` encounters a 429 rate limit or timeout on the primary model, it automatically switches to the next fallback model in sequence, logging an explicit warning on each transition.
