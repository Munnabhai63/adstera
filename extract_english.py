import re
import json
import httpx

client = httpx.Client(
    timeout=20,
    follow_redirects=True,
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
)

english_articles_urls = [
    ("21-machines-business", "https://bazartak.net/21-machines-to-start-a-profitable-home-business/", "Business"),
    ("hotshot-trucking-insurance", "https://bazartak.net/hotshot-trucking-insurance/", "Insurance"),
    ("commercial-auto-insurance", "https://bazartak.net/commercial-auto-insurance-quotes/", "Insurance"),
    ("bobtail-insurance-guide", "https://bazartak.net/bobtail-insurance-what-it-costs-what-it-covers/", "Insurance"),
    ("will-ai-replace-truck-drivers", "https://bazartak.net/will-ai-replace-truck-drivers/", "Carrier"),
    ("fleet-truck-insurance-guide", "https://bazartak.net/fleet-truck-insurance-cost-small-operators/", "Insurance"),
    ("how-to-get-cdl-trucking", "https://bazartak.net/how-i-went-from-broke-to-80000-a-year-by-trucking/", "Carrier"),
    ("commercial-truck-insurance", "https://bazartak.net/commercial-truck-insurance/", "Insurance"),
    ("semi-truck-insurance-cost", "https://bazartak.net/semi-truck-insurance-cost-in-2026/", "Insurance"),
    ("owner-operator-insurance", "https://bazartak.net/owner-operator-insurance-what-it-really-costs/", "Insurance"),
    ("cdl-training-guide", "https://bazartak.net/i-earned-my-cdl-at-26-with-no-experience/", "Carrier"),
    ("commercial-business-insurance", "https://kamtak.in/how-to-compare-commercial-business-insurance/", "Finance"),
]

extracted = []

print("Extracting full English articles from bazartak.net & kamtak.in...")

for slug, url, category in english_articles_urls:
    try:
        r = client.get(url)
        if r.status_code != 200:
            print(f"Skipping {url} (status {r.status_code})")
            continue
            
        html = r.text
        
        # Title
        title_m = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        if not title_m:
            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else slug.replace('-', ' ').title()
        clean_title = raw_title.replace('Bazartak', 'LoanRaaj').replace('- Bazartak', '').strip()
        
        # Image
        feat_img = ""
        og_img = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_img:
            feat_img = og_img.group(1)
        else:
            first_img = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>.*?<img[^>]*src=["\']([^"\']+)["\']', html, re.DOTALL | re.IGNORECASE)
            if first_img:
                feat_img = first_img.group(1)
                
        # Content
        content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>\s*<!--\s*\.entry-content', html, re.DOTALL | re.IGNORECASE)
        if not content_m:
            content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>\s*<div[^>]*class=["\'][^"\']*post-tags', html, re.DOTALL | re.IGNORECASE)
        if not content_m:
            content_m = re.search(r'<div[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
            
        raw_content = content_m.group(1) if content_m else ""
        
        # Clean Content
        clean_content = re.sub(r'<script.*?</script>', '', raw_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<ins.*?</ins>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<iframe.*?</iframe>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = clean_content.replace('Bazartak', 'LoanRaaj').replace('bazartak.net', 'loanraaj.com').replace('bazartak.in', 'loanraaj.com').replace('kamtak.in', 'loanraaj.com')
        
        snippet = re.sub(r'<[^>]+>', ' ', clean_content)[:170].strip() + '...'
        
        extracted.append({
            "slug": slug,
            "title": clean_title,
            "category": category,
            "image": feat_img or "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=800&auto=format&fit=crop&q=80",
            "snippet": snippet,
            "content": clean_content,
            "read_time": "5 min read",
            "date": "November 2026",
            "author": "LoanRaaj Editorial Team"
        })
        print(f"  [OK] {clean_title[:55]} ({category})")
        
    except Exception as e:
        print(f"  [ERR] {url}: {e}")

with open('extracted_english_articles.json', 'w', encoding='utf-8') as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"Successfully saved {len(extracted)} pure English articles.")
