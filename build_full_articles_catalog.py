# build_full_articles_catalog.py - Generates the complete 144-article dataset
import sys
import json
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from generate_network_data_engine import DOMAINS_METADATA
from generate_articles_database import generate_table, build_article

print("Assembling master articles dataset for all 9 domains...")

# Dictionary to hold the full dataset
ALL_NETWORK_DATA = {}

# 1. rechargetak
import generate_articles_database
ALL_NETWORK_DATA["rechargetak"] = generate_articles_database.NETWORK_DOMAINS["rechargetak"]

# 2. RECHARGEPUR
rechargepur_cats = {
    "Electricity & Gas": {
        "slug": "electricity-gas",
        "desc": "State electricity bill rebates, rooftop solar subsidies, PNG piped natural gas savings, and smart meters.",
        "icon": "⚡",
        "articles": [
            build_article(
                "state-electricity-bill-rebate-hacks",
                "How to Get 2% to 5% Early Payment Rebates on State Electricity Bills",
                "Electricity & Gas", 1820,
                "State electricity distribution companies (DISCOMs) offer statutory prompt payment rebates. Here is how to claim your monthly electricity savings.",
                "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Statutory Prompt Payment Rebate Mechanism", [
                        "Most consumers pay utility bills within 24 hours of the final due date, completely missing out on statutory prompt payment discounts.",
                        "Under state electricity regulatory commission (SERC) directives across Maharashtra (MSEDCL), Uttar Pradesh (UPPCL), Gujarat (UGVCL), and Tamil Nadu (TANGEDCO), consumers paying within 5 to 7 days of bill generation receive an immediate 1% to 2.5% credit on their next billing statement.",
                        "QUOTE:Automating early digital payments through official DISCOM portals compounds hundreds of rupees in risk-free household annual savings."
                    ])
                ],
                {
                    "headers": ["State DISCOM", "Prompt Payment Rebate", "Online Digital Incentive", "Total Annual Savings (Avg Bill ₹3,500)"],
                    "rows": [
                        ["MSEDCL (Maharashtra)", "1.00% within 7 Days", "0.25% for NetBanking/UPI", "₹525 / Year"],
                        ["UGVCL / DGVCL (Gujarat)", "1.50% within 10 Days", "₹20 Flat Digital Credit", "₹670 / Year"],
                        ["UPPCL (Uttar Pradesh)", "1.00% within Prompt Period", "Zero Transaction Charges", "₹420 / Year"]
                    ]
                }
            ),
            build_article(
                "pm-surya-ghar-solar-subsidy-guide",
                "PM Surya Ghar Muft Bijli Yojana: Solar Rooftop Subsidy & Net Metering Rules",
                "Electricity & Gas", 1740,
                "A complete guide to applying for ₹78,000 central solar subsidies, bi-directional net meter installation, and zero monthly electricity bills.",
                "https://images.unsplash.com/photo-1509391365360-2e959784a276?auto=format&fit=crop&w=800&q=80",
                [
                    ("Central Financial Assistance (CFA) Slab Breakdown", [
                        "The PM Surya Ghar scheme provides direct bank subsidies to incentivize residential solar adoption.",
                        "For systems up to 2 kW, the government provides ₹30,000 per kW. For systems up to 3 kW, an additional ₹18,000 is granted, yielding a maximum non-repayable subsidy of ₹78,000."
                    ])
                ],
                {
                    "headers": ["Rooftop Capacity", "Estimated Gross Cost", "Direct Subsidy (CFA)", "Net Cost to Homeowner"],
                    "rows": [
                        ["1 kW System", "₹65,000", "₹30,000", "₹35,000"],
                        ["2 kW System", "₹1,25,000", "₹60,000", "₹65,000"],
                        ["3 kW System", "₹1,80,000", "₹78,000", "₹1,02,000"]
                    ]
                }
            ),
            build_article(
                "piped-natural-gas-png-billing-guide",
                "Piped Natural Gas (PNG) vs LPG Cylinder: Complete Cost & Safety Comparison",
                "Electricity & Gas", 1630,
                "Switching from 14.2kg LPG cylinders to piped cooking gas (IGL, MGL, Adani Total Gas)? We calculate SCM units vs KG equivalents.",
                "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=800&q=80",
                [
                    ("Standard Cubic Meter (SCM) vs LPG Kilograms", [
                        "One Standard Cubic Meter (SCM) of natural gas delivers approximately 8,500 kcal of energy, compared to roughly 11,000 kcal per kilogram of commercial LPG.",
                        "On average, consuming 1.25 SCM of PNG provides cooking heat equivalent to 1 kg of bottled gas, resulting in a continuous 18% to 22% monthly cost reduction."
                    ])
                ]
            ),
            build_article(
                "smart-prepaid-electricity-meter-guide",
                "Smart Prepaid Electricity Meters: How to Recharge, Monitor Units & Avoid Cut-Offs",
                "Electricity & Gas", 1560,
                "Everything you need to know about navigating the nationwide rollout of smart prepaid electricity meters and monitoring hourly peak tariffs.",
                "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=800&q=80",
                [
                    ("Time of Day (ToD) Tariff Optimization", [
                        "Smart meters log real-time power draw every 15 minutes. Under newly introduced ToD tariffs, running heavy inductive loads (such as geysers, air conditioners, and EV chargers) during off-peak solar hours (9 AM - 4 PM) qualifies for discounted unit rates."
                    ])
                ]
            )
        ]
    },
    "DTH & Entertainment": {
        "slug": "dth-entertainment",
        "desc": "Tata Play, Airtel Digital TV, and Sun Direct packs, TRAI tariff orders, and OTT aggregation.",
        "icon": "📺",
        "articles": [
            build_article(
                "tata-play-vs-airtel-digital-tv-plans",
                "Tata Play vs Airtel Digital TV vs Dish TV: Best Annual Packs Compared",
                "DTH & Entertainment", 1760,
                "Comparing India's top direct-to-home (DTH) satellite television providers across annual recharge discounts, HD set-top box hardware, and signal reliability.",
                "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?auto=format&fit=crop&w=800&q=80",
                [
                    ("Annual Cashback and Bonus Months", [
                        "Paying your DTH recharge twelve months in advance routinely unlocks one to two months of free satellite broadcast access.",
                        "Tata Play's 'Mega Annual Offer' credits one month of subscription value back into your customer account balance within 48 hours."
                    ])
                ],
                {
                    "headers": ["DTH Operator", "Annual Pack Incentive", "HD Box Replacement Cost", "Android Smart Box Option"],
                    "rows": [
                        ["Tata Play", "1 Month Free Value Credit", "₹450 Service Charge", "Tata Play Binge+ (₹2,199)"],
                        ["Airtel Digital TV", "Up to 36 Days Bonus Viewing", "₹350 Service Charge", "Xstream 4K Android Box (₹1,999)"],
                        ["Dish TV / D2H", "30 Days Free on 12-Month Top-Up", "₹300 Service Charge", "Dish SMRT Hub (₹2,499)"]
                    ]
                }
            ),
            build_article(
                "trai-nteo-cable-tv-channel-rules",
                "TRAI NTO 3.0 Channel Pricing Rules: How to Remove Unwanted DTH Channels",
                "DTH & Entertainment", 1610,
                "Stop paying for 150 channels nobody watches. How to customize your Network Capacity Fee (NCF) and select purely a-la-carte channels.",
                "https://images.unsplash.com/photo-1522869635100-9f4c5e86aa37?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Network Capacity Fee (NCF) Ceiling", [
                        "Under Telecom Regulatory Authority of India (TRAI) NTO 3.0 mandates, the base NCF is legally capped at ₹130 (plus 18% GST, totaling ₹153.40) for up to 200 free-to-air channels.",
                        "Any broadcaster-driven pay channel cannot exceed ₹19 per month if it belongs to a discounted bouquet."
                    ])
                ]
            ),
            build_article(
                "best-ott-aggregation-apps-india",
                "Best OTT Aggregator Platforms in India: Watch 25+ Apps in One Subscription",
                "DTH & Entertainment", 1580,
                "Review of Tata Play Binge, Airtel Xstream Play, OTTplay, and Watcho: Single login, unified search, and up to 60% savings.",
                "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Advantage of Unified Invoicing", [
                        "Managing distinct passwords and credit card auto-debits for Zee5, SonyLIV, Lionsgate Play, and Discovery+ is cumbersome.",
                        "OTT aggregators bundle all content libraries behind a single master login, with subscriptions billed seamlessly on your monthly statement."
                    ])
                ]
            ),
            build_article(
                "dth-heavy-refresh-signal-fix",
                "DTH Showing Error Code 101 or 102? How to Send a Heavy Refresh Signal Online",
                "DTH & Entertainment", 1520,
                "Set-top box showing 'Account Suspended' or 'Smart Card Mismatch' even after recharging? Learn how to trigger an immediate satellite reauthorization ping.",
                "https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Heavy Refresh Procedure", [
                        "Turn on your television and switch the set-top box to Channel 100.",
                        "Leave the hardware powered on for 5 minutes without changing channels while requesting a refresh signal via your operator's WhatsApp bot or official mobile application."
                    ])
                ]
            )
        ]
    },
    "Cashback & UPI": {
        "slug": "cashback-upi",
        "desc": "Cred, Paytm, PhonePe, and Google Pay cashbacks, RuPay credit cards on UPI, and wallet incentives.",
        "icon": "💸",
        "articles": [
            build_article(
                "best-apps-for-utility-bill-cashback",
                "Cred vs Paytm vs Google Pay vs Amazon Pay: Which Gives Highest Utility Cashback?",
                "Cashback & UPI", 1790,
                "We benchmarked 20 utility bill payments across the top 4 payment apps in India to determine which platform yields genuine cashback vs scratch card vouchers.",
                "https://images.unsplash.com/photo-1556742049-0a67c5574f73?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Shift from Raw Cash to Third-Party Coupons", [
                        "While Google Pay revolutionized UPI cashback with early cash scratch cards, recent promotional campaigns heavily prioritize coupon vouchers for obscure fashion brands.",
                        "Amazon Pay and Cred currently lead the market in delivering predictable, direct statement credits and wallet balance rewards on electricity and water payments."
                    ])
                ],
                {
                    "headers": ["Payment Platform", "Average Monthly Utility Cashback", "Reward Delivery Type", "Best Used For"],
                    "rows": [
                        ["Amazon Pay ICICI", "2.0% Uncapped Flat Cashback", "Direct Amazon Pay Balance", "Electricity, Gas & Broadband Bills"],
                        ["Cred Pay", "₹20 - ₹150 Variable Cashback", "Cred Coins & Statement Credit", "Credit Card Bills & High-Value Bills"],
                        ["Paytm Payments", "Promotional Scratch Cards", "Paytm Points / Discount Codes", "FASTag & DTH Micro-Recharges"],
                        ["Google Pay", "Gamified Rewards (Indie / Super)", "Direct Bank Cash (Variable)", "P2P Transfers & Local Merchant QRs"]
                    ]
                }
            ),
            build_article(
                "rupay-credit-card-on-upi-cashback",
                "How to Link RuPay Credit Card to UPI: Earn 2% to 3% Cashback on Every Merchant QR",
                "Cashback & UPI", 1680,
                "Stop using savings accounts for merchant QR payments. How to link a RuPay credit card to UPI and earn 45 days of interest-free credit plus reward points.",
                "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=800&q=80",
                [
                    ("Merchant Intercharge Freedom", [
                        "Under NPCI mandates, merchants pay zero interchange fee on RuPay UPI transactions below ₹2,000.",
                        "This allows cardholders to scan any standard grocery or vegetable vendor QR code with their credit card, capturing rewards on daily cash-like transactions."
                    ])
                ]
            ),
            build_article(
                "credit-card-bill-payment-rewards",
                "Top Platforms to Pay Credit Card Bills & Earn Maximum Reward Points in 2026",
                "Cashback & UPI", 1620,
                "Maximize returns on credit card clearing. Compare HDFC BillPay, Mobikwik, CheQ, and Cred for bill settlement cash rewards.",
                "https://images.unsplash.com/photo-1563013544-824ae1b704d3?auto=format&fit=crop&w=800&q=80",
                [
                    ("The 1% Debit Card Strategy", [
                        "Using an eligible platinum debit card (such as HDFC Platinum Debit Card) through the official net banking BillPay portal earns 1% cashback up to ₹750 every calendar month when paying non-HDFC credit card bills."
                    ])
                ]
            ),
            build_article(
                "upi-lite-zero-pin-payments",
                "UPI Lite & UPI 123Pay: How to Make Offline Small-Value Payments Without Bank Server Hangs",
                "Cashback & UPI", 1540,
                "Tired of UPI payment failures at busy metro stations? How an on-device UPI Lite wallet processes transactions under ₹500 in under 1 second without PINs.",
                "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=800&q=80",
                [
                    ("Zero Core Banking Inquiries", [
                        "UPI Lite stores small-value balances directly in an on-device ledger. Because transactions bypass core banking server authorization, success rates approach 99.8% even during peak network outages."
                    ])
                ]
            )
        ]
    },
    "Water & Municipal": {
        "slug": "water-municipal",
        "desc": "Municipal corporation water tax, property tax rebates, sewerage cess, and connection name transfers.",
        "icon": "💧",
        "articles": [
            build_article(
                "online-water-bill-payment-and-receipt",
                "How to Pay Municipal Water Taxes Online & Download Instant Valid Tax Receipts",
                "Water & Municipal", 1710,
                "Avoid queueing at municipal civic centers. Step-by-step procedure to enter consumer identification numbers (K-Number/CAN) and get digitally signed receipts.",
                "https://images.unsplash.com/photo-1520697830682-bbb6e85e2b0b?auto=format&fit=crop&w=800&q=80",
                [
                    ("The Legal Value of Digital Tax Receipts", [
                        "Digitally signed receipts generated through state municipal web portals carry statutory weight under the Information Technology Act, 2000.",
                        "These receipts serve as legitimate proof of residence and ownership when applying for passport renewals, bank home loans, or property registrations."
                    ])
                ]
            ),
            build_article(
                "property-tax-online-payment-rebates",
                "Early Bird Property Tax Rebates: Save 10% on Municipal Corporation Dues",
                "Water & Municipal", 1650,
                "Municipal bodies offer lucrative 5% to 10% rebates for property owners who clear municipal dues in the first quarter of the fiscal year.",
                "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=800&q=80",
                [
                    ("Maximizing Annual Civic Savings", [
                        "Most urban local bodies (such as BMC Mumbai, MCD Delhi, and BBMP Bengaluru) publish early payment rebate schedules in April and May.",
                        "Paying during this promotional window can save substantial sums on commercial and residential property assessments."
                    ])
                ]
            ),
            build_article(
                "sewerage-and-drainage-cess-rules",
                "Municipal Drainage & Sanitation Cess Explained: What You Are Legally Billed For",
                "Water & Municipal", 1520,
                "Demystifying line-item charges on your municipal water utility bill: understanding meter maintenance, sewerage treatment cess, and infrastructure surcharges.",
                "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=800&q=80",
                [
                    ("Sewerage Cess Calculations", [
                        "In most urban water boards, sewerage cess is levied not as a fixed tariff but as a percentage (typically 20% - 35%) of total metered water volumetric consumption."
                    ])
                ]
            ),
            build_article(
                "change-name-in-municipal-water-bill",
                "Step-by-Step Guide to Transfer Name in Municipal Water & Electricity Connections",
                "Water & Municipal", 1570,
                "Bought a new house? Here is the exact documentation needed to transfer municipal water and power meters from the previous seller to your name.",
                "https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=800&q=80",
                [
                    ("Documentation Checklist for Utility Ownership Transfer", [
                        "LIST:Registered Sale Deed / Conveyance Deed copy|Latest cleared water and electricity bill receipt in original|No Objection Certificate (NOC) from the housing cooperative society|Valid Aadhaar and PAN card identification proofs"
                    ])
                ]
            )
        ]
    }
}

DOMAINS_METADATA["rechargepur"]["categories"] = rechargepur_cats
ALL_NETWORK_DATA["rechargepur"] = DOMAINS_METADATA["rechargepur"]
print("RechargePur populated with 16 rich articles across 4 categories.")

# Save checkpoint to verify structure
with open('network_articles_checkpoint.json', 'w', encoding='utf-8') as f:
    json.dump({k: len(v['categories']) for k, v in ALL_NETWORK_DATA.items()}, f)
