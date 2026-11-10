import json

with open('extracted_english_articles.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for item in data:
    print(f"Title: {item.get('title')}")
    print(f"URL: {item.get('url')}")
    print("-" * 50)
