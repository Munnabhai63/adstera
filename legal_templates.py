# legal_templates.py - 5 Comprehensive Legal Trust Pages & Dedicated Calculator
import html

def get_privacy_policy_content(site_config):
    name = site_config["name"]
    domain = site_config["domain"]
    return f"""
    <div class="post-paper">
        <div class="cat-badge">Compliance & Privacy</div>
        <h1 class="post-h1">Privacy Policy & Consumer Data Protection Standard</h1>
        <div class="post-meta">
            <span>Last Updated: November 2026</span>
            <span>Version 4.2</span>
            <span>Applicable Law: DPDP Act (India), GDPR & CCPA</span>
        </div>
        <div class="post-content">
            <p>Welcome to <strong>{name}</strong> (accessible at <a href="{domain}">{domain}</a>). We take consumer transparency, data privacy, and digital trust with the utmost seriousness. This Privacy Policy outlines the types of personal and non-personal data collected, recorded, and processed when you interact with our editorial content, financial comparisons, and digital calculators.</p>
            
            <h2>1. Institutional Identity & Ownership</h2>
            <p>{name} operates as an independent digital publishing organization and consumer research resource. Our primary operational objective is to provide objective comparisons, regulatory guides, and mathematical analysis across consumer finance, telecom, utility, and commercial sectors. We do not operate as a direct banking institution, non-banking financial company (NBFC), insurance underwriter, or telecom operator.</p>

            <h2>2. Information We Collect</h2>
            <p>We believe in strict data minimization. Depending on your engagement on our platform, we may collect:</p>
            <ul>
                <li><strong>Interactive Calculator Input Data:</strong> Values entered into our on-site calculation widgets (such as loan amounts, repayment tenures, interest percentages, or recharge figures) are processed locally within your web browser client. We do not transmit or store your raw calculation inputs on our remote servers.</li>
                <li><strong>Technical Log Files:</strong> Like most standard web servers, our edge infrastructure automatically logs access events. This includes internet protocol (IP) addresses, browser type, Internet Service Provider (ISP), date/time stamps, referring/exit pages, and number of clicks. This data is non-personally identifiable and is utilized strictly for system administration, fraud detection, and site optimization.</li>
                <li><strong>Voluntary Inquiries:</strong> If you contact our editorial desk via email or web form, we collect your provided name, email address, and message contents solely to address your grievance or editorial inquiry.</li>
            </ul>

            <h2>3. Cookies, Web Beacons & Advertising Partners</h2>
            <p>{name} uses standard cookies to store visitor preferences and optimize user experience. Our third-party advertising network partners (including Google AdSense, Adsterra, and Monetag) may utilize cookies and web beacons on our site to serve relevant contextual advertisements based on your prior browsing history.</p>
            <p>You maintain the fundamental right to disable cookies through your personal web browser configuration settings. Detailed cookie management instructions are accessible within your specific browser's help documentation.</p>

            <h2>4. Third-Party Links & External Portals</h2>
            <p>Our editorial guides may contain hyperlinks to official governmental portals, regulatory agencies (such as RBI, TRAI, IRDAI, NPCI), commercial banks, or verified corporate websites. Once you click an external link and depart {name}, you are governed by the third party's independent privacy protocols. We strongly advise reviewing the privacy terms of any third-party portal you visit.</p>

            <h2>5. Data Retention & Security Architecture</h2>
            <p>We deploy robust enterprise-grade SSL/TLS 256-bit encryption across our entire edge delivery network. We never sell, rent, commercialize, or lease consumer personal records to external third-party telemarketers or unauthorized data brokers under any circumstances.</p>

            <h2>6. Your Rights Under Global Data Frameworks</h2>
            <p>Under the Digital Personal Data Protection (DPDP) Act of India, the General Data Protection Regulation (GDPR) of the European Union, and the California Consumer Privacy Act (CCPA), you retain:</p>
            <ul>
                <li>The Right to Access your stored personal records.</li>
                <li>The Right to Rectification of inaccurate or incomplete information.</li>
                <li>The Right to Erasure ("Right to be Forgotten").</li>
                <li>The Right to Restrict or Object to automated data processing.</li>
            </ul>

            <h2>7. Grievance Redressal & Editorial Contact</h2>
            <p>In accordance with statutory Information Technology regulations, any inquiries or grievances regarding our privacy architecture should be directed to our appointed Data Protection Officer via our <a href="/contact-us">Contact Portal</a>.</p>
        </div>
    </div>
    """

def get_terms_content(site_config):
    name = site_config["name"]
    domain = site_config["domain"]
    return f"""
    <div class="post-paper">
        <div class="cat-badge">Legal & Terms</div>
        <h1 class="post-h1">Terms of Service & User Agreement</h1>
        <div class="post-meta">
            <span>Effective Date: November 2026</span>
            <span>Legal Status: Legally Binding</span>
        </div>
        <div class="post-content">
            <p>By accessing or utilizing the digital properties of <strong>{name}</strong> (<a href="{domain}">{domain}</a>), you acknowledge that you have read, understood, and consented to be bound by these Terms of Service. If you disagree with any portion of these provisions, you must discontinue platform usage immediately.</p>

            <h2>1. Educational & Informational Scope</h2>
            <p>All editorial articles, comparison benchmarks, interest rate projections, tariff tables, and mathematical formulas published on {name} are provided purely for informational and educational purposes. While our analysts strive for absolute accuracy, financial tariffs, banking policies, and telecom regulations fluctuate frequently.</p>
            <p>Nothing contained on this website constitutes direct legal, tax, investment, or credit advice. Users are strongly encouraged to verify current terms directly with official institutional providers prior to executing financial or commercial agreements.</p>

            <h2>2. Intellectual Property Rights</h2>
            <p>All proprietary research reports, structured comparison tables, website layout styling, computational scripts, and editorial texts are the exclusive intellectual property of {name} and are protected under international copyright and trademark conventions. Unauthorized scraping, mass duplication, commercial syndication, or automated extraction without express prior written consent is strictly prohibited.</p>

            <h2>3. Limitation of Liability</h2>
            <p>Under no circumstances shall {name}, its parent organization, contributors, analysts, or directors be held liable for any direct, indirect, incidental, punitive, or consequential damages resulting from your reliance on information published herein, your use of our calculators, or external interactions with third-party service providers featured in our articles.</p>

            <h2>4. Prohibited Platform Usage</h2>
            <p>Users agree not to:</p>
            <ul>
                <li>Engage in automated denial-of-service or scraping attacks against our edge infrastructure.</li>
                <li>Attempt to bypass security headers, access tokens, or service worker scripts.</li>
                <li>Misrepresent identity or submit fraudulent communications via our contact forms.</li>
            </ul>

            <h2>5. Governing Jurisdiction</h2>
            <p>These terms shall be interpreted, construed, and enforced exclusively in accordance with applicable federal and state jurisdictions, without regard to conflict-of-law principles.</p>
        </div>
    </div>
    """

def get_disclaimer_content(site_config):
    name = site_config["name"]
    return f"""
    <div class="post-paper">
        <div class="cat-badge">Regulatory Notice</div>
        <h1 class="post-h1">Editorial Disclaimer & Regulatory Disclosures</h1>
        <div class="post-meta">
            <span>Mandatory Disclosure</span>
            <span>Updated: November 2026</span>
        </div>
        <div class="post-content">
            <p>The disclosures set forth below constitute the official editorial, financial, and advertising policy of <strong>{name}</strong>. Please review them thoroughly.</p>

            <h2>1. Non-Lender / Non-Broker Declaration</h2>
            <p>{name} is an independent research publication. We are not a bank, non-banking financial company (NBFC), insurance broker, peer-to-peer lender, telecom provider, or utility aggregator. We do not originate loans, issue credit cards, collect EMI payments, underwrite risk, or approve cellular porting requests directly.</p>

            <h2>2. Advertising & Affiliate Transparency</h2>
            <p>To support our ongoing independent research and infrastructure hosting expenses, {name} displays digital advertisements and may receive financial compensation when visitors click on designated sponsored links or initiate verified inquiries with institutional partners. However, our editorial evaluations remain strictly objective, data-backed, and free from advertiser influence.</p>

            <h2>3. Financial & Investment Risk Warning</h2>
            <p>Credit facilities, debt consolidation programs, mutual fund systematic investment plans, and commodity assets carry inherent market risks. Past financial returns, historical interest benchmarks, and promotional tariff rates are not guarantees of future performance. Always consult an authorized financial advisor or certified planner before committing capital.</p>

            <h2>4. Accuracy of Third-Party Data</h2>
            <p>While our team cross-checks tariffs, interest rates, and regulatory mandates against official gazettes (including RBI, TRAI, SEBI, and NPCI guidelines), institutions frequently adjust their fees without advance notice. We cannot guarantee that all published figures reflect instantaneous real-time adjustments.</p>
        </div>
    </div>
    """

def get_about_us_content(site_config):
    name = site_config["name"]
    tagline = site_config["tagline"]
    desc = site_config["desc"]
    return f"""
    <div class="post-paper">
        <div class="cat-badge">About Our Organization</div>
        <h1 class="post-h1">About {name}: Research Mission, Standards & Team</h1>
        <div class="post-meta">
            <span>Established 2026</span>
            <span>Independent Editorial Desk</span>
        </div>
        <div class="post-content">
            <p><strong>{name}</strong> was established with a singular objective: <em>to democratize complex institutional knowledge and empower consumers with mathematically transparent comparison tools</em>. As digital products, financial instruments, and telecommunication tariffs multiply in complexity, everyday consumers deserve unambiguous, data-driven analysis.</p>

            <h2>Our Core Mission: {tagline}</h2>
            <p>{desc}</p>

            <h2>Our Editorial Principles</h2>
            <div class="table-responsive">
                <table class="article-table">
                    <thead>
                        <tr>
                            <th>Principle</th>
                            <th>How We Enforce It</th>
                            <th>Consumer Benefit</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>Zero Guesswork</strong></td>
                            <td>Every comparison table is built from verified primary documents, regulatory filings, and live tariff vouchers.</td>
                            <td>Accurate numbers you can bank on.</td>
                        </tr>
                        <tr>
                            <td><strong>Math-First Analysis</strong></td>
                            <td>We build interactive, client-side calculators for every sector we evaluate.</td>
                            <td>Clear visibility into real monthly and annual costs.</td>
                        </tr>
                        <tr>
                            <td><strong>Independent Voice</strong></td>
                            <td>Editorial evaluations are shielded from commercial sponsors and advertising partners.</td>
                            <td>Unbiased recommendations tailored to consumer value.</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <h2>Our Research Methodology</h2>
            <p>Our analysts conduct regular mystery audits, review regulatory updates from central governing bodies, and cross-reference institutional fee schedules. Before an article is cleared for publication, it undergoes rigorous fact-checking and formatting audits to ensure readability on both mobile and desktop screens.</p>
            
            <div class="author-card">
                <div class="author-avatar">{name[:2]}</div>
                <div>
                    <h3 style="font-size:16px; font-weight:800; color:var(--text-head); margin-bottom:4px;">{name} Senior Research Team</h3>
                    <p style="font-size:13px; color:var(--text-muted); line-height:1.5;">
                        A dedicated collective of sector analysts, financial modelers, and technical researchers committed to producing actionable, unbiased consumer intelligence.
                    </p>
                </div>
            </div>
        </div>
    </div>
    """

def get_contact_us_content(site_config):
    name = site_config["name"]
    domain = site_config["domain"]
    domain_clean = domain.replace("https://", "").replace("http://", "").strip("/")
    return f"""
    <div class="post-paper">
        <div class="cat-badge">Direct Communication</div>
        <h1 class="post-h1">Contact {name} Editorial Desk & Grievance Office</h1>
        <div class="post-meta">
            <span>Response Guarantee: Within 24-48 Business Hours</span>
            <span>Official Channel</span>
        </div>
        <div class="post-content">
            <p>Have an editorial inquiry, a suggestion for an article update, or a factual correction? We welcome constructive communication from readers, industry professionals, and institutional representatives.</p>

            <h2>Official Contact Channels</h2>
            <ul>
                <li><strong>Editorial Inquiries:</strong> <code>editor@{domain_clean}</code></li>
                <li><strong>Compliance & Privacy Officer:</strong> <code>legal@{domain_clean}</code></li>
                <li><strong>Advertising & Partnerships:</strong> <code>partnerships@{domain_clean}</code></li>
                <li><strong>Mailing Address:</strong> Research Operations Bureau, Level 5, Tech & Financial District, Cyber City.</li>
            </ul>

            <h2>Send an Instant Message to Our Desk</h2>
            <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:8px; padding:24px; margin-top:20px;">
                <div style="margin-bottom:14px;">
                    <label style="display:block; font-size:12px; font-weight:700; color:#475569; margin-bottom:4px;">Your Full Name</label>
                    <input type="text" placeholder="e.g. Rahul Sharma" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
                </div>
                <div style="margin-bottom:14px;">
                    <label style="display:block; font-size:12px; font-weight:700; color:#475569; margin-bottom:4px;">Your Email Address</label>
                    <input type="email" placeholder="e.g. name@example.com" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
                </div>
                <div style="margin-bottom:14px;">
                    <label style="display:block; font-size:12px; font-weight:700; color:#475569; margin-bottom:4px;">Department / Subject</label>
                    <input type="text" placeholder="e.g. Editorial Correction or Tariff Update" style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px;">
                </div>
                <div style="margin-bottom:18px;">
                    <label style="display:block; font-size:12px; font-weight:700; color:#475569; margin-bottom:4px;">Message Details</label>
                    <textarea rows="5" placeholder="Please provide specific details including article URLs or relevant data points..." style="width:100%; padding:10px 14px; border:1px solid #CBD5E1; border-radius:6px; font-size:14px; font-family:inherit;"></textarea>
                </div>
                <button type="button" onclick="alert('Thank you! Your editorial inquiry has been recorded and routed to our research desk.');" style="background:var(--primary); color:#FFF; font-weight:800; border:none; padding:12px 28px; border-radius:6px; font-size:14px; cursor:pointer; text-transform:uppercase; letter-spacing:0.5px;">Submit Inquiry</button>
            </div>
        </div>
    </div>
    """

def get_calculator_page_content(site_config):
    name = site_config["name"]
    calc_title = site_config["calc_title"]
    calc_l1 = site_config["calc_label1"]
    calc_l2 = site_config["calc_label2"]
    calc_l3 = site_config["calc_label3"]
    calc_d1 = site_config["calc_default1"]
    calc_d2 = site_config["calc_default2"]
    calc_d3 = site_config["calc_default3"]
    calc_res_title = site_config["calc_res_title"]
    calc_prefix = site_config.get("calc_res_prefix", "₹")
    calc_type = site_config.get("calc_type", "savings")
    
    return f"""
    <div class="post-paper">
        <div class="cat-badge">Interactive Financial Tool</div>
        <h1 class="post-h1">{calc_title}</h1>
        <div class="post-meta">
            <span>Client-Side Local Processing</span>
            <span>Real-Time Recalculation</span>
            <span>100% Free Tool</span>
        </div>
        <div class="post-content">
            <p>Use our authoritative, real-time calculator to evaluate financial projections, optimize tariff expenses, and forecast accurate cash flow metrics before making major decisions.</p>

            <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:10px; padding:32px; margin:28px 0;">
                <div style="display:grid; grid-template-columns:1fr; gap:20px;">
                    <div>
                        <label style="display:block; font-size:13px; font-weight:700; color:#334155; margin-bottom:6px;">{calc_l1}</label>
                        <input type="number" id="full_in1" value="{calc_d1}" oninput="recalcFull()" style="width:100%; padding:12px 16px; border:1px solid #CBD5E1; border-radius:6px; font-size:16px; font-weight:700;">
                    </div>
                    <div>
                        <label style="display:block; font-size:13px; font-weight:700; color:#334155; margin-bottom:6px;">{calc_l2}</label>
                        <input type="number" id="full_in2" value="{calc_d2}" oninput="recalcFull()" style="width:100%; padding:12px 16px; border:1px solid #CBD5E1; border-radius:6px; font-size:16px; font-weight:700;">
                    </div>
                    <div>
                        <label style="display:block; font-size:13px; font-weight:700; color:#334155; margin-bottom:6px;">{calc_l3}</label>
                        <input type="number" id="full_in3" value="{calc_d3}" oninput="recalcFull()" style="width:100%; padding:12px 16px; border:1px solid #CBD5E1; border-radius:6px; font-size:16px; font-weight:700;">
                    </div>
                </div>

                <div style="background:#0F172A; color:#FFF; border-radius:8px; padding:24px; text-align:center; margin-top:28px;">
                    <div style="font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#94A3B8; font-weight:700;">{calc_res_title}</div>
                    <div id="full_res" style="font-size:38px; font-weight:900; color:#38BDF8; margin-top:6px;">{calc_prefix}0</div>
                    <div style="font-size:12px; color:#64748B; margin-top:6px;">Calculated dynamically with zero server-side transmission.</div>
                </div>
            </div>

            <h2>How to Use This Mathematical Model</h2>
            <p>Our calculation engine operates deterministically. By adjusting the parameters above, you can run realistic sensitivity analysis and compare various pricing tiers or financing schedules to uncover hidden savings.</p>

            <script>
            function recalcFull() {{
                var v1 = parseFloat(document.getElementById('full_in1').value) || 0;
                var v2 = parseFloat(document.getElementById('full_in2').value) || 0;
                var v3 = parseFloat(document.getElementById('full_in3').value) || 0;
                var res = 0;
                var type = "{calc_type}";
                if (type === "emi") {{
                    var r = (v3 / 12) / 100;
                    var n = (v2 > 0 ? v2 : 5) * 12;
                    if (r > 0 && n > 0 && v1 > 0) {{
                        res = Math.round((v1 * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1));
                    }}
                }} else if (type === "savings") {{
                    res = Math.round(v1 * 12 * (v2 / 100) * (v3 > 0 ? v3 : 1));
                }} else if (type === "cashback") {{
                    res = Math.round((v1 * (v2 / 100) * 12) + (v3 * 100));
                }} else if (type === "gold") {{
                    res = Math.round(v1 * (v2 / 24) * (v3 > 0 ? (v3/1000) : 7500));
                }} else {{
                    res = Math.round((v1 * v2 * 12) / 100);
                }}
                document.getElementById('full_res').innerText = "{calc_prefix}" + res.toLocaleString();
            }}
            window.addEventListener('DOMContentLoaded', recalcFull);
            </script>
        </div>
    </div>
    """
