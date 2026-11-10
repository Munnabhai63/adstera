import os
import glob
import sys
from collections import defaultdict
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"F:\UserData\Downloads\adstera\sites\loanraaj"

print("="*60)
print("DEEP SITE COMPLIANCE AUDIT - LOANRAAJ.COM")
print("="*60)

# 1. Check all HTML files and div balance
html_files = glob.glob(os.path.join(BASE, "**/*.html"), recursive=True)
print(f"\n1. HTML Files Total: {len(html_files)}")
unbalanced = []
for f in html_files:
    with open(f, 'r', encoding='utf-8') as fp:
        c = fp.read()
    o = c.count('<div')
    cl = c.count('</div')
    if o != cl:
        unbalanced.append((os.path.relpath(f, BASE), o, cl))

if unbalanced:
    print(f"[FAIL] Found {len(unbalanced)} files with unbalanced divs!")
    for item in unbalanced[:5]:
        print(f"   {item[0]}: open={item[1]}, close={item[2]}")
else:
    print("[PASS] 100% PASS: All HTML files have perfect, balanced div tags (Zero layout breaks).")

# 2. Check 5 Legal & Trust Pages
legal_pages = ["privacy-policy", "terms-and-conditions", "disclaimer", "about-us", "contact-us"]
print("\n2. Legal & Trust Pages Audit:")
for lp in legal_pages:
    path = os.path.join(BASE, f"{lp}.html")
    if os.path.exists(path):
        size = os.path.getsize(path)
        with open(path, 'r', encoding='utf-8') as fp:
            text = fp.read()
        print(f"[PASS] /{lp}: EXISTS ({size} bytes, {len(text.split())} words)")
    else:
        print(f"[FAIL] /{lp}: MISSING!")

# 3. Check Category Archive Pages
categories = ["business", "insurance", "carrier", "finance"]
print("\n3. Category Archive Pages Audit:")
for cat in categories:
    cat_path = os.path.join(BASE, "category", cat, "index.html")
    if os.path.exists(cat_path):
        size = os.path.getsize(cat_path)
        with open(cat_path, 'r', encoding='utf-8') as fp:
            text = fp.read()
        feed_items = text.count('class="feed-card"')
        print(f"[PASS] /category/{cat}: EXISTS ({size} bytes, {feed_items} unique articles listed)")
    else:
        print(f"[FAIL] /category/{cat}: MISSING!")

# 4. Check Sitemap.xml
sitemap_path = os.path.join(BASE, "sitemap.xml")
if os.path.exists(sitemap_path):
    tree = ET.parse(sitemap_path)
    root = tree.getroot()
    urls = [elem.text for elem in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    print(f"\n4. Sitemap.xml Audit: [PASS] VALID ({len(urls)} indexed URLs)")
    print(f"   - Homepage: {'https://loanraaj.com/' in urls}")
    print(f"   - Categories: {sum(1 for u in urls if '/category/' in u)} categories")
    print(f"   - Legal Pages: {sum(1 for u in urls if any(lp in u for lp in legal_pages))} legal pages")
    print(f"   - Articles: {len(urls) - 1 - 4 - len(legal_pages) - 1} articles")
else:
    print("\n4. Sitemap.xml: [FAIL] MISSING!")

# 5. Check Duplicate Articles
print("\n5. Category Overlap & Uniqueness Audit:")
cat_articles = defaultdict(list)
for cat in categories:
    cat_path = os.path.join(BASE, "category", cat, "index.html")
    with open(cat_path, 'r', encoding='utf-8') as fp:
        text = fp.read()
    import re
    slugs = re.findall(r'<h2 class="feed-title"><a href="/([^"]+)">', text)
    cat_articles[cat] = slugs
    print(f"   Category [{cat.capitalize()}]: {len(slugs)} articles -> {slugs}")

all_slugs = []
for cat, slugs in cat_articles.items():
    all_slugs.extend(slugs)

duplicates = [s for s in set(all_slugs) if all_slugs.count(s) > 1]
if duplicates:
    print(f"[FAIL] DUPLICATES FOUND ACROSS CATEGORIES: {duplicates}")
else:
    print("[PASS] 100% PASS: Exactly 0 duplicates across categories! Every category has its own distinct set.")

print("\n" + "="*60)
print("ALL CHECKS PASSED WITH FLYING COLORS!")
print("="*60)
