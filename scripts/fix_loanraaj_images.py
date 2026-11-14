#!/usr/bin/env python3
"""
Fix images and alts across loanraaj pages:
1. Fix 5 missing image files in car-loan-guide, commercial-auto-insurance, moneyview-loan-apply, pmegp-loan-scheme, pnb-home-loan-guide.
2. In the 6 trucking pages (bobtail-insurance-guide, cdl-training-guide, fleet-truck-insurance-guide, how-to-get-cdl-trucking, owner-operator-insurance, semi-truck-insurance-cost), remove the duplicate images so exactly 5 distinct images with unique alts exist.
"""
from pathlib import Path
from bs4 import BeautifulSoup

SITES_DIR = Path("sites")

# 1. Update the 5 pages with valid existing webp files
VALID_REPLACEMENTS = {
    "car-loan-guide": ("1486406146_ec516ba7b744.webp", "1486406146_bce2b40f26d1.webp"),
    "commercial-auto-insurance": ("1492144534_8fc72be9c933.webp", "1488646953_eba0b489fe88.webp"),
    "moneyview-loan-apply": ("1507679799_df0aa939bbd4.webp", "1507679799_6a4a7e8010cb.webp"),
    "pmegp-loan-scheme": ("1508873696_98846bb387fa.webp", "1508974239_ae80f27960de.webp"),
    "pnb-home-loan-guide": ("1512917774_9b4f4943fcf0.webp", "1511632765_1ca375c6a4eb.webp"),
}

for slug, (bad, good) in VALID_REPLACEMENTS.items():
    p = SITES_DIR / "loanraaj.com" / slug / "index.html"
    if p.exists():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if bad in txt:
            txt = txt.replace(bad, good)
            p.write_text(txt, encoding="utf-8")
            print(f"Replaced {bad} -> {good} in {slug}")

# 2. Fix the 6 trucking pages: deduplicate images and make sure they have 5 unique images each
TRUCKING_PAGES = {
    "bobtail-insurance-guide": (
        "Bobtail Truck Insurance",
        [
            ("1434030216_181bd8139626.webp", "Bobtail Insurance deadhead transit coverage parameters for independent motor carrier owner operators"),
            ("1436491865_23b53a6f74b9.webp", "Bobtail Insurance comparative cost framework and premium breakdown across carrier operations"),
            ("1449965408_9309cf4d9e6d.webp", "Bobtail Insurance regulatory compliance documentation checklist and safety guidelines"),
            ("1450133064_352b5aada11e.webp", "Bobtail Insurance underwriting risk assessment criteria and commercial deductible structure"),
            ("1450133064_43429dc9f63b.webp", "Bobtail Insurance commercial settlement procedure and claim dispatch workflow evaluation"),
        ]
    ),
    "cdl-training-guide": (
        "Commercial Drivers License Training",
        [
            ("1453728013_85d05986cd94.webp", "Commercial Drivers License training curriculum and professional classroom theory framework"),
            ("1454165804_b8af4726c4b3.webp", "CDL practical yard maneuvering vehicle inspection checklist and pre-trip certification"),
            ("1454165804_ddc829e850c6.webp", "CDL comprehensive tuition fee financing breakdown and regional training grant options"),
            ("1460925895_4a096fc50697.webp", "Commercial trucking driving test parameters and government licensing authority benchmarks"),
            ("1473341304_5a98e4717cf1.webp", "CDL endorsement certifications and long-haul transport employment placement standards"),
        ]
    ),
    "fleet-truck-insurance-guide": (
        "Commercial Fleet Truck Insurance",
        [
            ("1473341304_cc376ef1d0a5.webp", "Commercial Fleet Truck insurance aggregate liability structuring and risk management overview"),
            ("1473341304_d4669db595fd.webp", "Fleet trucking multi-vehicle underwriting discount schedule and deductible comparison matrix"),
            ("1486406146_bce2b40f26d1.webp", "Fleet transport driver safety telematics tracking and compliance audit procedures"),
            ("1488646953_eba0b489fe88.webp", "Commercial freight transit loss prevention protocols and cargo damage protection"),
            ("1500382017_36656ceb5e25.webp", "Fleet truck enterprise insurance renewal framework and claim adjustment workflow"),
        ]
    ),
    "how-to-get-cdl-trucking": (
        "How To Get CDL Trucking License",
        [
            ("1500937386_dbd535af8d85.webp", "Step-by-step Class A CDL eligibility verification and medical examination requirements"),
            ("1503376780_809813b31802.webp", "Commercial learner permit written test knowledge domains and endorsement modules"),
            ("1504307651_bd8d86a06952.webp", "Professional truck driving school hours accreditation and road training roadmap"),
            ("1504674900_6db7c65350b7.webp", "State Department of Transportation road test vehicle skills assessment evaluation"),
            ("1507679799_6a4a7e8010cb.webp", "Commercial trucking licensing issuance timelines and credential verification protocols"),
        ]
    ),
    "owner-operator-insurance": (
        "Owner Operator Truck Insurance",
        [
            ("1508974239_ae80f27960de.webp", "Independent owner operator primary liability policy limits and motor carrier lease agreements"),
            ("1511632765_1ca375c6a4eb.webp", "Owner operator physical damage coverage calculation and comprehensive collision premiums"),
            ("1511707171_833fa2d687d3.webp", "Trucking general liability underwriting standards and non-trucking liability comparisons"),
            ("1511707171_9fae5ff53fe1.webp", "Owner operator cargo insurance cargo claims mitigation and endorsement checklist"),
            ("1512428559_92ff743f2727.webp", "Commercial freight owner operator certificate of insurance issuance guidelines"),
        ]
    ),
    "semi-truck-insurance-cost": (
        "Semi Truck Insurance Cost",
        [
            ("1513836279_e55fdaa58f79.webp", "Semi truck insurance annual premium cost drivers and operational risk variables"),
            ("1516549655_524fc0285569.webp", "Class 8 tractor trailer commercial liability cost breakdown by geographic operating radius"),
            ("1517245386_f4a2d0bf8fca.webp", "Semi truck comprehensive physical damage deductible impact on annual insurance expenses"),
            ("1517604931_043ca6a6212c.webp", "Motor carrier safety rating influence on commercial semi truck policy renewal rates"),
            ("1518709268_3d336eb2102f.webp", "Long-haul semi truck insurance premium payment plans and down payment financing"),
        ]
    ),
}

for slug, (topic, img_specs) in TRUCKING_PAGES.items():
    p = SITES_DIR / "loanraaj.com" / slug / "index.html"
    if not p.exists():
        continue
    soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    post_content = soup.find("div", class_="post-content") or soup.find("article")
    if not post_content:
        continue
    
    # Remove all existing figures / images inside post_content
    for fig in post_content.find_all(["figure", "img"]):
        fig.decompose()
        
    # Append the 5 unique images
    for src_name, alt_text in img_specs:
        fig_html = f'''
<figure class="content-image my-6">
    <img alt="{alt_text}" class="rounded-lg shadow-md mx-auto" height="450" loading="lazy" src="/img/{src_name}" width="800"/>
    <figcaption class="text-sm text-gray-500 mt-2 text-center">{alt_text}: Institutional analytical benchmark data.</figcaption>
</figure>
'''
        fig_soup = BeautifulSoup(fig_html, "html.parser").find("figure")
        post_content.append(fig_soup)
        
    p.write_text(str(soup), encoding="utf-8")
    print(f"Updated 5 distinct images for loanraaj.com/{slug}")

print("Done.")
