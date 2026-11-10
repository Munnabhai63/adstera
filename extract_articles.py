import sys
import re
import json
import httpx

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

client = httpx.Client(
    timeout=20,
    follow_redirects=True,
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
)

target_urls = [
    ("pmegp-loan-scheme", "https://bazartak.in/pmegp-business-loan-apply-now/", "Business Loan"),
    ("daughter-loan-scheme", "https://bazartak.in/loan-scheme-for-daughter/", "Personal Loan"),
    ("moneyview-loan-apply", "https://bazartak.in/moneyview-loan-apply-now/", "Instant Loan"),
    ("pnb-home-loan-guide", "https://bazartak.in/pnb-home-loan/", "Home Loan"),
    ("hdfc-credit-card-apply", "https://bazartak.in/hdfc-credit-card/", "Credit Card"),
    ("car-loan-guide", "https://bazartak.in/car-loan-kaise-le/", "Car Loan"),
    ("uyegp-loan-scheme", "https://bazartak.in/uyegp-loan-scheme-apply-online/", "Government Loan"),
    ("best-health-insurance", "https://bazartak.in/best-health-insurance-in-india/", "Insurance"),
    ("work-from-home-jobs", "https://bazartak.in/best-work-from-home-jobs-in-india/", "Work From Home"),
    ("jio-data-loan", "https://kamtak.in/jio-data-loan-2026/", "Recharge & Data"),
    ("21-machines-business", "https://bazartak.net/21-machines-to-start-a-profitable-home-business/", "Business Ideas"),
    ("commercial-auto-insurance", "https://bazartak.net/commercial-auto-insurance-quotes/", "Insurance"),
]

extracted = []

print("=" * 60)
print(f"EXTRACTING {len(target_urls)} ARTICLES FROM BROTHER SITES")
print("=" * 60)

for slug, url, category in target_urls:
    try:
        r = client.get(url)
        if r.status_code != 200:
            print(f"[FAIL] {url} -> Status {r.status_code}")
            continue
            
        html = r.text
        
        # 1. Title
        title_m = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        if not title_m:
            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else slug.replace('-', ' ').title()
        
        # 2. Featured Image
        feat_img = ""
        og_img = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_img:
            feat_img = og_img.group(1)
        else:
            first_img = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>.*?<img[^>]*src=["\']([^"\']+)["\']', html, re.DOTALL | re.IGNORECASE)
            if first_img:
                feat_img = first_img.group(1)
                
        # 3. Main Content
        content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>\s*<!--\s*\.entry-content', html, re.DOTALL | re.IGNORECASE)
        if not content_m:
            content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>\s*<div[^>]*class=["\'][^"\']*post-tags', html, re.DOTALL | re.IGNORECASE)
        if not content_m:
            # Fallback
            content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
            
        raw_content = content_m.group(1) if content_m else ""
        
        # Clean Content: Remove scripts, iframes, original site ads
        clean_content = re.sub(r'<script.*?</script>', '', raw_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<ins.*?</ins>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<iframe.*?</iframe>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        # Re-brand Bazartak / Kamtak to LoanRaaj
        clean_content = clean_content.replace('Bazartak', 'LoanRaaj').replace('bazartak.in', 'loanraaj.com').replace('bazartak.net', 'loanraaj.com').replace('kamtak.in', 'loanraaj.com')
        clean_title = raw_title.replace('Bazartak', 'LoanRaaj').replace('- Bazartak', '').strip()
        
        # Meta description summary
        snippet = re.sub(r'<[^>]+>', ' ', clean_content)[:160].strip() + '...'
        
        extracted.append({
            "slug": slug,
            "title": clean_title,
            "category": category,
            "image": feat_img or "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=800&auto=format&fit=crop&q=80",
            "snippet": snippet,
            "content": clean_content,
            "read_time": "5 min read",
            "date": "November 2026",
            "author": "LoanRaaj Financial Editorial Team"
        })
        print(f"[SUCCESS] Extracted: {clean_title[:55]} ({category})")
        
    except Exception as e:
        print(f"[ERROR] Extracting {url}: {e}")

with open('extracted_articles.json', 'w', encoding='utf-8') as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(extracted)} complete articles to extracted_articles.json")
