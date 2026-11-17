from pathlib import Path
from bs4 import BeautifulSoup

p = Path("sites/loanraaj.com/secured-overdraft-facility-against-property-interest-ma/index.html")
raw = p.read_text(encoding="utf-8", errors="ignore")
soup = BeautifulSoup(raw, "html.parser")

post_paper = soup.find("div", class_="post-paper")
if post_paper:
    for old in post_paper.find_all("div", class_="post-content"):
        old.decompose()
    
    new_html = """<div class="post-content">
<p class="lead">A secured overdraft facility against property allows commercial borrowers and real estate owners to access revolving working capital against mortgaged residential, commercial, or industrial real estate assets with interest charged solely on utilized funds.</p>

<figure class="article-figure" style="margin:28px 0; text-align:center;">
    <img src="/img/1434030216_181bd8139626.webp" alt="Secured Overdraft Facility Against Property statutory credit evaluation" width="1200" height="675" loading="lazy" style="width:100%; height:auto; border-radius:8px;">
    <figcaption style="font-size:13px; color:#6b7280; margin-top:8px;">Institutional collateral valuation and loan-to-value limits for property-backed overdraft credit.</figcaption>
</figure>

<h2>Interest Rate Structures and Utilization Charges</h2>
<p>Unlike standard term loans where interest accumulates across the sanctioned principal, an overdraft facility computes interest on a daily closing balance method. Borrowers servicing credit lines against clear residential titles typically secure competitive margins benchmarked to the bank repo-linked lending rate (RLLR).</p>
<p>Maintaining high collateral liquidity enables business operators to draw funds during seasonal working capital shortages and repay principal immediately upon customer receivable clearance, substantially curbing total financing overhead.</p>

<figure class="article-figure" style="margin:28px 0; text-align:center;">
    <img src="/img/1436491865_23b53a6f74b9.webp" alt="Interest Rate Slabs and Utilization Margins for Property Overdraft Credit" width="1200" height="675" loading="lazy" style="width:100%; height:auto; border-radius:8px;">
    <figcaption style="font-size:13px; color:#6b7280; margin-top:8px;">Comparative appraisal of sanctioned overdraft limits versus effective interest outlays.</figcaption>
</figure>

<div class="table-responsive">
    <table class="article-table">
        <thead>
            <tr>
                <th>Property Category</th>
                <th>Standard LTV Ratio</th>
                <th>Benchmark Interest Slabs</th>
                <th>Annual Review Charges</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Residential Self-Occupied</td>
                <td>Up to 65% Market Value</td>
                <td>8.85% - 9.75% Per Annum</td>
                <td>0.25% or ₹5,000 Flat</td>
            </tr>
            <tr>
                <td>Commercial Office / Retail</td>
                <td>Up to 55% Market Value</td>
                <td>9.50% - 10.80% Per Annum</td>
                <td>0.50% + GST</td>
            </tr>
            <tr>
                <td>Industrial Warehouse / Shed</td>
                <td>Up to 50% Market Value</td>
                <td>10.25% - 11.50% Per Annum</td>
                <td>0.50% + GST</td>
            </tr>
        </tbody>
    </table>
</div>

<figure class="article-figure" style="margin:28px 0; text-align:center;">
    <img src="/img/1000063733-ezgi_511eddf01105.webp" alt="Documentation Checklist for Secured Property Overdraft Approval" width="1200" height="675" loading="lazy" style="width:100%; height:auto; border-radius:8px;">
    <figcaption style="font-size:13px; color:#6b7280; margin-top:8px;">Mandatory property search reports, encumbrance verification, and income validation workflow.</figcaption>
</figure>

<h2>Eligibility Criteria and Legal Search Requirements</h2>
<p>Lending institutions conduct thorough 30-year title searches, municipal tax verification, and independent structural evaluations before issuing formal overdraft sanction letters. Borrowers must possess registered sale deeds, sanction plans approved by local urban authorities, and latest non-encumbrance certificates.</p>
<p>Additionally, commercial business entities must furnish audited balance sheets for consecutive financial years demonstrating healthy debt service coverage ratios and consistent operational cash flows.</p>

<figure class="article-figure" style="margin:28px 0; text-align:center;">
    <img src="/img/1000104511-70kb_7aae85c1e860.webp" alt="Annual Renewal Procedures and Bank Compliance for Overdraft Accounts" width="1200" height="675" loading="lazy" style="width:100%; height:auto; border-radius:8px;">
    <figcaption style="font-size:13px; color:#6b7280; margin-top:8px;">Periodic property inspection and account turnover monitoring guidelines.</figcaption>
</figure>

<h2>Step-by-Step Application and Sanction Workflow</h2>
<p>Applicants begin by submitting primary property deeds alongside certified financial statements to the underwriting branch. The lender assigns an empaneled legal advocate to draft the search report while an authorized surveyor inspects real estate boundaries to establish fair market value.</p>
<p>Following title clearance and credit committee approval, equitable mortgage is registered with CERSAI, and the sanctioned credit line is activated within the designated operational current account.</p>

<figure class="article-figure" style="margin:28px 0; text-align:center;">
    <img src="/img/1000111648-60kb_e46773729705.webp" alt="Repayment Discipline and Collateral Release Protocols" width="1200" height="675" loading="lazy" style="width:100%; height:auto; border-radius:8px;">
    <figcaption style="font-size:13px; color:#6b7280; margin-top:8px;">Protocols for line closure, full no-objection certificates, and original title deed recovery.</figcaption>
</figure>
</div>"""
    
    post_paper.append(BeautifulSoup(new_html, "html.parser"))
    p.write_text(str(soup), encoding="utf-8")
    print("Updated secured overdraft article successfully!")
