"""
main.py — Scheduler with diurnal curve, daily cap, rate limiting, graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import signal
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml
from playwright.async_api import async_playwright

import db
from mahi_connector import MahiConnector
import tests.audit as audit_mod
import worker
from pool import ProxyPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

_SHUTDOWN = asyncio.Event()


def _load_cfg(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _diurnal_rate(cfg: dict) -> float:
    """Return the target sessions-per-second rate for the current hour/weekday."""
    now = time.localtime()
    hour = now.tm_hour
    weekday = now.tm_wday  # 0=Mon … 6=Sun

    diurnal = cfg["scheduler"]["diurnal"]
    weekday_scale = cfg["scheduler"]["weekday_scale"]
    base_per_hour = cfg["scheduler"]["sessions_per_hour"]

    factor = diurnal[hour] * weekday_scale[weekday]
    # STAT-1: Organic traffic chaos (5% dead hour, 3% mini viral spike, 92% normal variance)
    chaos_roll = random.random()
    if chaos_roll < 0.05:
        chaos_factor = random.uniform(0.15, 0.35)  # Dead hour / lull
    elif chaos_roll < 0.08:
        chaos_factor = random.uniform(1.8, 3.2)   # Mini viral spike
    else:
        chaos_factor = random.uniform(0.85, 1.15) # Normal organic variance
    rate_per_hour = base_per_hour * factor * chaos_factor
    return max(0.0, rate_per_hour) / 3600.0  # sessions/second


async def _session_loop(cfg: dict, pool: ProxyPool, playwright, browser) -> None:
    """
    Main session dispatch loop. Respects daily_cap, diurnal curve, and concurrency.
    SCHED-1: Microsecond-precision RNG seed to prevent correlated concurrent sessions.
    SCHED-2: Atomic in-flight counter to prevent daily cap overshoot.
    SCHED-3: Exponential backoff on pool exhaustion (max 30 min).
    """
    daily_cap = cfg["scheduler"]["daily_cap"]
    jitter_s = cfg["scheduler"]["jitter_seconds"]
    concurrency = cfg["scheduler"]["concurrency"]
    sem = asyncio.Semaphore(concurrency)

    active_tasks: set[asyncio.Task] = set()
    _in_flight: int = 0          # SCHED-2: atomic in-flight session counter
    _exhaustion_count: int = 0   # SCHED-3: consecutive pool-exhausted events

    async def run_one(proxy) -> None:
        nonlocal _in_flight
        # SCHED-1: Microsecond seed XOR'd with object identity — unique per concurrent session
        rng = random.Random(
            int.from_bytes(proxy.fingerprint_seed[:4], "big")
            ^ int(time.time() * 1_000_000)
            ^ id(proxy)
        )
        async with sem:
            await worker.run_session(playwright, browser, proxy, cfg, rng)
        pool.release(proxy)
        _in_flight -= 1

    while not _SHUTDOWN.is_set():
        # SCHED-2: Atomic cap check — done_today + in_flight >= daily_cap → skip
        done_today = db.today()
        if done_today + _in_flight >= daily_cap:
            logger.info("Daily cap (%d) reached (done=%d, in_flight=%d). Stopping.",
                        daily_cap, done_today, _in_flight)
            break

        # Rate calculation
        rate = _diurnal_rate(cfg)
        if rate <= 0:
            await asyncio.sleep(60)
            continue

        interval = 1.0 / rate
        jitter = random.uniform(-jitter_s, jitter_s)
        sleep_time = max(0.5, interval + jitter)

        # Try to acquire a proxy
        proxy = await pool.acquire()
        if proxy is None:
            _exhaustion_count += 1
            # SCHED-3: Exponential backoff — 60s, 120s, 240s, 480s … max 1800s (30 min)
            wait = min(60 * (2 ** min(_exhaustion_count - 1, 4)), 1800)
            logger.info("Pool exhausted (attempt %d) — sleeping %ds before retry",
                        _exhaustion_count, wait)
            await asyncio.sleep(wait)
            continue
        _exhaustion_count = 0  # Reset on successful acquire

        # SCHED-2: Increment in-flight counter before task starts
        _in_flight += 1

        # Launch session task
        task = asyncio.create_task(run_one(proxy))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

        # Wait before next dispatch
        try:
            await asyncio.wait_for(
                asyncio.shield(asyncio.ensure_future(_SHUTDOWN.wait())),
                timeout=sleep_time,
            )
        except asyncio.TimeoutError:
            pass

    # Wait for all in-flight sessions to complete
    if active_tasks:
        logger.info("Draining %d active sessions…", len(active_tasks))
        await asyncio.gather(*active_tasks, return_exceptions=True)


def _handle_sigterm(*_) -> None:
    logger.info("SIGTERM received — initiating graceful shutdown")
    _SHUTDOWN.set()


async def main() -> None:
    cfg = _load_cfg()
    db.init()

    # Pre-flight audit
    try:
        await audit_mod.run_all_async(cfg)
    except SystemExit as e:
        logger.error("Pre-flight audit failed — aborting.")
        sys.exit(int(str(e)))

    net_mode = cfg.get("network", {}).get("mode", "proxy")
    failover_enabled = cfg.get("failover", {}).get("enabled", False)

    if failover_enabled or net_mode == "dual_failover":
        from failover_manager import DualTransportManager
        from pool import MobileTetherPool
        logger.info("Operating in Dual-ISP Hot-Failover Mode (Mobile ADB + Residential Proxy)")
        mobile_sub = MobileTetherPool(cfg)
        proxy_sub = None
        api_url = cfg.get("proxy", {}).get("api_url", "")
        if api_url:
            proxy_sub = await ProxyPool.from_api(api_url, cfg)
        elif Path(cfg["proxy"]["file"]).is_file():
            proxy_sub = await ProxyPool.from_file(cfg["proxy"]["file"], cfg)

        failover_mgr = DualTransportManager(cfg)
        failover_mgr.set_sub_pools(mobile_pool=mobile_sub, proxy_pool=proxy_sub)
        pool = failover_mgr
    elif net_mode == "mobile_tether":
        from pool import MobileTetherPool
        logger.info("Operating in Mobile USB Tethering Mode (ADB IP Rotation) — Locking Concurrency to 1")
        cfg["scheduler"]["concurrency"] = 1
        pool = MobileTetherPool(cfg)
    else:
        api_url = cfg.get("proxy", {}).get("api_url", "")
        if api_url:
            logger.info("Fetching proxy pool dynamically from API: %s", api_url)
            pool = await ProxyPool.from_api(api_url, cfg)
        else:
            pool = await ProxyPool.from_file(cfg["proxy"]["file"], cfg)

        if len(pool) == 0:
            logger.error("No valid proxies in pool. Exiting.")
            sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    headless = cfg["browser"].get("headless", False)
    slow_mo = cfg["browser"].get("slow_mo_ms", 40)

    # MAHI Browser Custom Chromium Core (Gate 2 MD Spec 2)
    engine_type = cfg.get("browser", {}).get("engine", "mahi")
    executable_path = None
    mahi_conn = MahiConnector()
    if engine_type == "mahi" and mahi_conn.is_available():
        executable_path = mahi_conn.get_chrome_executable_path()
        logger.info("Gate 2 Active: Launching MAHI Browser custom Chromium core (v138.0.7204.0)")

    launch_kwargs: dict = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": [
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-popup-blocking",
            "--window-position=100,100",
            "--window-size=1280,800",
        ],
    }
    if executable_path:
        launch_kwargs["executable_path"] = executable_path

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**launch_kwargs)
        try:
            logger.info("Browser launched. Starting session loop.")
            await _session_loop(cfg, pool, pw, browser)
        finally:
            await browser.close()

    logger.info("Shutdown complete. Sessions today: %d", db.today())
    ctr = db.ctr()
    logger.info("Current CTR (last 100): %.2f%%", ctr * 100)


if __name__ == "__main__":
    asyncio.run(main())

