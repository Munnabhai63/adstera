import urllib.request
import re

req = urllib.request.Request('https://kamtak.in/post-sitemap.xml', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
with urllib.request.urlopen(req, timeout=10) as resp:
    data = resp.read().decode('utf-8')

urls = re.findall(r'<loc>(https://kamtak\.in/[^<]+)</loc>', data)
print(f"Total posts on kamtak.in: {len(urls)}")
for i, u in enumerate(urls):
    print(f"{i+1}: {u}")
