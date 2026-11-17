from common import npx_bin
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

VERIFY_FILENAME = "google31976c4df01121b2.html"
VERIFY_CONTENT = "google-site-verification: google31976c4df01121b2.html\n"
META_TAG = '<meta name="google-site-verification" content="google31976c4df01121b2">'

print("="*60)
print("1. Injecting Google Verification File & Meta Tags into all 10 sites")
print("="*60)

for proj, domain in PROJECTS:
    dirs_to_update = [os.path.join("sites", f"{proj}.com")]
    
    for d in dirs_to_update:
        if os.path.exists(d):
            # 1. Write verification file
            v_path = os.path.join(d, VERIFY_FILENAME)
            with open(v_path, "w", encoding="utf-8") as f:
                f.write(VERIFY_CONTENT)
            print(f"[{proj}] Wrote {v_path}")
            
            # 2. Inject meta tag into index.html and all html files
            for root, dirs, files in os.walk(d):
                dirs[:] = [sub for sub in dirs if sub not in ("layouts", "content")]
                for file in files:
                    if file.endswith(".html") and not file.startswith("google"):
                        html_path = os.path.join(root, file)
                        try:
                            with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                                html_text = f.read()
                            if "google-site-verification" not in html_text and "<head>" in html_text:
                                html_text = html_text.replace("<head>", f"<head>\n    {META_TAG}")
                                with open(html_path, "w", encoding="utf-8") as f:
                                    f.write(html_text)
                        except Exception as e:
                            print(f"Error updating {html_path}: {e}")

print("\n" + "="*60)
print("2. Deploying all 10 sites to Cloudflare Pages via Wrangler")
print("="*60)

for proj, domain in PROJECTS:
    site_dir = os.path.join("sites", f"{proj}.com")
    print(f"\nDeploying {proj} ({site_dir}) to Cloudflare Pages...")
    cmd = [npx_bin(), "wrangler", "pages", "deploy", site_dir, f"--project-name={proj}", "--branch=main", "--commit-dirty=true"]
    try:
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0:
            print(f"  -> SUCCESS! Deployed {proj}")
        else:
            print(f"  -> FAILED {proj}:\n{res.stderr[:300]}")
    except Exception as e:
        print(f"  -> Execution error {proj}: {e}")
    time.sleep(1)

print("\n" + "="*60)
print("3. Verifying live HTTP 200 on all 9 verification URLs")
print("="*60)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

all_ok = True
for proj, domain in PROJECTS:
    test_url = f"{domain}/{VERIFY_FILENAME}"
    try:
        req = urllib.request.Request(test_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            if "google-site-verification" in body:
                print(f"[PASS] {test_url} -> Status: {resp.status} (Verified content present)")
            else:
                print(f"[WARN] {test_url} -> Status: {resp.status} (Body mismatch)")
                all_ok = False
    except Exception as e:
        print(f"[FAIL] {test_url} -> Error: {e}")
        all_ok = False

if all_ok:
    print("\nALL 9 DOMAINS ARE 100% LIVE AND READY FOR GOOGLE SEARCH CONSOLE VERIFICATION!")
else:
    print("\nSome domains failed verification. Please review output above.")
