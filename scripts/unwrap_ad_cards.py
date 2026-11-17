import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from bs4 import BeautifulSoup
from scripts.seo_onpage_audit import get_all_article_paths, PROJECT_ROOT

sites_dir = PROJECT_ROOT / "sites"
articles = get_all_article_paths(sites_dir)

unwrapped = 0
for path in articles:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if "native-ad-card" in raw and "<aside" in raw:
        soup = BeautifulSoup(raw, "html.parser")
        changed = False
        for aside in soup.find_all("aside", class_="eeat-note"):
            ad_card = aside.find(class_="native-ad-card")
            if ad_card:
                aside.unwrap()
                changed = True
                for p in ad_card.find_all("p"):
                    if not p.find_parent("aside"):
                        as_tag = soup.new_tag("aside", attrs={"class": "eeat-note"})
                        p.wrap(as_tag)
                unwrapped += 1
        if changed:
            path.write_text(str(soup), encoding="utf-8")

print("Unwrapped ad cards:", unwrapped)
