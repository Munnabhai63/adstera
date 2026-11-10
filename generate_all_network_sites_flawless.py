# generate_all_network_sites_flawless.py - Flawless Multi-Site Network Generator & Validator
import os
import sys
import json
import re
import html
import subprocess
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Import templates
from site_templates import render_master_page, render_sidebar
from legal_templates import (
    get_privacy_policy_content,
    get_terms_content,
    get_disclaimer_content,
    get_about_us_content,
    get_contact_us_content,
    get_calculator_page_content
)

# Import domains
import generate_articles_database
import build_full_articles_catalog
import network_articles_builder_all
import network_articles_part2
import network_articles_part3

MASTER_SITES = {}
MASTER_SITES["rechargetak"] = generate_articles_database.NETWORK_DOMAINS["rechargetak"]
MASTER_SITES["rechargepur"] = build_full_articles_catalog.ALL_NETWORK_DATA["rechargepur"]
MASTER_SITES["tazaloan"] = network_articles_builder_all.MASTER_NETWORK_SITES["tazaloan"]
MASTER_SITES["loankiseva"] = network_articles_part2.PART2_SITES["loankiseva"]
MASTER_SITES["karzseva"] = network_articles_part2.PART2_SITES["karzseva"]
MASTER_SITES["loantau"] = network_articles_part3.PART3_SITES["loantau"]
MASTER_SITES["tazabhav"] = network_articles_part3.PART3_SITES["tazabhav"]
MASTER_SITES["tazarokda"] = network_articles_part3.PART3_SITES["tazarokda"]
MASTER_SITES["rechargekar"] = network_articles_part3.PART3_SITES["rechargekar"]

print("="*70)
print(f"Loaded {len(MASTER_SITES)} sites into Master Network Generator")
print("="*70)

VERIFY_FILENAME = "google31976c4df01121b2.html"
VERIFY_CONTENT = "google-site-verification: google31976c4df01121b2.html\n"

SW_JS_CONTENT = """// Monetag / Service Worker
self.addEventListener('install', function(event) {
  self.skipWaiting();
});
self.addEventListener('activate', function(event) {
  event.waitUntil(self.clients.claim());
});
"""

HILLTOP_ADS_FILENAME = "92a7b03c56fd70822e83.txt"
HILLTOP_ADS_CONTENT = "92a7b03c56fd70822e83\n"

total_files_generated = 0
total_div_errors = 0

def write_and_validate(file_path, html_content):
    global total_files_generated, total_div_errors
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Div check
    o_div = html_content.count("<div")
    c_div = html_content.count("</div>")
    if o_div != c_div:
        print(f"[ERROR DIV MISMATCH] {file_path}: <div={o_div}, </div={c_div}")
        total_div_errors += 1
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    total_files_generated += 1

for site_id, site in MASTER_SITES.items():
    domain = site["domain"]
    name = site["name"]
    tagline = site["tagline"]
    categories = site["categories"]
    
    # Flatten all articles
    all_articles = []
    for cat_name, cat_data in categories.items():
        for art in cat_data["articles"]:
            art["category_slug"] = cat_data["slug"]
            art["category_desc"] = cat_data["desc"]
            all_articles.append(art)
            
    print(f"\nProcessing [{site_id}] {name}: {len(all_articles)} articles across {len(categories)} categories")
    
    # Output directories
    site_dirs = [os.path.join("sites", site_id), os.path.join("sites", f"{site_id}.com")]
    
    for site_dir in site_dirs:
        os.makedirs(site_dir, exist_ok=True)
        
        # 1. Preserved verification & ad tokens
        with open(os.path.join(site_dir, VERIFY_FILENAME), "w", encoding="utf-8") as f:
            f.write(VERIFY_CONTENT)
        with open(os.path.join(site_dir, HILLTOP_ADS_FILENAME), "w", encoding="utf-8") as f:
            f.write(HILLTOP_ADS_CONTENT)
        with open(os.path.join(site_dir, "sw.js"), "w", encoding="utf-8") as f:
            f.write(SW_JS_CONTENT)
            
        # 2. Robots.txt
        robots_txt = f"""User-agent: *
Allow: /
Disallow: /sw.js

Sitemap: {domain}/sitemap.xml
"""
        with open(os.path.join(site_dir, "robots.txt"), "w", encoding="utf-8") as f:
            f.write(robots_txt)

        # Common sidebar
        sidebar_html = render_sidebar(site, all_articles)
        
        # 3. Generate HOME page (index.html)
        hero1 = all_articles[0]
        hero2 = all_articles[1]
        hero3 = all_articles[2]
        feed_articles = all_articles[3:]
        
        hero_html = f"""
        <div class="hero-grid">
            <div class="hero-card main-hero">
                <img src="{hero1['image']}" alt="{html.escape(hero1['title'])}" loading="eager">
                <div class="hero-overlay">
                    <span class="hero-badge">{hero1['category']}</span>
                    <a href="/{hero1['slug']}" class="hero-h1">{hero1['title']}</a>
                    <div class="hero-meta">{hero1.get('words', 1800)} words · 8 min read · Comprehensive Guide</div>
                </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:18px;">
                <div class="hero-card">
                    <img src="{hero2['image']}" alt="{html.escape(hero2['title'])}" loading="lazy">
                    <div class="hero-overlay">
                        <span class="hero-badge">{hero2['category']}</span>
                        <a href="/{hero2['slug']}" class="hero-h1">{hero2['title']}</a>
                        <div class="hero-meta">{hero2.get('words', 1700)} words · Industry Analysis</div>
                    </div>
                </div>
                <div class="hero-card">
                    <img src="{hero3['image']}" alt="{html.escape(hero3['title'])}" loading="lazy">
                    <div class="hero-overlay">
                        <span class="hero-badge">{hero3['category']}</span>
                        <a href="/{hero3['slug']}" class="hero-h1">{hero3['title']}</a>
                        <div class="hero-meta">{hero3.get('words', 1650)} words · Verified Rates</div>
                    </div>
                </div>
            </div>
        </div>
        """
        
        feed_html = ""
        for i, a in enumerate(feed_articles):
            feed_html += f"""
            <article class="feed-card">
                <div class="feed-thumb">
                    <img src="{a['image']}" alt="{html.escape(a['title'])}" loading="lazy">
                </div>
                <div class="feed-info">
                    <div class="feed-cat">{a['category']}</div>
                    <a href="/{a['slug']}" class="feed-title">{a['title']}</a>
                    <p class="feed-desc">{a['excerpt']}</p>
                    <div class="feed-meta">{a.get('words', 1600)} words · Detailed Sector Benchmark</div>
                </div>
            </article>
            """
            if i == 3:
                feed_html += """
                <div class="ad-slot-box">
                    <div class="ad-slot-label">Sponsored Recommendation</div>
                    <div class="ad-slot-spec">Responsive In-Feed Native Display Unit</div>
                </div>
                """
                
        home_body = f"""
        <main class="container">
            {hero_html}
            <div class="main-layout">
                <section>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:2px solid var(--border); padding-bottom:10px;">
                        <h2 style="font-size:20px; font-weight:900; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-head);">Latest Intelligence & Guides</h2>
                        <span style="font-size:12px; color:var(--text-muted); font-weight:700;">{len(all_articles)} In-Depth Publications</span>
                    </div>
                    {feed_html}
                </section>
                {sidebar_html}
            </div>
        </main>
        """
        
        home_full = render_master_page(
            site,
            title=f"{name} - {tagline}",
            desc=site["desc"],
            canonical=domain,
            main_body=home_body,
            active_nav="Home",
            ticker_title=hero1["title"],
            ticker_url=f"/{hero1['slug']}"
        )
        write_and_validate(os.path.join(site_dir, "index.html"), home_full)
        
        # 4. Generate all 16 ARTICLE pages
        for a in all_articles:
            art_body = f"""
            <main class="container">
                <div class="main-layout">
                    <article>
                        <div class="post-paper">
                            <div class="post-crumb">
                                <a href="/">Home</a> <span>›</span>
                                <a href="/category/{a['category_slug']}">{a['category']}</a> <span>›</span>
                                <span>{a['title']}</span>
                            </div>
                            <span class="cat-badge">{a['category']}</span>
                            <h1 class="post-h1">{a['title']}</h1>
                            <div class="post-meta">
                                <span>Published: November 2026</span>
                                <span>{a.get('words', 1700)} Words</span>
                                <span>8 Min Read</span>
                                <span>Verified by {name} Desk</span>
                            </div>
                            <div class="post-feature-wrap">
                                <img src="{a['image']}" alt="{html.escape(a['title'])}" loading="eager">
                            </div>
                            <div class="post-content">
                                {a['content']}
                            </div>
                            <div class="ad-slot-box">
                                <div class="ad-slot-label">Sponsored Resource</div>
                                <div class="ad-slot-spec">Mid-Article Responsive Ad Space (300x250 / 728x90)</div>
                            </div>
                            <div class="author-card">
                                <div class="author-avatar">{name[:2]}</div>
                                <div>
                                    <h3 style="font-size:16px; font-weight:800; color:var(--text-head); margin-bottom:4px;">{name} Senior Research Team</h3>
                                    <p style="font-size:13px; color:var(--text-muted); line-height:1.5;">
                                        Our editorial team conducts primary research, benchmarks statutory guidelines, and cross-references regulatory mandates to deliver verified, transparent consumer guidance.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </article>
                    {sidebar_html}
                </div>
            </main>
            """
            
            art_full = render_master_page(
                site,
                title=a["title"],
                desc=a["excerpt"],
                canonical=f"{domain}/{a['slug']}",
                main_body=art_body,
                active_nav=a["category"],
                ticker_title=a["title"],
                ticker_url=f"/{a['slug']}"
            )
            # Write both root slug.html and clean directory slug/index.html
            write_and_validate(os.path.join(site_dir, f"{a['slug']}.html"), art_full)
            write_and_validate(os.path.join(site_dir, a["slug"], "index.html"), art_full)

        # 5. Generate all 4 CATEGORY pages
        for cat_name, cat_data in categories.items():
            cat_slug = cat_data["slug"]
            cat_arts = [x for x in all_articles if x["category"] == cat_name]
            
            cat_cards_html = ""
            for ca in cat_arts:
                cat_cards_html += f"""
                <article class="feed-card">
                    <div class="feed-thumb">
                        <img src="{ca['image']}" alt="{html.escape(ca['title'])}" loading="lazy">
                    </div>
                    <div class="feed-info">
                        <div class="feed-cat">{ca['category']}</div>
                        <a href="/{ca['slug']}" class="feed-title">{ca['title']}</a>
                        <p class="feed-desc">{ca['excerpt']}</p>
                        <div class="feed-meta">{ca.get('words', 1600)} words · Industry Analysis</div>
                    </div>
                </article>
                """
                
            cat_body = f"""
            <main class="container">
                <div class="cat-header-card">
                    <div class="cat-header-title">{cat_data.get('icon', '📌')} {cat_name}</div>
                    <div class="cat-header-desc">{cat_data['desc']}</div>
                    <div style="font-size:12px; font-weight:700; color:var(--primary); margin-top:10px; text-transform:uppercase;">
                        {len(cat_arts)} Curated Guides in this Sector
                    </div>
                </div>
                <div class="main-layout">
                    <section>
                        {cat_cards_html}
                    </section>
                    {sidebar_html}
                </div>
            </main>
            """
            
            cat_full = render_master_page(
                site,
                title=f"{cat_name} Guides & Intelligence",
                desc=cat_data["desc"],
                canonical=f"{domain}/category/{cat_slug}",
                main_body=cat_body,
                active_nav=cat_name
            )
            # Write both category/slug.html and category/slug/index.html
            os.makedirs(os.path.join(site_dir, "category", cat_slug), exist_ok=True)
            write_and_validate(os.path.join(site_dir, "category", f"{cat_slug}.html"), cat_full)
            write_and_validate(os.path.join(site_dir, "category", cat_slug, "index.html"), cat_full)

        # 6. Generate 5 LEGAL Trust Pages
        legal_pages = [
            ("privacy-policy", "Privacy Policy & Data Protection", get_privacy_policy_content(site)),
            ("terms-and-conditions", "Terms of Service Agreement", get_terms_content(site)),
            ("disclaimer", "Editorial Disclaimer & Disclosures", get_disclaimer_content(site)),
            ("about-us", f"About {name} Research Team", get_about_us_content(site)),
            ("contact-us", f"Contact {name} Editorial Desk", get_contact_us_content(site)),
            ("calculator", f"{site['calc_title']} - {name}", get_calculator_page_content(site))
        ]
        
        for slug, page_title, page_content in legal_pages:
            legal_body = f"""
            <main class="container">
                <div class="main-layout">
                    <section>
                        {page_content}
                    </section>
                    {sidebar_html}
                </div>
            </main>
            """
            legal_full = render_master_page(
                site,
                title=page_title,
                desc=f"{page_title} - Official compliance and governance documentation for {name}.",
                canonical=f"{domain}/{slug}",
                main_body=legal_body,
                active_nav="Home" if slug != "calculator" else "Calculator"
            )
            write_and_validate(os.path.join(site_dir, f"{slug}.html"), legal_full)
            write_and_validate(os.path.join(site_dir, slug, "index.html"), legal_full)

        # 7. Generate clean SITEMAP.xml
        sitemap_urls = [
            f"<url><loc>{domain}</loc><priority>1.0</priority><changefreq>daily</changefreq></url>",
            f"<url><loc>{domain}/calculator</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>"
        ]
        for cat_data in categories.values():
            sitemap_urls.append(f"<url><loc>{domain}/category/{cat_data['slug']}</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>")
        for a in all_articles:
            sitemap_urls.append(f"<url><loc>{domain}/{a['slug']}</loc><priority>0.9</priority><changefreq>weekly</changefreq></url>")
        for slug, _, _ in legal_pages[:5]:
            sitemap_urls.append(f"<url><loc>{domain}/{slug}</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>")
            
        sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    {"".join(sitemap_urls)}
</urlset>
"""
        with open(os.path.join(site_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
            f.write(sitemap_xml)
        total_files_generated += 1

print("\n" + "="*70)
print(f"GENERATION COMPLETE!")
print(f"Total HTML & XML files generated across all sites: {total_files_generated}")
print(f"Total Div Mismatch Errors: {total_div_errors}")
print("="*70)
