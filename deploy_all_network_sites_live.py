from common import npx_bin
# deploy_all_network_sites_live.py - Automated Cloudflare Pages Deployment & Live Verification
import os
import subprocess
import urllib.request
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECTS = [
    ("loanraaj", "https://loanraaj.com"),
    ("rechargetak", "https://rechargetak.com"),
    ("rechargepur", "https://rechargepur.com"),
    ("tazaloan", "https://tazaloan.com"),
    ("loankiseva", "https://loankiseva.com"),
    ("karzseva", "https://karzseva.com"),
    ("loantau", "https://loantau.com"),
    ("tazabhav", "https://tazabhav.com"),
    ("tazarokda", "https://tazarokda.com"),
    ("rechargekar", "https://rechargekar.com")
]

print("="*70)
print("DEPLOYING ALL 10 NETWORK DOMAINS TO CLOUDFLARE PAGES")
print("="*70)

deploy_results = {}

for proj, domain in PROJECTS:
    site_dir = os.path.join("sites", f"{proj}.com")
    print(f"\n[Deploying {proj}] -> Source: {site_dir} to Cloudflare Project: {proj}...")
    
    cmd = [npx_bin(), "wrangler", "pages", "deploy", site_dir, f"--project-name={proj}", "--branch=main", "--commit-dirty=true"]
    try:
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0:
            print(f"  -> SUCCESS! Deployed {proj} to Cloudflare Pages.")
            deploy_results[proj] = True
        else:
            print(f"  -> FAILED to deploy {proj}:\n{res.stderr[:300]}")
            deploy_results[proj] = False
    except Exception as e:
        print(f"  -> Execution error on {proj}: {e}")
        deploy_results[proj] = False
    time.sleep(1)

print("\n" + "="*70)
print("VERIFYING LIVE HTTPS REACHABILITY ACROSS ALL 9 DOMAINS")
print("="*70)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

all_live = True

for proj, domain in PROJECTS:
    urls_to_test = [
        f"{domain}/",
        f"{domain}/google31976c4df01121b2.html",
        f"{domain}/sitemap.xml",
        f"{domain}/calculator"
    ]
    
    site_ok = True
    for url in urls_to_test:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    pass
                else:
                    print(f"  [WARN] {url} -> Status {resp.status}")
                    site_ok = False
        except Exception as e:
            print(f"  [FAIL] {url} -> Error: {e}")
            site_ok = False
            
    if site_ok:
        print(f"[LIVE OK] {domain:28} -> Homepage, Verification Token, Sitemap, and Calculator all HTTP 200!")
    else:
        print(f"[DEGRADED] {domain:28} -> Issues detected during live ping.")
        all_live = False

print("\n" + "="*70)
if all_live:
    print("ALL 9 DOMAINS ARE 100% LIVE, UPDATED, AND FULLY FUNCTIONAL!")
else:
    print("Deployment completed with some live reachability warnings.")
print("="*70)
