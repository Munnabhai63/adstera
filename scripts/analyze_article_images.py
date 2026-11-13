from pathlib import Path
import re

base = Path("sites")
article_pages = []
for p in base.glob("*/*/index.html"):
    article_pages.append(p)

print(f"Total article pages (slug/index.html): {len(article_pages)}")

img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

zero_image = []
lt5_image = []
gte5_image = []

for p in article_pages:
    text = p.read_text(encoding="utf-8", errors="ignore")
    # Content images (exclude logo, tracker, etc.)
    imgs = [i for i in img_pattern.findall(text) if "logo" not in i.lower() and "badge" not in i.lower()]
    count = len(imgs)
    if count == 0:
        zero_image.append(p)
    elif count < 5:
        lt5_image.append((p, count))
    else:
        gte5_image.append((p, count))

print(f"Zero-image articles: {len(zero_image)}")
print(f"1-4 images articles: {len(lt5_image)}")
print(f"5+ images articles: {len(gte5_image)}")
