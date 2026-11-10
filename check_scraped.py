import json
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

print(f"Total articles in full_scraped_articles.json: {len(articles)}")
for a in articles:
    print(f"- {a['slug']} | title: {a['title'][:40]} | chars: {a.get('content_len', 0)} | words: {a.get('words', 0)}")
