import urllib.request
import re

req = urllib.request.Request('https://bazartak.net/post-sitemap.xml', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    content = resp.read().decode('utf-8')

urls = re.findall(r'<loc>(https://bazartak\.net/[^<]+)</loc>', content)
print(f"Total posts in post-sitemap.xml: {len(urls)}")
for i, u in enumerate(urls):
    print(f"{i+1}: {u}")
