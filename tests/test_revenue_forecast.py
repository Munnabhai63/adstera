"""
tests/test_revenue_forecast.py — Step 5.5: Revenue Forecasting Model Tests

Covers:
1. Cold-start baseline fitting when historical data is absent
2. OLS slope and trailing moving average computation on time series
3. Day-of-week seasonality multiplier application
4. Next 7 days projection output structure and confidence bounds
5. 30-day cumulative monthly forecast
6. Revenue drop anomaly detection (>20% deficit)
7. Normal revenue variation does not trigger false positive alert
8. db.get_daily_revenue_history database integration
"""
from __future__ import annotations

import datetime
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
import revenue_forecast
from revenue_forecast import RevenueForecaster


def test_forecast_cold_start():
    """Forecaster initializes a viable baseline even without history."""
    cfg = {"target": {"cpm_rate": 3.00}, "scheduler": {"daily_cap": 1000}}
    forecaster = RevenueForecaster(cfg=cfg)
    forecaster.fit(history=[])

    assert forecaster.fitted
    # 1000 imps * 3.0 / 1000 = $3.00 baseline
    assert forecaster.trailing_avg == 3.00
    pred = forecaster.predict_day(day_offset=1)
    assert pred > 0.0
    print(f"  [OK] Cold-start baseline predicted: ${pred:.2f}")


def test_forecast_trend_fitting():
    """Forecaster accurately captures positive upward trend slope."""
    # 10 days of steady growth: $10, $11, $12, ..., $19
    history = [
        {"date": f"2026-11-0{i+1}", "total_revenue": 10.0 + i}
        for i in range(10)
    ]
    forecaster = RevenueForecaster()
    forecaster.fit(history=history)

    assert forecaster.slope > 0.8  # Real slope is 1.0
    assert forecaster.trailing_avg > 15.0  # Trailing 7 days average of 13..19 is 16.0
    print(f"  [OK] Trend slope fitted: {forecaster.slope:.4f}, trailing_avg: ${forecaster.trailing_avg:.2f}")


def test_forecast_seasonality_multipliers():
    """Weekend days receive lower projected multiplier than peak weekdays."""
    forecaster = RevenueForecaster()
    # Constant historical revenue of $20/day
    history = [
        {"date": f"2026-11-{i+1:02d}", "total_revenue": 20.0}
        for i in range(14)
    ]
    forecaster.fit(history=history)

    wednesday = datetime.date(2026, 11, 11)  # Wednesday (idx 2, mult 1.08)
    sunday = datetime.date(2026, 11, 15)     # Sunday (idx 6, mult 0.66)

    pred_wed = forecaster.predict_day(target_date=wednesday)
    pred_sun = forecaster.predict_day(target_date=sunday)

    assert pred_wed > pred_sun
    print(f"  [OK] Seasonality verified: Wed=${pred_wed:.2f} > Sun=${pred_sun:.2f}")


def test_forecast_7_days_and_monthly():
    """forecast_next_7_days produces 7 rows and monthly estimate sums 30 days."""
    history = [{"date": "2026-11-01", "total_revenue": 15.0}] * 7
    forecaster = RevenueForecaster().fit(history=history)

    weekly = forecaster.forecast_next_7_days()
    assert len(weekly) == 7
    for row in weekly:
        assert "date" in row
        assert "projected_usd" in row
        assert row["confidence_low"] <= row["projected_usd"] <= row["confidence_high"]

    monthly = forecaster.forecast_monthly_estimate()
    assert 300.0 <= monthly <= 600.0
    print(f"  [OK] Weekly 7 days generated; Monthly projection: ${monthly:.2f}")


def test_forecast_anomaly_detection():
    """detect_anomaly flags drops >20% and ignores minor deviations."""
    history = [{"date": "2026-11-01", "total_revenue": 50.0}] * 7
    forecaster = RevenueForecaster().fit(history=history)

    # Actual $45 vs projected ~$50 is only 10% drop -> NO anomaly
    normal_res = forecaster.detect_anomaly(actual_today=45.0, threshold_pct=0.20)
    assert not normal_res["anomaly"]

    # Actual $20 vs projected ~$50 is 60% drop -> CRITICAL anomaly
    alert_res = forecaster.detect_anomaly(actual_today=20.0, threshold_pct=0.20)
    assert alert_res["anomaly"]
    assert alert_res["severity"] == "CRITICAL"
    assert "Revenue dropped" in alert_res["message"]
    print(f"  [OK] Anomaly detector correctly flagged {alert_res['deficit_pct']}% deficit")


def test_db_get_daily_revenue_history():
    """db.get_daily_revenue_history aggregates daily impressions, API sync, and CPA revenue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_db = db._DB_PATH
        db._DB_PATH = Path(tmpdir) / "test_rev.db"
        try:
            db.init()
            # Log session which populates daily_stats
            db.log_session("p1", "UA", "", 25.0, 1, ad_clicks=2, impressions=200, status="ok")
            # Log CPA conversion for today
            db.log_cpa_conversion("mb_1", "maxbounty", "loan", "p1", "loanraaj.com", payout_usd=18.50)

            history = db.get_daily_revenue_history(days=7, fallback_cpm=2.50)
            assert len(history) >= 1
            today_entry = history[-1]
            assert today_entry["impressions"] == 200
            # 200 imps * 2.50 / 1000 = $0.50 ad revenue
            assert abs(today_entry["ad_revenue"] - 0.50) < 0.05
            assert abs(today_entry["cpa_revenue"] - 18.50) < 0.05
            assert abs(today_entry["total_revenue"] - 19.00) < 0.05
            print(f"  [OK] db.get_daily_revenue_history total: ${today_entry['total_revenue']}")
        finally:
            db._DB_PATH = orig_db


if __name__ == "__main__":
    test_forecast_cold_start()
    test_forecast_trend_fitting()
    test_forecast_seasonality_multipliers()
    test_forecast_7_days_and_monthly()
    test_forecast_anomaly_detection()
    test_db_get_daily_revenue_history()
    print("\nAll revenue forecasting tests PASSED!")
