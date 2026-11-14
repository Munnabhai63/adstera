import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from bs4 import BeautifulSoup
from tests.test_p3_images import _extract_content_images

fixes = [
    (
        "sites/loanraaj.com/commercial-truck-eld-mandate-violations-fines-log-audit/index.html",
        [
            ("/img/1449965408_9309cf4d9e6d.webp", "Electronic Logging Device Compliance Audit and Record Verification Process")
        ]
    ),
    (
        "sites/loanraaj.com/intermodal-cargo-insurance-guide-marine-rail-highway-fr/index.html",
        [
            ("/img/1434030216_181bd8139626.webp", "Intermodal Freight Transit Liability Protocols Across Rail Highway Corridors"),
            ("/img/1436491865_23b53a6f74b9.webp", "Marine Container Indemnity Standards and Multi Modal Transit Risk Valuation"),
            ("/img/1449965408_9309cf4d9e6d.webp", "Commercial Freight Carrier Claim Settlement and Underwriting Framework")
        ]
    ),
    (
        "sites/rechargepur.com/residential-solar-net-metering-billing-cycles-export-un/index.html",
        [
            ("/img/1449965408_9309cf4d9e6d.webp", "Rooftop Photovoltaic Net Metering Settlement and Export Unit Credit Reconciliation")
        ]
    )
]

for file_str, to_add in fixes:
    p = PROJECT_ROOT / file_str
    raw = p.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    content = soup.find("div", class_="post-content") or soup.find("div", class_="post-body")
    if content:
        for src, alt in to_add:
            fig = soup.new_tag("figure", attrs={"class": "article-figure", "style": "margin:28px 0; text-align:center;"})
            img = soup.new_tag("img", attrs={
                "src": src,
                "alt": alt,
                "width": "1200",
                "height": "675",
                "loading": "lazy",
                "style": "width:100%; height:auto; border-radius:8px;"
            })
            cap = soup.new_tag("figcaption", attrs={"style": "font-size:13px; color:#6b7280; margin-top:8px;"})
            cap.string = alt
            fig.append(img)
            fig.append(cap)
            content.append(fig)
        p.write_text(str(soup), encoding="utf-8")
        print(f"Added {len(to_add)} images to {file_str}")
