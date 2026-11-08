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

import yaml
from playwright.async_api import async_playwright

import db
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
    # ±20% random variance
    jitter = random.uniform(0.8, 1.2)
    rate_per_hour = base_per_hour * factor * jitter
    return max(0.0, rate_per_hour) / 3600.0  # sessions/second


async def _session_loop(cfg: dict, pool: ProxyPool, playwright, browser) -> None:
    """
    Main session dispatch loop. Respects daily_cap, diurnal curve, and concurrency.
    """
    daily_cap = cfg["scheduler"]["daily_cap"]
    jitter_s = cfg["scheduler"]["jitter_seconds"]
    concurrency = cfg["scheduler"]["concurrency"]
    sem = asyncio.Semaphore(concurrency)

    active_tasks: set[asyncio.Task] = set()

    async def run_one(proxy) -> None:
        rng = random.Random(int.from_bytes(proxy.fingerprint_seed[:4], "big") ^ int(time.time()))
        async with sem:
            await worker.run_session(playwright, browser, proxy, cfg, rng)
        pool.release(proxy)

    while not _SHUTDOWN.is_set():
        # Daily cap check (from DB)
        done_today = db.today()
        if done_today >= daily_cap:
            logger.info("Daily cap (%d) reached. Stopping.", daily_cap)
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
            logger.info("Pool exhausted — sleeping 60s before retry")
            await asyncio.sleep(60)
            continue

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
    if net_mode == "mobile_tether":
        from pool import MobileTetherPool
        logger.info("Operating in Mobile USB Tethering Mode (ADB IP Rotation)")
        pool = MobileTetherPool(cfg)
    else:
        pool = await ProxyPool.from_file(cfg["proxy"]["file"], cfg)
        if len(pool) == 0:
            logger.error("No valid proxies in pool. Exiting.")
            sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    headless = cfg["browser"].get("headless", False)
    slow_mo = cfg["browser"].get("slow_mo_ms", 40)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-popup-blocking",
            ],
        )
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

