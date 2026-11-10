import urllib.request
import re

url = "https://kamtak.in/how-to-get-an-instant-loan/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        print("Length:", len(html))
        # check title
        m_t = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        print("Title:", re.sub(r'<[^>]+>', '', m_t.group(1)).strip() if m_t else "No h1")
        # find content
        for marker in ['id="mvp-content-main"', 'class="entry-content"', 'id="content-main"']:
            idx = html.find(marker)
            if idx != -1:
                print(f"Found {marker} at {idx}")
                print(html[idx:idx+500])
                break
except Exception as e:
    print("Error:", e)
