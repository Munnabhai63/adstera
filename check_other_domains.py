import urllib.request
import re

for domain in ['https://bazartak.in', 'https://kamtak.in']:
    for sm in ['/post-sitemap.xml', '/sitemap.xml', '/wp-sitemap-posts-post-1.xml']:
        url = domain + sm
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read().decode('utf-8', errors='ignore')
                urls = re.findall(r'<loc>(https?://[^<]+)</loc>', data)
                print(f"[{domain}] {sm} -> {len(urls)} items")
                for u in urls[:5]:
                    print("   ", u)
                break
        except Exception as e:
            print(f"[{domain}] {sm} -> {e}")
