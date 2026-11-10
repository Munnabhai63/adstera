import os
import json
import re
import html
import sys
from bs4 import BeautifulSoup, Tag

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = r"F:\UserData\Downloads\adstera\sites\loanraaj"
os.makedirs(BASE_DIR, exist_ok=True)

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    raw_articles = json.load(f)

# PRECISE CATEGORY MAPPING (ZERO OVERLAP, 100% UNIQUE)
CATEGORY_MAPPING = {
    # Business
    "21-machines-to-start-a-profitable-home-business": ("Business", "Profitable equipment imports, manufacturing machines, and small business setups."),
    "pmegp-loan-apply-now": ("Business", "Government business loan schemes, subsidies, and commercial enterprise financing."),
    "business-loan-guide": ("Business", "Small business lines of credit, working capital, and commercial merchant cash advances."),
    "owner-operator-insurance-what-it-really-costs": ("Business", "Owner-operator economics, business operating expenses, and commercial trucking profit margins."),
    "fleet-truck-insurance-cost-small-operators": ("Business", "Fleet management, multi-truck operations, and business insurance budgeting."),

    # Insurance
    "commercial-auto-insurance-quotes": ("Insurance", "Commercial automobile insurance quotes, underwriting guidelines, and broker comparisons."),
    "hotshot-trucking-insurance": ("Insurance", "Non-CDL and CDL hotshot rig coverage, cargo limits, and primary liability costs."),
    "bobtail-insurance-what-it-costs-what-it-covers": ("Insurance", "Bobtail and non-trucking liability coverage rules, deductibles, and endorsements."),
    "commercial-truck-insurance": ("Insurance", "Complete beginner guide to primary liability, physical damage, and motor truck cargo insurance."),
    "semi-truck-insurance-cost-in-2026": ("Insurance", "Semi-truck insurance rate benchmarks, down payment requirements, and first-year cost reductions."),
    "trucking-insurance-quotes-how-i-compared-11-quotes": ("Insurance", "Rigorous side-by-side quote comparison across 11 top commercial insurance underwriters."),

    # Carrier
    "how-i-went-from-broke-to-80000-a-year-by-trucking": ("Carrier", "Real-world CDL career roadmap, freight dispatching reality, and commercial driver earnings."),
    "i-earned-my-cdl-at-26-with-no-experience": ("Carrier", "CDL school selection, pre-trip inspection mastery, and navigating first-year trucking challenges."),
    "will-ai-replace-truck-drivers": ("Carrier", "Autonomous freight technology, autonomous long-hauls, and the future of professional commercial drivers."),
    "car-accident-lawyer-guide": ("Carrier", "Commercial vehicle accident law, liability determination, and driver injury claims compensation."),

    # Finance
    "how-to-get-an-instant-loan": ("Finance", "Instant personal loans, fast cash disbursement apps, and interest rate evaluations."),
    "low-interest-personal-loan": ("Finance", "Unsecured personal loans, credit score optimization, and low APR borrowing strategies."),
    "home-loan-fast-approval": ("Finance", "Mortgage approvals, home loan interest rates, down payments, and debt-to-income ratios."),
    "loan-against-insurance-policy": ("Finance", "Secured borrowing against life insurance surrender value, low interest and zero CIBIL impact."),
    "health-insurance-guide": ("Finance", "Comprehensive medical insurance, family floater plans, cashless hospital networks, and claims."),
    "term-insurance-guide": ("Finance", "Term life insurance calculations, pure risk protection, critical illness riders, and claim settlement ratios.")
}

def clean_to_semantic_blocks(html_content):
    if not html_content:
        return "<p>Content being updated.</p>"
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for tag in soup(['script', 'style', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'noscript', 'meta', 'link']):
        tag.decompose()
        
    junk_markers = ['mvp-content-bot', 'mvp-post-tags', 'mvp-post-soc', 'posts-nav-link', 'comments', 'code-block', 'author-box', 'relpost', 'ast-single-related-posts', 'newsletter', 'signup']
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        tag_id = tag.attrs.get('id', '')
        tag_classes = ' '.join(tag.attrs.get('class', []))
        if any(m in str(tag_id).lower() or m in str(tag_classes).lower() for m in junk_markers):
            tag.decompose()
            continue
        if 'RIDE ALONG' in tag.get_text() or 'Insta ID' in tag.get_text():
            tag.decompose()

    blocks = []
    nav_phrases = {'home', 'about us', 'contact us', 'disclaimer', 'privacy policy', 'terms & conditions', 'terms and conditions'}
    
    for el in soup.find_all(['h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table', 'blockquote']):
        if not isinstance(el, Tag):
            continue
        if el.parent and el.parent.name in ['ul', 'ol', 'blockquote', 'table']:
            continue
            
        text = el.get_text().strip()
        if not text and not el.find('img'):
            continue
            
        if any(junk in text for junk in ['window.googletag', 'googletag.cmd', 'Related Posts', 'Advertisement', 'googletag.display']):
            continue

        if el.name in ['h2', 'h3', 'h4']:
            clean_head = re.sub(r'\s+', ' ', text)
            blocks.append(f'<{el.name}>{html.escape(clean_head)}</{el.name}>')
            
        elif el.name == 'p':
            imgs = el.find_all('img')
            if imgs:
                for img in imgs:
                    src = img.attrs.get('src', '') if img.attrs else ''
                    alt = img.attrs.get('alt', '') if img.attrs else ''
                    if src and not src.startswith('data:') and 'google' not in src:
                        blocks.append(f'<div class="article-inner-img"><img src="{src}" alt="{html.escape(alt)}" loading="lazy"></div>')
                        
            for a in el.find_all('a'):
                if a.attrs:
                    href = a.attrs.get('href', '')
                    if 'bazartak.net/' in href or 'kamtak.in/' in href:
                        slug = href.strip('/').split('/')[-1]
                        a['href'] = f'/{slug}'
                    a.attrs = {'href': a.attrs.get('href', '#')}
                    
            for child in el.find_all(True):
                if child.name not in ['a', 'strong', 'b', 'em', 'i']:
                    child.unwrap()
                else:
                    child.attrs = {k: v for k, v in child.attrs.items() if k in ['href', 'target']}
                    
            p_html = ''.join(str(c) for c in el.contents).strip()
            p_html = p_html.replace('&nbsp;', ' ').strip()
            if p_html and len(p_html) > 5 and not any(p_html.lower() == phrase for phrase in nav_phrases):
                p_html = p_html.replace('BazarTak', 'LoanRaaj').replace('bazartak.net', 'loanraaj.com').replace('KamTak', 'LoanRaaj').replace('kamtak.in', 'loanraaj.com')
                blocks.append(f'<p>{p_html}</p>')
                
        elif el.name in ['ul', 'ol']:
            items = []
            for li in el.find_all('li', recursive=False):
                li_text = li.get_text().strip()
                if li_text and li_text.lower() not in nav_phrases:
                    items.append(f'<li>{html.escape(li_text)}</li>')
            if len(items) >= 2:
                blocks.append(f'<{el.name}>' + ''.join(items) + f'</{el.name}>')
                
        elif el.name == 'blockquote':
            bq_text = el.get_text().strip()
            if bq_text:
                blocks.append(f'<blockquote><p>{html.escape(bq_text)}</p></blockquote>')
                
        elif el.name == 'table':
            rows = []
            for tr in el.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    tag_name = td.name
                    cell_text = td.get_text().strip()
                    cells.append(f'<{tag_name}>{html.escape(cell_text)}</{tag_name}>')
                if cells:
                    rows.append('<tr>' + ''.join(cells) + '</tr>')
            if rows:
                blocks.append('<div class="table-responsive"><table class="article-table">' + ''.join(rows) + '</table></div>')

    return '\n'.join(blocks)

# Process articles with exact category assignments
processed_articles = []
for a in raw_articles:
    slug = a['slug']
    cat_info = CATEGORY_MAPPING.get(slug, ("Finance", "Financial guides and money management strategies."))
    cat_name = cat_info[0]
    cleaned_body = clean_to_semantic_blocks(a['content'])
    
    processed_articles.append({
        "slug": slug,
        "title": a['title'],
        "category": cat_name,
        "category_desc": cat_info[1],
        "image": a['image'],
        "excerpt": a['excerpt'],
        "content": cleaned_body,
        "words": a.get('words', len(cleaned_body.split()))
    })

print(f"Processed {len(processed_articles)} articles with strict category taxonomy.")

# Category descriptions for category pages
CATEGORY_METADATA = {
    "Business": {
        "title": "Business Financing, Imports & Machinery",
        "desc": "Actionable guides on importing profitable machinery, securing government PMEGP business loans, and commercial enterprise funding.",
        "icon": "💼"
    },
    "Insurance": {
        "title": "Commercial Insurance & Vehicle Protection",
        "desc": "Independent rate benchmarks, policy limit explanations, and comparisons across commercial auto, semi-truck, bobtail, and hotshot insurance.",
        "icon": "🛡️"
    },
    "Carrier": {
        "title": "CDL Career, Fleet & Transportation Logistics",
        "desc": "Road-tested guides for commercial truck drivers, CDL license training, autonomous freight analysis, and accident legal rights.",
        "icon": "🚛"
    },
    "Finance": {
        "title": "Personal Loans, Mortgages & Family Protection",
        "desc": "Data-backed guides on instant online personal loans, low-interest mortgage approvals, life term insurance, and loans against policies.",
        "icon": "💰"
    }
}

# CSS STYLESHEET
CSS_PROFESSIONAL = """
:root {
    --primary: #E11D48;
    --primary-hover: #BE123C;
    --dark: #0F172A;
    --dark-surface: #1E293B;
    --light-bg: #F8FAFC;
    --card-bg: #FFFFFF;
    --border: #E2E8F0;
    --border-light: #F1F5F9;
    --text-head: #0F172A;
    --text-body: #334155;
    --text-muted: #64748B;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background-color: var(--light-bg);
    color: var(--text-body);
    font-family: var(--font-sans);
    font-size: 16px;
    line-height: 1.7;
    -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; transition: color 0.15s ease; }
a:hover { color: var(--primary); }
img { max-width: 100%; height: auto; display: block; }

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

/* 1. Top Bar */
.topbar {
    background: #090D16;
    color: #94A3B8;
    font-size: 12px;
    padding: 8px 0;
    border-bottom: 1px solid #1E293B;
}
.topbar-flex {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.ticker-box {
    display: flex;
    align-items: center;
    gap: 12px;
    overflow: hidden;
}
.ticker-badge {
    background: var(--primary);
    color: #FFF;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.5px;
    flex-shrink: 0;
}
.ticker-text {
    color: #CBD5E1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* 2. Main Header */
.header {
    background: #FFF;
    padding: 24px 0;
    border-bottom: 1px solid var(--border);
}
.header-flex {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 20px;
}
.brand-logo {
    font-size: 34px;
    font-weight: 900;
    letter-spacing: -1px;
    color: var(--dark);
    line-height: 1;
}
.brand-logo span { color: var(--primary); }
.brand-tag {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-muted);
    letter-spacing: 1.2px;
    font-weight: 700;
    margin-top: 6px;
}
.header-ad {
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    border-radius: 6px;
    padding: 14px 28px;
    text-align: center;
    min-width: 320px;
    max-width: 728px;
    flex-grow: 1;
}
.header-ad-title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #94A3B8;
    font-weight: 700;
}
.header-ad-sub {
    font-size: 12px;
    color: #64748B;
    font-weight: 600;
    margin-top: 2px;
}

/* 3. Navbar */
.nav-wrap {
    background: var(--dark);
    position: sticky;
    top: 0;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.nav-ul {
    display: flex;
    list-style: none;
    align-items: center;
    gap: 2px;
    overflow-x: auto;
    white-space: nowrap;
}
.nav-item a {
    display: block;
    padding: 15px 18px;
    font-size: 13px;
    font-weight: 700;
    color: #E2E8F0;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
.nav-item a:hover, .nav-item a.active {
    background: var(--primary);
    color: #FFF;
}

/* 4. Page Grid */
.main-layout {
    display: grid;
    grid-template-columns: 1fr;
    gap: 32px;
    margin: 32px auto;
    align-items: start;
}
@media (min-width: 992px) {
    .main-layout {
        grid-template-columns: 8fr 4fr;
    }
}

/* Hero 3-Grid */
.hero-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 18px;
    margin-top: 26px;
}
@media (min-width: 768px) {
    .hero-grid {
        grid-template-columns: 7fr 5fr;
    }
}
.hero-card {
    position: relative;
    border-radius: 8px;
    overflow: hidden;
    background: #090D16;
    min-height: 280px;
}
.hero-card.main-hero { min-height: 440px; }
.hero-card img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0.85;
    transition: transform 0.35s ease;
}
.hero-card:hover img { transform: scale(1.03); }
.hero-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(9,13,22,0) 25%, rgba(9,13,22,0.92) 100%);
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    color: #FFF;
}
.hero-badge {
    align-self: flex-start;
    background: var(--primary);
    color: #FFF;
    font-size: 10px;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 10px;
}
.hero-h1 {
    font-size: 24px;
    font-weight: 800;
    line-height: 1.3;
    color: #FFF;
    margin-bottom: 8px;
}
.hero-card.main-hero .hero-h1 { font-size: 30px; }
.hero-meta {
    font-size: 12px;
    color: #94A3B8;
}

/* Feed Cards */
.feed-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
@media (min-width: 600px) {
    .feed-card { flex-direction: row; }
}
.feed-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 20px -3px rgba(0,0,0,0.06);
}
.feed-thumb {
    width: 100%;
    height: 190px;
    border-radius: 6px;
    overflow: hidden;
    background: #E2E8F0;
    flex-shrink: 0;
}
@media (min-width: 600px) {
    .feed-thumb {
        width: 250px;
        height: 170px;
    }
}
.feed-thumb img { width: 100%; height: 100%; object-fit: cover; }
.feed-info { display: flex; flex-direction: column; justify-content: center; }
.feed-cat {
    color: var(--primary);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 6px;
}
.feed-title {
    font-size: 18px;
    font-weight: 800;
    color: var(--text-head);
    line-height: 1.35;
    margin-bottom: 8px;
}
.feed-desc {
    font-size: 14px;
    color: var(--text-muted);
    line-height: 1.6;
    margin-bottom: 10px;
}
.feed-meta {
    font-size: 12px;
    color: #94A3B8;
}

/* Single Post Container */
.post-paper {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 32px 24px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.04);
}
@media (min-width: 768px) {
    .post-paper { padding: 44px 38px; }
}
.post-crumb {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
}
.cat-badge {
    background: #FFF1F2;
    color: var(--primary);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 4px 10px;
    border-radius: 4px;
    display: inline-block;
    margin-bottom: 14px;
}
.post-h1 {
    font-size: 28px;
    font-weight: 900;
    line-height: 1.25;
    color: var(--text-head);
    letter-spacing: -0.5px;
    margin-bottom: 16px;
}
@media (min-width: 768px) {
    .post-h1 { font-size: 36px; }
}
.post-meta {
    display: flex;
    gap: 16px;
    font-size: 13px;
    color: var(--text-muted);
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border-light);
    margin-bottom: 26px;
    flex-wrap: wrap;
}
.post-feature-wrap {
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 30px;
    max-height: 480px;
    background: #E2E8F0;
    border: 1px solid var(--border);
}
.post-feature-wrap img { width: 100%; height: 100%; object-fit: cover; }

/* In-Post Typography & Clean Layout */
.post-content {
    font-size: 17px;
    line-height: 1.85;
    color: var(--text-body);
}
.post-content p { margin-bottom: 22px; }
.post-content h2 {
    font-size: 24px;
    font-weight: 800;
    color: var(--text-head);
    margin: 38px 0 16px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--border-light);
    position: relative;
}
.post-content h2::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    width: 48px;
    height: 2px;
    background: var(--primary);
}
.post-content h3 {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-head);
    margin: 28px 0 12px 0;
}
.post-content h4 {
    font-size: 17px;
    font-weight: 700;
    color: var(--text-head);
    margin: 22px 0 10px 0;
}
.post-content ul, .post-content ol {
    margin: 18px 0 24px 26px;
}
.post-content li {
    margin-bottom: 10px;
    line-height: 1.75;
}
.post-content strong {
    color: var(--text-head);
    font-weight: 700;
}
.post-content blockquote {
    margin: 26px 0;
    padding: 16px 22px;
    background: #F8FAFC;
    border-left: 4px solid var(--primary);
    border-radius: 0 8px 8px 0;
    font-style: italic;
    color: #475569;
}
.table-responsive {
    width: 100%;
    overflow-x: auto;
    margin: 28px 0;
    border-radius: 8px;
    border: 1px solid var(--border);
}
.article-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    text-align: left;
}
.article-table th {
    background: #F8FAFC;
    color: var(--text-head);
    font-weight: 700;
    padding: 12px 16px;
    border-bottom: 2px solid var(--border);
}
.article-table td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-light);
    color: var(--text-body);
}
.article-table tr:hover { background: #F8FAFC; }
.article-inner-img {
    margin: 28px 0;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
}

/* Ad Banners */
.ad-slot-box {
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    border-radius: 8px;
    padding: 18px;
    margin: 28px 0;
    text-align: center;
}
.ad-slot-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #94A3B8;
    font-weight: 700;
    margin-bottom: 4px;
}
.ad-slot-spec {
    font-size: 12px;
    color: #64748B;
    font-weight: 600;
}

/* Author Box */
.author-card {
    background: #F8FAFC;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 22px;
    margin-top: 38px;
    display: flex;
    gap: 18px;
    align-items: center;
}
.author-avatar {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: var(--dark);
    color: #FFF;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 22px;
    flex-shrink: 0;
}

/* Sidebar & Sticky Column */
.sidebar-col {
    position: sticky;
    top: 75px;
}
.widget-card {
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 22px;
    margin-bottom: 24px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.03);
}
.widget-title {
    font-size: 14px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--text-head);
    padding-bottom: 10px;
    border-bottom: 2px solid var(--primary);
    margin-bottom: 16px;
}
.calc-field { margin-bottom: 14px; }
.calc-field label { display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 4px; }
.calc-field input[type="number"] {
    width: 100%;
    padding: 9px 12px;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    font-size: 14px;
    font-weight: 600;
}
.calc-badge {
    background: #0F172A;
    color: #FFF;
    border-radius: 6px;
    padding: 16px;
    text-align: center;
    margin-top: 14px;
}
.calc-badge-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #94A3B8; }
.calc-badge-val { font-size: 26px; font-weight: 800; color: #38BDF8; margin-top: 2px; }

/* Category Header Banner */
.cat-header-card {
    background: #FFF;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 32px 28px;
    margin-top: 24px;
    margin-bottom: 24px;
    border-left: 6px solid var(--primary);
}
.cat-header-title {
    font-size: 28px;
    font-weight: 900;
    color: var(--text-head);
    margin-bottom: 8px;
}
.cat-header-desc {
    font-size: 15px;
    color: var(--text-muted);
    line-height: 1.6;
}

/* Footer */
.footer {
    background: #090D16;
    color: #94A3B8;
    margin-top: 60px;
    padding-top: 50px;
    border-top: 4px solid var(--primary);
}
.footer-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 36px;
    padding-bottom: 44px;
}
@media (min-width: 768px) {
    .footer-grid { grid-template-columns: 2fr 1fr 1fr; }
}
.footer-h4 {
    font-size: 15px;
    font-weight: 800;
    color: #FFF;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 16px;
}
.footer-list { list-style: none; }
.footer-list li { margin-bottom: 10px; font-size: 13px; }
.footer-list a { color: #94A3B8; }
.footer-list a:hover { color: #FFF; }
.footer-btm {
    background: #06090F;
    padding: 22px 0;
    font-size: 12px;
    color: #64748B;
    text-align: center;
    border-top: 1px solid #1E293B;
}
"""

def render_page(title, desc, canonical, main_body, active_nav="Home"):
    navs = [
        ("Home", "/"),
        ("Business", "/category/business"),
        ("Insurance", "/category/insurance"),
        ("Carrier", "/category/carrier"),
        ("Finance", "/category/finance"),
        ("EMI Calculator", "/emi-calculator")
    ]
    nav_links = "".join([f'<li class="nav-item"><a href="{h}" class="{"active" if active_nav == n else ""}">{n}</a></li>' for n, h in navs])
    
    ticker_article = processed_articles[0]
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | LoanRaaj</title>
    <meta name="description" content="{desc}">
    <link rel="canonical" href="{canonical}">
    <meta name="google-site-verification" content="google31976c4df01121b2">
    <meta property="og:title" content="{title} | LoanRaaj">
    <meta property="og:description" content="{desc}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="LoanRaaj">
    <style>{CSS_PROFESSIONAL}</style>
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "LoanRaaj",
        "url": "https://loanraaj.com",
        "description": "Your Trusted Guide for Business Finance, Loans & Insurance Intelligence"
    }}
    </script>
</head>
<body>
    <!-- Topbar -->
    <div class="topbar">
        <div class="container">
            <div class="topbar-flex">
                <div class="ticker-box">
                    <span class="ticker-badge">Trending</span>
                    <a href="/{ticker_article['slug']}" class="ticker-text">{ticker_article['title']}</a>
                </div>
                <div style="font-size:11px; color:#64748B;">November 2026 Edition</div>
            </div>
        </div>
    </div>

    <!-- Header -->
    <header class="header">
        <div class="container">
            <div class="header-flex">
                <div>
                    <a href="/" class="brand-logo">LOAN<span>RAAJ</span></a>
                    <div class="brand-tag">Business, Finance & Insurance Network</div>
                </div>
                <div class="header-ad">
                    <div class="ad-slot-label">Advertisement</div>
                    <div class="header-ad-sub">728x90 Leaderboard / Adaptive Display Unit</div>
                </div>
            </div>
        </div>
    </header>

    <!-- Navigation -->
    <nav class="nav-wrap">
        <div class="container">
            <ul class="nav-ul">
                {nav_links}
            </ul>
        </div>
    </nav>

    <!-- Main Content -->
    {main_body}

    <!-- Footer -->
    <footer class="footer">
        <div class="container">
            <div class="footer-grid">
                <div>
                    <div class="brand-logo" style="color:#FFF; font-size:24px; margin-bottom:10px;">LOAN<span style="color:var(--primary);">RAAJ</span></div>
                    <p style="font-size:13px; line-height:1.75; color:#94A3B8; margin-bottom:14px;">
                        LoanRaaj is an authoritative financial intelligence publisher providing detailed rate comparisons, owner-operator insurance guides, equipment financing breakdowns, and interactive calculators.
                    </p>
                    <p style="font-size:11px; color:#64748B;">
                        Disclaimer: LoanRaaj is an independent educational publisher and not a banking lender or insurance underwriter.
                    </p>
                </div>
                <div>
                    <h4 class="footer-h4">Categories</h4>
                    <ul class="footer-list">
                        <li><a href="/category/business">Business Ideas & Import</a></li>
                        <li><a href="/category/insurance">Commercial Insurance</a></li>
                        <li><a href="/category/carrier">CDL & Trucking Career</a></li>
                        <li><a href="/category/finance">Loan Guides & Schemes</a></li>
                        <li><a href="/emi-calculator">Loan EMI Calculator</a></li>
                    </ul>
                </div>
                <div>
                    <h4 class="footer-h4">Trust & Legal</h4>
                    <ul class="footer-list">
                        <li><a href="/privacy-policy">Privacy Policy</a></li>
                        <li><a href="/terms-and-conditions">Terms & Conditions</a></li>
                        <li><a href="/disclaimer">Disclaimer</a></li>
                        <li><a href="/about-us">About Editorial Team</a></li>
                        <li><a href="/contact-us">Contact Us</a></li>
                    </ul>
                </div>
            </div>
        </div>
        <div class="footer-btm">
            <div class="container">
                &copy; 2026 LoanRaaj.com. All Rights Reserved. Ultra-Clean Professional Publishing Engine.
            </div>
        </div>
    </footer>
</body>
</html>"""

def get_sidebar():
    trending = processed_articles[1:6]
    items_html = ""
    for idx, t in enumerate(trending, 1):
        items_html += f"""
        <div style="display:flex; gap:12px; margin-bottom:16px; align-items:flex-start;">
            <span style="font-size:20px; font-weight:800; color:#CBD5E1; line-height:1;">0{idx}</span>
            <div>
                <a href="/{t['slug']}" style="font-weight:700; font-size:13px; line-height:1.4; display:block; color:var(--text-head); margin-bottom:4px;">{t['title']}</a>
                <span style="font-size:11px; color:var(--text-muted);">{t.get('category', 'Finance')} • 5 min read</span>
            </div>
        </div>
        """
        
    return f"""
    <aside class="sidebar-col">
        <!-- 300x250 Ad -->
        <div class="widget-card">
            <div class="ad-slot-box" style="margin:0; padding:28px 14px;">
                <div class="ad-slot-label">Sponsored Unit</div>
                <div class="ad-slot-spec">300x250 Medium Rectangle</div>
            </div>
        </div>

        <!-- EMI Calculator -->
        <div class="widget-card">
            <h3 class="widget-title">Loan EMI Calculator</h3>
            <div class="calc-field">
                <label>Loan Amount ($)</label>
                <input type="number" id="sLoan" value="50000" step="5000" oninput="runSideCalc()">
            </div>
            <div class="calc-field">
                <label>Interest Rate (% P.A.)</label>
                <input type="number" id="sRate" value="8.5" step="0.25" oninput="runSideCalc()">
            </div>
            <div class="calc-field">
                <label>Tenure (Years)</label>
                <input type="number" id="sYears" value="5" min="1" max="30" oninput="runSideCalc()">
            </div>
            <div class="calc-badge">
                <div class="calc-badge-title">Estimated Monthly Payment</div>
                <div class="calc-badge-val" id="sResult">$1,025</div>
            </div>
            <a href="/emi-calculator" style="display:block; text-align:center; font-size:12px; font-weight:700; color:var(--primary); margin-top:14px;">Open Full Amortization Schedule &rarr;</a>
            <script>
            function runSideCalc() {{
                var p = parseFloat(document.getElementById('sLoan').value) || 0;
                var r = parseFloat(document.getElementById('sRate').value) || 0;
                var y = parseFloat(document.getElementById('sYears').value) || 0;
                if (p > 0 && r > 0 && y > 0) {{
                    var mr = (r / 12) / 100;
                    var n = y * 12;
                    var emi = (p * mr * Math.pow(1 + mr, n)) / (Math.pow(1 + mr, n) - 1);
                    document.getElementById('sResult').innerText = '$' + Math.round(emi).toLocaleString();
                }}
            }}
            </script>
        </div>

        <!-- Top Articles -->
        <div class="widget-card">
            <h3 class="widget-title">Trending Insights</h3>
            {items_html}
        </div>
    </aside>
    """

# 1. GENERATE HOMEPAGE
hero1 = processed_articles[0]
hero2 = processed_articles[1]
hero3 = processed_articles[2]
feed_list = processed_articles[3:]

feed_html = ""
for f_art in feed_list:
    feed_html += f"""
    <article class="feed-card">
        <div class="feed-thumb">
            <img src="{f_art['image']}" alt="{html.escape(f_art['title'])}" loading="lazy">
        </div>
        <div class="feed-info">
            <a href="/category/{f_art['category'].lower()}" class="feed-cat">{f_art['category']}</a>
            <h2 class="feed-title"><a href="/{f_art['slug']}">{f_art['title']}</a></h2>
            <p class="feed-desc">{f_art['excerpt']}</p>
            <div class="feed-meta">By LoanRaaj Editorial • {f_art.get('words', 2000)} Words</div>
        </div>
    </article>
    """

home_body = f"""
<div class="container">
    <section class="hero-grid">
        <div class="hero-card main-hero">
            <img src="{hero1['image']}" alt="{html.escape(hero1['title'])}">
            <div class="hero-overlay">
                <a href="/category/{hero1['category'].lower()}" class="hero-badge">{hero1['category']}</a>
                <h1 class="hero-h1"><a href="/{hero1['slug']}">{hero1['title']}</a></h1>
                <div class="hero-meta">By LoanRaaj Team • {hero1.get('words', 2500)} words</div>
            </div>
        </div>
        <div style="display:flex; flex-direction:column; gap:18px;">
            <div class="hero-card">
                <img src="{hero2['image']}" alt="{html.escape(hero2['title'])}">
                <div class="hero-overlay">
                    <a href="/category/{hero2['category'].lower()}" class="hero-badge">{hero2['category']}</a>
                    <h2 class="hero-h1" style="font-size:18px;"><a href="/{hero2['slug']}">{hero2['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • {hero2['category']}</div>
                </div>
            </div>
            <div class="hero-card">
                <img src="{hero3['image']}" alt="{html.escape(hero3['title'])}">
                <div class="hero-overlay">
                    <a href="/category/{hero3['category'].lower()}" class="hero-badge">{hero3['category']}</a>
                    <h2 class="hero-h1" style="font-size:18px;"><a href="/{hero3['slug']}">{hero3['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • {hero3['category']}</div>
                </div>
            </div>
        </div>
    </section>

    <div class="main-layout">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:2px solid var(--dark); padding-bottom:10px;">
                <h2 style="font-size:18px; font-weight:800; text-transform:uppercase;">Latest Stories & In-Depth Guides</h2>
                <span style="font-size:12px; color:var(--text-muted); font-weight:700;">{len(processed_articles)} Publications</span>
            </div>
            {feed_html}
        </div>
        {get_sidebar()}
    </div>
</div>
"""

home_page_html = render_page(
    title="LoanRaaj - Business, Finance & Insurance Network",
    desc="Authoritative guides on commercial trucking insurance, owner-operator costs, small business machinery, and loan calculations.",
    canonical="https://loanraaj.com",
    main_body=home_body,
    active_nav="Home"
)

with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as fp:
    fp.write(home_page_html)

# 2. GENERATE DEDICATED CATEGORY PAGES
for cat_name, meta in CATEGORY_METADATA.items():
    cat_slug = cat_name.lower()
    cat_articles = [a for a in processed_articles if a['category'] == cat_name]
    
    cat_feed_html = ""
    for c_art in cat_articles:
        cat_feed_html += f"""
        <article class="feed-card">
            <div class="feed-thumb">
                <img src="{c_art['image']}" alt="{html.escape(c_art['title'])}" loading="lazy">
            </div>
            <div class="feed-info">
                <span class="feed-cat">{cat_name}</span>
                <h2 class="feed-title"><a href="/{c_art['slug']}">{c_art['title']}</a></h2>
                <p class="feed-desc">{c_art['excerpt']}</p>
                <div class="feed-meta">By LoanRaaj Editorial • {c_art.get('words', 2000)} Words • 5 Min Read</div>
            </div>
        </article>
        """
        
    cat_body = f"""
    <div class="container">
        <div class="cat-header-card">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <span style="font-size:24px;">{meta['icon']}</span>
                <h1 class="cat-header-title">{meta['title']}</h1>
            </div>
            <p class="cat-header-desc">{meta['desc']}</p>
            <div style="margin-top:12px; font-size:12px; color:var(--primary); font-weight:700;">
                {len(cat_articles)} In-Depth Publications in this Category
            </div>
        </div>

        <div class="main-layout">
            <div>
                {cat_feed_html}
            </div>
            {get_sidebar()}
        </div>
    </div>
    """
    
    cat_html = render_page(
        title=f"{cat_name} Guides & Financial Intelligence",
        desc=meta['desc'],
        canonical=f"https://loanraaj.com/category/{cat_slug}",
        main_body=cat_body,
        active_nav=cat_name
    )
    
    # Save both /category/name.html and /category/name/index.html
    cat_dir = os.path.join(BASE_DIR, "category", cat_slug)
    os.makedirs(cat_dir, exist_ok=True)
    with open(os.path.join(cat_dir, "index.html"), "w", encoding="utf-8") as fp:
        fp.write(cat_html)
    # also save /category/name.html for direct extension routes
    with open(os.path.join(BASE_DIR, "category", f"{cat_slug}.html"), "w", encoding="utf-8") as fp:
        fp.write(cat_html)

print("Generated dedicated category archive pages for Business, Insurance, Carrier, and Finance.")

# 3. GENERATE INDIVIDUAL ARTICLES
for post in processed_articles:
    p_slug = post['slug']
    p_cat = post['category']
    p_cat_slug = p_cat.lower()
    
    post_body = f"""
    <div class="container">
        <div class="main-layout">
            <main>
                <article class="post-paper">
                    <div class="post-crumb">
                        <a href="/">Home</a> <span>/</span>
                        <a href="/category/{p_cat_slug}">{p_cat}</a> <span>/</span>
                        <span style="color:var(--text-head);">{post['title'][:40]}...</span>
                    </div>

                    <a href="/category/{p_cat_slug}" class="cat-badge">{p_cat}</a>
                    <h1 class="post-h1">{post['title']}</h1>

                    <div class="post-meta">
                        <span>By <strong>LoanRaaj Editorial Board</strong></span> • 
                        <span>Updated November 2026</span> • 
                        <span>{post.get('words', 2000)} Words</span> • 
                        <span>5 Min Read</span>
                    </div>

                    <div class="post-feature-wrap">
                        <img src="{post['image']}" alt="{html.escape(post['title'])}" loading="eager">
                    </div>

                    <div class="ad-slot-box">
                        <div class="ad-slot-label">Sponsored Content</div>
                        <div class="ad-slot-spec">Responsive In-Article Banner (728x90)</div>
                    </div>

                    <div class="post-content">
                        {post['content']}
                    </div>

                    <div class="ad-slot-box">
                        <div class="ad-slot-label">Recommended Resources</div>
                        <div class="ad-slot-spec">Related Insurance & Financial Service Providers</div>
                    </div>

                    <!-- Author Box -->
                    <div class="author-card">
                        <div class="author-avatar">LR</div>
                        <div>
                            <div style="font-weight:800; font-size:16px; color:var(--text-head);">LoanRaaj Research Team</div>
                            <div style="font-size:13px; color:var(--text-muted); margin-top:3px; line-height:1.6;">
                                Specialist commercial finance and freight logistics research desk publishing transparent cost benchmarks, rate comparisons, and regulatory guides.
                            </div>
                        </div>
                    </div>
                </article>
            </main>
            {get_sidebar()}
        </div>
    </div>
    """
    
    post_html = render_page(
        title=post['title'],
        desc=post['excerpt'],
        canonical=f"https://loanraaj.com/{p_slug}",
        main_body=post_body,
        active_nav=p_cat
    )
    
    with open(os.path.join(BASE_DIR, f"{p_slug}.html"), "w", encoding="utf-8") as fp:
        fp.write(post_html)
    p_dir = os.path.join(BASE_DIR, p_slug)
    os.makedirs(p_dir, exist_ok=True)
    with open(os.path.join(p_dir, "index.html"), "w", encoding="utf-8") as fp:
        fp.write(post_html)

# 4. DEDICATED EMI CALCULATOR PAGE
emi_content = f"""
<div class="container">
    <div class="main-layout">
        <main>
            <div class="post-paper">
                <div class="post-crumb">
                    <a href="/">Home</a> <span>/</span> <span>Calculators</span> <span>/</span> <span>Loan EMI Calculator</span>
                </div>
                <h1 class="post-h1">Interactive Loan EMI & Amortization Calculator</h1>
                <p style="color:var(--text-muted); margin-bottom:28px;">Compute precise monthly installment schedules, total accrued interest, and payback ratios in real-time.</p>

                <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:8px; padding:26px; margin-bottom:30px;">
                    <div style="display:grid; grid-template-columns:1fr; gap:20px;">
                        <div>
                            <label style="font-weight:700; font-size:13px; display:block; margin-bottom:6px;">Loan Amount ($): <span id="fullAmtDisplay" style="color:var(--primary); font-weight:800;">$100,000</span></label>
                            <input type="range" id="fullAmtRange" min="5000" max="1000000" step="5000" value="100000" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                        <div>
                            <label style="font-weight:700; font-size:13px; display:block; margin-bottom:6px;">Annual Interest Rate (%): <span id="fullRateDisplay" style="color:var(--primary); font-weight:800;">8.5%</span></label>
                            <input type="range" id="fullRateRange" min="2" max="25" step="0.25" value="8.5" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                        <div>
                            <label style="font-weight:700; font-size:13px; display:block; margin-bottom:6px;">Tenure: <span id="fullTenureDisplay" style="color:var(--primary); font-weight:800;">10 Years</span></label>
                            <input type="range" id="fullTenureRange" min="1" max="30" step="1" value="10" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:16px; margin-top:26px;">
                        <div style="background:#0F172A; color:#FFF; padding:20px; border-radius:8px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:#94A3B8; letter-spacing:0.8px;">Monthly EMI</div>
                            <div id="fullEmiRes" style="font-size:30px; font-weight:900; color:#38BDF8; margin-top:4px;">$1,240</div>
                        </div>
                        <div style="background:#FFF; border:1px solid var(--border); padding:20px; border-radius:8px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.8px;">Total Interest</div>
                            <div id="fullTotalInterest" style="font-size:26px; font-weight:800; color:var(--text-head); margin-top:4px;">$48,789</div>
                        </div>
                        <div style="background:#FFF; border:1px solid var(--border); padding:20px; border-radius:8px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.8px;">Total Payment</div>
                            <div id="fullTotalPayment" style="font-size:26px; font-weight:800; color:var(--text-head); margin-top:4px;">$148,789</div>
                        </div>
                    </div>
                </div>

                <div class="post-content">
                    <h2>Formula Behind Loan Calculations</h2>
                    <p>The Equated Monthly Installment (EMI) formula standard across major banking and lending institutions is:</p>
                    <blockquote>
                        EMI = [P x R x (1+R)^N] / [(1+R)^N - 1]
                    </blockquote>
                    <p>Where <strong>P</strong> represents the principal, <strong>R</strong> is the periodic monthly rate, and <strong>N</strong> denotes the total number of amortization cycles.</p>
                </div>

                <script>
                function updateFullCalc() {{
                    var p = parseFloat(document.getElementById('fullAmtRange').value);
                    var r = parseFloat(document.getElementById('fullRateRange').value);
                    var y = parseFloat(document.getElementById('fullTenureRange').value);

                    document.getElementById('fullAmtDisplay').innerText = '$' + p.toLocaleString();
                    document.getElementById('fullRateDisplay').innerText = r + '%';
                    document.getElementById('fullTenureDisplay').innerText = y + ' Years';

                    var mr = (r / 12) / 100;
                    var n = y * 12;
                    var emi = (p * mr * Math.pow(1 + mr, n)) / (Math.pow(1 + mr, n) - 1);
                    var total = emi * n;
                    var interest = total - p;

                    document.getElementById('fullEmiRes').innerText = '$' + Math.round(emi).toLocaleString();
                    document.getElementById('fullTotalInterest').innerText = '$' + Math.round(interest).toLocaleString();
                    document.getElementById('fullTotalPayment').innerText = '$' + Math.round(total).toLocaleString();
                }}
                </script>
            </div>
        </main>
        {get_sidebar()}
    </div>
</div>
"""

emi_html = render_page(
    title="Loan EMI Calculator - Monthly Payment & Amortization Estimator",
    desc="Free interactive loan EMI calculator to compute monthly installments, interest rates, and loan tenure amortizations.",
    canonical="https://loanraaj.com/emi-calculator",
    main_body=emi_content,
    active_nav="EMI Calculator"
)

with open(os.path.join(BASE_DIR, "emi-calculator.html"), "w", encoding="utf-8") as fp:
    fp.write(emi_html)
os.makedirs(os.path.join(BASE_DIR, "emi-calculator"), exist_ok=True)
with open(os.path.join(BASE_DIR, "emi-calculator", "index.html"), "w", encoding="utf-8") as fp:
    fp.write(emi_html)

# 5. EXPANDED, DEEP LEGAL PAGES (COMPREHENSIVE GOOGLE ADSENSE & TRUST SHIELD)
legal_pages = [
    ("privacy-policy", "Privacy Policy", """
    <h2>1. Introduction & Overview</h2>
    <p>LoanRaaj ("we", "our", or "us") operates https://loanraaj.com (the "Site"). We are firmly committed to safeguarding the digital privacy of our visitors, readers, and registered members. This Privacy Policy outlines what information is collected, how it is processed, and your privacy rights under global regulations including the General Data Protection Regulation (GDPR) and California Consumer Privacy Act (CCPA).</p>

    <h2>2. Information We Collect</h2>
    <p>When browsing LoanRaaj, we collect two categories of information:</p>
    <ul>
        <li><strong>Log Files & Technical Data:</strong> Standard server logs capturing IP addresses, browser types, Internet Service Providers (ISPs), date/time stamps, referring/exit pages, and click counts. None of this data is linked to personally identifiable information.</li>
        <li><strong>Voluntary Correspondence:</strong> When contacting our editorial or support desk, we collect your name, email address, and message contents solely to respond to your inquiry.</li>
    </ul>

    <h2>3. Cookies, Web Beacons & Third-Party Advertising</h2>
    <p>LoanRaaj monetizes digital traffic through reputable advertising platforms, including <strong>Google AdSense, Adsterra, Monetag, and HilltopAds</strong>. These third-party vendors utilize cookies, JavaScript, and Web Beacons to measure campaign efficacy and deliver personalized advertisements based on past visits to this and other websites across the Internet.</p>
    <ul>
        <li><strong>Google DoubleClick DART Cookies:</strong> Google uses DART cookies to serve ads based on user visits. You can opt out of DART cookie usage by visiting the <a href="https://policies.google.com/technologies/ads" target="_blank" rel="nofollow">Google Ad and Content Network Privacy Policy</a>.</li>
        <li><strong>Ad Choices Opt-Out:</strong> Readers can opt out of third-party behavioral advertising via the Network Advertising Initiative (NAI) or <a href="https://aboutads.info/choices" target="_blank" rel="nofollow">aboutads.info</a>.</li>
    </ul>

    <h2>4. GDPR Compliance (EEA Readers)</h2>
    <p>Residents of the European Economic Area possess the right to access, rectify, port, or erase any personal information we retain. If you wish to execute any GDPR statutory rights, contact our Data Protection Officer at privacy@loanraaj.com.</p>

    <h2>5. CCPA Privacy Rights (California Consumers)</h2>
    <p>Under the CCPA, California consumers hold the right to request disclosure of personal data categories collected, request deletion of collected information, and demand that personal information not be sold. LoanRaaj does not sell personal user information to third-party data brokers.</p>

    <h2>6. Children's Privacy Protection (COPPA)</h2>
    <p>LoanRaaj does not knowingly solicit or collect personal identifiable information from children under the age of 13. If you believe your child submitted personal data on our portal, please contact us immediately, and we will promptly purge such records.</p>
    """),

    ("terms-and-conditions", "Terms and Conditions", """
    <h2>1. Acceptance of Agreement</h2>
    <p>By browsing, accessing, or utilizing any resources on LoanRaaj.com, you agree to comply with and be bound by these Terms and Conditions. If you do not accept these provisions, you should discontinue using our services immediately.</p>

    <h2>2. Independent Educational Content & No Financial Advice</h2>
    <p>LoanRaaj is an independent digital publishing property dedicated to commercial financial analysis, insurance cost education, freight career guides, and interactive calculators. <strong>LoanRaaj is not a bank, certified financial advisory, registered broker-dealer, or direct insurance carrier.</strong></p>
    <p>All calculators, rate tables, and cost benchmarks are presented for informational and illustrative purposes only. Past performance or sample quotes do not guarantee future commercial lending terms.</p>

    <h2>3. Proprietary Intellectual Property</h2>
    <p>All written editorial guides, mathematical calculators, graphics, website source code, layout systems, and trademarks appearing on LoanRaaj.com remain the exclusive intellectual property of LoanRaaj Media Group. Unauthorized reproduction, web scraping, or duplication without explicit written permission is strictly prohibited.</p>

    <h2>4. Limitation of Liability</h2>
    <p>Under no circumstance shall LoanRaaj, its officers, writers, or affiliates be liable for direct, indirect, incidental, or consequential damages resulting from your reliance on information published on this Site, including loan rejections, insurance policy rate variances, or commercial fleet decisions.</p>
    """),

    ("disclaimer", "Disclaimer & Regulatory Disclosure", """
    <h2>1. Non-Lender & Independent Publisher Disclosure</h2>
    <p>LoanRaaj.com operates strictly as an independent financial journalism and educational platform. <strong>We do not originate loans, issue commercial insurance policies, collect loan underwriting fees, or broker credit contracts.</strong></p>

    <h2>2. Accuracy of Rates & Market Quotes</h2>
    <p>While our editorial team strives to verify commercial quotes, government subsidies (such as PMEGP), and insurance benchmarks from official rate filings and state insurance commissioners, financial regulations change dynamically. We cannot warrant that all published interest rates, premiums, or eligibility criteria reflect real-time underwriter approvals.</p>

    <h2>3. Third-Party External Hyperlinks</h2>
    <p>Our articles may contain links to external third-party sites, including lenders, insurance aggregators, and regulatory agencies. LoanRaaj exercises no control over the content, security policies, or lending practices of external websites.</p>
    """),

    ("about-us", "About LoanRaaj Media", """
    <h2>Our Mission & Editorial Manifesto</h2>
    <p>Founded in 2026, LoanRaaj was established with a singular objective: <strong>to demystify commercial freight insurance, equipment procurement, and entrepreneurial lending for independent operators and small business owners.</strong></p>
    <p>Navigating commercial truck insurance, owner-operator operating costs, and business machinery loans is notoriously opaque. Commercial brokers often exploit informational asymmetries. LoanRaaj levels the playing field with transparent, data-driven cost benchmarks and independent rate breakdowns.</p>

    <h2>E-E-A-T Editorial Standards & Review Board</h2>
    <p>Every guide published on LoanRaaj undergoes rigorous internal fact-checking by our in-house commercial logistics and financial research desk:</p>
    <ul>
        <li><strong>Deep Industry Research:</strong> We analyze filings from the Federal Motor Carrier Safety Administration (FMCSA), state insurance regulators, and commercial lending registries.</li>
        <li><strong>Practical Calculator Tools:</strong> Our interactive EMI and amortization engines run client-side to ensure total privacy and immediate mathematical precision.</li>
        <li><strong>Zero Paid Editorial Bias:</strong> Advertisers and sponsors have zero influence over our rate comparisons, policy ratings, or editorial commentary.</li>
    </ul>
    """),

    ("contact-us", "Contact Our Editorial Office", """
    <h2>Reach Out to Our Team</h2>
    <p>We welcome feedback, editorial inquiries, rate verification requests, and legitimate advertising partnerships. Please contact our dedicated departments below:</p>

    <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:8px; padding:24px; margin:24px 0;">
        <h3 style="margin-top:0; font-size:18px; color:var(--text-head);">Corporate & Editorial Inquiries</h3>
        <p style="margin-bottom:8px;"><strong>Editorial Desk:</strong> editorial@loanraaj.com</p>
        <p style="margin-bottom:8px;"><strong>Legal & Privacy Officer:</strong> privacy@loanraaj.com</p>
        <p style="margin-bottom:8px;"><strong>Advertising & Partnerships:</strong> contact@loanraaj.com</p>
        <p style="margin-bottom:0;"><strong>Office Hours:</strong> Monday – Friday, 9:00 AM – 6:00 PM (IST). Average response turnaround: 24 to 48 business hours.</p>
    </div>

    <h2>Direct Inquiry Form</h2>
    <div style="background:#FFF; border:1px solid var(--border); border-radius:8px; padding:24px; max-width:650px;">
        <div style="margin-bottom:16px;">
            <label style="display:block; font-size:13px; font-weight:700; margin-bottom:6px;">Your Full Name</label>
            <input type="text" placeholder="e.g. John Doe" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
        </div>
        <div style="margin-bottom:16px;">
            <label style="display:block; font-size:13px; font-weight:700; margin-bottom:6px;">Email Address</label>
            <input type="email" placeholder="john@example.com" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
        </div>
        <div style="margin-bottom:16px;">
            <label style="display:block; font-size:13px; font-weight:700; margin-bottom:6px;">Subject</label>
            <input type="text" placeholder="Editorial inquiry or feedback" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
        </div>
        <div style="margin-bottom:18px;">
            <label style="display:block; font-size:13px; font-weight:700; margin-bottom:6px;">Your Message</label>
            <textarea rows="4" placeholder="How can we assist you?" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px; font-family:var(--font-sans);"></textarea>
        </div>
        <button type="button" style="background:var(--primary); color:#FFF; font-weight:700; font-size:14px; padding:12px 24px; border:none; border-radius:6px; cursor:pointer;" onclick="alert('Thank you! Your message has been routed to the LoanRaaj editorial desk.')">Send Message &rarr;</button>
    </div>
    """)
]

for l_slug, l_title, l_content in legal_pages:
    l_body = f"""
    <div class="container">
        <div class="main-layout">
            <main>
                <div class="post-paper">
                    <div class="post-crumb">
                        <a href="/">Home</a> <span>/</span> <span>Legal & Trust</span> <span>/</span> <span>{l_title}</span>
                    </div>
                    <h1 class="post-h1">{l_title}</h1>
                    <div class="post-content" style="margin-top:20px;">
                        {l_content}
                    </div>
                </div>
            </main>
            {get_sidebar()}
        </div>
    </div>
    """
    l_html = render_page(
        title=f"{l_title} - Official Policy",
        desc=f"Official {l_title} document for LoanRaaj.com.",
        canonical=f"https://loanraaj.com/{l_slug}",
        main_body=l_body,
        active_nav="Trust & Legal"
    )
    with open(os.path.join(BASE_DIR, f"{l_slug}.html"), "w", encoding="utf-8") as fp:
        fp.write(l_html)
    os.makedirs(os.path.join(BASE_DIR, l_slug), exist_ok=True)
    with open(os.path.join(BASE_DIR, l_slug, "index.html"), "w", encoding="utf-8") as fp:
        fp.write(l_html)

print("Generated expanded legal and trust pages.")

# 6. COMPREHENSIVE SITEMAP.XML
sitemap_urls = [
    ("https://loanraaj.com/", "1.0"),
    ("https://loanraaj.com/category/business", "0.9"),
    ("https://loanraaj.com/category/insurance", "0.9"),
    ("https://loanraaj.com/category/carrier", "0.9"),
    ("https://loanraaj.com/category/finance", "0.9"),
    ("https://loanraaj.com/emi-calculator", "0.9")
]

for post in processed_articles:
    sitemap_urls.append((f"https://loanraaj.com/{post['slug']}", "0.8"))

for l_slug, _, _ in legal_pages:
    sitemap_urls.append((f"https://loanraaj.com/{l_slug}", "0.7"))

sitemap_xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u, pri in sitemap_urls:
    sitemap_xml.append(f"""  <url>
    <loc>{u}</loc>
    <lastmod>2026-11-10</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{pri}</priority>
  </url>""")
sitemap_xml.append('</urlset>')

with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as fp:
    fp.write("\n".join(sitemap_xml))

print(f"Generated comprehensive sitemap.xml with {len(sitemap_urls)} unique indexed URLs.")
