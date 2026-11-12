"""Unit and regression tests for A3 IRLS Quantile Revenue & eCPM Forecaster."""
from __future__ import annotations

import random
from pathlib import Path

from phase3.a3_forecaster.irls_quantile import IRLSQuantileForecaster
from phase3.config_loader import A3ForecasterConfig, load_phase3_config
from phase3.db.migrations.runner import Phase3Store


def test_irls_recovers_linear_slopes_and_bands() -> None:
    rng = random.Random(42)
    true_slope = 0.50
    true_intercept = 10.0

    # 30 days of synthetic linear trend + symmetric uniform noise in [-2.0, +2.0]
    series = []
    for t in range(30):
        noise = rng.uniform(-2.0, 2.0)
        rev = true_intercept + true_slope * t + noise
        series.append({"revenue": rev, "impressions": 2000})

    cfg = load_phase3_config()
    forecaster = IRLSQuantileForecaster(cfg)
    res = forecaster.forecast(series, horizon_days=7)

    assert res["method"] == "irls_quantile"
    assert res["sample_count"] == 30
    assert res["horizon_days"] == 7

    for q_key in ("p10", "p50", "p90"):
        assert abs(res["slopes"][q_key] - true_slope) < 0.08

    assert res["p10"] < res["p50"] < res["p90"]
    assert res["ecpm_bands"]["p10"] < res["ecpm_bands"]["p50"] < res["ecpm_bands"]["p90"]


def test_irls_quantile_empirical_coverage() -> None:
    rng = random.Random(101)
    series = [20.0 + 0.25 * t + rng.gauss(0.0, 2.0) for t in range(50)]

    forecaster = IRLSQuantileForecaster(A3ForecasterConfig())
    res = forecaster.forecast(series, horizon_days=5)

    assert res["method"] == "irls_quantile"
    assert res["p10"] < res["p50"] < res["p90"]

    # Check empirical quantile ordering at historical t=0..49
    below_p10 = sum(
        1
        for t, y in enumerate(series)
        if y < res["intercepts"]["p10"] + res["slopes"]["p10"] * t
    )
    below_p50 = sum(
        1
        for t, y in enumerate(series)
        if y < res["intercepts"]["p50"] + res["slopes"]["p50"] * t
    )
    below_p90 = sum(
        1
        for t, y in enumerate(series)
        if y < res["intercepts"]["p90"] + res["slopes"]["p90"] * t
    )

    assert 1 <= below_p10 <= 12
    assert 18 <= below_p50 <= 32
    assert 38 <= below_p90 <= 49


def test_median_fallback_under_min_history() -> None:
    forecaster = IRLSQuantileForecaster(A3ForecasterConfig(min_history_days=7))

    # Empty history
    empty_res = forecaster.forecast([], horizon_days=7)
    assert empty_res["method"] == "median_fallback"
    assert empty_res["sample_count"] == 0
    assert empty_res["p10"] == 0.0 and empty_res["p50"] == 0.0 and empty_res["p90"] == 0.0

    # Short history (5 days < 7)
    short_series = [4.0, 5.0, 6.0, 7.0, 8.0]
    short_res = forecaster.forecast(short_series, horizon_days=7)
    assert short_res["method"] == "median_fallback"
    assert short_res["sample_count"] == 5
    # Median of [4, 5, 6, 7, 8] is 6.0 -> 7-day horizon total = 42.0
    assert abs(short_res["p50"] - 42.0) < 1e-6
    assert short_res["p10"] < short_res["p50"] < short_res["p90"]
    assert short_res["ecpm_bands"]["p10"] < short_res["ecpm_bands"]["p50"] < short_res["ecpm_bands"]["p90"]


def test_max_history_cap_and_sqlite_persistence(tmp_path: Path) -> None:
    store = Phase3Store(tmp_path / "forecasts.db")
    cfg = load_phase3_config()
    forecaster = IRLSQuantileForecaster(cfg, store=store)

    series = [1.0 + 0.1 * t for t in range(90)]
    res = forecaster.forecast(series, horizon_days=7)

    assert res["method"] == "irls_quantile"
    assert res["sample_count"] == cfg.a3_forecaster.max_history_days  # 60

    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM p3_forecasts").fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["method"] == "irls_quantile"
    assert row["sample_count"] == 60
    assert row["horizon_days"] == 7
    assert abs(row["p50_revenue"] - res["p50"]) < 1e-6
    assert abs(row["p50_ecpm"] - res["ecpm_bands"]["p50"]) < 1e-6


def test_mixed_dict_and_malformed_series_failsafe() -> None:
    forecaster = IRLSQuantileForecaster()
    series = [
        {"total_revenue": 2.0, "ecpm": 1.2},
        {"revenue": 2.4, "impressions": 2000},
        {"revenue": float("nan"), "impressions": 1000},
        "invalid_item",
        {"revenue": 2.8, "impressions": 2000},
        {"revenue": 3.1, "impressions": 2000},
        {"revenue": 3.5, "impressions": 2000},
        {"revenue": 3.9, "impressions": 2000},
        {"revenue": 4.2, "impressions": 2000},
    ]
    res = forecaster.forecast(series, horizon_days=3)
    assert res["method"] == "irls_quantile"
    assert res["sample_count"] == 7
    assert res["p10"] <= res["p50"] <= res["p90"]
    assert res["ecpm_bands"]["p10"] <= res["ecpm_bands"]["p50"] <= res["ecpm_bands"]["p90"]
