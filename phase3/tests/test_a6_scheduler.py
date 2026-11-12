"""Unit and statistical tests for A6 NHPP Smart Scheduler and CGNAT IP Tracker."""
from __future__ import annotations

import datetime
import math
import random
from pathlib import Path

from phase3.a6_scheduler.cgnat_tracker import CGNATTracker
from phase3.a6_scheduler.nhpp import NHPPScheduler
from phase3.config_loader import A6SchedulerConfig, CGNATTrackerConfig, Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store


def _local_ts(hour: int, weekday_offset: int = 0) -> float:
    """Return a local timestamp for 2026-11-09 (Monday) + weekday_offset at `hour`:00."""
    base = datetime.datetime(2026, 11, 9 + weekday_offset, hour, 0, 0)
    return base.timestamp()


def test_nhpp_determinism() -> None:
    cfg = load_phase3_config()
    s1 = NHPPScheduler(cfg, rng=random.Random(12345))
    s2 = NHPPScheduler(cfg, rng=random.Random(12345))
    s3 = NHPPScheduler(cfg, rng=random.Random(99999))

    ts = _local_ts(hour=9, weekday_offset=0)
    seq1 = [s1.schedule_next(ts + i * 10.0) for i in range(25)]
    seq2 = [s2.schedule_next(ts + i * 10.0) for i in range(25)]
    seq3 = [s3.schedule_next(ts + i * 10.0) for i in range(25)]

    assert seq1 == seq2
    assert seq1 != seq3


def test_nhpp_intensity_diurnal_and_weekday() -> None:
    cfg = load_phase3_config()
    sched = NHPPScheduler(cfg, rng=random.Random(7))

    # Monday (weekday 0, scale=1.0): 03:00 (diurnal=0.12) vs 09:00 (diurnal=1.00)
    low_ts = _local_ts(hour=3, weekday_offset=0)
    peak_ts = _local_ts(hour=9, weekday_offset=0)
    sun_peak_ts = _local_ts(hour=9, weekday_offset=6)  # Sunday scale=0.66

    low_lam = sched.intensity_at(low_ts)
    peak_lam = sched.intensity_at(peak_ts)
    sun_lam = sched.intensity_at(sun_peak_ts)

    assert abs(low_lam - (90.0 * 0.12 * 1.0) / 3600.0) < 1e-9
    assert abs(peak_lam - (90.0 * 1.00 * 1.0) / 3600.0) < 1e-9
    assert abs(sun_lam - (90.0 * 1.00 * 0.66) / 3600.0) < 1e-9
    assert abs((low_lam / peak_lam) - 0.12) < 1e-9


def test_nhpp_statistical_diurnal_rate_ratio_and_ks() -> None:
    # Wide delay bounds & zero burst to test pure NHPP thinning distribution
    a6_cfg = A6SchedulerConfig(
        base_sessions_per_hour=180.0,
        min_delay_seconds=0.0,
        max_delay_seconds=7200.0,
        burst_probability=0.0,
        burst_multiplier=1.0,
    )
    sched = NHPPScheduler(a6_cfg, rng=random.Random(2026))

    # Sample within constant-intensity windows (Monday 03:00 vs Monday 09:00)
    # Using fixed hour start with small jitter so samples stay inside the hour
    low_ts = _local_ts(hour=3, weekday_offset=0)
    peak_ts = _local_ts(hour=9, weekday_offset=0)

    n = 1500
    low_delays = [sched.schedule_next(low_ts) for _ in range(n)]
    peak_delays = [sched.schedule_next(peak_ts) for _ in range(n)]

    emp_low_rate = 1.0 / (sum(low_delays) / n)
    emp_peak_rate = 1.0 / (sum(peak_delays) / n)
    theo_low_rate = sched.intensity_at(low_ts)
    theo_peak_rate = sched.intensity_at(peak_ts)

    assert abs(emp_low_rate - theo_low_rate) / theo_low_rate < 0.10
    assert abs(emp_peak_rate - theo_peak_rate) / theo_peak_rate < 0.10

    emp_ratio = emp_low_rate / emp_peak_rate
    theo_ratio = theo_low_rate / theo_peak_rate
    assert abs(emp_ratio - theo_ratio) / theo_ratio < 0.12

    # One-sample KS statistic against Exponential(theo_peak_rate)
    sorted_peak = sorted(peak_delays)
    d_max = 0.0
    for idx, x in enumerate(sorted_peak):
        cdf = 1.0 - math.exp(-theo_peak_rate * x)
        d_plus = ((idx + 1) / n) - cdf
        d_minus = cdf - (idx / n)
        d_max = max(d_max, d_plus, d_minus)
    # 99.9% critical value ~ 1.95 / sqrt(n)
    assert d_max < 1.95 / math.sqrt(n)


def test_nhpp_bounds_and_bad_config_failsafe() -> None:
    cfg = load_phase3_config()
    sched = NHPPScheduler(cfg, rng=random.Random(42))
    ts = _local_ts(hour=14, weekday_offset=2)
    for _ in range(100):
        d = sched.schedule_next(ts)
        assert cfg.a6_scheduler.min_delay_seconds <= d <= cfg.a6_scheduler.max_delay_seconds

    bad_cfg = {
        "base_sessions_per_hour": -10,
        "diurnal_curve": [0.0, 0.0],
        "weekday_scale": "bad",
        "min_delay_seconds": 5.0,
        "max_delay_seconds": 1.0,
        "burst_probability": 2.5,
        "burst_multiplier": -1.0,
    }
    bad_sched = NHPPScheduler(bad_cfg, rng=random.Random(1))
    d_nan = bad_sched.schedule_next(float("nan"))
    assert 1.0 <= d_nan <= 5.0


def test_cgnat_24_and_20_collision_and_cooldown(tmp_path: Path) -> None:
    store = Phase3Store(tmp_path / "cgnat.db")
    cfg = Phase3Config(
        cgnat_tracker=CGNATTrackerConfig(
            slash24_cooldown_seconds=1800,
            slash20_cooldown_seconds=600,
            slot_ttl_seconds=3600,
            allow_missing_ip_in_paper=True,
        )
    )
    tracker = CGNATTracker(cfg, store)

    t0 = 1_700_000_000.0
    assert tracker.acquire_slot("dev_a", "100.64.10.5", now_ts=t0) is True

    # While active: same /24 blocked, different /24 in same /20 blocked, different /20 allowed
    assert tracker.acquire_slot("dev_b", "100.64.10.99", now_ts=t0 + 10) is False
    assert tracker.acquire_slot("dev_c", "100.64.15.20", now_ts=t0 + 10) is False
    assert tracker.is_subnet_on_cooldown("100.64.10.99", now_ts=t0 + 10) is True
    assert tracker.is_subnet_on_cooldown("100.64.15.20", now_ts=t0 + 10) is True
    assert tracker.is_subnet_on_cooldown("100.64.48.10", now_ts=t0 + 10) is False
    assert tracker.acquire_slot("dev_d", "100.64.48.10", now_ts=t0 + 10) is True

    # Release dev_a at t0 + 100
    t_rel = t0 + 100.0
    tracker.release_slot("dev_a", now_ts=t_rel)

    # Within /20 cooldown (600s): both /20 and /24 remain blocked
    assert tracker.acquire_slot("dev_c", "100.64.15.20", now_ts=t_rel + 599.0) is False
    assert tracker.acquire_slot("dev_b", "100.64.10.99", now_ts=t_rel + 599.0) is False

    # After /20 cooldown (600s), before /24 cooldown (1800s):
    # different /24 in same /20 succeeds, same /24 still blocked
    assert tracker.acquire_slot("dev_c", "100.64.15.20", now_ts=t_rel + 601.0) is True
    assert tracker.acquire_slot("dev_b", "100.64.10.99", now_ts=t_rel + 601.0) is False

    # Release dev_c and advance past /24 cooldown for dev_a and /20 cooldown for dev_c
    tracker.release_slot("dev_c", now_ts=t_rel + 650.0)
    assert tracker.acquire_slot("dev_b", "100.64.10.99", now_ts=t_rel + 1801.0) is True


def test_cgnat_sqlite_persistence_and_ttl_expiry(tmp_path: Path) -> None:
    db_path = tmp_path / "persist.db"
    cfg = CGNATTrackerConfig(
        slash24_cooldown_seconds=300,
        slash20_cooldown_seconds=100,
        slot_ttl_seconds=60,
        allow_missing_ip_in_paper=False,
    )
    t0 = 1_700_010_000.0

    tracker1 = CGNATTracker(cfg, Phase3Store(db_path))
    assert tracker1.acquire_slot("dev_1", "10.20.30.40", now_ts=t0) is True

    # New instance pointing to same SQLite DB sees the active lock
    tracker2 = CGNATTracker(cfg, Phase3Store(db_path))
    assert tracker2.acquire_slot("dev_2", "10.20.30.41", now_ts=t0 + 20.0) is False

    # After TTL (60s) + slash24 cooldown (300s from release at t0+60), slot auto-expires
    assert tracker2.acquire_slot("dev_2", "10.20.30.41", now_ts=t0 + 400.0) is True


def test_cgnat_missing_and_invalid_ip_failsafe(tmp_path: Path) -> None:
    store = Phase3Store(tmp_path / "failsafe.db")
    t_paper = CGNATTracker(CGNATTrackerConfig(allow_missing_ip_in_paper=True), store)
    assert t_paper.acquire_slot("dev_1", None, now_ts=1000.0) is True
    assert t_paper.acquire_slot("dev_2", "", now_ts=1001.0) is True
    t_paper.release_slot("dev_1", now_ts=1002.0)

    t_strict = CGNATTracker(CGNATTrackerConfig(allow_missing_ip_in_paper=False), store)
    assert t_strict.acquire_slot("dev_3", None, now_ts=1003.0) is False
    assert t_strict.acquire_slot("dev_3", "999.999.999.999", now_ts=1004.0) is False
    assert t_strict.is_subnet_on_cooldown("invalid-ip", now_ts=1004.0) is False
