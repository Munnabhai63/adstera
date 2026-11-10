import urllib.request
import re
import json
import time

urls = [
    "https://bazartak.net/21-machines-to-start-a-profitable-home-business/",
    "https://bazartak.net/pmegp-loan-apply-now/",
    "https://bazartak.net/hotshot-trucking-insurance/",
    "https://bazartak.net/commercial-auto-insurance-quotes/",
    "https://bazartak.net/bobtail-insurance-what-it-costs-what-it-covers/",
    "https://bazartak.net/will-ai-replace-truck-drivers/",
    "https://bazartak.net/fleet-truck-insurance-cost-small-operators/",
    "https://bazartak.net/how-i-went-from-broke-to-80000-a-year-by-trucking/",
    "https://bazartak.net/trucking-insurance-quotes-how-i-compared-11-quotes/",
    "https://bazartak.net/owner-operator-insurance-what-it-really-costs/",
    "https://bazartak.net/semi-truck-insurance-cost-in-2026/",
    "https://bazartak.net/commercial-truck-insurance/",
    "https://bazartak.net/i-earned-my-cdl-at-26-with-no-experience/",
    "https://bazartak.net/10-best-spiral-snake-plant-varieties/",
    "https://bazartak.net/turn-a-snake-plant-into-a-spiral-shape/"
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

scraped_articles = []

for u in urls:
    slug = u.strip('/').split('/')[-1]
    print(f"Fetching: {slug} ...")
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
            # 1. Title
            title_m = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            if not title_m:
                title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else slug.replace('-', ' ').title()
            
            # 2. Category
            cat_m = re.search(r'rel="category tag"[^>]*>(.*?)</a>', html)
            category = re.sub(r'<[^>]+>', '', cat_m.group(1)).strip() if cat_m else "Finance"
            
            # 3. Featured Image
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if not img_m:
                img_m = re.search(r'class="attachment-mvp-post-thumb[^"]*"[^>]+src="([^"]+)"', html)
            img_url = img_m.group(1) if img_m else ""
            
            # 4. Content inside #mvp-content-main
            # Find start of mvp-content-main
            content_start = html.find('id="mvp-content-main"')
            if content_start != -1:
                # Find the tag closure or container end
                # In Zox, it's <div id="mvp-content-main" ... > ... </div><!--mvp-content-main--> or similar
                # Let's extract between id="mvp-content-main" and next post author / share box
                sub = html[content_start:]
                # tag opening end
                tag_open_end = sub.find('>')
                sub = sub[tag_open_end+1:]
                
                # End markers in Zox-News
                end_markers = ['<div class="posts-nav-link', '<div id="comments"', '<div class="mvp-org-wrap"', '<div class="mvp-post-tags"', '<div id="mvp-author-box-wrap"']
                end_pos = len(sub)
                for em in end_markers:
                    pos = sub.find(em)
                    if pos != -1 and pos < end_pos:
                        end_pos = pos
                
                raw_body = sub[:end_pos].strip()
                
                # Clean scripts and ad codes from raw_body
                clean_body = re.sub(r'<script.*?</script>', '', raw_body, flags=re.DOTALL | re.IGNORECASE)
                clean_body = re.sub(r'<div class=[\'"]code-block.*?</div>', '', clean_body, flags=re.DOTALL | re.IGNORECASE)
                clean_body = re.sub(r'<!--.*?-->', '', clean_body, flags=re.DOTALL)
                
                # Replace branding
                clean_body = clean_body.replace('BazarTak', 'LoanRaaj').replace('bazartak.net', 'loanraaj.com').replace('Bazar Tak', 'LoanRaaj')
                
                # Internal links rewriting
                clean_body = re.sub(r'https?://(?:www\.)?bazartak\.net/([a-z0-9\-]+)/?', r'/\1', clean_body)
                
                # Remove empty tags
                clean_body = re.sub(r'<p>\s*</p>', '', clean_body)
                clean_body = re.sub(r'<div>\s*</div>', '', clean_body)
            else:
                clean_body = ""
            
            # Excerpt
            clean_text = re.sub(r'<[^>]+>', ' ', clean_body)
            clean_text = ' '.join(clean_text.split())
            excerpt = clean_text[:180] + "..." if len(clean_text) > 180 else clean_text
            
            scraped_articles.append({
                "slug": slug,
                "title": title,
                "category": category,
                "image": img_url,
                "excerpt": excerpt,
                "content": clean_body,
                "content_len": len(clean_body),
                "words": len(clean_text.split())
            })
            print(f" -> OK: {title[:40]} | Body: {len(clean_body)} chars | {len(clean_text.split())} words")
            time.sleep(0.3)
    except Exception as e:
        print(f" -> ERROR: {e}")

with open('full_scraped_articles.json', 'w', encoding='utf-8') as f:
    json.dump(scraped_articles, f, ensure_ascii=False, indent=2)

print(f"\nDone! Saved {len(scraped_articles)} full articles to full_scraped_articles.json")
