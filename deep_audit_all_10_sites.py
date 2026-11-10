# deep_audit_all_10_sites.py - Exhaustive Audit for All 10 Domains
import os
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SITES = [
    "loanraaj",
    "rechargetak",
    "rechargepur",
    "tazaloan",
    "loankiseva",
    "karzseva",
    "loantau",
    "tazabhav",
    "tazarokda",
    "rechargekar"
]

print("="*70)
print("DEEP AUDIT FOR ALL 10 DOMAINS IN SITES DIRECTORY")
print("="*70)

all_ok = True
total_audited_html = 0

for site in SITES:
    site_path = os.path.join("sites", site)
    if not os.path.exists(site_path):
        print(f"[FAIL] Missing site directory: {site_path}")
        all_ok = False
        continue
        
    # Check verification file
    v_file = os.path.join(site_path, "google31976c4df01121b2.html")
    if not os.path.exists(v_file):
        print(f"[{site}] Missing verification file: {v_file}")
        all_ok = False
        
    # Check sitemap
    sm_file = os.path.join(site_path, "sitemap.xml")
    if not os.path.exists(sm_file):
        print(f"[{site}] Missing sitemap.xml")
        all_ok = False
    else:
        try:
            tree = ET.parse(sm_file)
            root = tree.getroot()
            url_count = len(root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'))
        except Exception as e:
            print(f"[{site}] Invalid XML sitemap: {e}")
            all_ok = False
            url_count = 0

    # Audit all HTML files for div balance and verification meta tag
    site_html_count = 0
    div_errors = []
    meta_errors = []
    
    for root, _, files in os.walk(site_path):
        for f in files:
            if f.endswith(".html") and not f.startswith("google"):
                f_path = os.path.join(root, f)
                site_html_count += 1
                total_audited_html += 1
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    
                    o_div = content.count("<div")
                    c_div = content.count("</div>")
                    if o_div != c_div:
                        div_errors.append((f, o_div, c_div))
                        
                    if "google-site-verification" not in content:
                        meta_errors.append(f)
                except Exception as e:
                    print(f"[{site}] Read error on {f}: {e}")
                    all_ok = False

    status = "PASS" if not div_errors and not meta_errors else "FAIL"
    print(f"[{status}] {site:12} -> {site_html_count:3} HTML files | {url_count:2} URLs in sitemap | Div errors: {len(div_errors)} | Meta errors: {len(meta_errors)}")
    if div_errors:
        print(f"   -> Div mismatches in: {div_errors[:3]}")
        all_ok = False
    if meta_errors:
        print(f"   -> Missing meta in: {meta_errors[:3]}")
        all_ok = False

print("\n" + "="*70)
print(f"Total HTML files verified across 10 sites: {total_audited_html}")
if all_ok:
    print("ALL 10 SITES PASSED THE DEEP AUDIT WITH ZERO ERRORS!")
else:
    print("Some sites had audit warnings. Check details above.")
print("="*70)
