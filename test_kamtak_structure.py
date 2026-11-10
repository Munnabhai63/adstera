import urllib.request
import re

url = "https://kamtak.in/how-to-get-an-instant-loan/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# find all divs with id or class that contain content or post or entry
matches = re.findall(r'<div[^>]+(?:id|class)=["\']([^"\']+)["\']', html)
candidates = [m for m in matches if any(k in m.lower() for k in ['content', 'entry', 'post', 'article', 'body'])]
print("Found candidate containers:", candidates[:20])

# let's search for some text from the article
p_tags = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
print(f"Total <p> tags: {len(p_tags)}")
for p in p_tags[5:10]:
    clean = re.sub(r'<[^>]+>', '', p).strip()
    if len(clean) > 30:
        print("P snippet:", clean[:100])
