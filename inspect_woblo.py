import re

file_path = r'F:\UserData\Downloads\adstera\woblo_extracted\home-bazartak\index.html'

with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    html = f.read()

print(f"File size: {len(html)} chars")

# Check Title
m_title = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE)
print("Title:", m_title.group(1) if m_title else "None")

# Check Header structure
m_header = re.search(r'<header[^>]*>(.*?)</header>', html, re.DOTALL | re.IGNORECASE)
if m_header:
    print(f"Header found (len={len(m_header.group(1))})")

# Check Nav menu items
print("\n--- NAV MENU ITEMS ---")
# find all links in navigation or menu
nav_links = re.findall(r'<li[^>]*class=["\'][^"\']*menu-item[^"\']*["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
for href, text in nav_links[:20]:
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    if clean_text:
        print(f"  * {clean_text} -> {href}")

# Check Section Headings
print("\n--- SECTION HEADINGS ---")
headings = re.findall(r'<h[1-4][^>]*>(.*?)</h[1-4]>', html, re.DOTALL | re.IGNORECASE)
for h in headings[:25]:
    clean_h = re.sub(r'<[^>]+>', '', h).strip()
    if clean_h and len(clean_h) < 100:
        print(f"  H: {clean_h}")

# Check Widgets & Footer
print("\n--- FOOTER LINKS ---")
footer_links = re.findall(r'<footer.*?</footer>', html, re.DOTALL | re.IGNORECASE)
if footer_links:
    f_links = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', footer_links[0], re.DOTALL | re.IGNORECASE)
    for href, text in f_links[:15]:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        print(f"  F: {clean_text} -> {href}")
