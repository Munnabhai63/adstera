#!/usr/bin/env python3
"""
scripts/add_5th_image_loanraaj.py — Add a 5th self-hosted content image with unique
topic-derived alt text to the 11 loanraaj pages that currently have 4 images.
"""
from pathlib import Path
from bs4 import BeautifulSoup

SITES_DIR = Path("sites")

PAGES_AND_IMAGES = [
    ("21-machines-business", "1434030216_181bd8139626.webp", "Manufacturing Machinery Operational Capacity and Equipment Layout in Indian Factory"),
    ("best-health-insurance", "1436491865_23b53a6f74b9.webp", "Cashless Hospital Treatment and Comprehensive Family Health Coverage Protocols"),
    ("car-loan-guide", "1486406146_ec516ba7b744.webp", "Automobile Vehicle Financing Application and Loan Amortization Schedule Review"),
    ("commercial-auto-insurance", "1492144534_8fc72be9c933.webp", "Commercial Auto Fleet Transport Risk Underwriting and Statutory Policy Assessment"),
    ("daughter-loan-scheme", "1500382017_36656ceb5e25.webp", "Sovereign Savings Deposit and Education Funding Scheme Verification Workflow"),
    ("hdfc-credit-card-apply", "1504307651_bd8d86a06952.webp", "Digital Credit Card Cardholder Approval and Reward Points Optimization Structure"),
    ("moneyview-loan-apply", "1507679799_df0aa939bbd4.webp", "Digital Personal Loan Instant Verification and Account Aggregator Workflow"),
    ("pmegp-loan-scheme", "1508873696_98846bb387fa.webp", "PMEGP Project Subsidy Evaluation and Bank Term Loan Approval Architecture"),
    ("pnb-home-loan-guide", "1512917774_9b4f4943fcf0.webp", "Residential Housing Construction Mortgage Loan Assessment and Legal Title Review"),
    ("uyegp-loan-scheme", "1522869635_a99623ba671a.webp", "District Industries Centre Micro Enterprise Subsidy Interview and Sanction Procedure"),
    ("work-from-home-jobs", "1526304640_ce4c46bf6097.webp", "Remote Professional Digital Workplace Ergonomics and High Speed Broadband Architecture"),
]

def main():
    for slug, img_name, alt_text in PAGES_AND_IMAGES:
        page_path = SITES_DIR / "loanraaj.com" / slug / "index.html"
        if not page_path.exists():
            continue
            
        raw = page_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")
        
        post_content = soup.find("div", class_="post-content") or soup.find("article")
        if not post_content:
            continue
            
        fig_html = f'''
<figure class="content-image my-6">
    <img alt="{alt_text}" class="rounded-lg shadow-md mx-auto" height="450" loading="lazy" src="/img/{img_name}" width="800"/>
    <figcaption class="text-sm text-gray-500 mt-2 text-center">{alt_text}: Institutional analytical benchmark data.</figcaption>
</figure>
'''
        fig_soup = BeautifulSoup(fig_html, "html.parser").find("figure")
        post_content.append(fig_soup)
        
        page_path.write_text(str(soup), encoding="utf-8")
        print(f"Added 5th image to loanraaj.com/{slug}")

if __name__ == "__main__":
    main()
