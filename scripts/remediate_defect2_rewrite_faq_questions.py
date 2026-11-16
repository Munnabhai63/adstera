"""Remediate Defect 2: Rewrite 15 FAQ entries that are not questions across 8 pages.

Rules:
- Every rewritten question ends in ?.
- Answers actually answer the question and land 40-80 words.
- In rechargepur/sbi-vs-hdfc-electricity-bill-payment: collapse 4 steps into 1 consolidated question + answer.
- Resync JSON-LD FAQPage schema so body and schema are 100% in sync.
- Verify faq_matches_ok remains True.
- Strictly LF line endings.
"""

import json
import re
import sys
from pathlib import Path
import bs4

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seo_onpage_audit import audit_article

REWRITES = {
    "karzseva.com/low-cibil-score-options-for-how-to-clear-credit-card-de/index.html": {
        "Common Mistakes to Avoid When Clearing Credit Card Debt": (
            "What are the most common mistakes to avoid when clearing credit card debt?",
            "Borrowers clearing credit card debt commonly err by paying only the minimum due amount, which causes compounding interest rates up to 45% annually. Other costly mistakes include closing oldest credit card accounts abruptly, neglecting to request a written No Dues Certificate after settlement, or executing high-fee balance transfers without verifying processing charges under RBI Fair Practices Code guidelines."
        ),
        "Dispute Resolution Process for Credit Card Debts": (
            "How does the dispute resolution process work for disputed credit card debts?",
            "When encountering disputed charges or incorrect credit bureau reporting, cardholders must first file a formal written complaint with the card issuer's grievance redressal cell within thirty days. If the bank fails to provide a satisfactory resolution within thirty days, the customer can escalate the dispute to the Reserve Bank of India Banking Ombudsman for binding investigation and correction."
        )
    },
    "karzseva.com/settled-vs-closed-loan-in-cibil/index.html": {
        "How to Upgrade Your CIBIL Score After a Settlement": (
            "How can borrowers upgrade their CIBIL score after settling a distressed loan?",
            "Borrowers must first approach the original lending institution to pay the waived balance amount, converting the credit bureau status from Settled to Closed and obtaining a formal No Dues Certificate. Subsequently, opening a fixed-deposit-backed secured credit card and maintaining on-time repayments for twelve to twenty-four consecutive months systematically repairs the bureau score above 750."
        )
    },
    "loankiseva.com/annapurna-scheme-for-food-catering-businesses-equipment/index.html": {
        "Common Mistakes to Avoid When Applying for Annapurna Scheme": (
            "What common mistakes should catering entrepreneurs avoid when applying for the Annapurna Scheme?",
            "Applicants under the Annapurna Scheme frequently make errors such as submitting unverified equipment vendor quotations, failing to provide required third-party guarantor credentials, or operating without mandatory FSSAI food safety registrations. Ensuring complete project report documentation and maintaining clean tax compliance records prevents application rejection across State Bank of India and nationalized partner bank branches."
        ),
        "Dispute Resolution Mechanism Under Annapurna Scheme": (
            "What dispute resolution mechanisms are available under the Annapurna Scheme?",
            "If an entrepreneur encounters processing delays or disputed subsidy calculations, the issue can be formally escalated to the branch credit committee or the regional MSME development commissioner. For unresolved institutional grievances, applicants are entitled to lodge complaints through the government's centralized public grievance portal or escalate directly to the designated Banking Ombudsman."
        )
    },
    "rechargetak.com/corporate-sim-to-personal-mnp-transfer-noc-format-billi/index.html": {
        "Institutional Comparisons": (
            "How do corporate SIM to personal MNP charges and procedures compare across major telecom operators?",
            "Corporate-to-personal number porting policies vary across operators while adhering to TRAI portability regulations. Reliance Jio and Bharti Airtel process corporate individual migration digitally within three to five working days once company NOC validation completes, whereas Vodafone Idea and BSNL require physical authorized signatory signatures and full clearance of the corporate account's outstanding billing cycle before releasing porting authorization codes."
        )
    },
    "tazabhav.com/how-to-claim-maximum-cashback-fee-waiver-on-silver-pric/index.html": {
        "Common Mistakes to Avoid When Investing in Silver": (
            "What are the most critical mistakes to avoid when purchasing physical or digital silver?",
            "Investors frequently overlook essential verification standards when purchasing silver, such as buying non-hallmarked physical bullion, paying excessive retail making charges exceeding ten percent, or ignoring vault storage fees. In digital silver holdings, failing to verify physical asset backing or neglecting short-term capital gains tax obligations can significantly reduce net annualized investment returns."
        ),
        "Dispute Resolution in Silver Investments": (
            "How does the dispute resolution mechanism work for retail silver transactions?",
            "For physical hallmarked silver transactions, disputes concerning purity discrepancies or assay certification failures can be formally registered with the Bureau of Indian Standards consumer portal. For digital silver or commodity futures contracts, grievances regarding trade execution or custodial holdings must be filed through SEBI SCORES or the relevant national commodity exchange investor protection cell."
        )
    },
    "tazaloan.com/sbi-vs-hdfc-urgent-cash-loan-today-real-interest-rate-c/index.html": {
        "Dispute Resolution Process for SBI and HDFC Loans": (
            "What is the dispute resolution process for personal loan issues with SBI and HDFC Bank?",
            "Borrowers experiencing interest calculation discrepancies or unauthorized loan fee deductions should submit a formal complaint through the bank's internal grievance portal or contact the principal nodal officer. If the lending institution does not resolve the complaint within thirty days, the borrower is legally entitled to escalate the dispute to the RBI Integrated Ombudsman Scheme for independent adjudication."
        )
    },
    "tazarokda.com/rbi-guidelines-for-top-mutual-funds-sip-2026-in-india-s/index.html": {
        "Common Mistakes to Avoid in Mutual Fund SIP Investments": (
            "What common mistakes should investors avoid when investing in mutual fund SIPs?",
            "Common mutual fund SIP mistakes include pausing installments during market downturns, selecting dividend payout options instead of growth for compounding, and duplicating portfolio holdings across identical large-cap funds. Maintaining consistent disciplined monthly investments across full market cycles captures rupee cost averaging benefits and maximizes risk-adjusted long-term wealth creation."
        ),
        "Dispute Resolution Mechanisms for Mutual Fund SIP Investors": (
            "What dispute resolution mechanisms protect mutual fund SIP investors under regulatory rules?",
            "Mutual fund investors encountering operational failures such as delayed NAV allotment, unauthorized redemption, or uncredited dividends can file formal complaints directly with the Asset Management Company. If the issue remains unresolved after twenty-one days, investors can escalate the dispute to SEBI via the SCORES 2.0 portal or access SMART ODR for independent conciliation and arbitration."
        )
    }
}

CONSOLIDATED_ELECTRICITY_PAGE = "rechargepur.com/sbi-vs-hdfc-electricity-bill-payment-cashback-google-pa/index.html"
CONSOLIDATED_Q = "How do I check and resolve the status of an electricity bill cashback transaction across SBI and HDFC?"
CONSOLIDATED_A = "To resolve pending or uncredited electricity bill cashback transactions, first verify the payment confirmation and unique UTR reference within Google Pay or your mobile banking portal. Second, contact the customer service desk of SBI or HDFC with your biller consumer number. If the query remains pending after forty-eight hours, escalate to the bank's principal nodal officer or lodge a formal complaint with the RBI Banking Ombudsman for prompt resolution."


def resync_schema_from_body(soup: bs4.BeautifulSoup, page_url: str):
    faq_cards = soup.find_all(class_="faq-card")
    entities = []
    
    for card in faq_cards:
        q_el = card.find(class_="faq-question")
        a_el = card.find(class_="faq-answer")
        if not q_el or not a_el:
            continue
            
        q_text = q_el.get_text().strip()
        q_clean = q_text.replace("❓", "").strip()
        a_text = a_el.get_text().strip()
        
        entities.append({
            "@type": "Question",
            "name": q_clean,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": a_text
            }
        })
        
    # Update script tag
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or "{}")
            graph = data.get("@graph", [data])
            for item in graph:
                if item.get("@type") == "FAQPage":
                    item["mainEntity"] = entities
                    sc.string = json.dumps(data, indent=2)
                    return
        except Exception:
            pass
            
    # If no FAQPage node was found, create one in @graph
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or "{}")
            if "@graph" in data:
                faq_node = {
                    "@type": "FAQPage",
                    "@id": f"{page_url}#faq",
                    "mainEntity": entities
                }
                data["@graph"].append(faq_node)
                sc.string = json.dumps(data, indent=2)
                return
        except Exception:
            pass


def process_regular_page(rel_path: str, rewrites_dict: dict):
    file_path = PROJECT_ROOT / "sites" / rel_path
    raw_html = file_path.read_text(encoding="utf-8")
    soup = bs4.BeautifulSoup(raw_html, "html.parser")
    
    faq_cards = soup.find_all(class_="faq-card")
    rewritten_count = 0
    
    for card in faq_cards:
        q_el = card.find(class_="faq-question")
        a_el = card.find(class_="faq-answer")
        if not q_el or not a_el:
            continue
            
        q_text = q_el.get_text().strip()
        for target_sub, (new_q, new_a) in rewrites_dict.items():
            if target_sub in q_text:
                q_el.string = f"❓ {new_q}"
                a_el.string = new_a
                rewritten_count += 1
                break
                
    # Resync schema
    page_url = f"https://{rel_path.split('/')[0]}/{rel_path.split('/')[1]}"
    resync_schema_from_body(soup, page_url)
    
    out_html = str(soup).replace("\r\n", "\n")
    file_path.write_text(out_html, encoding="utf-8", newline="\n")
    print(f"Processed {rel_path}: {rewritten_count} questions rewritten.")


def process_electricity_page():
    file_path = PROJECT_ROOT / "sites" / CONSOLIDATED_ELECTRICITY_PAGE
    raw_html = file_path.read_text(encoding="utf-8")
    soup = bs4.BeautifulSoup(raw_html, "html.parser")
    
    step_targets = [
        "Step 1: Check Transaction Status",
        "Step 2: Contact Customer Service",
        "Step 3: Escalate the Issue",
        "Step 4: Lodge a Complaint with Banking Ombudsman"
    ]
    
    faq_cards = soup.find_all(class_="faq-card")
    first_step_card = None
    step_cards_to_remove = []
    
    for card in faq_cards:
        q_el = card.find(class_="faq-question")
        if not q_el:
            continue
        q_text = q_el.get_text().strip()
        if any(t in q_text for t in step_targets):
            if first_step_card is None:
                first_step_card = card
            else:
                step_cards_to_remove.append(card)
                
    if first_step_card:
        q_el = first_step_card.find(class_="faq-question")
        a_el = first_step_card.find(class_="faq-answer")
        q_el.string = f"❓ {CONSOLIDATED_Q}"
        a_el.string = CONSOLIDATED_A
        
    for c in step_cards_to_remove:
        c.decompose()
        
    page_url = f"https://rechargepur.com/sbi-vs-hdfc-electricity-bill-payment-cashback-google-pa"
    resync_schema_from_body(soup, page_url)
    
    out_html = str(soup).replace("\r\n", "\n")
    file_path.write_text(out_html, encoding="utf-8", newline="\n")
    print(f"Processed {CONSOLIDATED_ELECTRICITY_PAGE}: consolidated 4 step cards into 1.")


def main():
    print("Starting Defect 2 remediation...")
    for rel_path, r_dict in REWRITES.items():
        process_regular_page(rel_path, r_dict)
        
    process_electricity_page()
    
    # Audit all 8 pages
    print("\nVerifying on-page audit on all 8 remediated pages:")
    all_ok = True
    for rel_path in list(REWRITES.keys()) + [CONSOLIDATED_ELECTRICITY_PAGE]:
        res = audit_article("sites/" + rel_path)
        faq_ok = res.get("faq_matches_ok")
        dup_ok = res.get("dup_headings_ok")
        print(f"{rel_path[:45]:45} | faq_matches_ok={faq_ok} | dup_headings_ok={dup_ok}")
        if not faq_ok or not dup_ok:
            all_ok = False
            
    if all_ok:
        print("\nAll 8 pages successfully verified! Defect 2 complete.")
    else:
        print("\nERRORS encountered during audit check.")
        sys.exit(1)

if __name__ == "__main__":
    main()
