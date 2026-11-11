"""
hugo_cf_builder.py — Step 3.1 (CF-1 to CF-6): Hugo Static Site & Cloudflare Pages Deployer

Sets up production-ready Hugo static site configurations, semantic layouts,
and Cloudflare Pages deployment manifests for all 10 publisher domains:
1. loanraaj.com | rechargetak.com | rechargepur.com | tazaloan.com | loankiseva.com
2. karzseva.com | loantau.com | tazabhav.com | tazarokda.com | rechargekar.com
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).parent / "sites"

DOMAINS_METADATA = {
    "loanraaj.com": {"niche": "Finance & Loans", "lang": "hi-IN", "title": "LoanRaaj — Instant Personal & Business Loans Guide"},
    "rechargetak.com": {"niche": "Telecom & Recharge", "lang": "hi-IN", "title": "RechargeTak — Best Mobile Recharge Offers & Tricks"},
    "rechargepur.com": {"niche": "Cashback & Utility", "lang": "hi-IN", "title": "RechargePur — Cashback, Bill Pay & UPI Rewards"},
    "tazaloan.com": {"niche": "Emergency Cash Loans", "lang": "hi-IN", "title": "TazaLoan — 5-Minute Cash & Low CIBIL Loans"},
    "loankiseva.com": {"niche": "MSME & Govt Schemes", "lang": "hi-IN", "title": "LoanKiSeva — MUDRA, MSME & Govt Subsidy Loans"},
    "karzseva.com": {"niche": "Credit Score & Debt", "lang": "hi-IN", "title": "KarzSeva — CIBIL Score Repair & Settlement Guide"},
    "loantau.com": {"niche": "Rural, Tractor & Gold", "lang": "hi-IN", "title": "LoanTau — Kisan Credit, Tractor & Gold Loans"},
    "tazabhav.com": {"niche": "Commodity & Gold Rates", "lang": "hi-IN", "title": "TazaBhav — Live Gold, Silver & Mandi Rates India"},
    "tazarokda.com": {"niche": "Stocks, Crypto & Wealth", "lang": "hi-IN", "title": "TazaRokda — Stock Market, Demat & Crypto Guide"},
    "rechargekar.com": {"niche": "DTH & Broadband Plans", "lang": "hi-IN", "title": "RechargeKar — DTH, Fiber & OTT Subscription Deals"},
}


def build_hugo_config(domain: str, meta: dict[str, str]) -> str:
    return f"""baseURL = "https://{domain}/"
languageCode = "{meta['lang']}"
title = "{meta['title']}"
theme = "editorial-clean"

[params]
  description = "{meta['title']} — Latest updates, guides, and tools for 2026."
  niche = "{meta['niche']}"
  author = "Mahi Editorial Team"
  adsterra_banner_active = true
  adsterra_socialbar_active = true
  cloudflare_pages = true

[taxonomies]
  category = "categories"
  tag = "tags"
"""


def build_baseof_html(domain: str, meta: dict[str, str]) -> str:
    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{{{ if .Title }}}}{{{{ .Title }}}} — {{{{ end }}}}{meta['title']}</title>
  <meta name="description" content="{{{{ with .Description }}}}{{{{ . }}}}{{{{ else }}}}{meta['title']}{{{{ end }}}}">
  <link rel="canonical" href="{{{{ .Permalink }}}}">
  
  <!-- Schema.org WebSite JSON-LD -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "{meta['title']}",
    "url": "https://{domain}/",
    "potentialAction": {{
      "@type": "SearchAction",
      "target": "https://{domain}/search?q={{search_term_string}}",
      "query-input": "required name=search_term_string"
    }}
  }}
  </script>

  <style>
    :root {{
      --primary: #1e3a8a; --accent: #2563eb; --bg: #f8fafc;
      --card: #ffffff; --text: #0f172a; --muted: #64748b; --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }}
    header {{ background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; position: sticky; top: 0; z-index: 50; }}
    .header-inner {{ max-width: 1040px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
    .logo {{ font-size: 20px; font-weight: 800; color: var(--primary); text-decoration: none; }}
    nav a {{ margin-left: 16px; color: var(--muted); text-decoration: none; font-size: 14px; }}
    nav a:hover {{ color: var(--accent); }}
    .container {{ max-width: 1040px; margin: 28px auto; padding: 0 16px; display: grid; grid-template-columns: 2.2fr 1fr; gap: 28px; }}
    @media (max-width: 768px) {{ .container {{ grid-template-columns: 1fr; }} }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 28px; }}
    .ad-slot {{ background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 16px; text-align: center; margin: 24px 0; }}
    footer {{ text-align: center; padding: 32px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--border); margin-top: 40px; }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <a href="/" class="logo">{domain}</a>
      <nav>
        <a href="/">होम</a>
        <a href="#articles">गाइड</a>
        <a href="#about">संपर्क</a>
      </nav>
    </div>
  </header>

  <main class="container">
    {{{{ block "main" . }}}}{{{{ end }}}}
  </main>

  <footer>
    <p>&copy; 2026 {domain} • All Rights Reserved • सर्वाधिकार सुरक्षित</p>
  </footer>
</body>
</html>
"""


def build_single_html() -> str:
    return """{{ define "main" }}
<article class="card">
  <h1>{{ .Title }}</h1>
  <div style="color:var(--muted); font-size:13px; margin-bottom:20px;">
    प्रकाशित: {{ .Date.Format "02 Jan 2026" }} • पढ़ना: ~{{ .ReadingTime }} मिनट
  </div>

  <div class="ad-slot">
    <div style="font-size:11px; text-transform:uppercase; color:var(--muted); margin-bottom:8px;">प्रायोजित विज्ञापन</div>
    <div id="adsterra-banner-top" style="min-height:90px; background:#e2e8f0; display:flex; align-items:center; justify-content:center;">
      <span style="color:#64748b; font-size:13px;">Adsterra Responsive Banner (728x90)</span>
    </div>
  </div>

  <div class="article-content">
    {{ .Content }}
  </div>

  <div class="ad-slot" style="margin-top:32px;">
    <div style="font-size:11px; text-transform:uppercase; color:var(--muted); margin-bottom:8px;">संबंधित ऑफ़र</div>
    <div id="adsterra-native-bottom" style="min-height:120px; background:#e2e8f0; display:flex; align-items:center; justify-content:center;">
      <span style="color:#64748b; font-size:13px;">Adsterra Native Recommendation Unit</span>
    </div>
  </div>
</article>

<aside>
  <div class="card" style="position:sticky; top:84px;">
    <h3 style="font-size:16px; margin-bottom:12px; color:var(--primary);">ताज़ा लेख एवं अपडेट्स</h3>
    <ul style="list-style:none;">
      {{ range first 5 (where .Site.RegularPages "Type" "posts") }}
        <li style="margin-bottom:10px;">
          <a href="{{ .RelPermalink }}" style="color:var(--accent); text-decoration:none; font-size:14px;">📄 {{ .Title }} →</a>
        </li>
      {{ end }}
    </ul>
  </div>
</aside>
{{ end }}
"""


def build_cf_headers() -> str:
    return """/*
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=()
  Cache-Control: public, max-age=3600
"""


def setup_all_hugo_sites(sites_dir: Path | None = None) -> dict[str, bool]:
    """Generates Hugo templates and Cloudflare Pages config across all 10 domains."""
    root_dir = Path(sites_dir) if sites_dir is not None else SITES_DIR
    status: dict[str, bool] = {}
    for domain, meta in DOMAINS_METADATA.items():
        dom_dir = root_dir / domain
        dom_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write hugo.toml
        (dom_dir / "hugo.toml").write_text(build_hugo_config(domain, meta), encoding="utf-8")

        # 2. Write layouts
        layouts_dir = dom_dir / "layouts" / "_default"
        layouts_dir.mkdir(parents=True, exist_ok=True)
        (layouts_dir / "baseof.html").write_text(build_baseof_html(domain, meta), encoding="utf-8")
        (layouts_dir / "single.html").write_text(build_single_html(), encoding="utf-8")

        # 3. Write Cloudflare Pages headers
        (dom_dir / "_headers").write_text(build_cf_headers(), encoding="utf-8")

        # 4. Content posts folder
        (dom_dir / "content" / "posts").mkdir(parents=True, exist_ok=True)

        status[domain] = True
        logger.info("Configured Hugo static site & Cloudflare Pages for %s", domain)

    return status


if __name__ == "__main__":
    res = setup_all_hugo_sites()
    print(f"Hugo & Cloudflare Pages setup complete for {len(res)} domains.")
