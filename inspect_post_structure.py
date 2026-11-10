import urllib.request
import re

url = "https://bazartak.net/21-machines-to-start-a-profitable-home-business/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# In Zox theme, find where the article text actually starts
# Look for <div id="content-main"> or class="theiaPostSlider_preloadedSlide" or itemprop="articleBody"
for tag in ['theiaPostSlider_preloadedSlide', 'entry-content', 'content-main', 'articleBody']:
    idx = html.find(tag)
    if idx != -1:
        print(f"Found {tag} at {idx}")
        print(html[idx-50:idx+250])
        print("="*50)
