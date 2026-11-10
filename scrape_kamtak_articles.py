import urllib.request
import re
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

kamtak_urls = [
    ("how-to-get-an-instant-loan", "https://kamtak.in/how-to-get-an-instant-loan/", "Finance"),
    ("low-interest-personal-loan", "https://kamtak.in/low-interest-personal-loan-2026-with/", "Finance"),
    ("business-loan-guide", "https://kamtak.in/business-loan-2026-complete-guide/", "Business"),
    ("home-loan-fast-approval", "https://kamtak.in/home-loan-2026-how-to-get-fast-approval-with-low-interest/", "Finance"),
    ("loan-against-insurance-policy", "https://kamtak.in/loan-against-insurance-policy-2026/", "Insurance"),
    ("car-accident-lawyer-guide", "https://kamtak.in/car-accident-lawyer-2026/", "Insurance"),
    ("health-insurance-guide", "https://kamtak.in/health-insurance-2026/", "Insurance"),
    ("term-insurance-guide", "https://kamtak.in/term-insurance-2026/", "Insurance")
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

# Filter out plant articles from bazartak if any
articles = [a for a in articles if 'snake-plant' not in a['slug']]

for slug, url, default_cat in kamtak_urls:
    print(f"Scraping kamtak: {slug} ...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
            # Title
            t_m = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html)
            if not t_m:
                t_m = re.search(r'<h1[^>]*>(.*?)</h1>', html)
            title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else slug.replace('-', ' ').title()
            
            # Featured Image
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if not img_m:
                img_m = re.search(r'class="[^"]*wp-post-image[^"]*"[^>]+src="([^"]+)"', html)
            img_url = img_m.group(1) if img_m else ""
            
            # Content inside entry-content
            # Astra uses <div class="entry-content clear" itemprop="text">
            cs = html.find('entry-content')
            if cs != -1:
                sub = html[cs:]
                # find start of tag
                open_bracket = sub.find('>')
                sub = sub[open_bracket+1:]
                
                # end marker
                end_pos = sub.find('class="relpost-thumb-wrapper')
                if end_pos == -1:
                    end_pos = sub.find('class="ast-single-related-posts-container')
                if end_pos == -1:
                    end_pos = sub.find('<!-- .entry-content -->')
                if end_pos != -1:
                    raw_body = sub[:end_pos].strip()
                else:
                    raw_body = sub[:20000].strip()
                
                # clean scripts and ad blocks
                clean_body = re.sub(r'<script.*?</script>', '', raw_body, flags=re.DOTALL | re.IGNORECASE)
                clean_body = re.sub(r'<style.*?</style>', '', clean_body, flags=re.DOTALL | re.IGNORECASE)
                clean_body = re.sub(r'<!--.*?-->', '', clean_body, flags=re.DOTALL)
                clean_body = clean_body.replace('KamTak', 'LoanRaaj').replace('kamtak.in', 'loanraaj.com').replace('Kam Tak', 'LoanRaaj')
                clean_body = re.sub(r'https?://(?:www\.)?kamtak\.in/([a-z0-9\-]+)/?', r'/\1', clean_body)
                clean_body = re.sub(r'<p>\s*</p>', '', clean_body)
            else:
                clean_body = ""
            
            clean_text = re.sub(r'<[^>]+>', ' ', clean_body)
            clean_text = ' '.join(clean_text.split())
            excerpt = clean_text[:180] + "..." if len(clean_text) > 180 else clean_text
            
            articles.append({
                "slug": slug,
                "title": title,
                "category": default_cat,
                "image": img_url,
                "excerpt": excerpt,
                "content": clean_body,
                "content_len": len(clean_body),
                "words": len(clean_text.split())
            })
            print(f" -> OK: {title[:40]} | Body: {len(clean_body)} chars | {len(clean_text.split())} words")
            time.sleep(0.4)
    except Exception as e:
        print(f" -> ERROR: {e}")

with open('full_scraped_articles.json', 'w', encoding='utf-8') as f:
    json.dump(articles, f, ensure_ascii=False, indent=2)

print(f"\nAll complete! Total articles in library: {len(articles)}")
