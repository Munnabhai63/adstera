"""
deploy_all_pages.py — Autonomous deployment of all 10 publisher sites to Cloudflare Pages.
Binds custom apex and www domains to Cloudflare global edge CDN.
Eliminates Cloudflare Error 1033 permanently.
"""
import os
import sys
import time
import subprocess
import httpx

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

def load_env():
    env = {}
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"\'')
    return env

env = load_env()
account_id = env.get('CLOUDFLARE_ACCOUNT_ID')
token = env.get('CLOUDFLARE_API_TOKEN')

if not account_id or not token:
    print("[ERROR] CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN not found in .env")
    sys.exit(1)

# Ensure no stray wrangler.jsonc in root
if os.path.exists('wrangler.jsonc'):
    try:
        os.remove('wrangler.jsonc')
    except Exception:
        pass

os.environ['CLOUDFLARE_ACCOUNT_ID'] = account_id
os.environ['CLOUDFLARE_API_TOKEN'] = token

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

client = httpx.Client(headers=headers, timeout=25)

DOMAINS = [
    ("loanraaj", "loanraaj.com"),
    ("rechargetak", "rechargetak.com"),
    ("rechargepur", "rechargepur.com"),
    ("tazaloan", "tazaloan.com"),
    ("loankiseva", "loankiseva.com"),
    ("karzseva", "karzseva.com"),
    ("loantau", "loantau.com"),
    ("tazabhav", "tazabhav.com"),
    ("tazarokda", "tazarokda.com"),
    ("rechargekar", "rechargekar.com"),
]

TUNNEL_ID = '3fd601c7-288f-496c-9f93-db0d37822076'

print("=" * 60)
print("CLOUDFLARE PAGES 24/7 PERMANENT ZERO-DOWNTIME DEPLOYMENT")
print("=" * 60)

# STEP 1: Fetch Zone IDs
print("\n[1/6] Fetching Cloudflare Zone IDs...")
r_zones = client.get('https://api.cloudflare.com/client/v4/zones?per_page=50')
zone_map = {}
if r_zones.status_code == 200:
    for z in r_zones.json().get('result', []):
        zone_map[z['name']] = z['id']
    print(f"Loaded {len(zone_map)} zones from account.")
else:
    print(f"[ERROR] Failed to fetch zones: {r_zones.text}")
    sys.exit(1)

# STEP 2: Clean Tunnel Ingress so DNS records are unlocked
print("\n[2/6] Cleaning Cloudflare Tunnel ingress configuration...")
try:
    r_tun = client.get(f'https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel/{TUNNEL_ID}/configurations')
    if r_tun.status_code == 200:
        cfg = r_tun.json()['result']['config']
        old_ingress = cfg.get('ingress', [])
        
        all_domain_names = set()
        for name, d_name in DOMAINS:
            all_domain_names.add(d_name)
            all_domain_names.add(f"www.{d_name}")
            
        new_ingress = [
            ig for ig in old_ingress
            if ig.get('hostname') not in all_domain_names
        ]
        has_admin = any(ig.get('hostname') == 'admin.rechargetak.com' for ig in new_ingress)
        if not has_admin:
            new_ingress.insert(0, {
                "hostname": "admin.rechargetak.com",
                "service": "http://localhost:5050"
            })
            
        cfg['ingress'] = new_ingress
        r_up = client.put(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel/{TUNNEL_ID}/configurations',
            json={'config': cfg}
        )
        print(f"Tunnel config updated: Status {r_up.status_code}, success={r_up.json().get('success')}")
        time.sleep(2)
except Exception as e:
    print(f"[WARN] Tunnel config update error: {e}")

# STEP 3: Clean up any old Workers custom domains for our 10 domains
print("\n[3/6] Checking for old Workers custom domain bindings...")
try:
    r_wcd = client.get(f'https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/domains')
    if r_wcd.status_code == 200:
        w_domains = r_wcd.json().get('result', [])
        for wd in w_domains:
            h = wd.get('hostname', '')
            for _, d_name in DOMAINS:
                if h == d_name or h == f"www.{d_name}":
                    wd_id = wd.get('id')
                    print(f"  Removing worker domain binding: {h} ({wd_id})")
                    client.delete(f'https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/domains/{wd_id}')
except Exception as e:
    print(f"[WARN] Worker domain cleanup error: {e}")

# STEP 4: Deploy Each Site & Configure DNS / Pages Domains
print("\n[4/6] Deploying all 10 sites to Cloudflare Pages & binding domains...")

results = {}

for proj_name, domain_name in DOMAINS:
    print(f"\n>>> Processing: {proj_name} ({domain_name})")
    z_id = zone_map.get(domain_name)
    if not z_id:
        print(f"  [ERROR] Zone not found for {domain_name}")
        results[domain_name] = "FAIL: Zone not found"
        continue

    # A. Check or Create Pages Project via Cloudflare REST API
    r_proj = client.get(f'https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{proj_name}')
    if r_proj.status_code != 200:
        print(f"  Creating Pages project '{proj_name}' via REST API...")
        r_create = client.post(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects',
            json={'name': proj_name, 'production_branch': 'main'}
        )
        if r_create.status_code in [200, 201]:
            print(f"  Created Pages project '{proj_name}' successfully.")
        else:
            print(f"  Create status: {r_create.status_code}, response: {r_create.text[:200]}")
    else:
        print(f"  Pages project '{proj_name}' already exists.")

    # B. Deploy Directory to Cloudflare Pages using Wrangler
    site_dir = f"sites/{domain_name}"
    print(f"  Deploying '{site_dir}' to Pages project '{proj_name}'...")
    deploy_cmd = [
        "npx", "wrangler", "pages", "deploy", site_dir,
        f"--project-name={proj_name}",
        "--branch=main",
        "--commit-dirty=true"
    ]
    res_dep = subprocess.run(deploy_cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    stdout_txt = res_dep.stdout or ""
    stderr_txt = res_dep.stderr or ""
    if "Deployment complete" in stdout_txt or "Success!" in stdout_txt:
        print(f"  Deployment complete: {proj_name}.pages.dev")
    else:
        last_line = (stdout_txt.strip().splitlines() or stderr_txt.strip().splitlines() or [""])[-1]
        print(f"  Deploy result: {last_line}")

    # C. Bind Custom Domains to Pages Project
    for host in [domain_name, f"www.{domain_name}"]:
        r_add_dom = client.post(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{proj_name}/domains',
            json={'name': host}
        )
        if r_add_dom.status_code in [200, 201]:
            print(f"  Bound {host} to Pages project.")
        else:
            err = r_add_dom.json().get('errors', [{}])[0].get('message', 'Already added or in progress')
            print(f"  Domain bind {host}: {err}")

    # D. Manage DNS Records in Zone
    target_cname = f"{proj_name}.pages.dev"
    r_dns = client.get(f'https://api.cloudflare.com/client/v4/zones/{z_id}/dns_records?per_page=50')
    dns_records = r_dns.json().get('result', []) if r_dns.status_code == 200 else []

    # Apex Record
    apex_recs = [r for r in dns_records if r['name'] == domain_name and r['type'] in ['CNAME', 'A', 'AAAA']]
    apex_already_ok = False
    for ar in apex_recs:
        if ar['type'] == 'CNAME' and ar['content'] == target_cname and ar['proxied']:
            print(f"  Apex CNAME already set to {target_cname}")
            apex_already_ok = True
            break
        else:
            del_r = client.delete(f'https://api.cloudflare.com/client/v4/zones/{z_id}/dns_records/{ar["id"]}')
            print(f"  Deleted old apex {ar['type']} record (ID: {ar['id']}): success={del_r.json().get('success')}")
    
    if not apex_already_ok:
        cr = client.post(
            f'https://api.cloudflare.com/client/v4/zones/{z_id}/dns_records',
            json={'type': 'CNAME', 'name': domain_name, 'content': target_cname, 'proxied': True}
        )
        print(f"  Created apex CNAME -> {target_cname}: success={cr.json().get('success')}")

    # WWW Record
    www_host = f"www.{domain_name}"
    www_recs = [r for r in dns_records if r['name'] == www_host and r['type'] in ['CNAME', 'A', 'AAAA']]
    www_already_ok = False
    for wr in www_recs:
        if wr['type'] == 'CNAME' and wr['content'] == target_cname and wr['proxied']:
            print(f"  WWW CNAME already set to {target_cname}")
            www_already_ok = True
            break
        else:
            up_r = client.put(
                f'https://api.cloudflare.com/client/v4/zones/{z_id}/dns_records/{wr["id"]}',
                json={'type': 'CNAME', 'name': www_host, 'content': target_cname, 'proxied': True}
            )
            print(f"  Updated WWW record -> {target_cname}: success={up_r.json().get('success')}")
            www_already_ok = True
            break
            
    if not www_already_ok:
        cr_w = client.post(
            f'https://api.cloudflare.com/client/v4/zones/{z_id}/dns_records',
            json={'type': 'CNAME', 'name': www_host, 'content': target_cname, 'proxied': True}
        )
        print(f"  Created WWW CNAME -> {target_cname}: success={cr_w.json().get('success')}")

    results[domain_name] = "DEPLOYED"

# STEP 5: Verification
print("\n" + "=" * 60)
print("[5/6] LIVE EDGE VERIFICATION (HTTP GET FROM CLOUDFLARE)")
print("=" * 60)

time.sleep(3)
verify_client = httpx.Client(timeout=12, follow_redirects=True)

success_count = 0
for proj_name, domain_name in DOMAINS:
    url = f"https://{domain_name}"
    url_sw = f"https://{domain_name}/sw.js"
    url_txt = f"https://{domain_name}/92a7b03c56fd70822e83.txt"
    try:
        r_main = verify_client.get(url)
        r_sw = verify_client.get(url_sw)
        r_txt = verify_client.get(url_txt)
        
        status_main = r_main.status_code
        status_sw = r_sw.status_code
        status_txt = r_txt.status_code
        
        has_hilltop = "e4262eb657cf6ce184c5" in r_txt.text
        
        print(f"[{domain_name:16}] Main: {status_main} | sw.js: {status_sw} | HilltopAds: {status_txt} -> Verified: {status_main == 200 and has_hilltop}")
        if status_main == 200:
            success_count += 1
    except Exception as e:
        print(f"[{domain_name:16}] Verification Error: {e}")

print("\n" + "=" * 60)
print(f"FINAL SUMMARY: {success_count}/{len(DOMAINS)} DOMAINS FULLY ONLINE ON CLOUDFLARE EDGE")
print("=" * 60)
