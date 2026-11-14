"""
scripts/fix_bug2_h1_and_faq.py — Restore <h1> on 24 pages and align JSON-LD FAQPage schemas with on-page H3s.
"""

import re
import json
from pathlib import Path
from bs4 import BeautifulSoup

TARGET_PAGES = [
    'karzseva.com/personal-loan-guide',
    'loankiseva.com/personal-loan-guide',
    'loanraaj.com/21-machines-business',
    'loanraaj.com/best-health-insurance',
    'loanraaj.com/car-loan-guide',
    'loanraaj.com/commercial-auto-insurance',
    'loanraaj.com/daughter-loan-scheme',
    'loanraaj.com/hdfc-credit-card-apply',
    'loanraaj.com/moneyview-loan-apply',
    'loanraaj.com/personal-loan-guide',
    'loanraaj.com/pmegp-loan-scheme',
    'loanraaj.com/pnb-home-loan-guide',
    'loanraaj.com/uyegp-loan-scheme',
    'loanraaj.com/work-from-home-jobs',
    'loantau.com/personal-loan-guide',
    'rechargekar.com/best-recharge-plans',
    'rechargekar.com/fastag-recharge-guide',
    'rechargepur.com/best-recharge-plans',
    'rechargepur.com/fastag-recharge-guide',
    'rechargetak.com/best-recharge-plans',
    'rechargetak.com/fastag-recharge-guide',
    'tazabhav.com/gold-rate-today',
    'tazaloan.com/personal-loan-guide',
    'tazarokda.com/credit-card-apply'
]

H1_TITLES = {
    'karzseva.com/personal-loan-guide': 'पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई',
    'loankiseva.com/personal-loan-guide': 'पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई',
    'loanraaj.com/21-machines-business': '21 Machines You Can Import From China to Start a Profitable Business',
    'loanraaj.com/best-health-insurance': 'Best Health Insurance Plans in India 2026: Comprehensive Coverage Guide',
    'loanraaj.com/car-loan-guide': 'Car Loan 2026 Guide: Interest Rates, Eligibility & Application',
    'loanraaj.com/commercial-auto-insurance': 'Commercial Auto Insurance Quotes 2026: Rates & Policy Guide',
    'loanraaj.com/daughter-loan-scheme': 'बेटियों के लिए सरकारी योजनाएं और एजुकेशन लोन गाइड 2026',
    'loanraaj.com/hdfc-credit-card-apply': 'HDFC Credit Card Online Apply: Eligibility, Cashback & Rewards Guide',
    'loanraaj.com/moneyview-loan-apply': 'Moneyview Personal Loan Online Apply: Interest Rates & Approval Process',
    'loanraaj.com/personal-loan-guide': 'पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई',
    'loanraaj.com/pmegp-loan-scheme': 'PMEGP Business Loan Scheme: Subsidy, Eligibility & Online Application',
    'loanraaj.com/pnb-home-loan-guide': 'PNB Home Loan 2026: Interest Rates, EMI Calculator & Application',
    'loanraaj.com/uyegp-loan-scheme': 'UYEGP Loan Scheme 2026: Government Subsidy & MSME Finance Guide',
    'loanraaj.com/work-from-home-jobs': 'Best Work From Home Jobs in India: High Paying Opportunities 2026',
    'loantau.com/personal-loan-guide': 'पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई',
    'rechargekar.com/best-recharge-plans': 'Best Mobile Recharge Plans 2026: Jio, Airtel, Vi & BSNL Comparison',
    'rechargekar.com/fastag-recharge-guide': 'फास्टैग ऑनलाइन रिचार्ज और बैलेंस चेक गाइड 2026',
    'rechargepur.com/best-recharge-plans': 'Best Mobile Recharge Plans 2026: 5G Data, Validity & Tariff Guide',
    'rechargepur.com/fastag-recharge-guide': 'फास्टैग ऑनलाइन रिचार्ज और बैलेंस चेक गाइड 2026',
    'rechargetak.com/best-recharge-plans': 'Best Mobile Recharge Plans 2026: Prepaid Offers & OTT Benefits',
    'rechargetak.com/fastag-recharge-guide': 'फास्टैग ऑनलाइन रिचार्ज और बैलेंस चेक गाइड 2026',
    'tazabhav.com/gold-rate-today': 'आज का सोने का ताजा भाव (Gold Rate Today in India): 22K & 24K',
    'tazaloan.com/personal-loan-guide': 'पर्सनल लोन कैसे लें — ब्याज दर, जरूरी दस्तावेज और ऑनलाइन अप्लाई',
    'tazarokda.com/credit-card-apply': 'लाइफटाइम फ्री क्रेडिट कार्ड कैसे प्राप्त करें — बेस्ट कैशबैक कार्ड्स 2026'
}


def fix_h1s():
    fixed = 0
    for target in TARGET_PAGES:
        domain, slug = target.split('/', 1)
        path = Path('sites') / domain / slug / 'index.html'
        if not path.exists():
            continue
        html = path.read_text(encoding='utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        h1s = soup.find_all('h1')
        if len(h1s) == 0:
            h1_text = H1_TITLES.get(target, slug.replace('-', ' ').title())
            h1_html = f'<h1 class="post-h1" style="font-size:2rem; font-weight:800; margin-bottom:1.5rem; line-height:1.3; color:#0F172A;">{h1_text}</h1>\n'
            
            # Place at top of post-content or entry-content or main article
            content_div = soup.find('div', class_='post-content') or soup.find('div', class_='entry-content') or soup.find('article')
            if content_div:
                # Insert via regex on raw HTML right after opening div to preserve exact formatting
                class_name = content_div.get('class', ['post-content'])[0]
                pattern = re.compile(rf'(<div[^>]*class=["\'][^"\']*{class_name}[^"\']*["\'][^>]*>)', re.IGNORECASE)
                m = pattern.search(html)
                if m:
                    new_html = html[:m.end()] + "\n" + h1_html + html[m.end():]
                    path.write_text(new_html, encoding='utf-8')
                    fixed += 1
                    print(f"[H1 Fixed] {target}")
                else:
                    print(f"[Warning: Div pattern not found] {target}")
            else:
                print(f"[Warning: Content div not found] {target}")
        else:
            print(f"[Already has H1] {target}")
    print(f"Total H1 fixed: {fixed}")


def fix_faq_schemas():
    """Align FAQPage schemas with on-page H3s on the 8 affected pages."""
    pages = [
        'sites/loanraaj.com/secured-overdraft-facility-against-property-interest-ma/index.html',
        'sites/rechargekar.com/best-recharge-plans/index.html',
        'sites/rechargekar.com/fastag-recharge-guide/index.html',
        'sites/rechargepur.com/best-recharge-plans/index.html',
        'sites/rechargepur.com/fastag-recharge-guide/index.html',
        'sites/rechargetak.com/best-recharge-plans/index.html',
        'sites/rechargetak.com/fastag-recharge-guide/index.html',
        'sites/tazabhav.com/gold-rate-today/index.html'
    ]

    for p_str in pages:
        p = Path(p_str)
        if not p.exists():
            continue
        html = p.read_text(encoding='utf-8')
        soup = BeautifulSoup(html, 'html.parser')

        # For secured-overdraft, add missing H3s in the content
        if 'secured-overdraft' in p_str:
            content_div = soup.find('div', class_='post-content')
            if content_div and not soup.find_all('h3'):
                faq_block = """
<h2>Frequently Asked Questions</h2>
<h3>What is the main advantage of Secured Overdraft Facility Against Property: Interest?</h3>
<p>The primary benefit of a mortgage overdraft facility is paying interest solely on the utilized credit balance rather than the entire sanctioned loan sanction limit, drastically lowering interest outflow.</p>
<h3>How to verify current rates and eligibility?</h3>
<p>Eligible borrowers require unencumbered commercial or residential property titles, minimum 65% LTV buffer, and clean 750+ CIBIL track record to secure competitive 8.95% to 10.50% APR overdraft limits.</p>
<h3>Are there any hidden charges?</h3>
<p>Borrowers must verify upfront processing charges (0.50% to 1.0%), annual line renewal fees, legal valuation charges, and property insurance costs in the Key Fact Statement (KFS).</p>
"""
                # Insert before closing div of post-content
                html = html.replace('</div><figure class="content-image', faq_block + '</div><figure class="content-image')
                soup = BeautifulSoup(html, 'html.parser')

        # Collect genuine on-page FAQ H3s
        faq_items = []
        for h3 in soup.find_all('h3'):
            text = h3.get_text().strip()
            if text in ('Frequently Asked Questions', 'FAQ', 'सम्बंधित विषय (Related Articles)', 'Related Topics'):
                continue
            # find next p sibling
            next_p = h3.find_next_sibling('p')
            ans = next_p.get_text().strip() if next_p else "Check official guidelines and terms for latest details."
            faq_items.append({
                "@type": "Question",
                "name": text,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": ans
                }
            })

        if not faq_items:
            continue

        # Update JSON-LD script containing FAQPage
        updated_scripts = False
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or '{}')
                changed = False
                nodes = data.get('@graph', [data]) if isinstance(data, dict) else []
                for node in nodes:
                    if node.get('@type') == 'FAQPage':
                        node['mainEntity'] = faq_items
                        changed = True
                if changed:
                    script.string = json.dumps(data, ensure_ascii=False, indent=2)
                    updated_scripts = True
            except Exception:
                pass

        if updated_scripts:
            p.write_text(str(soup), encoding='utf-8')
            print(f"[FAQ Schema Updated] {p_str}")


if __name__ == '__main__':
    fix_h1s()
    fix_faq_schemas()
