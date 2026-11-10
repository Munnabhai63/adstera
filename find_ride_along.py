with open('test_sanitizer.py', 'r') as f:
    pass

import json
from bs4 import BeautifulSoup

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

target = next(a for a in articles if 'broke-to-80000' in a['slug'])
idx = target['content'].find('RIDE ALONG')
if idx != -1:
    print(target['content'][max(0, idx-300):idx+300])
else:
    print("Not found")
