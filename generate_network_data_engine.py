# generate_network_data_engine.py - Constructs the full 144-article dataset for all 9 domains
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("Generating comprehensive network articles data...")

# Let's verify our domain definitions
DOMAINS_METADATA = {
    "rechargetak": {
        "domain": "https://rechargetak.com",
        "name": "RechargeTak",
        "tagline": "India's Premier Telecom, 5G & FASTag Portal",
        "desc": "Authoritative guides on 5G mobile recharge plans, emergency data loans, FASTag recharge rules, and fiber broadband comparisons.",
        "brand_sub": "Telecom & Digital Connectivity Intelligence",
        "color_primary": "#2563EB", # Royal Blue
        "color_hover": "#1D4ED8",
        "calc_title": "Telecom Plan & Annual Savings Calculator",
        "calc_label1": "Monthly Recharge Sum ($ / ₹)",
        "calc_label2": "Annual Plan Discount (%)",
        "calc_label3": "Number of Lines in Family",
        "calc_default1": 299,
        "calc_default2": 22,
        "calc_default3": 3,
        "calc_res_title": "Estimated Annual Savings",
        "calc_res_prefix": "₹",
        "calc_type": "savings"
    },
    "rechargepur": {
        "domain": "https://rechargepur.com",
        "name": "RechargePur",
        "tagline": "Utility Savings, Cashbacks & Digital Payments Hub",
        "desc": "Smart strategies for electricity bill rebates, piped natural gas savings, DTH recharge packs, and RuPay UPI cashback optimization.",
        "brand_sub": "Utility Bills, Rebates & Cashback Savings",
        "color_primary": "#059669", # Emerald Green
        "color_hover": "#047857",
        "calc_title": "Monthly Utility Cashback & Rebate Estimator",
        "calc_label1": "Total Monthly Utility Spend ($ / ₹)",
        "calc_label2": "Average Platform Cashback (%)",
        "calc_label3": "Number of Monthly Bill Payments",
        "calc_default1": 4500,
        "calc_default2": 3.5,
        "calc_default3": 4,
        "calc_res_title": "Estimated Annual Cashback",
        "calc_res_prefix": "₹",
        "calc_type": "cashback"
    },
    "tazaloan": {
        "domain": "https://tazaloan.com",
        "name": "TazaLoan",
        "tagline": "Instant Personal Loans & Credit Score Intelligence",
        "desc": "Unbiased benchmarks on fast disbursement personal loans, CIBIL credit repair strategies, emergency medical cash, and student education financing.",
        "brand_sub": "Instant Personal Credit & CIBIL Optimization",
        "color_primary": "#D97706", # Amber
        "color_hover": "#B45309",
        "calc_title": "Instant Personal Loan EMI & Interest Calculator",
        "calc_label1": "Loan Principal Amount ($ / ₹)",
        "calc_label2": "Loan Tenure (Years)",
        "calc_label3": "Annual Interest Rate (%)",
        "calc_default1": 150000,
        "calc_default2": 3,
        "calc_default3": 11.5,
        "calc_res_title": "Monthly Personal Loan EMI",
        "calc_res_prefix": "₹",
        "calc_type": "emi"
    },
    "loankiseva": {
        "domain": "https://loankiseva.com",
        "name": "LoanKiSeva",
        "tagline": "MSME Business Financing & Government Subsidies Portal",
        "desc": "Complete actionable guides to Pradhan Mantri Mudra Yojana, CGTMSE collateral-free loans, Stand-Up India women subsidies, and NABARD agri-finance.",
        "brand_sub": "MSME, Mudra & Government Credit Schemes",
        "color_primary": "#4F46E5", # Indigo
        "color_hover": "#4338CA",
        "calc_title": "MSME & Mudra Subsidized EMI Calculator",
        "calc_label1": "Sanctioned Scheme Amount ($ / ₹)",
        "calc_label2": "Repayment Horizon (Years)",
        "calc_label3": "Subsidized Interest Rate (%)",
        "calc_default1": 500000,
        "calc_default2": 5,
        "calc_default3": 8.5,
        "calc_res_title": "Monthly Subsidized EMI",
        "calc_res_prefix": "₹",
        "calc_type": "emi"
    },
    "karzseva": {
        "domain": "https://karzseva.com",
        "name": "KarzSeva",
        "tagline": "Debt Freedom, Loan Restructuring & Credit Recovery",
        "desc": "Empowering borrowers with One-Time Settlement (OTS) rules, RBI recovery agent guidelines, debt consolidation balance transfers, and credit score dispute fixes.",
        "brand_sub": "Debt Relief, Restructuring & Rights Protection",
        "color_primary": "#DC2626", # Crimson Red
        "color_hover": "#B91C1C",
        "calc_title": "Debt Consolidation & Monthly Savings Calculator",
        "calc_label1": "Combined Existing Debt Sum ($ / ₹)",
        "calc_label2": "Current Blended Interest Rate (%)",
        "calc_label3": "New Consolidated Rate (%)",
        "calc_default1": 600000,
        "calc_default2": 24.0,
        "calc_default3": 12.5,
        "calc_res_title": "Annual Interest Saved",
        "calc_res_prefix": "₹",
        "calc_type": "savings"
    },
    "loantau": {
        "domain": "https://loantau.com",
        "name": "LoanTau",
        "tagline": "Commercial Vehicle, Truck & Heavy Equipment Financing",
        "desc": "Specialized financing intelligence for multi-axle trucks, tippers, used commercial transport vehicles, agricultural tractors, and transporter credit lines.",
        "brand_sub": "Commercial Vehicles, HCV & Fleet Financing",
        "color_primary": "#EA580C", # Orange
        "color_hover": "#C2410C",
        "calc_title": "Commercial Truck Loan EMI & Down Payment Estimator",
        "calc_label1": "Truck On-Road Cost ($ / ₹)",
        "calc_label2": "Repayment Horizon (Years)",
        "calc_label3": "Commercial Vehicle APR (%)",
        "calc_default1": 3200000,
        "calc_default2": 4,
        "calc_default3": 10.5,
        "calc_res_title": "Estimated Monthly Truck EMI",
        "calc_res_prefix": "₹",
        "calc_type": "emi"
    },
    "tazabhav": {
        "domain": "https://tazabhav.com",
        "name": "TazaBhav",
        "tagline": "Gold Rates, Commodities & Daily SIP Wealth Portal",
        "desc": "Live price benchmarks on 24K and 22K hallmarked gold, silver ETFs, daily versus monthly SIP compounding backtests, and commodity price dynamics.",
        "brand_sub": "Bullion, Commodities & Systematic Investing",
        "color_primary": "#B45309", # Warm Bronze Gold
        "color_hover": "#92400E",
        "calc_title": "Gold Hallmarking Purity & Resale Value Calculator",
        "calc_label1": "Gold Weight (Grams)",
        "calc_label2": "Hallmark Purity (Carats, e.g. 22 or 24)",
        "calc_label3": "Current 24K Market Rate per 10g ($ / ₹)",
        "calc_default1": 25,
        "calc_default2": 22,
        "calc_default3": 76500,
        "calc_res_title": "Estimated Resale Value",
        "calc_res_prefix": "₹",
        "calc_type": "gold"
    },
    "tazarokda": {
        "domain": "https://tazarokda.com",
        "name": "TazaRokda",
        "tagline": "Premium Credit Cards, Business Banking & Cash Flow Hub",
        "desc": "In-depth evaluations of lifetime-free credit cards, airport lounge access benefits, zero-MAB business current accounts, and high-yield auto-sweep deposits.",
        "brand_sub": "Cards, Corporate Banking & High-Yield Yields",
        "color_primary": "#0D9488", # Teal
        "color_hover": "#0F766E",
        "calc_title": "Credit Card Reward Points to Cash Value Calculator",
        "calc_label1": "Average Monthly Card Spend ($ / ₹)",
        "calc_label2": "Reward Points Earned per 100 Spent",
        "calc_label3": "Redemption Cash Value per Point ($ / ₹)",
        "calc_default1": 35000,
        "calc_default2": 4,
        "calc_default3": 0.25,
        "calc_res_title": "Annual Reward Net Value",
        "calc_res_prefix": "₹",
        "calc_type": "cashback"
    },
    "rechargekar": {
        "domain": "https://rechargekar.com",
        "name": "RechargeKar",
        "tagline": "Modern eSIM, Global Roaming & 5G Data Portal",
        "desc": "Expert guides on converting physical SIM cards to eSIM, global international roaming packages vs travel SIM cards, and emergency 5G booster packs.",
        "brand_sub": "Next-Gen eSIM & International Travel Roaming",
        "color_primary": "#7C3AED", # Purple
        "color_hover": "#6D28D9",
        "calc_title": "International Roaming vs Travel eSIM Cost Comparison",
        "calc_label1": "Trip Duration (Days)",
        "calc_label2": "Estimated Daily Roaming Spend ($ / ₹)",
        "calc_label3": "Fixed Local eSIM Package Cost ($ / ₹)",
        "calc_default1": 10,
        "calc_default2": 650,
        "calc_default3": 1800,
        "calc_res_title": "Net Savings Choosing Travel eSIM",
        "calc_res_prefix": "₹",
        "calc_type": "savings"
    }
}

print(f"Configured metadata for all {len(DOMAINS_METADATA)} network sites.")
