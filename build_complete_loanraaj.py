import os
import json
import re
import html
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = r"F:\UserData\Downloads\adstera\sites\loanraaj"
os.makedirs(BASE_DIR, exist_ok=True)

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

print(f"Loaded {len(articles)} full articles.")

# Categories
CATEGORIES = ["Business", "Insurance", "Carrier", "Finance", "EMI Calculator"]

# Color palette & Zox News styling tokens
CSS_COMMON = """
:root {
    --primary: #FF2C3B;
    --primary-hover: #E01B2A;
    --dark: #111625;
    --dark-alt: #1A2238;
    --light-bg: #F4F6F9;
    --card-bg: #FFFFFF;
    --border: #E5E9F0;
    --text-main: #2D3748;
    --text-muted: #718096;
    --font-head: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background-color: var(--light-bg);
    color: var(--text-main);
    font-family: var(--font-body);
    font-size: 15px;
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; transition: color 0.15s ease; }
a:hover { color: var(--primary); }
img { max-width: 100%; height: auto; display: block; }

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 16px;
}

/* 1. Top bar */
.topbar {
    background: #0D121F;
    color: #94A3B8;
    font-size: 12px;
    padding: 7px 0;
    border-bottom: 1px solid #1E293B;
}
.topbar .container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.ticker-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    overflow: hidden;
}
.ticker-badge {
    background: var(--primary);
    color: #FFF;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 3px;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.5px;
}
.ticker-link {
    color: #CBD5E1;
    white-space: nowrap;
}

/* 2. Header */
.main-header {
    background: #FFF;
    padding: 20px 0;
    border-bottom: 1px solid var(--border);
}
.header-flex {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
}
.logo-title {
    font-family: var(--font-head);
    font-size: 32px;
    font-weight: 900;
    letter-spacing: -1px;
    color: var(--dark);
    line-height: 1;
}
.logo-title span { color: var(--primary); }
.logo-tagline {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-muted);
    letter-spacing: 1px;
    margin-top: 4px;
    font-weight: 600;
}
.header-banner {
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    border-radius: 4px;
    padding: 12px 24px;
    text-align: center;
    color: #94A3B8;
    font-size: 11px;
    min-width: 320px;
    max-width: 728px;
    flex-grow: 1;
}

/* 3. Navigation */
.navbar {
    background: var(--dark);
    position: sticky;
    top: 0;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.nav-list {
    display: flex;
    list-style: none;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    white-space: nowrap;
}
.nav-link {
    display: block;
    padding: 14px 16px;
    font-size: 13px;
    font-weight: 700;
    color: #E2E8F0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.nav-link:hover, .nav-link.active {
    background: var(--primary);
    color: #FFF;
}

/* 4. Grid & Layout */
.main-layout {
    display: grid;
    grid-template-columns: 1fr;
    gap: 28px;
    margin: 28px auto;
}
@media (min-width: 992px) {
    .main-layout {
        grid-template-columns: 8fr 4fr;
    }
}

/* Hero Section */
.hero-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 28px;
}
@media (min-width: 768px) {
    .hero-grid {
        grid-template-columns: 7fr 5fr;
    }
}
.hero-card {
    position: relative;
    border-radius: 6px;
    overflow: hidden;
    background: var(--dark);
    min-height: 280px;
}
.hero-card.main-hero { min-height: 420px; }
.hero-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0.85;
    transition: transform 0.3s ease;
}
.hero-card:hover .hero-img { transform: scale(1.03); }
.hero-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(0,0,0,0) 30%, rgba(13,18,31,0.92) 100%);
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    color: #FFF;
}
.hero-cat {
    align-self: flex-start;
    background: var(--primary);
    color: #FFF;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
}
.hero-title {
    font-family: var(--font-head);
    font-size: 22px;
    font-weight: 800;
    line-height: 1.3;
    color: #FFF;
    margin-bottom: 8px;
}
.hero-card.main-hero .hero-title { font-size: 28px; }
.hero-meta {
    font-size: 11px;
    color: #94A3B8;
}

/* Article Feed Cards */
.article-feed-item {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 18px;
    margin-bottom: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
@media (min-width: 600px) {
    .article-feed-item {
        flex-direction: row;
    }
}
.article-feed-item:hover {
    box-shadow: 0 8px 24px rgba(0,0,0,0.06);
    transform: translateY(-2px);
}
.feed-thumb {
    width: 100%;
    height: 180px;
    border-radius: 4px;
    overflow: hidden;
    background: #E2E8F0;
    flex-shrink: 0;
}
@media (min-width: 600px) {
    .feed-thumb {
        width: 240px;
        height: 160px;
    }
}
.feed-thumb img { width: 100%; height: 100%; object-fit: cover; }
.feed-content {
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.cat-tag {
    display: inline-block;
    color: var(--primary);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}
.feed-title {
    font-family: var(--font-head);
    font-size: 18px;
    font-weight: 700;
    color: var(--dark);
    line-height: 1.35;
    margin-bottom: 8px;
}
.feed-excerpt {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.6;
    margin-bottom: 10px;
}
.feed-meta {
    font-size: 11px;
    color: #94A3B8;
}

/* Sidebar Widgets */
.widget {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 20px;
    margin-bottom: 24px;
}
.widget-title {
    font-family: var(--font-head);
    font-size: 15px;
    font-weight: 800;
    color: var(--dark);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--primary);
    margin-bottom: 16px;
}
.ad-slot-300 {
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    padding: 24px 10px;
    text-align: center;
    color: #94A3B8;
    font-size: 11px;
    border-radius: 4px;
}

/* EMI Calculator Widget */
.calc-field { margin-bottom: 14px; }
.calc-field label { display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 4px; }
.calc-field input[type="range"] { width: 100%; accent-color: var(--primary); }
.calc-val-box { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-muted); }
.calc-field input[type="number"] {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 600;
}
.calc-res-card {
    background: #0F172A;
    color: #FFF;
    border-radius: 6px;
    padding: 16px;
    text-align: center;
    margin-top: 16px;
}
.calc-emi-num {
    font-size: 26px;
    font-weight: 800;
    color: #38BDF8;
    font-family: var(--font-head);
}

/* Single Post Page */
.post-container {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 28px 24px;
}
@media (min-width: 768px) {
    .post-container { padding: 40px; }
}
.post-breadcrumb {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 16px;
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
}
.post-h1 {
    font-family: var(--font-head);
    font-size: 28px;
    font-weight: 800;
    line-height: 1.25;
    color: var(--dark);
    margin-bottom: 16px;
}
@media (min-width: 768px) {
    .post-h1 { font-size: 36px; }
}
.post-meta-bar {
    display: flex;
    gap: 16px;
    align-items: center;
    font-size: 12px;
    color: var(--text-muted);
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
}
.post-featured-img {
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 28px;
    max-height: 500px;
    background: #E2E8F0;
}
.post-featured-img img { width: 100%; height: 100%; object-fit: cover; }
.post-content {
    font-size: 16px;
    line-height: 1.85;
    color: #334155;
}
.post-content h2 {
    font-family: var(--font-head);
    font-size: 24px;
    font-weight: 800;
    margin: 32px 0 14px 0;
    color: var(--dark);
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}
.post-content h3 {
    font-family: var(--font-head);
    font-size: 19px;
    font-weight: 700;
    margin: 24px 0 10px 0;
    color: var(--dark);
}
.post-content p { margin-bottom: 18px; }
.post-content ul, .post-content ol { margin: 16px 0 22px 28px; }
.post-content li { margin-bottom: 8px; }
.post-content table {
    width: 100%;
    border-collapse: collapse;
    margin: 24px 0;
    font-size: 14px;
}
.post-content th, .post-content td {
    padding: 12px 14px;
    border: 1px solid var(--border);
    text-align: left;
}
.post-content th { background: #F8FAFC; font-weight: 700; }
.post-content blockquote {
    border-left: 4px solid var(--primary);
    padding: 12px 18px;
    background: #FFF5F5;
    margin: 20px 0;
    font-style: italic;
    color: #4A5568;
}
.ad-slot-inarticle {
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    padding: 18px;
    text-align: center;
    color: #94A3B8;
    font-size: 11px;
    margin: 28px 0;
    border-radius: 4px;
}
.author-box {
    background: #F8FAFC;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 20px;
    margin-top: 36px;
    display: flex;
    gap: 16px;
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
    font-size: 22px;
    font-weight: 800;
    flex-shrink: 0;
}

/* Footer */
.footer {
    background: var(--dark);
    color: #94A3B8;
    margin-top: 50px;
    padding-top: 48px;
    border-top: 4px solid var(--primary);
}
.footer-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 32px;
    padding-bottom: 40px;
}
@media (min-width: 768px) {
    .footer-grid { grid-template-columns: 2fr 1fr 1fr; }
}
.footer-h4 {
    font-family: var(--font-head);
    font-size: 15px;
    font-weight: 800;
    color: #FFF;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 16px;
}
.footer-list { list-style: none; }
.footer-list li { margin-bottom: 10px; font-size: 13px; }
.footer-list a { color: #94A3B8; }
.footer-list a:hover { color: #FFF; }
.footer-btm {
    background: #090D17;
    padding: 20px 0;
    font-size: 12px;
    color: #64748B;
    text-align: center;
    border-top: 1px solid #1E293B;
}
"""

def render_layout(title, desc, canonical, main_html, active_cat="Home"):
    nav_links = [
        ("Home", "/"),
        ("Business", "/#business"),
        ("Insurance", "/#insurance"),
        ("Carrier", "/#carrier"),
        ("Finance", "/#finance"),
        ("EMI Calculator", "/emi-calculator")
    ]
    nav_html = "".join([f'<li><a href="{href}" class="nav-link {"active" if active_cat == name else ""}">{name}</a></li>' for name, href in nav_links])
    
    first_post = articles[0]
    
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
    <style>{CSS_COMMON}</style>
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
            <div class="ticker-wrap">
                <span class="ticker-badge">Trending</span>
                <a href="/{first_post['slug']}" class="ticker-link">{first_post['title']}</a>
            </div>
            <div style="font-size:11px; color:#64748B;">November 2026 Edition</div>
        </div>
    </div>

    <!-- Main Header -->
    <header class="main-header">
        <div class="container">
            <div class="header-flex">
                <div>
                    <a href="/" class="logo-title">LOAN<span>RAAJ</span></a>
                    <div class="logo-tagline">Business, Finance & Insurance Network</div>
                </div>
                <div class="header-banner">
                    <span>Ad Placement: 728x90 Leaderboard / Responsive Header Unit</span>
                </div>
            </div>
        </div>
    </header>

    <!-- Navigation -->
    <nav class="navbar">
        <div class="container">
            <ul class="nav-list">
                {nav_html}
            </ul>
        </div>
    </nav>

    <!-- Page Body -->
    {main_html}

    <!-- Footer -->
    <footer class="footer">
        <div class="container">
            <div class="footer-grid">
                <div>
                    <div class="logo-title" style="color:#FFF; font-size:24px; margin-bottom:8px;">LOAN<span style="color:var(--primary);">RAAJ</span></div>
                    <p style="font-size:13px; line-height:1.7; color:#94A3B8; margin-bottom:14px;">
                        LoanRaaj is an independent financial education portal delivering practical guides on commercial trucking insurance, small business financing, home equipment imports, and interactive EMI loan calculators.
                    </p>
                    <p style="font-size:11px; color:#64748B;">
                        Disclaimer: LoanRaaj is an educational publication and not a registered banking institution or lender.
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
                &copy; 2026 LoanRaaj.com. All Rights Reserved. Clean High-Speed Publisher Engine.
            </div>
        </div>
    </footer>
</body>
</html>"""

def get_sidebar_html():
    trending_items = articles[1:6]
    trending_html = ""
    for idx, t in enumerate(trending_items, 1):
        trending_html += f"""
        <div style="display:flex; gap:12px; margin-bottom:14px; align-items:flex-start;">
            <span style="font-family:var(--font-head); font-size:20px; font-weight:800; color:#CBD5E1; line-height:1;">0{idx}</span>
            <div>
                <a href="/{t['slug']}" style="font-weight:700; font-size:13px; line-height:1.4; display:block; color:var(--dark); margin-bottom:3px;">{t['title']}</a>
                <span style="font-size:11px; color:#94A3B8;">{t.get('category', 'Finance')} • 4 min read</span>
            </div>
        </div>
        """
        
    return f"""
    <aside>
        <!-- Ad Slot -->
        <div class="widget">
            <div class="ad-slot-300">
                <span style="font-weight:700; display:block; margin-bottom:4px;">Responsive Ad Space</span>
                <span>300x250 Medium Rectangle</span>
            </div>
        </div>

        <!-- Loan Calculator -->
        <div class="widget">
            <h3 class="widget-title">Loan EMI Calculator</h3>
            <div class="calc-field">
                <label>Loan Amount ($)</label>
                <input type="number" id="sideLoanAmt" value="50000" step="5000" oninput="calcSideEMI()">
            </div>
            <div class="calc-field">
                <label>Interest Rate (% P.A.)</label>
                <input type="number" id="sideRate" value="8.5" step="0.25" oninput="calcSideEMI()">
            </div>
            <div class="calc-field">
                <label>Tenure (Years)</label>
                <input type="number" id="sideYears" value="5" min="1" max="30" oninput="calcSideEMI()">
            </div>
            <div class="calc-res-card">
                <div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#94A3B8;">Estimated Monthly EMI</div>
                <div class="calc-emi-num" id="sideEmiRes">$1,025</div>
            </div>
            <a href="/emi-calculator" style="display:block; text-align:center; font-size:12px; font-weight:700; color:var(--primary); margin-top:12px;">Open Full Amortization Calculator &rarr;</a>
            <script>
            function calcSideEMI() {{
                var p = parseFloat(document.getElementById('sideLoanAmt').value) || 0;
                var r = parseFloat(document.getElementById('sideRate').value) || 0;
                var y = parseFloat(document.getElementById('sideYears').value) || 0;
                if (p > 0 && r > 0 && y > 0) {{
                    var mr = (r / 12) / 100;
                    var n = y * 12;
                    var emi = (p * mr * Math.pow(1 + mr, n)) / (Math.pow(1 + mr, n) - 1);
                    document.getElementById('sideEmiRes').innerText = '$' + Math.round(emi).toLocaleString();
                }}
            }}
            </script>
        </div>

        <!-- Trending -->
        <div class="widget">
            <h3 class="widget-title">Most Read Stories</h3>
            {trending_html}
        </div>
    </aside>
    """

# 1. BUILD HOMEPAGE
hero_main = articles[0]
hero_sub1 = articles[1]
hero_sub2 = articles[2]
feed_articles = articles[3:]

feed_html = ""
for a in feed_articles:
    feed_html += f"""
    <article class="article-feed-item">
        <div class="feed-thumb">
            <img src="{a['image']}" alt="{html.escape(a['title'])}" loading="lazy">
        </div>
        <div class="feed-content">
            <span class="cat-tag">{a.get('category', 'Finance')}</span>
            <h2 class="feed-title"><a href="/{a['slug']}">{a['title']}</a></h2>
            <p class="feed-excerpt">{a['excerpt']}</p>
            <div class="feed-meta">By LoanRaaj Team • {a.get('words', 1500)} words • 5 min read</div>
        </div>
    </article>
    """

homepage_main = f"""
<div class="container">
    <!-- Hero 3-Grid -->
    <section class="hero-grid" style="margin-top:24px;">
        <div class="hero-card main-hero">
            <img src="{hero_main['image']}" alt="{html.escape(hero_main['title'])}" class="hero-img">
            <div class="hero-overlay">
                <span class="hero-cat">{hero_main.get('category', 'Business')}</span>
                <h1 class="hero-title"><a href="/{hero_main['slug']}">{hero_main['title']}</a></h1>
                <div class="hero-meta">By LoanRaaj Team • {hero_main.get('words', 2000)} words</div>
            </div>
        </div>
        <div style="display:flex; flex-direction:column; gap:16px;">
            <div class="hero-card">
                <img src="{hero_sub1['image']}" alt="{html.escape(hero_sub1['title'])}" class="hero-img">
                <div class="hero-overlay">
                    <span class="hero-cat">{hero_sub1.get('category', 'Insurance')}</span>
                    <h2 class="hero-title" style="font-size:18px;"><a href="/{hero_sub1['slug']}">{hero_sub1['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • Insurance</div>
                </div>
            </div>
            <div class="hero-card">
                <img src="{hero_sub2['image']}" alt="{html.escape(hero_sub2['title'])}" class="hero-img">
                <div class="hero-overlay">
                    <span class="hero-cat">{hero_sub2.get('category', 'Carrier')}</span>
                    <h2 class="hero-title" style="font-size:18px;"><a href="/{hero_sub2['slug']}">{hero_sub2['title']}</a></h2>
                    <div class="hero-meta">By LoanRaaj Team • Carrier & Fleet</div>
                </div>
            </div>
        </div>
    </section>

    <!-- Main Content Layout -->
    <div class="main-layout">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; border-bottom:2px solid var(--dark); padding-bottom:8px;">
                <h2 style="font-family:var(--font-head); font-size:18px; font-weight:800; text-transform:uppercase;">Latest Stories & In-Depth Guides</h2>
                <span style="font-size:12px; color:var(--text-muted); font-weight:600;">{len(articles)} In-Depth Publications</span>
            </div>
            {feed_html}
        </div>
        {get_sidebar_html()}
    </div>
</div>
"""

home_output = render_layout(
    title="LoanRaaj - Business, Finance & Insurance Network",
    desc="Authoritative guides on commercial trucking insurance, owner operator costs, small business machinery, and loan calculations.",
    canonical="https://loanraaj.com",
    main_html=homepage_main,
    active_cat="Home"
)

with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(home_output)
print("Saved homepage index.html")

# 2. BUILD INDIVIDUAL ARTICLES
for a in articles:
    post_slug = a['slug']
    cat = a.get('category', 'Finance')
    
    post_main = f"""
    <div class="container">
        <div class="main-layout">
            <main>
                <article class="post-container">
                    <div class="post-breadcrumb">
                        <a href="/">Home</a> <span>/</span>
                        <a href="/#{cat.lower()}">{cat}</a> <span>/</span>
                        <span style="color:#1E293B;">{a['title'][:40]}...</span>
                    </div>

                    <span class="cat-tag" style="font-size:13px;">{cat}</span>
                    <h1 class="post-h1">{a['title']}</h1>
                    
                    <div class="post-meta-bar">
                        <span>By <strong>LoanRaaj Editorial Board</strong></span> • 
                        <span>Updated November 2026</span> • 
                        <span>{a.get('words', 2000)} Words</span> •
                        <span>5 Min Read</span>
                    </div>

                    <div class="post-featured-img">
                        <img src="{a['image']}" alt="{html.escape(a['title'])}" loading="eager">
                    </div>

                    <div class="ad-slot-inarticle">
                        <span style="font-weight:700; display:block; margin-bottom:4px;">Responsive In-Article Advertisement</span>
                        <span>High-CTR 728x90 Leaderboard / Adaptive Display Unit</span>
                    </div>

                    <div class="post-content">
                        {a['content']}
                    </div>

                    <div class="ad-slot-inarticle">
                        <span style="font-weight:700; display:block; margin-bottom:4px;">Sponsored Financial Recommendation</span>
                        <span>Relevant Insurance & Commercial Finance Opportunities</span>
                    </div>

                    <!-- Author Box -->
                    <div class="author-box">
                        <div class="author-avatar">LR</div>
                        <div>
                            <div style="font-family:var(--font-head); font-weight:800; font-size:16px; color:var(--dark);">LoanRaaj Research Team</div>
                            <div style="font-size:13px; color:var(--text-muted); margin-top:2px;">
                                Experienced commercial finance researchers and freight transportation analysts providing actionable rate comparisons and regulatory guides.
                            </div>
                        </div>
                    </div>
                </article>
            </main>
            {get_sidebar_html()}
        </div>
    </div>
    """
    
    post_output = render_layout(
        title=a['title'],
        desc=a['excerpt'],
        canonical=f"https://loanraaj.com/{post_slug}",
        main_html=post_main,
        active_cat=cat
    )
    
    # Save as slug.html
    with open(os.path.join(BASE_DIR, f"{post_slug}.html"), "w", encoding="utf-8") as f:
        f.write(post_output)
        
    # Also save as slug/index.html for clean URL routing
    slug_dir = os.path.join(BASE_DIR, post_slug)
    os.makedirs(slug_dir, exist_ok=True)
    with open(os.path.join(slug_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(post_output)

print(f"Saved {len(articles)} individual articles (both .html and /dir/index.html).")

# 3. BUILD DEDICATED EMI CALCULATOR PAGE
emi_main = f"""
<div class="container">
    <div class="main-layout">
        <main>
            <div class="post-container">
                <div class="post-breadcrumb">
                    <a href="/">Home</a> <span>/</span> <span>Calculators</span> <span>/</span> <span>Loan EMI Calculator</span>
                </div>
                <h1 class="post-h1">Interactive Loan EMI & Amortization Calculator</h1>
                <p style="color:var(--text-muted); margin-bottom:24px;">Calculate your exact monthly payments, total interest payable, and repayment breakdown in seconds.</p>

                <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:6px; padding:24px; margin-bottom:28px;">
                    <div style="display:grid; grid-template-columns:1fr; gap:18px;">
                        <div>
                            <label style="font-weight:700; font-size:13px;">Loan Amount ($): <span id="fullAmtDisplay" style="color:var(--primary);">$100,000</span></label>
                            <input type="range" id="fullAmtRange" min="5000" max="1000000" step="5000" value="100000" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                        <div>
                            <label style="font-weight:700; font-size:13px;">Annual Interest Rate (%): <span id="fullRateDisplay" style="color:var(--primary);">8.5%</span></label>
                            <input type="range" id="fullRateRange" min="2" max="25" step="0.25" value="8.5" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                        <div>
                            <label style="font-weight:700; font-size:13px;">Tenure: <span id="fullTenureDisplay" style="color:var(--primary);">10 Years</span></label>
                            <input type="range" id="fullTenureRange" min="1" max="30" step="1" value="10" style="width:100%; accent-color:var(--primary);" oninput="updateFullCalc()">
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:16px; margin-top:24px;">
                        <div style="background:#0F172A; color:#FFF; padding:18px; border-radius:6px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:#94A3B8;">Monthly EMI</div>
                            <div id="fullEmiRes" style="font-size:28px; font-weight:800; color:#38BDF8; font-family:var(--font-head);">$1,240</div>
                        </div>
                        <div style="background:#FFF; border:1px solid var(--border); padding:18px; border-radius:6px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted);">Total Interest</div>
                            <div id="fullTotalInterest" style="font-size:24px; font-weight:800; color:var(--dark); font-family:var(--font-head);">$48,789</div>
                        </div>
                        <div style="background:#FFF; border:1px solid var(--border); padding:18px; border-radius:6px; text-align:center;">
                            <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted);">Total Payment</div>
                            <div id="fullTotalPayment" style="font-size:24px; font-weight:800; color:var(--dark); font-family:var(--font-head);">$148,789</div>
                        </div>
                    </div>
                </div>

                <div class="post-content">
                    <h2>How is Loan EMI Calculated?</h2>
                    <p>The Equated Monthly Installment (EMI) is calculated using the standard mathematical formula:</p>
                    <blockquote style="background:#F1F5F9; border-left:4px solid var(--dark); padding:12px 18px; font-family:monospace; font-style:normal;">
                        EMI = [P x R x (1+R)^N] / [(1+R)^N - 1]
                    </blockquote>
                    <p>Where <strong>P</strong> is the principal loan amount, <strong>R</strong> is the monthly interest rate (annual rate divided by 12 and then by 100), and <strong>N</strong> is the total number of monthly payments.</p>
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
        {get_sidebar_html()}
    </div>
</div>
"""

emi_output = render_layout(
    title="Loan EMI Calculator - Monthly Payment & Interest Estimator",
    desc="Free interactive loan EMI calculator to compute monthly installments, interest rates, and loan tenure amortizations.",
    canonical="https://loanraaj.com/emi-calculator",
    main_html=emi_main,
    active_cat="EMI Calculator"
)

with open(os.path.join(BASE_DIR, "emi-calculator.html"), "w", encoding="utf-8") as f:
    f.write(emi_output)
os.makedirs(os.path.join(BASE_DIR, "emi-calculator"), exist_ok=True)
with open(os.path.join(BASE_DIR, "emi-calculator", "index.html"), "w", encoding="utf-8") as f:
    f.write(emi_output)
print("Saved emi-calculator pages.")

# 4. BUILD 5 LEGAL TRUST PAGES
legal_pages = [
    ("privacy-policy", "Privacy Policy", """
    <h2>Introduction</h2>
    <p>Welcome to LoanRaaj ("we", "our", or "us"). We respect your privacy and are committed to protecting any personal data collected when you visit our website.</p>
    <h2>Information We Collect</h2>
    <p>We may collect non-personally identifiable information including browser type, operating system, IP address, and pages viewed to optimize user experience and analyze readership trends.</p>
    <h2>Cookies & Advertising Partners</h2>
    <p>We work with trusted third-party advertising partners including Google AdSense, Adsterra, and affiliate networks. These partners may use cookies and web beacons to serve advertisements based on your prior visits to this and other websites.</p>
    <p>Users may opt out of personalized advertising by visiting Google's Ads Settings or <a href="https://aboutads.info" target="_blank" rel="nofollow">aboutads.info</a>.</p>
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

for slug, p_title, p_content in legal_pages:
    legal_main = f"""
    <div class="container">
        <div class="main-layout">
            <main>
                <div class="post-container">
                    <div class="post-breadcrumb">
                        <a href="/">Home</a> <span>/</span> <span>Legal</span> <span>/</span> <span>{p_title}</span>
                    </div>
                    <h1 class="post-h1">{p_title}</h1>
                    <div class="post-content" style="margin-top:20px;">
                        {p_content}
                    </div>
                </div>
            </main>
            {get_sidebar_html()}
        </div>
    </div>
    """
    
    legal_output = render_layout(
        title=f"{p_title} - Official Policy",
        desc=f"Official {p_title} document for LoanRaaj.com.",
        canonical=f"https://loanraaj.com/{slug}",
        main_html=legal_main,
        active_cat="Trust & Legal"
    )
    
    with open(os.path.join(BASE_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(legal_output)
    os.makedirs(os.path.join(BASE_DIR, slug), exist_ok=True)
    with open(os.path.join(BASE_DIR, slug, "index.html"), "w", encoding="utf-8") as f:
        f.write(legal_output)

print("Saved all 5 legal trust pages.")

# 5. SITEMAP.XML
sitemap_urls = ["https://loanraaj.com/", "https://loanraaj.com/emi-calculator"]
for a in articles:
    sitemap_urls.append(f"https://loanraaj.com/{a['slug']}")
for slug, _, _ in legal_pages:
    sitemap_urls.append(f"https://loanraaj.com/{slug}")

sitemap_xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u in sitemap_urls:
    sitemap_xml.append(f"""  <url>
    <loc>{u}</loc>
    <lastmod>2026-11-10</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{"1.0" if u == "https://loanraaj.com/" else "0.8"}</priority>
  </url>""")
sitemap_xml.append('</urlset>')

with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(sitemap_xml))

# 6. ROBOTS.TXT
robots_txt = """User-agent: *
Allow: /

Sitemap: https://loanraaj.com/sitemap.xml
"""
with open(os.path.join(BASE_DIR, "robots.txt"), "w", encoding="utf-8") as f:
    f.write(robots_txt)

print("Saved sitemap.xml and robots.txt.")
