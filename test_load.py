import json
import os
import re

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

print(f"Loaded {len(articles)} articles.")
for a in articles[:5]:
    print(f"- {a['slug']}: title={a['title'][:30]} | img={a['image'][:40]}... | body={len(a['content'])} chars")
