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

print(f"Loaded {len(raw_articles)} raw articles.")

def clean_to_semantic_blocks(html_content):
    if not html_content:
        return "<p>Content being updated.</p>"
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Strip scripts, styles, forms, inputs, buttons, iframes, noscript
    for tag in soup(['script', 'style', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'noscript', 'meta', 'link']):
        tag.decompose()
        
    # 2. Decompose known junk IDs/classes/forms
    junk_markers = ['mvp-content-bot', 'mvp-post-tags', 'mvp-post-soc', 'posts-nav-link', 'comments', 'code-block', 'author-box', 'relpost', 'ast-single-related-posts', 'newsletter', 'signup']
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        tag_id = tag.attrs.get('id', '')
        tag_classes = ' '.join(tag.attrs.get('class', []))
        if any(m in str(tag_id).lower() or m in str(tag_classes).lower() for m in junk_markers):
            tag.decompose()
            continue
        # Also remove if text has RIDE ALONG or lead capture
        if 'RIDE ALONG' in tag.get_text() or 'Insta ID' in tag.get_text():
            tag.decompose()

    # 3. Collect only valid content blocks
    blocks = []
    nav_phrases = {'home', 'about us', 'contact us', 'disclaimer', 'privacy policy', 'terms & conditions', 'terms and conditions'}
    
    for el in soup.find_all(['h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table', 'blockquote']):
        if not isinstance(el, Tag):
            continue
        # If nested inside another block, skip parent iteration
        if el.parent and el.parent.name in ['ul', 'ol', 'blockquote', 'table']:
            continue
            
        text = el.get_text().strip()
        if not text and not el.find('img'):
            continue
            
        # Clean specific script/ad debris
        if any(junk in text for junk in ['window.googletag', 'googletag.cmd', 'Related Posts', 'Advertisement', 'googletag.display']):
            continue

        if el.name in ['h2', 'h3', 'h4']:
            clean_head = re.sub(r'\s+', ' ', text)
            # Remove redundant numbers or weird prefixes if any
            blocks.append(f'<{el.name}>{html.escape(clean_head)}</{el.name}>')
            
        elif el.name == 'p':
            # Check for inner images
            imgs = el.find_all('img')
            if imgs:
                for img in imgs:
                    src = img.attrs.get('src', '') if img.attrs else ''
                    alt = img.attrs.get('alt', '') if img.attrs else ''
                    if src and not src.startswith('data:') and 'google' not in src:
                        blocks.append(f'<div class="article-inner-img"><img src="{src}" alt="{html.escape(alt)}" loading="lazy"></div>')
                        
            # Clean inner links
            for a in el.find_all('a'):
                if a.attrs:
                    href = a.attrs.get('href', '')
                    if 'bazartak.net/' in href or 'kamtak.in/' in href:
                        slug = href.strip('/').split('/')[-1]
                        a['href'] = f'/{slug}'
                    a.attrs = {'href': a.attrs.get('href', '#')}
                    
            # Unwrap formatting tags other than bold/italic/links
            for child in el.find_all(True):
                if child.name not in ['a', 'strong', 'b', 'em', 'i']:
                    child.unwrap()
                else:
                    child.attrs = {k: v for k, v in child.attrs.items() if k in ['href', 'target']}
                    
            p_html = ''.join(str(c) for c in el.contents).strip()
            # Clean repetitive &nbsp; or whitespace
            p_html = p_html.replace('&nbsp;', ' ').strip()
            if p_html and len(p_html) > 5 and not any(p_html.lower() == phrase for phrase in nav_phrases):
                # Replace branding
                p_html = p_html.replace('BazarTak', 'LoanRaaj').replace('bazartak.net', 'loanraaj.com').replace('KamTak', 'LoanRaaj').replace('kamtak.in', 'loanraaj.com')
                blocks.append(f'<p>{p_html}</p>')
                
        elif el.name in ['ul', 'ol']:
            items = []
            for li in el.find_all('li', recursive=False):
                li_text = li.get_text().strip()
                # Filter navigation breadcrumbs that leaked into lists
                if li_text and li_text.lower() not in nav_phrases:
                    items.append(f'<li>{html.escape(li_text)}</li>')
            # Only append if at least 2 non-nav items exist
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

# Clean all articles
clean_articles = []
for a in raw_articles:
    cleaned_body = clean_to_semantic_blocks(a['content'])
    clean_articles.append({
        "slug": a['slug'],
        "title": a['title'],
        "category": a.get('category', 'Finance'),
        "image": a['image'],
        "excerpt": a['excerpt'],
        "content": cleaned_body,
        "words": a.get('words', len(cleaned_body.split()))
    })

print(f"Cleaned {len(clean_articles)} articles into semantic HTML.")

# HIGH-END PROFESSIONAL STYLESHEET
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
        ("Business", "/#business"),
        ("Insurance", "/#insurance"),
        ("Carrier", "/#carrier"),
        ("Finance", "/#finance"),
        ("EMI Calculator", "/emi-calculator")
    ]
    nav_links = "".join([f'<li class="nav-item"><a href="{h}" class="{"active" if active_nav == n else ""}">{n}</a></li>' for n, h in navs])
    
    ticker_article = clean_articles[0]
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | LoanRaaj</title>
    <meta name="description" content="{desc}">
    <link rel="canonical" href="{canonical}">
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
                        <li><a href="/#business">Business Ideas & Import</a></li>
                        <li><a href="/#insurance">Commercial Insurance</a></li>
                        <li><a href="/#carrier">CDL & Trucking Career</a></li>
                        <li><a href="/#finance">Loan Guides & Schemes</a></li>
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
    trending = clean_articles[1:6]
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

# 1. HOMEPAGE
hero1 = clean_articles[0]
hero2 = clean_articles[1]
hero3 = clean_articles[2]
feed_list = clean_articles[3:]

feed_html = ""
for f_art in feed_list:
    feed_html += f"""
    <article class="feed-card">
        <div class="feed-thumb">
            <img src="{f_art['image']}" alt="{html.escape(f_art['title'])}" loading="lazy">
        </div>
        <div class="feed-info">
            <span class="feed-cat">{f_art.get('category', 'Finance')}</span>
            <h2 class="feed-title"><a href="/{f_art['slug']}">{f_art['title']}</a></h2>
            <p class="feed-desc">{f_art['excerpt']}</p>
            <div class="feed-meta">By LoanRaaj Editorial • {f_art.get('words', 2000)} Words</div>
        </div>
    </article>
    """

home_body = f"""
<div class="container">
    <!-- Hero 3-Grid -->
    <section class="hero-grid">
        <div class="hero-card main-hero">
            <img src="{hero1['image']}" alt="{html.escape(hero1['title'])}">
            <div class="hero-overlay">
                <span class="hero-badge">{hero1.get('category', 'Business')}</span>
                <h1 class="hero-h1"><a href="/{hero1['slug']}">{hero1['title']}</a></h1>
                <div class="hero-meta">By LoanRaaj Team • {hero1.get('words', 2500)} words</div>
            </div>
        </div>
        <div style="display:flex; flex-direction:column; gap:18px;">
            <div class="hero-card">
                <img src="{hero2['image']}" alt="{html.escape(hero2['title'])}">
                <div class="hero-overlay">
                    <span class="hero-badge">{hero2.get('category', 'Insurance')}</span>
                    <h2 class="hero-h1" style="font-size:18px;"><a href="/{hero2['slug']}">{hero2['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • Insurance</div>
                </div>
            </div>
            <div class="hero-card">
                <img src="{hero3['image']}" alt="{html.escape(hero3['title'])}">
                <div class="hero-overlay">
                    <span class="hero-badge">{hero3.get('category', 'Carrier')}</span>
                    <h2 class="hero-h1" style="font-size:18px;"><a href="/{hero3['slug']}">{hero3['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • Fleet & Career</div>
                </div>
            </div>
        </div>
    </section>

    <!-- Main Layout Grid -->
    <div class="main-layout">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:2px solid var(--dark); padding-bottom:10px;">
                <h2 style="font-size:18px; font-weight:800; text-transform:uppercase;">Latest Stories & In-Depth Guides</h2>
                <span style="font-size:12px; color:var(--text-muted); font-weight:700;">{len(clean_articles)} Publications</span>
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

# 2. INDIVIDUAL POSTS
for post in clean_articles:
    p_slug = post['slug']
    p_cat = post.get('category', 'Finance')
    
    post_body = f"""
    <div class="container">
        <div class="main-layout">
            <main>
                <article class="post-paper">
                    <div class="post-crumb">
                        <a href="/">Home</a> <span>/</span>
                        <a href="/#{p_cat.lower()}">{p_cat}</a> <span>/</span>
                        <span style="color:var(--text-head);">{post['title'][:40]}...</span>
                    </div>

                    <span class="cat-badge">{p_cat}</span>
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

# 3. DEDICATED EMI CALCULATOR PAGE
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

# 4. LEGAL PAGES
legal_pages = [
    ("privacy-policy", "Privacy Policy", """
    <h2>Introduction</h2>
    <p>Welcome to LoanRaaj ("we", "our", or "us"). We respect your privacy and are committed to protecting any personal data collected when you visit our website.</p>
    <h2>Information We Collect</h2>
    <p>We may collect non-personally identifiable information including browser type, operating system, IP address, and pages viewed to optimize user experience and analyze readership trends.</p>
    <h2>Cookies & Advertising Partners</h2>
    <p>We work with trusted third-party advertising partners including Google AdSense, Adsterra, and affiliate networks. These partners may use cookies and web beacons to serve advertisements based on your prior visits to this and other websites.</p>
    <h2>GDPR & CCPA Rights</h2>
    <p>If you are a resident of the European Economic Area (EEA) or California, you are entitled to certain rights regarding your personal information, including the right to request access, correction, or deletion of any stored data.</p>
    <h2>Contact</h2>
    <p>For inquiries regarding this privacy statement, contact us at editorial@loanraaj.com.</p>
    """),
    ("terms-and-conditions", "Terms and Conditions", """
    <h2>Agreement to Terms</h2>
    <p>By accessing or using LoanRaaj.com, you agree to be bound by these Terms and Conditions and our Privacy Policy.</p>
    <h2>Informational Purposes Only</h2>
    <p>All content provided on LoanRaaj is for educational and informational purposes only. We do not provide banking, financial lending, legal, or investment advice. Always consult with a licensed financial professional or legal attorney before making financial commitments.</p>
    <h2>Intellectual Property</h2>
    <p>All written text, calculations, site branding, and layout design are the proprietary intellectual property of LoanRaaj.com.</p>
    """),
    ("disclaimer", "Disclaimer", """
    <h2>Non-Lender & Educational Disclosure</h2>
    <p>LoanRaaj.com is an independent publisher of commercial financial information. We are not a direct lender, loan broker, or insurance provider.</p>
    <p>Rates, quotes, and insurance estimates referenced in our articles are based on historical industry averages and may vary depending on jurisdiction, credit profile, and market fluctuations.</p>
    """),
    ("about-us", "About LoanRaaj", """
    <h2>Our Mission</h2>
    <p>LoanRaaj was founded to simplify commercial freight insurance, equipment procurement, and small business capital acquisition for independent entrepreneurs and owner-operators.</p>
    <h2>Editorial Integrity</h2>
    <p>Our research team conducts comprehensive rate audits across commercial insurers, equipment brokers, and financial lenders to publish actionable, transparent advice.</p>
    """),
    ("contact-us", "Contact Us", """
    <h2>Get in Touch</h2>
    <p>Have questions, editorial suggestions, or commercial partnerships? Reach out to our team below:</p>
    <div style="background:#F8FAFC; border:1px solid var(--border); padding:20px; border-radius:6px; margin:20px 0;">
        <p><strong>Editorial Office:</strong> LoanRaaj Media Group</p>
        <p><strong>Email:</strong> editorial@loanraaj.com / contact@loanraaj.com</p>
        <p><strong>Response Time:</strong> Within 24-48 business hours.</p>
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
                        <a href="/">Home</a> <span>/</span> <span>Legal</span> <span>/</span> <span>{l_title}</span>
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

print("Build complete! All files generated cleanly.")
