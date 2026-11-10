import urllib.request
import re

url = "https://bazartak.net/21-machines-to-start-a-profitable-home-business/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        print(f"Fetched live article! Total HTML Length: {len(html)}")
        
        # Check title
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        if title_m:
            print("Title:", re.sub(r'<[^>]+>', '', title_m.group(1)).strip())
        
        # In Zox-News theme, content is usually in <div id="content-area"> or <div class="entry-content"> or <div id="post-content"> or <div class="theiaPostSlider_preloadedSlide">
        for p in [r'<div[^>]*id="content-main"[^>]*>(.*?)</div>\s*<!--content-main-->',
                  r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>',
                  r'<div[^>]*id="post-content[^"]*"[^>]*>(.*?)</div>',
                  r'<article[^>]*>(.*?)</article>']:
            m = re.search(p, html, re.DOTALL | re.IGNORECASE)
            if m:
                print(f"Matched {p[:30]}! Length: {len(m.group(1))}")
                body = m.group(1)
                # print first 500 chars of plain text
                clean = re.sub(r'<[^>]+>', ' ', body)
                clean = ' '.join(clean.split())
                print("Text preview:", clean[:300])
                break
        else:
            print("Looking for divs with id or class...")
            matches = re.findall(r'<div[^>]+(?:id|class)=["\']([^"\']+)["\']', html)
            print("Divs:", [m for m in matches if any(k in m.lower() for k in ['content', 'post', 'body', 'entry', 'article', 'main'])][:20])
except Exception as e:
    print(f"Fetch error: {e}")
