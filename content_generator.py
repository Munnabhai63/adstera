"""
content_generator.py — Step 6.1: SEO Landing Page & Internal Article Generator

Generates high-intent semantic content for all 10 publisher sites:
- Semantic HTML5 structure (<main>, <article>, <nav>, <h1>, <h2>, <h3>)
- Schema.org JSON-LD structured data (Article, FAQPage, BreadcrumbList)
- Natural Adsterra ad placement placeholders (responsive banner & social bar iframes)
- Multi-page internal navigation graph (enables deep 2-3 page bot browsing)
- Clean sitemap.xml and robots.txt generation per domain
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).parent / "sites"

# Domain category mapping
DOMAIN_CATEGORIES = {
    "loanraaj": "loan",
    "tazaloan": "loan",
    "loankiseva": "loan",
    "karzseva": "loan",
    "loantau": "loan",
    "rechargetak": "recharge",
    "rechargepur": "recharge",
    "rechargekar": "recharge",
    "tazabhav": "bhav",
    "tazarokda": "finance",
}

# Template blueprints by category
ARTICLE_BLUEPRINTS = {
    "loan": [
        {
            "slug": "personal-loan-guide.html",
            "title": "पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई",
            "desc": "कम ब्याज दर पर 50,000 से 10 लाख तक का पर्सनल लोन कैसे प्राप्त करें। सिबिल स्कोर और योग्यता की पूरी जानकारी।",
            "h1": "पर्सनल लोन लेने का सबसे आसान और सुरक्षित तरीका (2026 गाइड)",
            "sections": [
                ("पर्सनल लोन की योग्यता और सिबिल स्कोर", "पर्सनल लोन प्राप्त करने के लिए आपका सिबिल स्कोर कम से कम 700 होना चाहिए। आवश्यक दस्तावेजों में आधार कार्ड, पैन कार्ड और 6 महीने का बैंक स्टेटमेंट अनिवार्य है।"),
                ("ब्याज दर और ईएमआई की तुलना", "विभिन्न बैंकों और NBFCs की ब्याज दरें 10.5% से 18% प्रति वर्ष के बीच होती हैं। हमेशा लोन अवधि और प्रोसेसिंग फीस की तुलना करके ही आवेदन करें।"),
                ("लोन अप्रूवल के 5 जरूरी नियम", "1. एक साथ कई जगह अप्लाई न करें। 2. क्रेडिट यूटिलाइजेशन रेश्यो 30% से कम रखें। 3. मौजूदा ईएमआई समय पर चुकाएं। 4. आय का सही प्रमाण प्रस्तुत करें।"),
            ],
            "faq": [
                {"q": "कम सिबिल स्कोर पर लोन कैसे मिलेगा?", "a": "आप को-एप्लिकेंट (सह-आवेदक) जोड़कर या सिक्योर्ड लोन (गोल्ड लोन या एफडी पर लोन) के जरिए आवेदन कर सकते हैं।"},
                {"q": "लोन अप्रूव होने में कितना समय लगता है?", "a": "डिजिटल केवाईसी के साथ अधिकांश बैंक 24 से 48 घंटे के भीतर राशि ट्रांसफर कर देते हैं।"},
            ],
        },
        {
            "slug": "emi-calculator.html",
            "title": "लोन ईएमआई कैलकुलेटर — मासिक किस्त और कुल ब्याज की गणना",
            "desc": "पर्सनल लोन, होम लोन और कार लोन की मासिक ईएमआई तुरंत कैलकुलेट करें। सटीक ब्याज और पुनर्भुगतान विवरण।",
            "h1": "ऑनलाइन लोन ईएमआई कैलकुलेटर (Instant EMI Calculator)",
            "sections": [
                ("ईएमआई (EMI) क्या है और इसकी गणना कैसे होती है?", "ईएमआई वह निश्चित राशि है जो आप हर महीने बैंक को चुकाते हैं। इसमें मूलधन (Principal) और ब्याज (Interest) दोनों शामिल होते हैं।"),
                ("ईएमआई घटाने के व्यावहारिक तरीके", "लोन अवधि बढ़ाकर मासिक ईएमआई घटाई जा सकती है, हालांकि कुल ब्याज बढ़ जाता है। पार्ट-पेमेंट या प्री-क्लोज़र से आप कुल ब्याज बचा सकते हैं।"),
            ],
            "faq": [
                {"q": "क्या लोन प्री-पेमेंट पर पेनल्टी लगती है?", "a": "फ्लोटिंग रेट पर्सनल लोन पर आरबीआई के नियमानुसार कोई प्री-पेमेंट पेनल्टी नहीं होती।"},
            ],
        },
    ],
    "recharge": [
        {
            "slug": "best-recharge-plans.html",
            "title": "बेस्ट मोबाइल रिचार्ज प्लान 2026 — जियो, एयरटेल और वीआई के सस्ते प्लान",
            "desc": "28 दिन, 56 दिन और 84 दिन की वैलिडिटी वाले बेस्ट अनलिमिटेड कॉलिंग और डेली 1.5GB/2GB डेटा पैक की सूची।",
            "h1": "2026 के सबसे सस्ते और बेस्ट मोबाइल रिचार्ज प्लान",
            "sections": [
                ("डेली 1.5GB डेटा और अनलिमिटेड कॉलिंग प्लान", "जियो और एयरटेल के 28 दिन वाले प्लान 299 से शुरू होते हैं जिनमें फ्री 100 एसएमएस और ओटीटी ऐप्स का सब्सक्रिप्शन भी मिलता है।"),
                ("लॉन्ग टर्म 84 दिन और 365 दिन के प्लान", "सालाना प्लान चुनने से हर महीने रिचार्ज कराने के झंझट से मुक्ति मिलती है और लगभग 25% तक की बचत होती है।"),
            ],
            "faq": [
                {"q": "अनलिमिटेड 5G डेटा कैसे एक्टिवेट करें?", "a": "5G सपोर्टेड फोन में एलिजिबल 239+ के प्लान पर MyJio या Airtel Thanks ऐप से 5G वेलकम ऑफर क्लेम करें।"},
            ],
        },
        {
            "slug": "fastag-recharge-guide.html",
            "title": "फास्टैग ऑनलाइन रिचार्ज कैसे करें — तुरंत बैलेंस चेक और ऑफर",
            "desc": "पेटीएम, गूगल पे और फोनपे से फास्टैग रिचार्ज करने का आसान तरीका और नेशनल हाईवे टोल छूट की जानकारी।",
            "h1": "फास्टैग ऑनलाइन रिचार्ज और बैलेंस चेक गाइड",
            "sections": [
                ("UPI से 1 मिनट में फास्टैग रिचार्ज", "गूगल पे या फोनपे पर व्हीकल नंबर दर्ज करके बैंक चुने बिना भी फास्टैग तुरंत रिचार्ज किया जा सकता है।"),
                ("ब्लैकलिस्ट फास्टैग को एक्टिवेट कैसे करें?", "न्यूनतम ₹150 बैलेंस बनाए रखें। कम बैलेंस होने पर तुरंत यूपीआई से टॉप-अप करें, फास्टैग 10 मिनट में एक्टिव हो जाता है।"),
            ],
            "faq": [
                {"q": "फास्टैग का मिनिमम बैलेंस कितना होना चाहिए?", "a": "कार और जीप के लिए न्यूनतम बैलेंस ₹100 से ₹200 रखना अनिवार्य है।"},
            ],
        },
    ],
    "bhav": [
        {
            "slug": "gold-rate-today.html",
            "title": "सोना-चांदी भाव आज का — 22K और 24K सोने का ताजा रेट",
            "desc": "भारत के प्रमुख शहरों में 22 कैरेट और 24 कैरेट सोने का आज का ताजा भाव। बाजार रुझान और विशेषज्ञ सलाह।",
            "h1": "आज का सोने का ताजा भाव (Gold Rate Today in India)",
            "sections": [
                ("22K बनाम 24K सोने में अंतर", "24 कैरेट सोना 99.9% शुद्ध होता है और निवेश के लिए उपयुक्त है। आभूषण बनाने के लिए 22 कैरेट (91.6% हॉलमार्क) सोना इस्तेमाल होता है।"),
                ("सोने के भाव तय करने वाले कारक", "वैश्विक मुद्रास्फीति, डॉलर इंडेक्स, भू-राजनीतिक तनाव और शादियों के सीजन की मांग से सोने की कीमतों में उतार-चढ़ाव आता है।"),
            ],
            "faq": [
                {"q": "हॉलमार्क सोना कैसे पहचानें?", "a": "गहने पर बीआईएस (BIS) का त्रिकोणीय लोगो, 6 अंकों का अल्फ़ान्यूमेरिक HUID कोड और 916 का मार्क अवश्य देखें।"},
            ],
        },
    ],
    "finance": [
        {
            "slug": "credit-card-apply.html",
            "title": "लाइफटाइम फ्री क्रेडिट कार्ड कैसे प्राप्त करें — बेस्ट कैशबैक कार्ड्स 2026",
            "desc": "बिना जॉइनिंग फीस और बिना एनुअल चार्ज वाले बेस्ट लाइफटाइम फ्री क्रेडिट कार्ड्स की लिस्ट और आवेदन प्रक्रिया।",
            "h1": "बेस्ट लाइफटाइम फ्री क्रेडिट कार्ड (Zero Annual Fee Cards)",
            "sections": [
                ("कैशबैक और रिवॉर्ड पॉइंट्स की तुलना", "शॉपिंग, डाइनिंग और फ्यूल पर 5% तक का फ्लैट कैशबैक देने वाले कार्ड्स आपकी मासिक खरीदारी पर भारी बचत कराते हैं।"),
                ("क्रेडिट कार्ड इस्तेमाल करने के स्मार्ट नियम", "हमेशा कुल देय राशि (Total Amount Due) का भुगतान समय पर करें। कभी भी केवल मिनिमम ड्यू न भरें।"),
            ],
            "faq": [
                {"q": "क्या बिना इनकम प्रूफ क्रेडिट कार्ड मिल सकता है?", "a": "हाँ, बैंक एफडी (FD-backed) के आधार पर बिना सैलरी स्लिप के सिक्योर्ड क्रेडिट कार्ड आसानी से मिल जाता है।"},
            ],
        },
    ],
}


def _build_article_html(
    domain_name: str,
    article_data: dict[str, Any],
    other_slugs: list[tuple[str, str]],
) -> str:
    """Renders a fully responsive, semantic, SEO-optimized HTML article."""
    canonical_url = f"https://{domain_name}/{article_data['slug']}"

    # Generate JSON-LD Schema
    schema_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": article_data["h1"],
                "description": article_data["desc"],
                "mainEntityOfPage": canonical_url,
                "inLanguage": "hi",
                "publisher": {
                    "@type": "Organization",
                    "name": domain_name,
                    "url": f"https://{domain_name}",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"https://{domain_name}"},
                    {"@type": "ListItem", "position": 2, "name": article_data["title"], "item": canonical_url},
                ],
            },
        ],
    }

    if article_data.get("faq"):
        faq_schema = {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
                }
                for item in article_data["faq"]
            ],
        }
        schema_ld["@graph"].append(faq_schema)

    sections_html = "".join(
        f'<section class="content-block"><h2>{title}</h2><p>{body}</p></section>'
        for title, body in article_data.get("sections", [])
    )

    faq_html = ""
    if article_data.get("faq"):
        items_html = "".join(
            f'<div class="faq-item"><h3>{item["q"]}</h3><p>{item["a"]}</p></div>'
            for item in article_data["faq"]
        )
        faq_html = f'<section class="faq-section"><h2>अक्सर पूछे जाने वाले सवाल (FAQ)</h2>{items_html}</section>'

    nav_links_html = "".join(
        f'<li><a href="/{slug}">{title}</a></li>'
        for slug, title in other_slugs
    )

    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{article_data['title']} — {domain_name}</title>
  <meta name="description" content="{article_data['desc']}">
  <link rel="canonical" href="{canonical_url}">
  <script type="application/ld+json">
{json.dumps(schema_ld, ensure_ascii=False, indent=2)}
  </script>
  <style>
    :root {{
      --primary: #1e3a8a;
      --accent: #2563eb;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }}
    header {{ background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; position: sticky; top: 0; z-index: 50; }}
    .header-inner {{ max-width: 1040px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
    .logo {{ font-size: 20px; font-weight: 800; color: var(--primary); text-decoration: none; }}
    nav a {{ margin-left: 16px; color: var(--muted); text-decoration: none; font-size: 14px; }}
    nav a:hover {{ color: var(--accent); }}
    .container {{ max-width: 1040px; margin: 28px auto; padding: 0 16px; display: grid; grid-template-columns: 2.2fr 1fr; gap: 28px; }}
    @media (max-width: 768px) {{ .container {{ grid-template-columns: 1fr; }} }}
    article {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 32px; }}
    h1 {{ font-size: 26px; font-weight: 800; color: var(--primary); margin-bottom: 16px; line-height: 1.3; }}
    h2 {{ font-size: 20px; font-weight: 700; color: var(--primary); margin: 24px 0 10px; }}
    h3 {{ font-size: 16px; font-weight: 600; color: #1e293b; margin-bottom: 6px; }}
    p {{ margin-bottom: 16px; color: #334155; font-size: 15px; }}
    .ad-slot {{ background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 16px; text-align: center; margin: 24px 0; }}
    .ad-label {{ font-size: 11px; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; letter-spacing: 0.5px; }}
    .sidebar-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
    .sidebar-card h3 {{ font-size: 16px; margin-bottom: 12px; color: var(--primary); }}
    .sidebar-card ul {{ list-style: none; }}
    .sidebar-card li {{ margin-bottom: 10px; }}
    .sidebar-card a {{ color: var(--accent); text-decoration: none; font-size: 14px; }}
    .sidebar-card a:hover {{ text-decoration: underline; }}
    .faq-item {{ margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
    footer {{ text-align: center; padding: 32px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--border); margin-top: 40px; }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <a href="/" class="logo">{domain_name}</a>
      <nav>
        <a href="/">Home</a>
        <a href="#related">Articles</a>
      </nav>
    </div>
  </header>

  <main class="container">
    <article>
      <h1>{article_data['h1']}</h1>
      
      <!-- In-Content Top Ad Unit -->
      <div class="ad-slot" id="top-ad">
        <div class="ad-label">Sponsored Resource</div>
        <iframe src="about:blank" style="width:100%;height:90px;border:none;" title="Ad Unit"></iframe>
      </div>

      {sections_html}

      <!-- Mid-Content Ad Unit -->
      <div class="ad-slot" id="mid-ad">
        <div class="ad-label">Advertisement</div>
        <iframe src="about:blank" style="width:100%;height:250px;border:none;" title="Responsive Ad"></iframe>
      </div>

      {faq_html}
    </article>

    <aside>
      <div class="sidebar-card" id="related">
        <h3>सम्बंधित विषय (Related Articles)</h3>
        <ul>
          <li><a href="/">🏠 मुख्य पृष्ठ (Home)</a></li>
          {nav_links_html}
        </ul>
      </div>

      <div class="sidebar-card">
        <div class="ad-label">Sponsored</div>
        <div class="ad-slot" style="margin:0;">
          <iframe src="about:blank" style="width:100%;height:250px;border:none;" title="Sidebar Ad"></iframe>
        </div>
      </div>
    </aside>
  </main>

  <footer>
    <p>© 2026 {domain_name}. सर्वाधिकार सुरक्षित। यह साइट केवल सूचनात्मक और शैक्षिक उद्देश्यों के लिए है।</p>
  </footer>
</body>
</html>
"""


def generate_all_domain_articles() -> dict[str, int]:
    """Generates all SEO articles, sitemaps, and robots.txt for each domain in sites/."""
    results: dict[str, int] = {}

    for domain_folder in SITES_DIR.iterdir():
        if not domain_folder.is_dir():
            continue

        folder_name = domain_folder.name.lower().replace(".com", "")
        if folder_name not in DOMAIN_CATEGORIES:
            continue
        category = DOMAIN_CATEGORIES.get(folder_name, "loan")
        blueprints = ARTICLE_BLUEPRINTS.get(category, ARTICLE_BLUEPRINTS["loan"])
        domain_fqdn = f"{folder_name}.com"

        created_slugs = []
        for bp in blueprints:
            other_links = [(other["slug"], other["title"]) for other in blueprints if other["slug"] != bp["slug"]]
            html_content = _build_article_html(
                domain_name=domain_fqdn,
                article_data=bp,
                other_slugs=other_links,
            )
            file_path = domain_folder / bp["slug"]
            file_path.write_text(html_content, encoding="utf-8")
            created_slugs.append(bp["slug"])

        # Generate sitemap.xml
        sitemap_urls = [f"https://{domain_fqdn}/"] + [f"https://{domain_fqdn}/{s}" for s in created_slugs]
        url_tags = "\n".join(
            f"  <url>\n    <loc>{u}</loc>\n    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>"
            for u in sitemap_urls
        )
        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{url_tags}
</urlset>"""
        (domain_folder / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")

        # Generate robots.txt
        robots_content = f"""User-agent: *
Allow: /
Sitemap: https://{domain_fqdn}/sitemap.xml
"""
        (domain_folder / "robots.txt").write_text(robots_content, encoding="utf-8")

        # Inject internal navigation links into index.html
        index_file = domain_folder / "index.html"
        if index_file.exists():
            idx_html = index_file.read_text(encoding="utf-8")
            if "<!-- INTERNAL_ARTICLES_NAV -->" not in idx_html:
                internal_links_markup = "\n<!-- INTERNAL_ARTICLES_NAV -->\n<div class=\"sidebar-card\" style=\"margin-top:16px;\"><div class=\"sidebar-title\">मुख्य लेख एवं गाइड</div><div class=\"sidebar-list\">\n"
                for bp in blueprints:
                    internal_links_markup += f'  <a href="/{bp["slug"]}" style="display:block;margin:6px 0;color:#2563eb;text-decoration:none;">📄 {bp["title"][:40]}... →</a>\n'
                internal_links_markup += "</div></div>\n"

                if "</aside>" in idx_html:
                    idx_html = idx_html.replace("</aside>", f"{internal_links_markup}</aside>")
                    index_file.write_text(idx_html, encoding="utf-8")

        results[folder_name] = len(created_slugs)
        logger.info("Generated %d articles + sitemap for %s", len(created_slugs), domain_fqdn)

    return results


if __name__ == "__main__":
    generated = generate_all_domain_articles()
    print("Content generation completed:")
    for dom, count in generated.items():
        print(f"  {dom}.com: {count} articles generated")
