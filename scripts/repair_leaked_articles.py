#!/usr/bin/env python3
"""
scripts/repair_leaked_articles.py — Regenerate the 4 leaked articles with genuine FreeLLMAPI content
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup
from autopublish_engine import generate_claude_seo_article
from scripts.fix_article_images import fix_images_in_article

LEAKED_TOPICS = [
    {
        "site_id": "loanraaj",
        "site_info": {"name": "LoanRaaj", "domain": "loanraaj.com"},
        "path": Path("sites/loanraaj.com/warehouse-lease-financing-structuring-industrial-logist/index.html"),
        "brief": {
            "primary_keyword": "Warehouse Lease Financing: Structuring Industrial Logistics Hubs with Bank Credit",
            "lsi_keywords": ["warehouse lease rental discounting", "industrial logistics bank credit", "LRD interest rate SBI HDFC"],
            "category": "Business Loans & Infrastructure"
        }
    },
    {
        "site_id": "loankiseva",
        "site_info": {"name": "LoanKiSeva", "domain": "loankiseva.com"},
        "path": Path("sites/loankiseva.com/pm-mudra-loan-apply-online-2026-sbi/index.html"),
        "brief": {
            "primary_keyword": "PM Mudra Loan Apply Online 2026 SBI: Step-by-Step Application, Eligibility & Helpline",
            "lsi_keywords": ["sbi pm mudra loan 2026 online apply", "mudra shishu kishore tarun sbi yono", "mudra loan interest rate sbi 50000"],
            "category": "Government Loans & MSME Subsidies"
        }
    },
    {
        "site_id": "loanraaj",
        "site_info": {"name": "LoanRaaj", "domain": "loanraaj.com"},
        "path": Path("sites/loanraaj.com/how-to-import-industrial-packaging-machinery-from-taiwa/index.html"),
        "brief": {
            "primary_keyword": "How to Import Industrial Packaging Machinery from Taiwan: Customs Tariffs & Bank LC",
            "lsi_keywords": ["import machinery taiwan letter of credit bank", "customs duty packaging equipment india", "epcg scheme capital goods import"],
            "category": "Commercial Equipment & Business Finance"
        }
    },
    {
        "site_id": "rechargetak",
        "site_info": {"name": "RechargeTak", "domain": "rechargetak.com"},
        "path": Path("sites/rechargetak.com/fastag-double-toll-deduction-disputes-how-to-claim-auto/index.html"),
        "brief": {
            "primary_keyword": "FASTag Double Toll Deduction Disputes: How to Claim Automatic NPCI Refunds",
            "lsi_keywords": ["fastag double deduction complaint npci", "toll plaza chargeback dispute 1033", "paytm airtel sbi fastag refund procedure"],
            "category": "FASTag & Digital Toll Disputes"
        }
    }
]


def repair_file(entry):
    path = (ROOT / entry["path"]).resolve()
    print(f"Generating content for {path}...")
    html_content, faqs = generate_claude_seo_article(
        entry["site_id"], entry["site_info"], entry["brief"]
    )
    
    file_text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(file_text, "html.parser")
    post_content = soup.find("div", class_="post-content")
    if not post_content:
        post_content = soup.find("article")
    
    if not post_content:
        print(f"Error: could not find post-content in {path}")
        return False
        
    # Replace contents of post-content with new generated HTML
    content_soup = BeautifulSoup(html_content, "html.parser")
    post_content.clear()
    for child in list(content_soup.children):
        post_content.append(child)
        
    path.write_text(str(soup), encoding="utf-8")
    
    # Run image injector to guarantee >=5 self-hosted images and clean alt text
    fix_images_in_article(path)
    print(f"Successfully repaired {path}")
    return True


def main():
    for entry in LEAKED_TOPICS:
        repair_file(entry)
    print("All leaked files repaired!")


if __name__ == "__main__":
    main()
