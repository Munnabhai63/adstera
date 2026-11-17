"""
Generate round 20 redirect mapping for the 221 purged articles.
Ensures every doomed article redirects to the most topically related kept article
on the SAME domain, or to that domain's closest category page.
"""
from pathlib import Path
import json
import re
from collections import defaultdict
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SITES_DIR = PROJECT_ROOT / "sites"
DATA_DIR = PROJECT_ROOT / "data"

BRAND_STOPWORDS = {
    "loanraaj", "karzseva", "tazaloan", "tazarokda", "tazabhav",
    "rechargetak", "rechargepur", "rechargekar", "loankiseva", "loantau",
    "com", "for", "and", "the", "how", "what", "you", "can", "with",
    "from", "this", "that", "guide", "2026", "online", "apply", "tips",
    "options", "complete", "real", "new", "best", "charges"
}

def get_category_from_html(p: Path) -> str | None:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                items = data if isinstance(data, list) else [data]
                for it in items:
                    if it.get("@type") == "BreadcrumbList":
                        elems = it.get("itemListElement", [])
                        if len(elems) >= 2:
                            item_url = elems[1].get("item", "")
                            m = re.search(r"/category/([a-z0-9\-]+)", item_url)
                            if m:
                                return m.group(1)
            except Exception:
                pass
    except Exception:
        pass
    return None

def tokenize(text: str) -> set[str]:
    text = text.lower().replace("-", " ").replace("_", " ")
    words = re.findall(r"\b[a-z0-9]{3,}\b", text)
    return set(w for w in words if w not in BRAND_STOPWORDS)

def build_redirect_map():
    from scripts.seo_onpage_audit import get_all_article_paths, audit_article

    domain_kept = defaultdict(list)
    domain_doomed = defaultdict(list)
    domain_cats = defaultdict(list)

    for cat_index in SITES_DIR.glob("*/category/*/index.html"):
        d = cat_index.relative_to(SITES_DIR).parts[0]
        cat_slug = cat_index.relative_to(SITES_DIR).parts[2]
        if cat_slug not in domain_cats[d]:
            domain_cats[d].append(cat_slug)

    for p in get_all_article_paths(SITES_DIR):
        res = audit_article(p)
        words = res.get("prose_words") or 0
        domain = p.relative_to(SITES_DIR).parts[0]
        slug = p.parent.name
        title = res.get("title") or slug
        cat = get_category_from_html(p)
        tokens = tokenize(f"{slug} {title}")
        item = {
            "domain": domain,
            "slug": slug,
            "title": title,
            "category": cat,
            "words": words,
            "path": p,
            "tokens": tokens,
        }
        if words >= 3000:
            domain_kept[domain].append(item)
        else:
            domain_doomed[domain].append(item)

    redirects = []

    for domain in sorted(domain_doomed):
        kept_list = domain_kept[domain]
        cats = domain_cats[domain]

        for doomed in domain_doomed[domain]:
            d_slug = doomed["slug"]
            d_cat = doomed["category"]
            d_tokens = doomed["tokens"]

            # Score each kept article
            scored_kept = []
            for k in kept_list:
                overlap = len(d_tokens & k["tokens"])
                cat_match = 1 if (d_cat and k["category"] == d_cat) else 0
                scored_kept.append((overlap, cat_match, k))

            # Sort by overlap desc, then cat_match desc
            scored_kept.sort(key=lambda x: (x[0], x[1]), reverse=True)
            best_overlap, best_cat_match, best_kept = scored_kept[0]

            # Score categories
            scored_cats = []
            for c in cats:
                c_tokens = tokenize(c)
                overlap = len(d_tokens & c_tokens)
                is_curr_cat = 1 if (d_cat == c) else 0
                scored_cats.append((overlap, is_curr_cat, c))
            scored_cats.sort(key=lambda x: (x[1], x[0]), reverse=True)
            cat_overlap, is_curr_cat, best_cat = scored_cats[0]

            # Decision:
            # If best_overlap >= 1 or best_cat_match == 1:
            # We map to best_kept article
            if best_overlap >= 1 or best_cat_match == 1:
                to_slug = best_kept["slug"]
                shared = sorted(d_tokens & best_kept["tokens"])
                if shared:
                    reason = f"Topical match on {domain} ({', '.join(shared)}) -> {to_slug}"
                else:
                    reason = f"Category match ({d_cat}) on {domain} -> {to_slug}"
            else:
                # Plausible kept match does not exist; route to closest category page
                to_slug = f"category/{best_cat}"
                reason = f"No direct article match on {domain}; routed to nearest category '{best_cat}'"

            redirects.append({
                "from_slug": d_slug,
                "to_slug": to_slug,
                "reason": reason,
                "domain": domain
            })

    assert len(redirects) == 221, f"Expected 221 redirects, got {len(redirects)}"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "redirects_round20.json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(redirects, f, indent=2)
        f.write("\n")

    print(f"Successfully generated {len(redirects)} redirects in {out_path}")
    return redirects

if __name__ == "__main__":
    build_redirect_map()
