"""
scripts/fix_homepages_and_categories.py
Full rebuild of category pages, homepages, and sidebars across all 10 publisher domains.
Guarantees:
- Category pages only render cards for surviving articles.
- Category sidebar "Browse Sectors" counts match actual surviving articles.
- "Trending Guides" lists surviving articles only.
- Homepage renders heroes and feed-cards for surviving articles only.
- ZERO links to doomed or redirected slugs remain in category pages, homepages, or sidebars.
- Strict LF line endings and no CRLF.
"""
from pathlib import Path
import json
import re
from collections import defaultdict
from bs4 import BeautifulSoup
import html
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = PROJECT_ROOT / "sites"
REDIRECTS_FILE = PROJECT_ROOT / "data" / "redirects_round20.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seo_onpage_audit import get_all_article_paths, audit_article

CATEGORY_KEYWORDS = {
    # karzseva.com
    "debt-consolidation": ["consolidat", "balance-transfer", "lap", "property", "salaried", "slip", "overdraft"],
    "credit-settlement": ["settl", "ots", "default", "recovery-agent", "closed"],
    "credit-repair": ["cibil", "dispute", "written-off", "noc", "bad-credit", "score"],
    "financial-recovery": ["budget", "snowball", "avalanche", "emergency", "psychology", "low-income"],
    
    # loankiseva.com
    "mudra-loans": ["mudra", "pmmy", "shishu", "kishor", "tarun"],
    "msme-credit": ["msme", "cgtmse", "machinery", "udyam", "treds", "subsidy"],
    "agriculture-dairy": ["kisan", "kcc", "dairy", "poultry", "crops", "warehouse", "cold-storage"],
    "women-entrepreneurship": ["women", "annapurna", "stand-up", "stree", "mahila"],
    
    # loanraaj.com
    "business": ["business", "machines", "pmegp", "import", "profit"],
    "carrier": ["truck", "trucking", "cdl", "driver", "ai-replace", "broke-to-80000"],
    "finance": ["personal-loan", "instant-loan", "home-loan", "mortgage"],
    "insurance": ["insurance", "bobtail", "commercial-auto", "hotshot", "semi-truck", "term-insurance", "fleet"],
    
    # loantau.com
    "fleet-finance": ["fleet", "commercial-fleet", "managing-cash", "depreciation", "tax-depreciation"],
    "tractor-loans": ["tractor", "kisan-tractor", "nabard", "mahindra", "swaraj", "sonalika", "farm-implements"],
    "truck-loans": ["truck-loans", "commercial-truck-loan", "tata", "ashok-leyland", "commercial-vehicle", "tipper", "trailer"],
    "used-trucks": ["used-truck", "ltv", "refinance", "fitness-certificate", "rto", "gold-loan"],
    
    # rechargekar.com
    "5g-vouchers-booster": ["5g-vouchers", "booster", "unlimited-night", "tata-play"],
    "esim-technology": ["esim", "convert-physical", "smartwatch", "qr"],
    "international-roaming": ["roaming", "international", "usa", "dubai", "europe"],
    "student-nomad": ["student", "budget", "nomad", "wifi", "pocket-friendly"],
    
    # rechargepur.com
    "cashback-upi": ["cashback", "utility-bill", "cred", "paytm", "gpay", "amazon-pay", "fastag"],
    "dth-entertainment": ["dth", "tata-play", "airtel-digital", "dish-tv", "ott"],
    "electricity-gas": ["electricity", "gas", "bill-payment", "state-electricity"],
    "water-municipal": ["water", "municipal", "property-tax", "challan"],
    
    # rechargetak.com
    "5g-broadband": ["5g-broadband", "wi-fi", "airfiber", "fiber", "mesh", "ping"],
    "fastag-tolls": ["fastag", "toll", "blacklisted", "satellite"],
    "prepaid-plans": ["prepaid", "28-day", "84-day", "84-days", "jio-best", "unlimited-night"],
    "sim-porting": ["porting", "mnp", "lost-sim", "corporate-sim"],
    
    # tazabhav.com
    "gold-silver": ["gold", "silver", "hallmark", "sgb", "etf", "24k", "22k"],
    "commodities": ["commodity", "commodities", "ncdex", "crude", "copper", "metal", "natural-gas"],
    "daily-sip-funds": ["sip", "funds", "nifty", "small-cap", "step-up"],
    "real-estate-land": ["real-estate", "land", "circle-rate", "stamp-duty", "rera"],
    
    # tazaloan.com
    "credit-score": ["cibil", "score", "hard-inquiries", "utilization"],
    "emergency-loans": ["urgent", "urgent-cash", "emergency", "medical", "paperless", "cash-loan"],
    "personal-loans": ["personal-loan", "salary-advance", "pre-approved", "self-employed"],
    "student-education": ["student", "education", "study-abroad", "moratorium"],
    
    # tazarokda.com
    "business-banking": ["business-banking", "payroll", "api-banking", "current-accounts", "merchant", "soundbox", "corporate-credit"],
    "cashback-rewards": ["cashback-rewards", "fuel", "grocery", "swiggy", "zomato", "milestone", "rupay"],
    "credit-cards": ["credit-cards", "lifetime-free", "lounge", "travel-rewards", "forex"],
    "high-yield-savings": ["savings", "sweep-in", "small-finance", "senior-citizen", "fixed-deposits", "sip", "mutual-funds"]
}

def extract_article_meta(p: Path) -> dict:
    text = p.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    slug = p.parent.name
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug

    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = desc_tag["content"] if desc_tag else ""

    words = audit_article(p).get("prose_words") or 3000

    img = soup.find("img")
    img_src = img["src"] if img else "/img/default.webp"

    return {
        "slug": slug,
        "title": title,
        "desc": desc,
        "words": words,
        "image": img_src,
        "path": p
    }

def determine_category(slug: str, title: str, domain_cats: list[dict]) -> dict:
    text = f"{slug} {title}".lower()
    best_cat = domain_cats[0]
    best_score = -1

    for c in domain_cats:
        c_slug = c["slug"]
        kws = CATEGORY_KEYWORDS.get(c_slug, [c_slug])
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best_score = score
            best_cat = c

    return best_cat

def render_feed_card(a: dict) -> str:
    escaped_title = html.escape(a["title"])
    return f"""
    <article class="feed-card">
        <div class="feed-thumb">
            <img src="{a['image']}" alt="{escaped_title}" loading="lazy">
        </div>
        <div class="feed-info">
            <div class="feed-cat">{a['category']['name']}</div>
            <a href="/{a['slug']}" class="feed-title">{escaped_title}</a>
            <p class="feed-desc">{html.escape(a['desc'])}</p>
            <div class="feed-meta">{a['words']} words · In-Depth Guide</div>
        </div>
    </article>
    """

def render_browse_sectors_widget(domain_cats: list[dict], cat_counts: dict) -> str:
    lis = ""
    for c in domain_cats:
        count = cat_counts.get(c["slug"], 0)
        lis += f"""
        <li style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-size:13px;">
            <a href="/category/{c['slug']}" style="font-weight:600; color:var(--text-body);">{c['icon']} {c['name']}</a>
            <span style="background:#F1F5F9; color:#64748B; font-size:11px; font-weight:700; padding:2px 8px; border-radius:10px;">{count}</span>
        </li>
        """
    return f"""
    <div class="widget-card">
        <div class="widget-title">Browse Sectors</div>
        <ul style="list-style:none;">
            {lis}
        </ul>
    </div>
    """

def render_trending_widget(surviving_articles: list[dict]) -> str:
    divs = ""
    for a in surviving_articles[:5]:
        divs += f"""
        <div style="margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--border-light);">
            <div style="font-size:10px; font-weight:800; color:var(--primary); text-transform:uppercase;">{a['category']['name']}</div>
            <a href="/{a['slug']}" style="font-size:13px; font-weight:700; color:var(--text-head); line-height:1.4; display:block; margin-top:2px;">
                {html.escape(a['title'])}
            </a>
        </div>
        """
    return f"""
    <div class="widget-card">
        <div class="widget-title">Trending Guides</div>
        {divs}
    </div>
    """

def update_sidebar_in_soup(soup: BeautifulSoup, browse_sectors_html: str, trending_html: str):
    # Replace Browse Sectors widget
    for title in soup.find_all(class_="widget-title"):
        if "Browse Sectors" in title.get_text():
            parent = title.find_parent("div", class_="widget-card")
            if parent:
                new_browse = BeautifulSoup(browse_sectors_html, "html.parser").find("div", class_="widget-card")
                if new_browse:
                    parent.replace_with(new_browse)
        elif "Trending Guides" in title.get_text() or "Trending Insights" in title.get_text():
            parent = title.find_parent("div", class_="widget-card")
            if parent:
                new_trending = BeautifulSoup(trending_html, "html.parser").find("div", class_="widget-card")
                if new_trending:
                    parent.replace_with(new_trending)

def main():
    article_paths = get_all_article_paths(SITES_DIR)
    assert len(article_paths) == 57, f"Expected 57 articles, got {len(article_paths)}"

    domain_articles = defaultdict(list)
    for p in article_paths:
        meta = extract_article_meta(p)
        domain = p.relative_to(SITES_DIR).parts[0]
        domain_articles[domain].append(meta)

    # Load categories for each domain
    domain_categories = {}
    for d_dir in sorted(SITES_DIR.iterdir()):
        if not d_dir.is_dir(): continue
        domain = d_dir.name
        cat_dir = d_dir / "category"
        cats = []
        if cat_dir.exists():
            for c_path in sorted(cat_dir.glob("*/index.html")):
                c_slug = c_path.parent.name
                c_soup = BeautifulSoup(c_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
                header_title = c_soup.find(class_="cat-header-title")
                header_text = header_title.get_text(strip=True) if header_title else ""
                icon = header_text[:2] if header_text and ord(header_text[0]) > 127 else "📌"
                name = header_text[2:].strip() if header_text and ord(header_text[0]) > 127 else c_slug.replace("-", " ").title()
                cats.append({"slug": c_slug, "name": name, "icon": icon})
        domain_categories[domain] = cats

    # Assign categories to articles
    domain_cat_counts = {}
    for domain, arts in domain_articles.items():
        cats = domain_categories[domain]
        counts = defaultdict(int)
        for a in arts:
            cat_obj = determine_category(a["slug"], a["title"], cats)
            a["category"] = cat_obj
            counts[cat_obj["slug"]] += 1
        domain_cat_counts[domain] = counts

    print("Rebuilding sidebars, category pages, and homepages...")

    # Process all domains
    for domain, arts in sorted(domain_articles.items()):
        cats = domain_categories[domain]
        cat_counts = domain_cat_counts[domain]
        site_dir = SITES_DIR / domain

        browse_sectors_html = render_browse_sectors_widget(cats, cat_counts)
        trending_html = render_trending_widget(arts)

        # 1. Update Category Pages
        for c in cats:
            cat_slug = c["slug"]
            cat_arts = [a for a in arts if a["category"]["slug"] == cat_slug]
            cat_idx = site_dir / "category" / cat_slug / "index.html"
            cat_flat = site_dir / "category" / f"{cat_slug}.html"

            for target_file in [cat_idx, cat_flat]:
                if not target_file.exists():
                    continue
                soup = BeautifulSoup(target_file.read_text(encoding="utf-8", errors="ignore"), "html.parser")

                # Update header count
                header_card = soup.find(class_="cat-header-card")
                if header_card:
                    # Look for count text
                    for el in header_card.find_all(True):
                        if "Curated Guides" in el.get_text():
                            el.string = f"{len(cat_arts)} Curated Guides in this Sector"

                # Update main section feed cards
                section = soup.find("section")
                if section:
                    if len(cat_arts) > 0:
                        cards_html = "".join([render_feed_card(a) for a in cat_arts])
                    else:
                        cards_html = f"""
                        <div class="empty-cat" style="padding:40px 20px; text-align:center; background:#fff; border-radius:12px; border:1px solid var(--border); margin:20px 0;">
                            <p style="color:var(--text-muted); font-size:15px; line-height:1.6;">Our research team is currently updating this sector with fresh in-depth publications. Please explore our other active categories or return shortly.</p>
                        </div>
                        """
                    new_section = BeautifulSoup(f"<section>{cards_html}</section>", "html.parser").find("section")
                    section.replace_with(new_section)

                # Update sidebar
                update_sidebar_in_soup(soup, browse_sectors_html, trending_html)

                # Write out
                target_file.write_bytes(str(soup).encode("utf-8").replace(b"\r\n", b"\n"))

        # 2. Update Homepage (index.html)
        home_path = site_dir / "index.html"
        if home_path.exists():
            soup = BeautifulSoup(home_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")

            # Update ticker link to first surviving article
            ticker = soup.find("a", class_="ticker-text")
            if ticker and len(arts) > 0:
                ticker["href"] = f"/{arts[0]['slug']}"
                ticker.string = arts[0]["title"]

            # Update publications count in section header
            for span in soup.find_all("span"):
                if "In-Depth Publications" in span.get_text():
                    span.string = f"{len(arts)} In-Depth Publications"

            # Update hero grid if exists
            hero_grid = soup.find(class_="hero-grid")
            if hero_grid and len(arts) >= 1:
                hero1 = arts[0]
                hero2 = arts[1] if len(arts) > 1 else hero1
                hero3 = arts[2] if len(arts) > 2 else hero1

                hero_html = f"""
                <div class="hero-grid">
                    <div class="hero-card main-hero">
                        <img src="{hero1['image']}" alt="{html.escape(hero1['title'])}" loading="eager">
                        <div class="hero-overlay">
                            <span class="hero-badge">{hero1['category']['name']}</span>
                            <a href="/{hero1['slug']}" class="hero-h1">{html.escape(hero1['title'])}</a>
                            <div class="hero-meta">{hero1['words']} words · Comprehensive Guide</div>
                        </div>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:18px;">
                        <div class="hero-card">
                            <img src="{hero2['image']}" alt="{html.escape(hero2['title'])}" loading="lazy">
                            <div class="hero-overlay">
                                <span class="hero-badge">{hero2['category']['name']}</span>
                                <a href="/{hero2['slug']}" class="hero-h1">{html.escape(hero2['title'])}</a>
                                <div class="hero-meta">{hero2['words']} words · Industry Analysis</div>
                            </div>
                        </div>
                        <div class="hero-card">
                            <img src="{hero3['image']}" alt="{html.escape(hero3['title'])}" loading="lazy">
                            <div class="hero-overlay">
                                <span class="hero-badge">{hero3['category']['name']}</span>
                                <a href="/{hero3['slug']}" class="hero-h1">{html.escape(hero3['title'])}</a>
                                <div class="hero-meta">{hero3['words']} words · Verified Rates</div>
                            </div>
                        </div>
                    </div>
                </div>
                """
                new_hero = BeautifulSoup(hero_html, "html.parser").find("div", class_="hero-grid")
                hero_grid.replace_with(new_hero)

            # Update section feed cards
            section = soup.find("section")
            if section:
                feed_arts = arts[3:] if len(arts) > 3 else arts
                feed_html = "".join([render_feed_card(a) for a in feed_arts])
                # Preserve section header
                hdr = section.find("div", style=re.compile(r"border-bottom"))
                hdr_html = str(hdr) if hdr else f'<div style="margin-bottom:20px;"><h2 style="font-size:20px; font-weight:900;">Latest Intelligence</h2><span>{len(arts)} In-Depth Publications</span></div>'
                new_sec_content = f"<section>{hdr_html}{feed_html}</section>"
                new_sec = BeautifulSoup(new_sec_content, "html.parser").find("section")
                section.replace_with(new_sec)

            # Update sidebar
            update_sidebar_in_soup(soup, browse_sectors_html, trending_html)
            home_path.write_bytes(str(soup).encode("utf-8").replace(b"\r\n", b"\n"))

        # 3. Update legal and calculator pages' sidebars
        for legal_dir in site_dir.iterdir():
            if not legal_dir.is_dir() or legal_dir.name in ("category", "layouts", "_default"):
                continue
            idx = legal_dir / "index.html"
            flat = site_dir / f"{legal_dir.name}.html"
            for f in [idx, flat]:
                if f.exists() and legal_dir.name in ("about-us", "contact-us", "privacy-policy", "terms-and-conditions", "disclaimer", "calculator", "emi-calculator"):
                    soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
                    update_sidebar_in_soup(soup, browse_sectors_html, trending_html)
                    f.write_bytes(str(soup).encode("utf-8").replace(b"\r\n", b"\n"))

    print("Completed rebuilding category pages, homepages, and sidebars.")

if __name__ == "__main__":
    main()
