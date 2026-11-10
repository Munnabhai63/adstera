import json

with open('extracted_english_articles.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Total articles in json:', len(data))
for i, item in enumerate(data):
    content = item.get('content', '')
    print(f"{i+1}. {item.get('title')[:50]}... | content len: {len(content)} | snippet: {repr(content[:60])}")
