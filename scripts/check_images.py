import re
from pathlib import Path

base = Path("sites")
img_re = re.compile(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', re.IGNORECASE)
urls = set()
for p in base.glob("**/*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    for u in img_re.findall(text):
        urls.add(u)

print(f"Total unique external image URLs: {len(urls)}")
domains = {}
for u in urls:
    dom = u.split("/")[2]
    domains[dom] = domains.get(dom, 0) + 1

for d, count in sorted(domains.items(), key=lambda x: -x[1]):
    print(f"  {d}: {count} images")
