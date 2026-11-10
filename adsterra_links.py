"""
adsterra_links.py — Centralized, authoritative Adsterra Direct Links mapping
for all 10 network publisher domains.

Each domain is mapped to its dedicated high-eCPM Adsterra direct link with
niche-tailored, high-converting copy for native in-article cards, header
recommendations, sidebar widgets, and calculator CTAs.
"""
from __future__ import annotations
from typing import Any

ADSTERRA_DIRECT_LINKS: dict[str, dict[str, str]] = {
    "loanraaj": {
        "url": "https://araplhn.org/4/17dc693c036f3b211f48887d232add4b",
        "badge": "Commercial Finance Partner",
        "title": "Commercial Vehicle & MSME Loan Pre-Approval",
        "desc": "Check competitive APRs, collateral-free credit limits, and fast-track business loan approvals with leading financial institutions.",
        "cta": "Check Pre-Approved Rates →",
        "calc_cta": "Apply for this Loan Amount →",
        "icon": "🚛",
    },
    "rechargetak": {
        "url": "https://araplhn.org/4/36def2a0119696fb23e3fe034ccfcbc6",
        "badge": "Sponsored Telecom Rewards",
        "title": "Unlimited 5G Data & OTT Combo Cashback",
        "desc": "Unlock up to ₹150 instant cashback voucher on annual recharge packs, 5G data boosters, and FASTag highway top-ups.",
        "cta": "Claim Recharge Rewards →",
        "calc_cta": "Activate Discount Plan →",
        "icon": "📱",
    },
    "rechargepur": {
        "url": "https://araplhn.org/4/efed43a0653e93bd1dc62b74d42e4c6a",
        "badge": "Official Utility Partner",
        "title": "Smart Meter Electricity & Cooking Gas Rebate",
        "desc": "Claim government subsidy rebates and instant UPI discount vouchers on your municipal bill payments and gas refills.",
        "cta": "Check Utility Subsidies →",
        "calc_cta": "Reduce Household Bill Expenses →",
        "icon": "⚡",
    },
    "tazaloan": {
        "url": "https://araplhn.org/4/b85c5d24beb88d58bfb4e161e1f74dd9",
        "badge": "Digital Credit Offer",
        "title": "Paperless Instant Cash Personal Loan",
        "desc": "Disbursal in 60 minutes, zero physical paperwork, low CIBIL considerations, and pre-approved digital credit lines up to ₹5,00,000.",
        "cta": "Check Instant Eligibility →",
        "calc_cta": "Apply for this Monthly EMI →",
        "icon": "💸",
    },
    "loankiseva": {
        "url": "https://araplhn.org/4/2caa4b8918499ce7fd21fc1b92ec94aa",
        "badge": "MSME Scheme Desk",
        "title": "CGTMSE Collateral-Free Business Credit",
        "desc": "PMEGP subsidy applications, industrial machinery lease financing, and fast-tracked SIDBI commercial working capital.",
        "cta": "Apply for MSME Subsidy →",
        "calc_cta": "Submit Scheme Application →",
        "icon": "🏭",
    },
    "karzseva": {
        "url": "https://araplhn.org/4/8b6f18f361f42dc7c2c708b4ce5f6f28",
        "badge": "Legal Settlement Partner",
        "title": "One-Time Bank Settlement (OTS) Relief",
        "desc": "Legally settle unmanageable credit card debts with up to 60% principal waivers and dispute negative credit bureau reporting.",
        "cta": "Get Free Debt Evaluation →",
        "calc_cta": "Calculate Settlement Savings →",
        "icon": "🛡️",
    },
    "loantau": {
        "url": "https://araplhn.org/4/5758e39593ed52767a2328758c2683da",
        "badge": "Kisan Credit Desk",
        "title": "KCC 4% Subsidized Agriculture Credit",
        "desc": "Low-interest crop loans, tractor purchase finance, solar pump subsidies, and NABARD rural dairy enterprise funding.",
        "cta": "Check Kisan Eligibility →",
        "calc_cta": "Check Subsidized Interest →",
        "icon": "🌾",
    },
    "tazabhav": {
        "url": "https://araplhn.org/4/ca5b06c43def4844f857da9379d3229d",
        "badge": "Live Bullion Desk",
        "title": "Digital Gold & Sovereign Commodity Trading",
        "desc": "Access live 24K MCX bullion spot rates, buy digital gold starting at ₹10, and accumulate pure bullion with zero vault fees.",
        "cta": "Explore Live Rates →",
        "calc_cta": "View Current Bullion Spreads →",
        "icon": "🥇",
    },
    "tazarokda": {
        "url": "https://araplhn.org/4/683357397a7ae6ec26a028b4100a876c",
        "badge": "Direct Investment Partner",
        "title": "Zero-Brokerage Demat & High-CAGR SIPs",
        "desc": "Open lifetime free demat account with zero maintenance fee and invest in direct zero-commission mutual funds and index funds.",
        "cta": "Open Free Demat Account →",
        "calc_cta": "Start This SIP Investment →",
        "icon": "📈",
    },
    "rechargekar": {
        "url": "https://araplhn.org/4/7a123d148c127cf4f54df5374d59a985",
        "badge": "Exclusive Entertainment Offer",
        "title": "Multi-Room DTH & Family Telecom Pack",
        "desc": "Save up to 30% annually on Tata Play, Airtel DTH, Dish TV, and pooled postpaid family telecom connections.",
        "cta": "Claim Family DTH Offer →",
        "calc_cta": "Save on Annual DTH →",
        "icon": "📺",
    },
}

# Aliases for domain names with .com and http/https
for short_name, data in list(ADSTERRA_DIRECT_LINKS.items()):
    ADSTERRA_DIRECT_LINKS[f"{short_name}.com"] = data
    ADSTERRA_DIRECT_LINKS[f"https://{short_name}.com"] = data
    ADSTERRA_DIRECT_LINKS[f"http://{short_name}.com"] = data


def get_adsterra_config(domain_or_key: str) -> dict[str, str]:
    """
    Look up the exact Adsterra configuration for any domain or key.
    Defaults to loanraaj configuration if unmatched.
    """
    clean = domain_or_key.lower().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    if clean in ADSTERRA_DIRECT_LINKS:
        return ADSTERRA_DIRECT_LINKS[clean]
    
    # Try stripping .com
    prefix = clean.replace(".com", "")
    if prefix in ADSTERRA_DIRECT_LINKS:
        return ADSTERRA_DIRECT_LINKS[prefix]
        
    return ADSTERRA_DIRECT_LINKS["loanraaj"]


def render_native_ad_card(domain_or_key: str) -> str:
    """Generate high-CTR, responsive native in-article sponsored card HTML."""
    cfg = get_adsterra_config(domain_or_key)
    return f"""
    <div class="native-ad-card">
        <div class="native-ad-badge">{cfg['badge']}</div>
        <div class="native-ad-body">
            <div class="native-ad-icon">{cfg['icon']}</div>
            <div class="native-ad-text">
                <h4 class="native-ad-title">{cfg['title']}</h4>
                <p class="native-ad-desc">{cfg['desc']}</p>
            </div>
            <a href="{cfg['url']}" target="_blank" rel="noopener sponsored" class="native-ad-btn">{cfg['cta']}</a>
        </div>
    </div>
    """


def render_sidebar_ad_widget(domain_or_key: str) -> str:
    """Generate responsive sidebar sponsored widget HTML."""
    cfg = get_adsterra_config(domain_or_key)
    return f"""
    <div class="widget-card sidebar-ad-card">
        <div class="sidebar-ad-tag">{cfg['badge']}</div>
        <div class="sidebar-ad-icon">{cfg['icon']}</div>
        <h4 class="sidebar-ad-title">{cfg['title']}</h4>
        <p class="sidebar-ad-desc">{cfg['desc']}</p>
        <a href="{cfg['url']}" target="_blank" rel="noopener sponsored" class="sidebar-ad-btn">{cfg['cta']}</a>
    </div>
    """


ADSTERRA_SCRIPTS: dict[str, dict[str, str]] = {
    "rechargetak": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/dc41505f499f4766916a1efc1fcc260c"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/bf2db224e6b41f48796445afdf3e666b"></script>',
    },
    "tazaloan": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/7c72b09e2f9b8efbeffc6adf72b46383"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/05f860490762d69285aa3dccbf6b7cee"></script>',
    },
    "tazabhav": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/4af55666d78005635674d84ca5705dc3"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/768c05ff622a4e818f439d86f0a45823"></script>',
    },
    "rechargepur": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/8921db9b7c660d20aee2be0f5e708fcc"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/79732d673f8eb0607b192edc9dc6a3b5"></script>',
    },
    "loankiseva": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/8c01d8d0e2d9e28a5b16ea2030075464"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/aaa958f01b1a81eaf466d3c9a001a862"></script>',
    },
    "loanraaj": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/469818ae009e95c4d51277eb83956347"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/33f1a7d198b5423ebc2a315b8eb76d52"></script>',
    },
    "karzseva": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/60fe0e370671a9c4feb05cbaf4af39aa"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/0278c131d8a4ef8d08fef6c937ccd0d2"></script>',
    },
    "loantau": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/4bed4e6942d4d450068417705aab2055"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/6bb0516e01dc9bdfe29ec03aee2a4e0d"></script>',
    },
    "tazarokda": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/2cb8a2b93f18d3107c54c7cd67102652"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/0f4d1c559ba16b9c12fc6d564c679bf5"></script>',
    },
    "rechargekar": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/02d7469ada7886443b3c4deff2a923cb"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/e742775cc78d4b7bb87893991c674116"></script>',
    },
}

def render_adsterra_scripts(domain_or_key: str) -> str:
    """Generate official Adsterra Popunder + SocialBar script block."""
    clean = domain_or_key.lower().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    prefix = clean.replace(".com", "")
    info = ADSTERRA_SCRIPTS.get(prefix) or ADSTERRA_SCRIPTS.get(clean) or ADSTERRA_SCRIPTS["loanraaj"]
    return f"""
    <!-- Adsterra Monetization Engine -->
    {info['popunder']}
    {info['socialbar']}
    """
