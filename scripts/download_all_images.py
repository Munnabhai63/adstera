from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx
from scripts.check_images import urls

base = Path("sites")
img_cache = Path("state/image_cache")
img_cache.mkdir(parents=True, exist_ok=True)

print(f"Starting download of {len(urls)} unique external images...")

def download_one(url: str):
    clean_url = url
    if "images.unsplash.com" in url and "fm=webp" not in url:
        clean_url = url + "&fm=webp"

    # Deterministic file name
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    # slug-like hint
    hint = "img"
    if "photo-" in url:
        hint = url.split("photo-")[1].split("?")[0][:10]
    elif "/" in url:
        hint = url.rstrip("/").split("/")[-1].split(".")[0][:15]
    hint = "".join(c for c in hint if c.isalnum() or c in "-_")
    filename = f"{hint}_{url_hash}.webp"
    target_file = img_cache / filename

    if target_file.exists() and target_file.stat().st_size > 500:
        return url, filename, True

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = httpx.get(clean_url, headers=headers, timeout=15.0, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 500:
            target_file.write_bytes(r.content)
            return url, filename, True
        else:
            return url, filename, False
    except Exception as e:
        return url, filename, False

success = 0
failed = []
mapping = {}

with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(download_one, u): u for u in urls}
    for f in as_completed(futures):
        u, fn, ok = f.result()
        if ok:
            success += 1
            mapping[u] = fn
        else:
            failed.append(u)

print(f"Downloaded: {success}/{len(urls)}")
if failed:
    print(f"Failed ({len(failed)}):")
    for u in failed[:10]:
        print(" ", u)
