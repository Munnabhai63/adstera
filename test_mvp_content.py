import urllib.request
import re

url = "https://bazartak.net/21-machines-to-start-a-profitable-home-business/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

idx = html.find('id="mvp-content-main"')
if idx != -1:
    print("Found id=\"mvp-content-main\" at", idx)
    # find where it ends or print next 2000 chars
    print(html[idx:idx+2000])
else:
    print("Not found exact, search for mvp-content:")
    for m in re.finditer(r'<div[^>]+id="[^"]*mvp-content[^"]*"[^>]*>', html):
        print(m.group(0))
