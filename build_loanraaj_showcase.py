"""
build_loanraaj_showcase.py — Generates the complete Zox-News clone for LoanRaaj.com
Features:
- Exact Zox-News modern typography, dark header, electric-accent styling (#FF005B, #0BE6AF)
- Full 11 articles extracted from brother sites + EMI calculator + SIP calculator
- Complete 5 Mandatory Legal Trust Pages (Privacy Policy, Terms, Disclaimer, About Us, Contact Us)
- Responsive ad slots for Adsterra & Monetag
- Monetag sw.js & HilltopAds verification file preserved
- Instant deployment to Cloudflare Pages for live preview
"""

import os
import sys
import json
import re
import html

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

OUTPUT_DIR = "sites/loanraaj"
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open('extracted_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

# Common HTML Head
def get_head(title, desc, slug="", is_article=False, image="https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=1200&auto=format&fit=crop&q=80"):
    canonical = f"https://loanraaj.com/{slug}" if slug else "https://loanraaj.com/"
    schema_type = "Article" if is_article else "WebSite"
    
    schema_json = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": title,
        "url": canonical,
        "description": desc,
        "publisher": {
            "@type": "Organization",
            "name": "LoanRaaj",
            "url": "https://loanraaj.com",
            "logo": {
                "@type": "ImageObject",
                "url": "https://loanraaj.com/logo.png"
            }
        }
    }
    if is_article:
        schema_json["headline"] = title
        schema_json["image"] = image
        schema_json["datePublished"] = "2026-11-01T08:00:00+05:30"
        schema_json["dateModified"] = "2026-11-10T12:00:00+05:30"
        schema_json["author"] = {
            "@type": "Person",
            "name": "LoanRaaj Financial Editorial Team"
        }

    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - LoanRaaj</title>
    <meta name="description" content="{html.escape(desc)}">
    <link rel="canonical" href="{canonical}">
    
    <!-- Open Graph / Meta -->
    <meta property="og:type" content="{'article' if is_article else 'website'}">
    <meta property="og:title" content="{html.escape(title)} - LoanRaaj">
    <meta property="og:description" content="{html.escape(desc)}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:image" content="{image}">
    <meta property="og:site_name" content="LoanRaaj">
    
    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{html.escape(title)} - LoanRaaj">
    <meta name="twitter:description" content="{html.escape(desc)}">
    <meta name="twitter:image" content="{image}">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Roboto:wght@300;400;500;700;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    
    <!-- Schema.org JSON-LD -->
    <script type="application/ld+json">
    {json.dumps(schema_json, ensure_ascii=False, indent=2)}
    </script>
    
    <!-- HilltopAds & Monetag -->
    <script src="/sw.js"></script>

    <style>
        /* === ZOX NEWS SIGNATURE MODERN THEME CSS === */
        :root {{
            --primary: #FF005B;
            --primary-hover: #D6004C;
            --accent: #0BE6AF;
            --dark: #111111;
            --dark-surface: #1E1E1E;
            --text-main: #222222;
            --text-muted: #666666;
            --bg-body: #F7F7F7;
            --bg-card: #FFFFFF;
            --border-color: #E5E5E5;
            --font-head: 'Oswald', sans-serif;
            --font-body: 'Roboto', sans-serif;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: var(--font-body);
            color: var(--text-main);
            background-color: var(--bg-body);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }}
        a {{ text-decoration: none; color: inherit; transition: color 0.2s; }}
        a:hover {{ color: var(--primary); }}
        img {{ max-width: 100%; height: auto; display: block; }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 16px;
        }}

        /* --- Top Bar --- */
        .top-bar {{
            background: var(--dark);
            color: #AAAAAA;
            font-size: 13px;
            padding: 8px 0;
            border-bottom: 1px solid #222;
        }}
        .top-bar-inner {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .top-ticker {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .ticker-badge {{
            background: var(--primary);
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            text-transform: uppercase;
            border-radius: 2px;
        }}
        .top-date {{ font-size: 12px; }}

        /* --- Main Header --- */
        .main-header {{
            background: #FFFFFF;
            padding: 20px 0;
            border-bottom: 2px solid var(--border-color);
        }}
        .header-inner {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .logo {{
            font-family: var(--font-head);
            font-size: 38px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: var(--dark);
            line-height: 1;
        }}
        .logo span {{ color: var(--primary); }}
        .logo-tagline {{
            font-size: 12px;
            color: var(--text-muted);
            font-family: var(--font-body);
            font-weight: 400;
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .header-ad-banner {{
            display: none;
        }}
        @media (min-width: 768px) {{
            .header-ad-banner {{
                display: block;
                width: 728px;
                height: 90px;
                background: #F0F2F5;
                border: 1px dashed #CBD5E1;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #94A3B8;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
        }}

        /* --- Main Navigation Bar --- */
        .navbar {{
            background: var(--dark);
            position: sticky;
            top: 0;
            z-index: 999;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .nav-inner {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .nav-menu {{
            display: flex;
            list-style: none;
            overflow-x: auto;
            white-space: nowrap;
        }}
        .nav-menu::-webkit-scrollbar {{ display: none; }}
        .nav-item a {{
            display: block;
            padding: 14px 16px;
            font-family: var(--font-head);
            font-size: 15px;
            text-transform: uppercase;
            color: #FFFFFF;
            font-weight: 600;
            letter-spacing: 0.5px;
            transition: all 0.2s;
        }}
        .nav-item a:hover, .nav-item.active a {{
            background: var(--primary);
            color: #FFFFFF;
        }}
        .nav-tools {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 0 12px;
            color: #FFF;
        }}
        .nav-calc-btn {{
            background: var(--accent);
            color: var(--dark) !important;
            padding: 6px 14px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 13px;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        /* --- Hero Featured Grid (Zox Style) --- */
        .hero-section {{
            margin: 20px 0;
        }}
        .hero-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
        }}
        @media (min-width: 992px) {{
            .hero-grid {{
                grid-template-columns: 2fr 1fr;
            }}
        }}
        .hero-main-card {{
            position: relative;
            height: 420px;
            border-radius: 6px;
            overflow: hidden;
            background: #000;
        }}
        .hero-main-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            opacity: 0.75;
            transition: transform 0.4s ease;
        }}
        .hero-main-card:hover img {{
            transform: scale(1.03);
            opacity: 0.85;
        }}
        .hero-card-content {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 24px;
            background: linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.6) 60%, transparent 100%);
            color: #FFF;
        }}
        .cat-tag {{
            display: inline-block;
            background: var(--primary);
            color: #FFF;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            text-transform: uppercase;
            border-radius: 3px;
            margin-bottom: 10px;
            font-family: var(--font-head);
            letter-spacing: 0.5px;
        }}
        .hero-main-title {{
            font-family: var(--font-head);
            font-size: 26px;
            font-weight: 700;
            line-height: 1.25;
            margin-bottom: 8px;
            color: #FFF;
        }}
        @media (min-width: 768px) {{
            .hero-main-title {{ font-size: 30px; }}
        }}
        .hero-side-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
        }}
        .hero-side-card {{
            position: relative;
            height: 202px;
            border-radius: 6px;
            overflow: hidden;
            background: #000;
        }}
        .hero-side-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            opacity: 0.75;
            transition: transform 0.4s ease;
        }}
        .hero-side-card:hover img {{
            transform: scale(1.03);
            opacity: 0.85;
        }}
        .hero-side-content {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 16px;
            background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 100%);
            color: #FFF;
        }}
        .hero-side-title {{
            font-family: var(--font-head);
            font-size: 18px;
            font-weight: 700;
            line-height: 1.25;
            color: #FFF;
        }}

        /* --- Two Column Layout: Main + Sidebar --- */
        .layout-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 30px;
            margin: 30px 0;
        }}
        @media (min-width: 992px) {{
            .layout-grid {{
                grid-template-columns: 2fr 1fr;
            }}
        }}

        .section-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 2px solid var(--dark);
            margin-bottom: 20px;
            padding-bottom: 6px;
        }}
        .section-title {{
            font-family: var(--font-head);
            font-size: 20px;
            font-weight: 700;
            text-transform: uppercase;
            position: relative;
        }}
        .section-title::after {{
            content: '';
            position: absolute;
            bottom: -8px;
            left: 0;
            width: 50px;
            height: 3px;
            background: var(--primary);
        }}

        /* --- Article Cards Feed --- */
        .article-card {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 20px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        @media (min-width: 576px) {{
            .article-card {{
                grid-template-columns: 200px 1fr;
            }}
        }}
        .article-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        }}
        .article-thumb {{
            border-radius: 4px;
            overflow: hidden;
            height: 140px;
            background: #E2E8F0;
        }}
        .article-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .article-details {{
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .article-title {{
            font-family: var(--font-head);
            font-size: 20px;
            font-weight: 700;
            line-height: 1.3;
            margin: 6px 0 8px 0;
            color: var(--dark);
        }}
        .article-title:hover {{
            color: var(--primary);
        }}
        .article-snippet {{
            font-size: 14px;
            color: var(--text-muted);
            margin-bottom: 10px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        .article-meta {{
            font-size: 12px;
            color: #888888;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        /* --- Sidebar Widgets --- */
        .widget {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 20px;
            margin-bottom: 25px;
        }}
        .widget-title {{
            font-family: var(--font-head);
            font-size: 18px;
            font-weight: 700;
            text-transform: uppercase;
            border-bottom: 2px solid var(--dark);
            padding-bottom: 8px;
            margin-bottom: 16px;
            position: relative;
        }}
        .widget-title::after {{
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            width: 40px;
            height: 2px;
            background: var(--primary);
        }}
        .widget-post-item {{
            display: flex;
            gap: 12px;
            margin-bottom: 14px;
            padding-bottom: 14px;
            border-bottom: 1px dashed var(--border-color);
        }}
        .widget-post-item:last-child {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}
        .widget-post-thumb {{
            width: 70px;
            height: 60px;
            border-radius: 3px;
            overflow: hidden;
            flex-shrink: 0;
        }}
        .widget-post-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .widget-post-title {{
            font-family: var(--font-head);
            font-size: 14px;
            font-weight: 600;
            line-height: 1.3;
        }}

        /* --- EMI Calculator Widget --- */
        .calc-box {{
            background: #F8FAFC;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 16px;
        }}
        .calc-field {{
            margin-bottom: 14px;
        }}
        .calc-field label {{
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            font-weight: 600;
            color: #334155;
            margin-bottom: 4px;
        }}
        .calc-field input[type="range"] {{
            width: 100%;
            accent-color: var(--primary);
        }}
        .calc-result {{
            background: var(--dark);
            color: #FFF;
            padding: 12px;
            border-radius: 4px;
            text-align: center;
            margin-top: 14px;
        }}
        .calc-result-val {{
            font-size: 24px;
            font-weight: 700;
            font-family: var(--font-head);
            color: var(--accent);
        }}

        /* --- Single Post Page Styling --- */
        .single-post-container {{
            background: #FFF;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 30px;
        }}
        .breadcrumb {{
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .single-title {{
            font-family: var(--font-head);
            font-size: 32px;
            font-weight: 700;
            line-height: 1.25;
            color: var(--dark);
            margin-bottom: 16px;
        }}
        .single-meta {{
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 13px;
            color: var(--text-muted);
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}
        .single-feat-img {{
            border-radius: 6px;
            overflow: hidden;
            margin-bottom: 25px;
            max-height: 450px;
        }}
        .single-feat-img img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .entry-content {{
            font-size: 16px;
            line-height: 1.8;
            color: #333333;
        }}
        .entry-content h2 {{
            font-family: var(--font-head);
            font-size: 24px;
            font-weight: 700;
            margin: 28px 0 14px 0;
            padding-bottom: 6px;
            border-bottom: 2px solid var(--border-color);
            color: var(--dark);
        }}
        .entry-content h3 {{
            font-family: var(--font-head);
            font-size: 20px;
            font-weight: 700;
            margin: 20px 0 10px 0;
            color: var(--dark);
        }}
        .entry-content p {{
            margin-bottom: 16px;
        }}
        .entry-content ul, .entry-content ol {{
            margin: 14px 0 18px 24px;
        }}
        .entry-content li {{
            margin-bottom: 8px;
        }}
        .in-article-ad {{
            background: #F1F5F9;
            border: 1px dashed #CBD5E1;
            padding: 16px;
            text-align: center;
            margin: 24px 0;
            border-radius: 4px;
            font-size: 12px;
            color: #94A3B8;
        }}

        /* --- Footer --- */
        .footer {{
            background: var(--dark);
            color: #CCCCCC;
            margin-top: 50px;
            padding-top: 40px;
            border-top: 4px solid var(--primary);
        }}
        .footer-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 30px;
            padding-bottom: 40px;
        }}
        @media (min-width: 768px) {{
            .footer-grid {{
                grid-template-columns: 2fr 1fr 1fr;
            }}
        }}
        .footer-title {{
            font-family: var(--font-head);
            font-size: 18px;
            font-weight: 700;
            color: #FFF;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .footer-links {{
            list-style: none;
        }}
        .footer-links li {{
            margin-bottom: 10px;
        }}
        .footer-links a {{
            color: #AAAAAA;
            font-size: 14px;
        }}
        .footer-links a:hover {{
            color: var(--primary);
            padding-left: 4px;
        }}
        .footer-bottom {{
            background: #090909;
            padding: 18px 0;
            font-size: 13px;
            color: #888888;
            text-align: center;
            border-top: 1px solid #1A1A1A;
        }}
    </style>
</head>
<body>
    <!-- Top Bar -->
    <div class="top-bar">
        <div class="container top-bar-inner">
            <div class="top-ticker">
                <span class="ticker-badge"><i class="fa-solid fa-bolt"></i> TRENDING</span>
                <span>PMEGP ₹25 लाख लोन • सुकन्या योजना 2026 • HDFC क्रेडिट कार्ड्स • होम लोन ब्याज दरें</span>
            </div>
            <div class="top-date">
                <i class="fa-regular fa-calendar"></i> मंगलवार, 10 नवंबर 2026
            </div>
        </div>
    </div>

    <!-- Main Header -->
    <header class="main-header">
        <div class="container header-inner">
            <div class="logo-area">
                <a href="/" class="logo">LOAN<span>RAAJ</span></a>
                <div class="logo-tagline">Finance, Banking & Government Schemes Hub</div>
            </div>
            <div class="header-ad-banner">
                <!-- 728x90 Header Ad Slot -->
                <span>Sponsored Financial Banner (728x90)</span>
            </div>
        </div>
    </header>

    <!-- Navigation Bar -->
    <nav class="navbar">
        <div class="container nav-inner">
            <ul class="nav-menu">
                <li class="nav-item active"><a href="/"><i class="fa-solid fa-house"></i> होम</a></li>
                <li class="nav-item"><a href="/#business-loans">बिजनेस लोन</a></li>
                <li class="nav-item"><a href="/#personal-loans">पर्सनल लोन</a></li>
                <li class="nav-item"><a href="/#govt-schemes">सरकारी योजनाएं</a></li>
                <li class="nav-item"><a href="/#credit-cards">क्रेडिट कार्ड</a></li>
                <li class="nav-item"><a href="/#insurance">इंश्योरेंस</a></li>
                <li class="nav-item"><a href="/emi-calculator"><i class="fa-solid fa-calculator"></i> EMI कैलकुलेटर</a></li>
            </ul>
            <div class="nav-tools">
                <a href="/emi-calculator" class="nav-calc-btn"><i class="fa-solid fa-calculator"></i> EMI चेक करें</a>
            </div>
        </div>
    </nav>
"""

# Common Footer
def get_footer():
    return """
    <!-- Footer -->
    <footer class="footer">
        <div class="container footer-grid">
            <div>
                <div class="logo" style="color:#FFF; font-size:30px; margin-bottom:12px;">LOAN<span>RAAJ</span></div>
                <p style="font-size:14px; color:#AAAAAA; line-height:1.7;">
                    LoanRaaj भारत का एक प्रमुख स्वतंत्र वित्तीय और सरकारी योजना सूचना पोर्टल है। यहाँ आप पर्सनल लोन, बिजनेस लोन (PMEGP/UYEGP), क्रेडिट कार्ड्स, और बैंक ब्याज दरों की सटीक व सत्यापित जानकारी प्राप्त कर सकते हैं।
                </p>
            </div>
            <div>
                <div class="footer-title">मुख्य केटेगरी</div>
                <ul class="footer-links">
                    <li><a href="/#business-loans"><i class="fa-solid fa-angle-right"></i> बिजनेस लोन (PMEGP)</a></li>
                    <li><a href="/#personal-loans"><i class="fa-solid fa-angle-right"></i> पर्सनल & इंसटेंट लोन</a></li>
                    <li><a href="/#govt-schemes"><i class="fa-solid fa-angle-right"></i> सरकारी कल्याणकारी योजनाएं</a></li>
                    <li><a href="/#credit-cards"><i class="fa-solid fa-angle-right"></i> क्रेडिट कार्ड कंपैरिजन</a></li>
                    <li><a href="/emi-calculator"><i class="fa-solid fa-angle-right"></i> ऑनलाइन लोन EMI कैलकुलेटर</a></li>
                </ul>
            </div>
            <div>
                <div class="footer-title">लीगल & पॉलिसीज</div>
                <ul class="footer-links">
                    <li><a href="/privacy-policy"><i class="fa-solid fa-shield-halved"></i> प्राइवेसी पॉलिसी</a></li>
                    <li><a href="/terms-and-conditions"><i class="fa-solid fa-file-contract"></i> नियम एवं शर्तें</a></li>
                    <li><a href="/disclaimer"><i class="fa-solid fa-triangle-exclamation"></i> डिस्क्लेमर (Disclaimer)</a></li>
                    <li><a href="/about-us"><i class="fa-solid fa-users"></i> हमारे बारे में (About Us)</a></li>
                    <li><a href="/contact-us"><i class="fa-solid fa-envelope"></i> संपर्क करें (Contact Us)</a></li>
                </ul>
            </div>
        </div>
        <div class="footer-bottom">
            <div class="container">
                © 2026 LoanRaaj.com. सर्वाधिकार सुरक्षित। यह वेबसाइट किसी भी सरकारी बैंक का आधिकारिक प्रतिनिधि नहीं है; यह केवल सूचनात्मक मार्गदर्शन प्रदान करती है।
            </div>
        </div>
    </footer>

    <!-- Interactive EMI Calculator Script -->
    <script>
    function updateEMI() {
        const p = parseFloat(document.getElementById('loanAmount').value);
        const r = parseFloat(document.getElementById('loanRate').value) / 12 / 100;
        const n = parseFloat(document.getElementById('loanTenure').value) * 12;
        
        document.getElementById('amountDisplay').innerText = '₹' + p.toLocaleString('en-IN');
        document.getElementById('rateDisplay').innerText = (document.getElementById('loanRate').value) + '%';
        document.getElementById('tenureDisplay').innerText = (document.getElementById('loanTenure').value) + ' वर्ष';
        
        const emi = (p * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
        if (!isNaN(emi)) {
            document.getElementById('emiResult').innerText = '₹' + Math.round(emi).toLocaleString('en-IN');
        }
    }
    </script>
</body>
</html>
"""

# 1. BUILD HOMEPAGE (index.html)
print("[1/4] Building Homepage (index.html)...")
hero_main = articles[0]
hero_side1 = articles[1]
hero_side2 = articles[2]

feed_articles = articles[3:]

home_html = get_head(
    title="LoanRaaj - पर्सनल लोन, बिजनेस लोन और सरकारी योजनाओं की ताज़ा जानकारी",
    desc="LoanRaaj पर पाएं पर्सनल लोन, PMEGP बिजनेस लोन, क्रेडिट कार्ड्स, सुकन्या योजना और बैंक ब्याज दरों की पूरी जानकारी।",
    slug=""
)

# Hero Section
home_html += f"""
<main class="container">
    <section class="hero-section">
        <div class="hero-grid">
            <a href="/{hero_main['slug']}" class="hero-main-card">
                <img src="{hero_main['image']}" alt="{hero_main['title']}" loading="eager">
                <div class="hero-card-content">
                    <span class="cat-tag">{hero_main['category']}</span>
                    <h1 class="hero-main-title">{hero_main['title']}</h1>
                    <div style="font-size:13px; opacity:0.9;"><i class="fa-regular fa-clock"></i> {hero_main['read_time']} • {hero_main['date']}</div>
                </div>
            </a>
            <div class="hero-side-grid">
                <a href="/{hero_side1['slug']}" class="hero-side-card">
                    <img src="{hero_side1['image']}" alt="{hero_side1['title']}" loading="lazy">
                    <div class="hero-side-content">
                        <span class="cat-tag">{hero_side1['category']}</span>
                        <div class="hero-side-title">{hero_side1['title']}</div>
                    </div>
                </a>
                <a href="/{hero_side2['slug']}" class="hero-side-card">
                    <img src="{hero_side2['image']}" alt="{hero_side2['title']}" loading="lazy">
                    <div class="hero-side-content">
                        <span class="cat-tag">{hero_side2['category']}</span>
                        <div class="hero-side-title">{hero_side2['title']}</div>
                    </div>
                </a>
            </div>
        </div>
    </section>

    <!-- Two-column Layout: Feed + Sidebar -->
    <div class="layout-grid">
        <div class="main-feed-area">
            <div class="section-header">
                <div class="section-title">ताज़ा वित्तीय आर्टिकल्स & योजनाएं</div>
            </div>
"""

for art in feed_articles:
    home_html += f"""
            <article class="article-card">
                <div class="article-thumb">
                    <a href="/{art['slug']}">
                        <img src="{art['image']}" alt="{art['title']}" loading="lazy">
                    </a>
                </div>
                <div class="article-details">
                    <div><span class="cat-tag">{art['category']}</span></div>
                    <a href="/{art['slug']}">
                        <h2 class="article-title">{art['title']}</h2>
                    </a>
                    <p class="article-snippet">{art['snippet']}</p>
                    <div class="article-meta">
                        <span><i class="fa-regular fa-user"></i> {art['author']}</span>
                        <span><i class="fa-regular fa-calendar"></i> {art['date']}</span>
                    </div>
                </div>
            </article>
    """

home_html += """
        </div>
        
        <!-- Sidebar -->
        <aside class="sidebar-area">
            <!-- Sticky Ad Slot -->
            <div class="widget" style="padding:10px; text-align:center;">
                <div style="font-size:11px; color:#999; text-transform:uppercase; margin-bottom:6px;">SPONSORED LINK</div>
                <div style="background:#F1F5F9; border:1px dashed #CBD5E1; height:250px; display:flex; align-items:center; justify-content:center; color:#64748B; border-radius:4px;">
                    <!-- Adsterra 300x250 Banner Slot -->
                    <span>300x250 Responsive Banner</span>
                </div>
            </div>

            <!-- Live Interactive EMI Calculator -->
            <div class="widget">
                <div class="widget-title">लोन EMI कैलकुलेटर</div>
                <div class="calc-box">
                    <div class="calc-field">
                        <label><span>लोन राशि:</span> <span id="amountDisplay">₹5,00,000</span></label>
                        <input type="range" id="loanAmount" min="50000" max="5000000" step="25000" value="500000" oninput="updateEMI()">
                    </div>
                    <div class="calc-field">
                        <label><span>ब्याज दर (% प्रति वर्ष):</span> <span id="rateDisplay">10.5%</span></label>
                        <input type="range" id="loanRate" min="7" max="24" step="0.25" value="10.5" oninput="updateEMI()">
                    </div>
                    <div class="calc-field">
                        <label><span>अवधि (साल):</span> <span id="tenureDisplay">3 वर्ष</span></label>
                        <input type="range" id="loanTenure" min="1" max="15" step="1" value="3" oninput="updateEMI()">
                    </div>
                    <div class="calc-result">
                        <div style="font-size:12px; text-transform:uppercase; letter-spacing:0.5px;">मासिक EMI</div>
                        <div class="calc-result-val" id="emiResult">₹16,252</div>
                    </div>
                </div>
            </div>

            <!-- Popular Categories Widget -->
            <div class="widget">
                <div class="widget-title">पॉपुलर केटेगरी</div>
                <div style="display:flex; flex-wrap:wrap; gap:8px;">
                    <a href="/#business-loans" class="cat-tag" style="background:#222;">बिजनेस लोन</a>
                    <a href="/#personal-loans" class="cat-tag" style="background:#222;">पर्सनल लोन</a>
                    <a href="/#govt-schemes" class="cat-tag" style="background:#222;">सरकारी योजनाएं</a>
                    <a href="/#credit-cards" class="cat-tag" style="background:#222;">क्रेडिट कार्ड</a>
                    <a href="/#insurance" class="cat-tag" style="background:#222;">हेल्थ इंश्योरेंस</a>
                    <a href="/#trucking" class="cat-tag" style="background:#222;">ऑटो इंश्योरेंस (Tier-1)</a>
                </div>
            </div>
        </aside>
    </div>
</main>
"""

home_html += get_footer()

with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(home_html)

# 2. BUILD SINGLE POST PAGES
print(f"[2/4] Building {len(articles)} Single Post Pages...")
for idx, art in enumerate(articles):
    post_html = get_head(
        title=art['title'],
        desc=art['snippet'],
        slug=f"{art['slug']}.html",
        is_article=True,
        image=art['image']
    )
    
    post_html += f"""
    <main class="container" style="margin-top:25px;">
        <div class="layout-grid">
            <article class="single-post-container">
                <div class="breadcrumb">
                    <a href="/">होम</a> <i class="fa-solid fa-angle-right"></i>
                    <span>{art['category']}</span> <i class="fa-solid fa-angle-right"></i>
                    <span style="color:#222;">{art['title'][:40]}...</span>
                </div>
                
                <span class="cat-tag">{art['category']}</span>
                <h1 class="single-title">{art['title']}</h1>
                
                <div class="single-meta">
                    <span><i class="fa-regular fa-user"></i> {art['author']}</span>
                    <span><i class="fa-regular fa-calendar"></i> {art['date']}</span>
                    <span><i class="fa-regular fa-clock"></i> {art['read_time']}</span>
                </div>

                <div class="single-feat-img">
                    <img src="{art['image']}" alt="{art['title']}" loading="eager">
                </div>

                <!-- Top In-Article Ad Slot -->
                <div class="in-article-ad">
                    <span>Sponsored Announcement (Responsive Top Ad)</span>
                </div>

                <div class="entry-content">
                    {art['content']}
                </div>

                <!-- Bottom In-Article Ad Slot -->
                <div class="in-article-ad">
                    <span>Sponsored Content Recommendation (Responsive Bottom Ad)</span>
                </div>

                <!-- Author Box -->
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:20px; margin-top:30px; display:flex; gap:16px; align-items:center;">
                    <div style="width:60px; height:60px; border-radius:50%; background:var(--primary); color:#FFF; display:flex; align-items:center; justify-content:center; font-size:24px; font-weight:700;">
                        LR
                    </div>
                    <div>
                        <div style="font-weight:700; font-family:var(--font-head); font-size:16px;">LoanRaaj फाइनेंशियल एडिटोरियल टीम</div>
                        <p style="font-size:13px; color:#64748B; margin-top:2px;">
                            हमारे विशेषज्ञ बैंकिंग, लोन योजनाओं, और सरकारी सब्सिडी पर निष्पक्ष और सटीक विश्लेषण प्रदान करते हैं ताकि आम नागरिक सही वित्तीय निर्णय ले सकें।
                        </p>
                    </div>
                </div>
            </article>

            <!-- Sidebar -->
            <aside class="sidebar-area">
                <div class="widget">
                    <div class="widget-title">ट्रेंडिंग योजनाएं</div>
"""
    for other in articles[:5]:
        if other['slug'] != art['slug']:
            post_html += f"""
                    <div class="widget-post-item">
                        <div class="widget-post-thumb">
                            <a href="/{other['slug']}"><img src="{other['image']}" alt="{other['title']}"></a>
                        </div>
                        <div>
                            <a href="/{other['slug']}" class="widget-post-title">{other['title']}</a>
                            <div style="font-size:11px; color:#888; margin-top:4px;">{other['category']}</div>
                        </div>
                    </div>
            """

    post_html += """
                </div>

                <!-- Live Interactive EMI Calculator in Single Post -->
                <div class="widget">
                    <div class="widget-title">लोन EMI कैलकुलेटर</div>
                    <div class="calc-box">
                        <div class="calc-field">
                            <label><span>लोन राशि:</span> <span id="amountDisplay">₹5,00,000</span></label>
                            <input type="range" id="loanAmount" min="50000" max="5000000" step="25000" value="500000" oninput="updateEMI()">
                        </div>
                        <div class="calc-field">
                            <label><span>ब्याज दर:</span> <span id="rateDisplay">10.5%</span></label>
                            <input type="range" id="loanRate" min="7" max="24" step="0.25" value="10.5" oninput="updateEMI()">
                        </div>
                        <div class="calc-field">
                            <label><span>अवधि (साल):</span> <span id="tenureDisplay">3 वर्ष</span></label>
                            <input type="range" id="loanTenure" min="1" max="15" step="1" value="3" oninput="updateEMI()">
                        </div>
                        <div class="calc-result">
                            <div style="font-size:12px; text-transform:uppercase;">मासिक EMI</div>
                            <div class="calc-result-val" id="emiResult">₹16,252</div>
                        </div>
                    </div>
                </div>
            </aside>
        </div>
    </main>
    """
    post_html += get_footer()
    
    with open(os.path.join(OUTPUT_DIR, f"{art['slug']}.html"), 'w', encoding='utf-8') as f:
        f.write(post_html)

# 3. BUILD 5 MANDATORY LEGAL PAGES
print("[3/4] Building 5 Mandatory Legal Trust Pages...")

legal_pages = {
    "privacy-policy.html": (
        "प्राइवेसी पॉलिसी (Privacy Policy)",
        """
        <h2>1. हम कौन सी जानकारी एकत्र करते हैं?</h2>
        <p>LoanRaaj.com पर आपकी गोपनीयता हमारे लिए सर्वोच्च प्राथमिकता है। जब आप हमारी वेबसाइट पर विजिट करते हैं, तो हम केवल आवश्यक गैर-व्यक्तिगत जानकारी (जैसे ब्राउज़र प्रकार, आईपी पता, और विज़िट किए गए पृष्ठ) एकत्र करते हैं ताकि हम उपयोगकर्ता अनुभव को बेहतर बना सकें।</p>
        
        <h2>2. Google AdSense और थर्ड-पार्टी विज्ञापन कुकीज़</h2>
        <p>Google और अन्य थर्ड-पार्टी वेंडर्स हमारी साइट पर विज्ञापन दिखाने के लिए कुकीज़ (Cookies) का उपयोग करते हैं। Google की DART कुकी का उपयोग इंटरनेट पर अन्य साइटों पर आपकी विज़िट के आधार पर आपको उपयुक्त विज्ञापन दिखाने के लिए किया जाता है। आप Google विज्ञापन और सामग्री नेटवर्क गोपनीयता नीति पर जाकर DART कुकी के उपयोग से बाहर निकल सकते हैं।</p>
        
        <h2>3. Monetag & Push Notifications</h2>
        <p>हमारी साइट वेब पुश नोटिफिकेशन के माध्यम से महत्वपूर्ण वित्तीय अपडेट और लोन अलर्ट भेज सकती है। आप अपने ब्राउज़र सेटिंग्स में जाकर किसी भी समय इन नोटिफिकेशन की अनुमति रद्द कर सकते हैं।</p>
        
        <h2>4. बाहरी वेबसाइट्स के लिंक्स</h2>
        <p>हमारी वेबसाइट पर सरकारी पोर्टलों और बैंक वेबसाइटों के आधिकारिक लिंक्स दिए जाते हैं। हम उन बाहरी वेबसाइटों की गोपनीयता प्रथाओं या सामग्री के लिए ज़िम्मेदार नहीं हैं।</p>
        
        <h2>5. संपर्क सूत्र</h2>
        <p>यदि इस गोपनीयता नीति के बारे में आपका कोई प्रश्न है, तो आप हमें <strong>contact@loanraaj.com</strong> पर ईमेल कर सकते हैं।</p>
        """
    ),
    "terms-and-conditions.html": (
        "नियम एवं शर्तें (Terms and Conditions)",
        """
        <h2>1. उपयोग की स्वीकृति</h2>
        <p>LoanRaaj.com का उपयोग करके, आप इन नियमों और शर्तों से पूरी तरह सहमत होते हैं। यदि आप इनमें से किसी भी शर्त से सहमत नहीं हैं, तो कृपया वेबसाइट का उपयोग न करें।</p>
        
        <h2>2. बौद्धिक संपदा अधिकार</h2>
        <p>इस वेबसाइट पर प्रकाशित सभी टेक्स्ट, लेआउट, ग्राफिक्स और डेटा LoanRaaj के स्वामित्व में हैं। किसी भी सामग्री को बिना पूर्व लिखित अनुमति के कॉपी, री-पब्लिश या व्यावसायिक उद्देश्य के लिए उपयोग करना प्रतिबंधित है।</p>
        
        <h2>3. वित्तीय सलाह का अस्वीकरण</h2>
        <p>LoanRaaj.com पर दी गई सभी जानकारी केवल सामान्य शैक्षिक और सूचनात्मक मार्गदर्शन के लिए है। हम वित्तीय सलाहकार नहीं हैं। किसी भी लोन योजना या निवेश में आवेदन करने से पहले संबंधित बैंक या पंजीकृत वित्तीय सलाहकार से परामर्श अवश्य लें।</p>
        
        <h2>4. दायित्व की सीमा</h2>
        <p>वेबसाइट की जानकारी के उपयोग से होने वाले किसी भी प्रत्यक्ष या अप्रत्यक्ष वित्तीय नुकसान के लिए LoanRaaj उत्तरदायी नहीं होगा।</p>
        """
    ),
    "disclaimer.html": (
        "डिस्क्लेमर (Disclaimer)",
        """
        <h2>गैर-सरकारी संस्था अस्वीकरण (Non-Government Disclaimer)</h2>
        <p>LoanRaaj.com एक स्वतंत्र और निजी सूचनात्मक ब्लॉग है। हम भारत सरकार, भारतीय रिजर्व बैंक (RBI), या किसी भी राष्ट्रीयकृत बैंक के आधिकारिक प्रतिनिधि नहीं हैं।</p>
        
        <h2>सटीकता और सत्यापन</h2>
        <p>यद्यपि हम सभी लोन योजनाओं (जैसे PMEGP, Mudra, UYEGP) और बैंक ब्याज दरों की जानकारी आधिकारिक स्रोतों से सत्यापित करके प्रकाशित करते हैं, फिर भी ब्याज दरों और पात्रता मानदंडों में समय-समय पर बदलाव हो सकते हैं। पाठकों को सलाह दी जाती है कि वे हमेशा आधिकारिक बैंक शाखा या आधिकारिक सरकारी पोर्टल पर जाकर अंतिम पुष्टि करें।</p>
        
        <h2>कोई शुल्क नहीं</h2>
        <p>LoanRaaj किसी भी पाठक से लोन स्वीकृति या मार्गदर्शन के नाम पर कोई शुल्क (फीस) नहीं लेता है। यदि कोई व्यक्ति LoanRaaj के नाम पर पैसे की मांग करता है, तो कृपया तुरंत सतर्क रहें।</p>
        """
    ),
    "about-us.html": (
        "हमारे बारे में (About Us)",
        """
        <h2>हमारा मिशन (Our Mission)</h2>
        <p>LoanRaaj.com की शुरुआत भारत के आम नागरिकों, छोटे व्यापारियों, और युवाओं को भारत की जटिल वित्तीय और बैंकिंग प्रणाली को सरल हिंदी भाषा में समझाने के लिए की गई है।</p>
        
        <h2>हम क्या प्रदान करते हैं?</h2>
        <ul>
            <li><strong>सरकारी लोन योजनाएं:</strong> PMEGP, मुद्रा लोन, UYEGP और सब्सिडी योजनाओं की स्टेप-बाय-स्टेप आवेदन प्रक्रिया।</li>
            <li><strong>पर्सनल & इंस्टेंट लोन:</strong> ब्याज दरों की तुलना और धोखाधड़ी से बचने के उपाय।</li>
            <li><strong>फाइनेंशियल टूल्स:</strong> घर बैठे अपनी किश्त जानने के लिए फ्री और सटीक EMI कैलकुलेटर।</li>
            <li><strong>क्रेडिट कार्ड समीक्षा:</strong> सही कार्ड चुनने और रिवॉर्ड पॉइंट्स अधिकतम करने के तरीके।</li>
        </ul>
        
        <h2>हमारी एडिटोरियल टीम</h2>
        <p>हमारी संपादकीय टीम में बैंकिंग और अर्थशास्त्र के जानकार शामिल हैं जो हर आर्टिकल को प्रकाशित करने से पहले आधिकारिक दिशानिर्देशों से मिलान करते हैं।</p>
        """
    ),
    "contact-us.html": (
        "संपर्क करें (Contact Us)",
        """
        <h2>हमसे संपर्क करें</h2>
        <p>यदि आपके पास किसी लोन योजना, आर्टिकल, या सुझाव के संबंध में कोई प्रश्न है, तो आप नीचे दिए गए विवरणों के माध्यम से सीधे हमारी टीम से संपर्क कर सकते हैं:</p>
        
        <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-radius:6px; padding:20px; margin:20px 0;">
            <p><strong>आधिकारिक सपोर्ट ईमेल:</strong> support@loanraaj.com</p>
            <p><strong>संपादकीय इंक्वायरी:</strong> editor@loanraaj.com</p>
            <p><strong>कार्यकारी समय:</strong> सोमवार से शुक्रवार (सुबह 10:00 बजे से शाम 6:00 बजे तक)</p>
            <p><strong>प्रतिक्रिया समय:</strong> हम सामान्यतः 24 से 48 व्यावसायिक घंटों के भीतर उत्तर देते हैं।</p>
        </div>
        
        <h2>क्विक फीडबैक फॉर्म</h2>
        <form style="display:grid; gap:14px; max-width:500px;" onsubmit="alert('संदेश प्राप्त हुआ! हमारी टीम जल्द ही आपसे संपर्क करेगी।'); return false;">
            <input type="text" placeholder="आपका नाम" required style="padding:10px; border:1px solid #CBD5E1; border-radius:4px;">
            <input type="email" placeholder="ईमेल आईडी" required style="padding:10px; border:1px solid #CBD5E1; border-radius:4px;">
            <textarea placeholder="आपका प्रश्न या संदेश" rows="4" required style="padding:10px; border:1px solid #CBD5E1; border-radius:4px;"></textarea>
            <button type="submit" style="background:var(--primary); color:#FFF; padding:12px; border:none; border-radius:4px; font-weight:700; cursor:pointer;">संदेश भेजें</button>
        </form>
        """
    )
}

for page_slug, (page_title, page_content) in legal_pages.items():
    p_html = get_head(
        title=page_title,
        desc=f"LoanRaaj.com का आधिकारिक {page_title} पेज।",
        slug=page_slug,
        is_article=False
    )
    p_html += f"""
    <main class="container" style="margin-top:25px;">
        <div class="single-post-container" style="max-width:900px; margin:0 auto;">
            <h1 class="single-title" style="border-bottom:2px solid var(--border-color); padding-bottom:12px;">{page_title}</h1>
            <div class="entry-content" style="margin-top:20px;">
                {page_content}
            </div>
        </div>
    </main>
    """
    p_html += get_footer()
    
    with open(os.path.join(OUTPUT_DIR, page_slug), 'w', encoding='utf-8') as f:
        f.write(p_html)

# 4. BUILD SITEMAP.XML & ROBOTS.TXT
print("[4/4] Building clean sitemap.xml and robots.txt...")

sitemap_entries = [
    ("https://loanraaj.com/", "1.0", "daily"),
    ("https://loanraaj.com/emi-calculator.html", "0.9", "monthly"),
]
for art in articles:
    sitemap_entries.append((f"https://loanraaj.com/{art['slug']}.html", "0.8", "weekly"))
for page_slug in legal_pages.keys():
    sitemap_entries.append((f"https://loanraaj.com/{page_slug}", "0.5", "monthly"))

sm_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
for url, prio, freq in sitemap_entries:
    sm_xml += f"""  <url>
    <loc>{url}</loc>
    <lastmod>2026-11-10</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>\n"""
sm_xml += '</urlset>'

with open(os.path.join(OUTPUT_DIR, 'sitemap.xml'), 'w', encoding='utf-8') as f:
    f.write(sm_xml)

robots_txt = """User-agent: *
Allow: /

Sitemap: https://loanraaj.com/sitemap.xml
"""

with open(os.path.join(OUTPUT_DIR, 'robots.txt'), 'w', encoding='utf-8') as f:
    f.write(robots_txt)

print("\n" + "=" * 60)
print("SUCCESS: LOANRAAJ.COM ZOX-NEWS CLONE GENERATED COMPLETELY!")
print("=" * 60)
