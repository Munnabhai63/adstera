import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

print(f"Total articles: {len(articles)}")

cat_map = defaultdict(list)
for a in articles:
    cat = a.get('category', 'Finance')
    cat_map[cat].append(a)

print("\n--- Category Breakdown ---")
for cat, arts in cat_map.items():
    print(f"\nCategory: [{cat}] -> {len(arts)} articles")
    for a in arts:
        print(f"   - {a['slug']}: {a['title'][:50]}")

print("\n--- Duplicate Check across categories ---")
slug_to_cats = defaultdict(set)
for a in articles:
    slug_to_cats[a['slug']].add(a.get('category', 'Finance'))

duplicates = {s: cats for s, cats in slug_to_cats.items() if len(cats) > 1}
if duplicates:
    print("Found duplicates across categories:", duplicates)
else:
    print("Zero duplicates across categories! Every article is strictly unique.")
