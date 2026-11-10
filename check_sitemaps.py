import urllib.request
import re

for sitemap_url in [
    'https://bazartak.net/sitemap.xml',
    'https://bazartak.net/sitemap_index.xml',
    'https://bazartak.net/wp-sitemap.xml',
    'https://bazartak.net/wp-sitemap-posts-post-1.xml',
    'https://bazartak.net/post-sitemap.xml'
]:
    try:
        req = urllib.request.Request(sitemap_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            print(f"Success fetching {sitemap_url}! Length: {len(content)}")
            urls = re.findall(r'<loc>(https://bazartak\.net/[^<]+)</loc>', content)
            print(f"Found {len(urls)} URLs inside {sitemap_url}:")
            for u in urls[:10]:
                print("  ", u)
            if len(urls) > 10:
                print(f"   ... and {len(urls)-10} more")
    except Exception as e:
        print(f"Failed {sitemap_url}: {e}")
