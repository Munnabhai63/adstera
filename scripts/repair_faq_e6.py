#!/usr/bin/env python3
"""
scripts/repair_faq_e6.py — Add FAQ block and FAQPage schema to E6 articles.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 1. hotshot-trucking-insurance
p1 = PROJECT_ROOT / "sites" / "loanraaj.com" / "hotshot-trucking-insurance" / "index.html"
txt1 = p1.read_text(encoding="utf-8")

faq_html1 = """<h2 id="section-faq">Frequently Asked Questions</h2>
<div class="faq-card">
<h3 class="faq-question">❓ What is hotshot trucking insurance and why is it different from standard auto coverage?</h3>
<p class="faq-answer">Hotshot trucking refers to expedited freight delivery using medium-duty trucks, typically Class 3 through Class 5 pickups. It requires specialized commercial coverage because standard personal auto policies exclude freight hauling for compensation.</p>
</div>
<div class="faq-card">
<h3 class="faq-question">❓ Who is required to carry hotshot trucking insurance?</h3>
<p class="faq-answer">If you are hauling freight for compensation using any truck and trailer combination, regardless of truck size or load weight, you are required by law to carry commercial auto liability insurance structured for for-hire motor carriers.</p>
</div>
<div class="faq-card">
<h3 class="faq-question">❓ What are the mandatory FMCSA insurance requirements for hotshot operators?</h3>
<p class="faq-answer">Federal compliance is mandatory for hotshot operators hauling interstate freight for compensation. Operators must maintain minimum primary auto liability coverage (typically $750,000 to $1,000,000) and motor truck cargo insurance to comply with FMCSA filings.</p>
</div>
"""

schema1 = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is hotshot trucking insurance and why is it different from standard auto coverage?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Hotshot trucking refers to expedited freight delivery using medium-duty trucks, typically Class 3 through Class 5 pickups. It requires specialized commercial coverage because standard personal auto policies exclude freight hauling for compensation."
      }
    },
    {
      "@type": "Question",
      "name": "Who is required to carry hotshot trucking insurance?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "If you are hauling freight for compensation using any truck and trailer combination, regardless of truck size or load weight, you are required by law to carry commercial auto liability insurance structured for for-hire motor carriers."
      }
    },
    {
      "@type": "Question",
      "name": "What are the mandatory FMCSA insurance requirements for hotshot operators?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Federal compliance is mandatory for hotshot operators hauling interstate freight for compensation. Operators must maintain minimum primary auto liability coverage (typically $750,000 to $1,000,000) and motor truck cargo insurance to comply with FMCSA filings."
      }
    }
  ]
}
</script>
"""

# 2. commercial-auto-insurance-quotes
p2 = PROJECT_ROOT / "sites" / "loanraaj.com" / "commercial-auto-insurance-quotes" / "index.html"
txt2 = p2.read_text(encoding="utf-8")

faq_html2 = """<h2 id="section-faq">Frequently Asked Questions</h2>
<div class="faq-card">
<h3 class="faq-question">❓ What is commercial auto insurance and who needs it?</h3>
<p class="faq-answer">Commercial auto insurance is a category of vehicle insurance specifically designed to cover vehicles used for business purposes. Any business or individual using vehicles to transport goods, tools, equipment, or passengers for compensation needs dedicated commercial auto coverage.</p>
</div>
<div class="faq-card">
<h3 class="faq-question">❓ What core coverage components are included in a commercial auto insurance quote?</h3>
<p class="faq-answer">A commercial auto insurance quote consists of multiple coverage layers, including commercial auto liability (bodily injury and property damage), physical damage (collision and comprehensive), uninsured motorist coverage, and cargo or inland marine protections.</p>
</div>
<div class="faq-card">
<h3 class="faq-question">❓ What information is required before requesting commercial auto insurance quotes?</h3>
<p class="faq-answer">Requesting accurate commercial auto quotes requires complete information ready upfront: vehicle identification numbers (VINs), driver license numbers with motor vehicle records (MVR), loss run reports for the past three to five years, and clear details of your operating radius and business use.</p>
</div>
"""

schema2 = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is commercial auto insurance and who needs it?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Commercial auto insurance is a category of vehicle insurance specifically designed to cover vehicles used for business purposes. Any business or individual using vehicles to transport goods, tools, equipment, or passengers for compensation needs dedicated commercial auto coverage."
      }
    },
    {
      "@type": "Question",
      "name": "What core coverage components are included in a commercial auto insurance quote?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "A commercial auto insurance quote consists of multiple coverage layers, including commercial auto liability (bodily injury and property damage), physical damage (collision and comprehensive), uninsured motorist coverage, and cargo or inland marine protections."
      }
    },
    {
      "@type": "Question",
      "name": "What information is required before requesting commercial auto insurance quotes?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Requesting accurate commercial auto quotes requires complete information ready upfront: vehicle identification numbers (VINs), driver license numbers with motor vehicle records (MVR), loss run reports for the past three to five years, and clear details of your operating radius and business use."
      }
    }
  ]
}
</script>
"""


def apply_faq(path: Path, txt: str, faq_html: str, schema_html: str) -> None:
    head_pos = txt.find("</head>")
    assert head_pos != -1, f"No </head> in {path}"
    txt = txt[:head_pos] + schema_html + "\n" + txt[head_pos:]

    pc_idx = txt.find('<div class="post-content">')
    assert pc_idx != -1, f"No post-content in {path}"
    close_pc = txt.find('</div>\n<div class="ad-slot-box">', pc_idx)
    if close_pc == -1:
        close_pc = txt.find('</div>\n<!-- Author Box -->', pc_idx)
    assert close_pc != -1, f"No closing post-content in {path}"
    txt = txt[:close_pc] + faq_html + "\n" + txt[close_pc:]

    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(txt, encoding="utf-8", newline="\n")
    print(f"Applied FAQ to {path.parent.name}/{path.name}")


if __name__ == "__main__":
    apply_faq(p1, txt1, faq_html1, schema1)
    apply_faq(p2, txt2, faq_html2, schema2)
