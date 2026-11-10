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
        "url": "https://asiafilm.org/4/5a10ac2f61030bfc4a933d19243bd9d5",
        "badge": "Commercial Finance Partner",
        "title": "Commercial Vehicle & MSME Loan Pre-Approval",
        "desc": "Check competitive APRs, collateral-free credit limits, and fast-track business loan approvals with leading financial institutions.",
        "cta": "Check Pre-Approved Rates →",
        "calc_cta": "Apply for this Loan Amount →",
        "icon": "🚛",
    },
    "rechargetak": {
        "url": "https://asiafilm.org/4/c8ee7e929c7c0f77f48b9eb7f198735b",
        "badge": "Sponsored Telecom Rewards",
        "title": "Unlimited 5G Data & OTT Combo Cashback",
        "desc": "Unlock up to ₹150 instant cashback voucher on annual recharge packs, 5G data boosters, and FASTag highway top-ups.",
        "cta": "Claim Recharge Rewards →",
        "calc_cta": "Activate Discount Plan →",
        "icon": "📱",
    },
    "rechargepur": {
        "url": "https://asiafilm.org/4/e534aa2882340b6d23a31b264a473449",
        "badge": "Official Utility Partner",
        "title": "Smart Meter Electricity & Cooking Gas Rebate",
        "desc": "Claim government subsidy rebates and instant UPI discount vouchers on your municipal bill payments and gas refills.",
        "cta": "Check Utility Subsidies →",
        "calc_cta": "Reduce Household Bill Expenses →",
        "icon": "⚡",
    },
    "tazaloan": {
        "url": "https://asiafilm.org/4/4cef2f60b337a83398fd5d4eccb2b035",
        "badge": "Digital Credit Offer",
        "title": "Paperless Instant Cash Personal Loan",
        "desc": "Disbursal in 60 minutes, zero physical paperwork, low CIBIL considerations, and pre-approved digital credit lines up to ₹5,00,000.",
        "cta": "Check Instant Eligibility →",
        "calc_cta": "Apply for this Monthly EMI →",
        "icon": "💸",
    },
    "loankiseva": {
        "url": "https://asiafilm.org/4/17ddb2ab1cf803847dffc03339639ae2",
        "badge": "MSME Scheme Desk",
        "title": "CGTMSE Collateral-Free Business Credit",
        "desc": "PMEGP subsidy applications, industrial machinery lease financing, and fast-tracked SIDBI commercial working capital.",
        "cta": "Apply for MSME Subsidy →",
        "calc_cta": "Submit Scheme Application →",
        "icon": "🏭",
    },
    "karzseva": {
        "url": "https://asiafilm.org/4/36bc7f04daecf4b91801beda6ea285a5",
        "badge": "Legal Settlement Partner",
        "title": "One-Time Bank Settlement (OTS) Relief",
        "desc": "Legally settle unmanageable credit card debts with up to 60% principal waivers and dispute negative credit bureau reporting.",
        "cta": "Get Free Debt Evaluation →",
        "calc_cta": "Calculate Settlement Savings →",
        "icon": "🛡️",
    },
    "loantau": {
        "url": "https://asiafilm.org/4/e5d95a7029b0b931e6310b08c33befa3",
        "badge": "Kisan Credit Desk",
        "title": "KCC 4% Subsidized Agriculture Credit",
        "desc": "Low-interest crop loans, tractor purchase finance, solar pump subsidies, and NABARD rural dairy enterprise funding.",
        "cta": "Check Kisan Eligibility →",
        "calc_cta": "Check Subsidized Interest →",
        "icon": "🌾",
    },
    "tazabhav": {
        "url": "https://asiafilm.org/4/dd81186b26c491b694a530a285873443",
        "badge": "Live Bullion Desk",
        "title": "Digital Gold & Sovereign Commodity Trading",
        "desc": "Access live 24K MCX bullion spot rates, buy digital gold starting at ₹10, and accumulate pure bullion with zero vault fees.",
        "cta": "Explore Live Rates →",
        "calc_cta": "View Current Bullion Spreads →",
        "icon": "🥇",
    },
    "tazarokda": {
        "url": "https://asiafilm.org/4/080aacbe5bb90ca178d15ff864c503f7",
        "badge": "Direct Investment Partner",
        "title": "Zero-Brokerage Demat & High-CAGR SIPs",
        "desc": "Open lifetime free demat account with zero maintenance fee and invest in direct zero-commission mutual funds and index funds.",
        "cta": "Open Free Demat Account →",
        "calc_cta": "Start This SIP Investment →",
        "icon": "📈",
    },
    "rechargekar": {
        "url": "https://asiafilm.org/4/c32806b04cb876619cbcff1c8f210313",
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
