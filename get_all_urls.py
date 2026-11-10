import re

with open(r'woblo_extracted\home-bazartak\index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

urls = re.findall(r'href="(https://bazartak\.net/[^"#?]+)"', text)
unique_urls = []
for u in urls:
    # clean trailing slash
    u = u.strip()
    if u in unique_urls:
        continue
    # filter out categories, feeds, wp-content, wp-includes, home
    if any(x in u for x in ['/category/', '/tag/', '/author/', '/feed', '/wp-', '/page/']):
        continue
    if u in ['https://bazartak.net/', 'https://bazartak.net']:
        continue
    unique_urls.append(u)

print(f"Total article URLs found: {len(unique_urls)}")
for i, u in enumerate(unique_urls):
    print(f"{i+1}: {u}")
