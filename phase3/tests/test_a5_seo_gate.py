"""Unit tests for Phase 3 A5 High-RPM Keyword Predictor & Anti-AI SEO Gate."""
from __future__ import annotations

import math

import pytest

from phase3.a5_seo_gate.quality_gate import AntiAIQualityGate, gate
from phase3.a5_seo_gate.rpm_predictor import (
    GammaPoissonRPMPredictor,
    _gamma_quantile,
    rank_keywords,
)
from phase3.config_loader import load_phase3_config


# ---------------------------------------------------------------------------
# Golden Fixtures: Realistic Varied Human Articles vs Uniform/Repetitive AI
# ---------------------------------------------------------------------------

HUMAN_FINANCE_ARTICLE = """
Small business owners often underestimate how quickly working capital dries up during a slow quarter. Why does that happen? Usually, invoices stretch from thirty days to seventy, while payroll and rent still hit on the first of the month.
Wait until you compare two lenders side by side. One quotes a flat twelve percent rate, which sounds fine until you spot the two percent processing fee and mandatory insurance add-on buried on page four of the contract. Another charges thirteen percent on a reducing balance with zero prepayment penalty. Over twenty-four months, that second loan costs noticeably less!
Check the numbers carefully. A quick spreadsheet saves thousands of rupees. In fact, borrowers who audit the Annual Percentage Rate before signing routinely cut total interest outgo by fifteen to twenty percent, especially when they make one extra principal payment every harvest or festival season.
Most banks also check your cash flow ratio before they approve a credit line. If your bank statements show steady deposits and few bounced cheques, the underwriter gives you a better tier. On the other hand, applying to five lenders in the same week triggers hard inquiries on your credit bureau file and pushes your score down right when you need leverage.
Take a breath and map out the repayment schedule first. Look at the monthly instalment alongside your slowest week of sales, not your best week. Does the business still clear rent, supplier bills, and basic staff wages after the EMI leaves the account? If the answer is yes, the debt helps you grow; if the answer is no, scale down the loan amount or wait until receivables settle.
Smart borrowers treat credit as a bridge, never as permanent revenue. Keep receipts clean, file taxes on time, and ask for a written foreclosure quote before you sign anything.
Before you submit the final application, verify whether the lender is registered with the Reserve Bank of India as a bank or an NBFC. Unregulated apps often ask for broad contact-list permissions and tack on steep daily late fees that spiral out of control after a single missed payment. Always read the Key Fact Statement first. Every regulated lender must hand over a single-page summary listing the exact loan amount, the total interest charge, the processing fee, the annual percentage rate, and the cooling-off period during which you can exit the loan without penalty. If an agent refuses to share that sheet in writing, walk away immediately and pick a transparent institution instead.
"""

HUMAN_HTML_ARTICLE = (
    "<article>"
    "<style>.hidden{display:none;}</style>"
    "<script>console.log('ignore me entirely in word count');</script>"
    "<h1>Prepaid 5G Data Plans: What Actually Changes Your Monthly Bill?</h1>"
    "<p class='lead'>Telecom headlines love big gigabyte numbers. Yet most subscribers overpay by thirty percent simply because they pick twenty-eight-day cycles instead of eighty-four-day packs!</p>"
    "<p>Look closely at the renewal math. Three twenty-eight-day recharges cover only eighty-four days, which quietly forces you to pay thirteen times every calendar year instead of twelve. Do the arithmetic once and the hidden cost jumps straight off the screen.</p>"
    "<h2>Data Rollover vs Daily Caps</h2>"
    "<p>Daily two-gigabyte caps look generous on paper, right? Not always. If you commute by train Monday through Friday and stream video mostly on Sunday afternoon, half of your weekday quota expires unused at midnight while Sunday evening buffers at low resolution.</p>"
    "<ul>"
    "<li>Check whether unlimited 5G applies only on standalone towers in your pin code.</li>"
    "<li>Compare the effective cost per day rather than the headline sticker price.</li>"
    "<li>Skip bundled OTT subscriptions if you already share a family streaming plan at home.</li>"
    "</ul>"
    "<p>Call quality matters too. Ask neighbors which carrier holds signal inside concrete office buildings before porting your primary banking SIM, because chasing a fifty-rupee discount means nothing if OTP texts stall during checkout.</p>"
    "<p>What happens when you travel outside your home circle? Domestic roaming is free on paper, yet congestion throttling kicks in much faster on crowded highway corridors and railway stations. Testing a secondary eSIM for one month reveals far more than any speed-test screenshot shared online.</p>"
    "<p>Keep a calendar reminder two days before expiry. Most prepaid apps push an expensive default renewal banner on the final morning, hoping busy subscribers tap pay without checking the pack validity or the daily data quota.</p>"
    "<p>Finally, keep an eye on validity extensions and tariff revisions announced after quarterly spectrum auctions. Locking in an annual pack right before a scheduled price hike often saves four hundred rupees across the year without changing how much data you consume.</p>"
    "</article>"
)

HUMAN_TELECOM_UTILITY_ARTICLE = """
Paying an electricity bill on time seems trivial until a summer heatwave doubles your air-conditioning load and pushes your connection into the top tariff slab. Did you check the slab jump on last month's receipt? Many households cross the four-hundred-unit threshold by just twelve units and suddenly pay an extra two rupees per unit across a huge slice of the bill.
Walk around the house with a notepad for ten minutes. Older window coolers, leaking refrigerator door gaskets, and desktop computers left humming overnight account for a surprising chunk of phantom draw. Replacing one aging ceiling fan with a brushless DC motor unit cuts wattage from seventy-five watts down to twenty-eight watts, paying back its purchase price within two warm seasons!
Check your sanctioned load as well. If the meter repeatedly trips during peak evening hours when the geyser and induction stove run together, the utility may slap an excess-demand surcharge on top of your energy units. Updating the sanctioned load online takes ten minutes with your latest bill number and stops those silent monthly penalties for good.
Digital bill payment apps also hide subtle trade-offs. One wallet promises scratch cards up to fifty rupees, then caps real cashback at three rupees while charging a two-percent convenience fee on credit card settlements. Meanwhile, paying directly through the state discom portal or Bharat BillPay via UPI clears the ledger in seconds with zero surcharge and gives you an instant PDF receipt for tax or reimbursement claims.
What if your meter reading looks wildly inflated compared to the prior quarter? Photograph the digital meter display alongside the day's newspaper and file a billing dispute ticket before the due date expires. Waiting until disconnection notice arrives only adds reconnection fees and needless stress!
Check the due date twice. Automatic standing instructions help, provided your linked account keeps enough buffer on billing morning so the mandate never bounces. One bounced auto-debit costs more in bank penalties than an entire year of cashback promos!
"""

AI_UNIFORM_PROSE = """
Digital financial services offer convenient solutions for modern consumers seeking quick capital access today.
Understanding loan terms remains an essential requirement for every responsible borrower in the marketplace.
Comparing multiple lending platforms helps individuals identify competitive interest rates and flexible repayment schedules.
Reviewing contractual obligations prevents unexpected charges and promotes healthier personal budget management over time.
Maintaining consistent monthly payments strengthens creditworthiness and unlocks improved borrowing opportunities in future years.
Evaluating processing fees ensures transparent calculations before committing to any long term financial agreement.
Consulting verified regulatory portals provides additional protection against unauthorized lending applications across digital channels.
Selecting suitable repayment durations balances affordable monthly installments against total cumulative interest expenses effectively.
"""

AI_KEYWORD_SPAM = ("best instant loan app apply online quick loan approval today. " * 14).strip()

GIBBERISH_UNIFORM_UNIQUE = " ".join(f"tok{i:03d}" for i in range(130)) + "."


# ---------------------------------------------------------------------------
# Quality Gate Tests
# ---------------------------------------------------------------------------

def test_quality_gate_passes_golden_human_articles() -> None:
    cfg = load_phase3_config()
    for label, article in [
        ("finance", HUMAN_FINANCE_ARTICLE),
        ("html", HUMAN_HTML_ARTICLE),
        ("utility", HUMAN_TELECOM_UTILITY_ARTICLE),
    ]:
        res = gate(article, cfg)
        assert res["pass"] is True, f"{label} failed unexpectedly: {res}"
        assert res["reason"] == "ok"
        assert res["word_count"] >= cfg.a5_seo_gate.min_word_count
        assert cfg.a5_seo_gate.burstiness_min <= res["burstiness"] <= cfg.a5_seo_gate.burstiness_max
        assert cfg.a5_seo_gate.zipf_entropy_min <= res["zipf"] <= cfg.a5_seo_gate.zipf_entropy_max
        assert cfg.a5_seo_gate.zipf_slope_min <= res["zipf_slope"] <= cfg.a5_seo_gate.zipf_slope_max


def test_quality_gate_strips_html_scripts_and_watermarks() -> None:
    dirty = "\u200b\ufeff" + HUMAN_HTML_ARTICLE.replace("<h1>", "<h1>\u200c")
    res = gate(dirty)
    assert res["pass"] is True
    assert "console" not in dirty or res["word_count"] < 400
    # Ensure script text ('ignore me entirely in word count') was not counted as prose
    plain_only = gate(HUMAN_HTML_ARTICLE.replace("<script>console.log('ignore me entirely in word count');</script>", ""))
    assert res["word_count"] == plain_only["word_count"]


def test_quality_gate_rejects_uniform_and_repetitive_ai_articles() -> None:
    uniform_res = gate(AI_UNIFORM_PROSE)
    assert uniform_res["pass"] is False
    assert "burstiness" in uniform_res["reason"]

    spam_res = gate(AI_KEYWORD_SPAM)
    assert spam_res["pass"] is False
    assert "zipf_entropy" in spam_res["reason"] or "zipf_slope" in spam_res["reason"]

    gibberish_res = gate(GIBBERISH_UNIFORM_UNIQUE)
    assert gibberish_res["pass"] is False
    assert "zipf_slope" in gibberish_res["reason"] or "sentence_count" in gibberish_res["reason"]


def test_quality_gate_fails_safe_on_empty_and_malformed_inputs() -> None:
    for bad in ("", "   \n\t ", "<div><script>var x=1;</script><style>p{}</style></div>", None, 42, ["not", "str"]):
        res = gate(bad)  # type: ignore[arg-type]
        assert res["pass"] is False
        assert res["word_count"] == 0
        assert isinstance(res["reason"], str) and len(res["reason"]) > 0


def test_quality_gate_respects_config_thresholds() -> None:
    strict_cfg = {
        "a5_seo_gate": {
            "min_word_count": 5000,
        }
    }
    res = AntiAIQualityGate(strict_cfg).evaluate(HUMAN_FINANCE_ARTICLE)
    assert res["pass"] is False
    assert "word_count_below_min" in res["reason"]


# ---------------------------------------------------------------------------
# Gamma-Poisson RPM Predictor Tests
# ---------------------------------------------------------------------------

def test_gamma_quantile_matches_exponential_special_case() -> None:
    # Gamma(1, 1) == Exponential(1): F^-1(p) = -ln(1 - p)
    for p in (0.025, 0.5, 0.975):
        expected = -math.log(1.0 - p)
        actual = _gamma_quantile(1.0, 1.0, p)
        assert abs(actual - expected) < 1e-9


def test_rank_keywords_orders_synthetic_gsc_and_adsterra_signals() -> None:
    keywords = [
        {
            "keyword": "low_tier_generic_tip",
            "impressions": 4000,
            "clicks": 20,
            "ctr": 0.005,
            "position": 19.0,
            "adsterra_impressions": 4000,
            "revenue": 1.20,
            "historical_ecpm": 0.30,
            "niche_rpm": 0.40,
        },
        {
            "keyword": "high_rpm_commercial_loan",
            "impressions": 12000,
            "clicks": 960,
            "ctr": 0.08,
            "position": 1.4,
            "adsterra_impressions": 10000,
            "revenue": 72.0,
            "historical_ecpm": 7.20,
            "niche_rpm": 6.50,
        },
        {
            "keyword": "mid_tier_recharge_guide",
            "gsc": {"impressions": 6000, "clicks": 180, "ctr": 0.03, "position": 5.0},
            "adsterra": {"impressions": 5000, "revenue": 11.0, "ecpm": 2.20, "niche_rpm": 2.00},
        },
    ]

    ranked = rank_keywords(keywords)
    assert [row["keyword"] for row in ranked] == [
        "high_rpm_commercial_loan",
        "mid_tier_recharge_guide",
        "low_tier_generic_tip",
    ]
    for row in ranked:
        assert row["posterior_alpha"] > 0
        assert row["posterior_beta"] > 0
        assert 0.0 <= row["rpm_ci_low"] <= row["score"] <= row["expected_rpm"] <= row["rpm_ci_high"]


def test_rpm_predictor_position_decay_and_volume_narrowing() -> None:
    predictor = GammaPoissonRPMPredictor()

    top_pos = predictor.predict_one({
        "keyword": "pos_1",
        "impressions": 5000,
        "ctr": 0.05,
        "position": 1.0,
        "historical_ecpm": 3.0,
        "adsterra_impressions": 5000,
    })
    deep_pos = predictor.predict_one({
        "keyword": "pos_18",
        "impressions": 5000,
        "ctr": 0.05,
        "position": 18.0,
        "historical_ecpm": 3.0,
        "adsterra_impressions": 5000,
    })
    assert top_pos["expected_rpm"] > deep_pos["expected_rpm"]
    assert top_pos["score"] > deep_pos["score"]

    low_vol = predictor.predict_one({
        "keyword": "low_vol",
        "impressions": 200,
        "ctr": 0.04,
        "position": 3.0,
        "historical_ecpm": 4.0,
        "adsterra_impressions": 200,
    })
    high_vol = predictor.predict_one({
        "keyword": "high_vol",
        "impressions": 50000,
        "ctr": 0.04,
        "position": 3.0,
        "historical_ecpm": 4.0,
        "adsterra_impressions": 50000,
    })
    low_width = low_vol["rpm_ci_high"] - low_vol["rpm_ci_low"]
    high_width = high_vol["rpm_ci_high"] - high_vol["rpm_ci_low"]
    assert high_width < low_width


def test_rank_keywords_fails_safe_on_malformed_items() -> None:
    assert rank_keywords([]) == []
    assert rank_keywords(None) == []  # type: ignore[arg-type]

    mixed = [
        None,
        "not_a_dict",
        123,
        {"keyword": "broken_values", "impressions": "nan", "ctr": float("inf"), "revenue": None, "position": -5},
        {"keyword": "valid_kw", "impressions": 3000, "clicks": 150, "position": 2.0, "historical_ecpm": 4.5},
    ]
    ranked = rank_keywords(mixed)  # type: ignore[arg-type]
    assert len(ranked) == 2
    assert ranked[0]["keyword"] == "valid_kw"
    for row in ranked:
        assert math.isfinite(row["expected_rpm"])
        assert math.isfinite(row["score"])
