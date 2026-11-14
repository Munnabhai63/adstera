# Step 1 Owner Action Guide — Credentials, Tokens & Transport Setup

This guide details the three essential setup and rotation steps required from the repository owner to enable production readiness, automated publishing, and Google Search Console indexing.

To inspect the live status of all credentials and inputs at any time, run:
```bash
python scripts/preflight_seo.py
```

---

## 1. Cloudflare Zero Trust Tunnel Setup

### Why It Is Needed
The system hosts a local CMS, admin API, and edge router for 10 publisher sites and the FreeLLMAPI local gateway. Cloudflare Zero Trust Tunnels route traffic securely through outbound HTTPS tunnels, eliminating the need to expose open ports or public IP addresses on the host machine.

### Action Steps
1. Navigate to the [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/).
2. In the left sidebar, go to **Networks** &rarr; **Tunnels**.
3. Click **Add a Tunnel** and select **Cloudflared**.
4. Name the tunnel (e.g. `adstera-publisher-mesh`).
5. Choose your environment (Windows `cloudflared.exe` or Docker) and copy the tunnel token from the installation command. The token is the string following `--token` (format: `eyJhIjoi...`).
6. Update your local `.env` file:
   ```env
   CLOUDFLARE_TUNNEL_TOKEN=your_new_tunnel_token_here
   ```
7. Verify configuration:
   ```bash
   python -c "import os; print('Tunnel Token set:', bool(os.environ.get('CLOUDFLARE_TUNNEL_TOKEN') or open('.env').read().count('CLOUDFLARE_TUNNEL_TOKEN=')))"
   ```

---

## 2. FreeLLMAPI Gateway Token Setup & Rotation

### Why It Is Needed
Content generation and automated SEO article expansions rely on the FreeLLMAPI multi-provider gateway (aggregating free inference tiers across Kilo, OVH, Cerebras, Google, and Groq). A valid bearer token is required to authenticate requests against the API gateway.

### Action Steps
1. Open your provider portal at [FreeLLMAPI](https://freellmapi.com) (or your self-hosted FreeLLMAPI gateway instance).
2. Go to **API Keys** and click **Generate New Key** (or rotate an existing key).
3. Copy the secret token.
4. Update your local `.env` file:
   ```env
   FREELLMAPI_TOKEN=your_new_freellmapi_token_here
   ```
   *(Note: `FREELLMAPI_KEY` is also supported as a fallback variable name).*
5. Verify configuration:
   ```bash
   python -c "from freellmapi_client import get_active_token; print('Token loaded:', bool(get_active_token()))"
   ```

---

## 3. Google Cloud GSC Service Account & Indexing Setup

### Why It Is Needed
The fleet manages 10 independent publisher domains. Submitting sitemaps, verifying ownership, and broadcasting URLs to Google via the Web Search Indexing API require server-to-server credentials via RS256 JWT assertions without interactive browser logins.

### Action Steps

#### 3.1 Create Service Account in Google Cloud Console
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project (e.g. `adstera-seo-network`).
3. Enable the required APIs under **APIs & Services** &rarr; **Library**:
   - **Google Search Console API** (Search Console / Webmasters API)
   - **Web Search Indexing API** (Indexing API)
4. Go to **IAM & Admin** &rarr; **Service Accounts** &rarr; **Create Service Account**.
   - Name: `gsc-indexer-bot`
   - Description: `Service account for automated Google Search Console sitemap and index broadcast`
5. Click **Done** (no project-level IAM roles are strictly required; site permissions are granted inside Google Search Console itself).

#### 3.2 Generate and Download JSON Key
1. Click on the newly created service account &rarr; select the **Keys** tab.
2. Click **Add Key** &rarr; **Create new key** &rarr; choose **JSON** format &rarr; click **Create**.
3. Save the downloaded JSON file to:
   ```
   state/gsc_service_account.json
   ```
   *(Alternatively, set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` in your `.env` file).*

#### 3.3 Grant Permissions in Google Search Console
**CRITICAL:** Google Search Console requires the service account email to be explicitly delegated on each verified property:
1. Copy the service account email address (e.g. `gsc-indexer-bot@adstera-seo-network.iam.gserviceaccount.com`).
2. Go to [Google Search Console](https://search.google.com/search-console).
3. For **each of your 10 domains** (`loanraaj.com`, `karzseva.com`, `loankiseva.com`, etc.):
   - Select the property.
   - Go to **Settings** &rarr; **Users and permissions** &rarr; **Add user**.
   - Paste the service account email.
   - Set Permission to **Owner** (or **Full**).
   - Click **Add**.

#### 3.4 Verify Credentials
Run the verification check:
```bash
python -c "from gsc_auth import GSCAuthManager; print(GSCAuthManager().get_status())"
```
Output should indicate `"configured": True` and display your service account's `client_email`.

---

## 4. Network Transport (Proxies or Mobile USB ADB)

### Action Steps
1. For proxy transport:
   - Copy `proxies.example.txt` to `proxies.txt` (which is gitignored).
   - Insert your real residential or 4G mobile proxy lines (`user:pass@host:port` or `host:port:user:pass`).
2. For mobile tethering transport:
   - Connect an Android smartphone via USB cable with **USB Debugging** enabled.
   - Run `adb devices` in terminal to confirm the device is detected in `device` status.

---

## 5. Final Pre-flight Verification

Once all three sections are completed, run:
```bash
python scripts/preflight_seo.py
```
When all inputs are configured, the command will display `[OK]` across all categories and exit with code `0`.

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
