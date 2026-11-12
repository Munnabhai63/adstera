"""Step 2 physical ADB device E2E runner for Phase 3 (--paper mode).

Inspects the attached physical Android device over ADB, detects its real
mobile public IP and /24 + /20 carrier subnets, registers the device and
CGNAT slot in ``state/phase3/phase3.db``, wakes the screen, opens the
publisher domain in Android Chrome, verifies A4 RuleFallbackDetector on the
live UIAutomator tree, and executes a 5-step ``--paper`` orchestrator run.

Usage:
    python -m phase3.scripts.step2_device_e2e
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import mobile_adb
from phase3.a6_scheduler.cgnat_tracker import CGNATTracker, _derive_subnets
from phase3.adapters.adsterra_feed import load_dotenv_into_environ
from phase3.adapters.phase1_device import DeviceTouchCaptureBridge, Phase1DeviceAdapter
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store, apply_migrations
from phase3.logging_utils import configure_json_logging, log_event
from phase3.wiring.live_orchestrator import Phase3LiveOrchestrator

logger = logging.getLogger("phase3.scripts.step2_device_e2e")


def _check_is_locked(serial: str, adb_path: str = "") -> bool:
    """Return True if Android keyguard/lockscreen is currently showing."""
    code, out = mobile_adb.run_adb(
        ["-s", serial, "shell", "dumpsys", "window", "policy"],
        custom_path=adb_path,
        timeout=8.0,
    )
    if code != 0:
        return False
    lower = (out or "").lower()
    return "showing=true" in lower or "isstatusbarkeyguard=true" in lower


def _prepare_device_browser(
    serial: str,
    url: str,
    adb_path: str = "",
) -> List[str]:
    """Wake screen, unlock if needed, and launch *url* in Android Chrome."""
    commands_run: List[str] = []

    wake_args = ["-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"]
    code_w, out_w = mobile_adb.run_adb(wake_args, custom_path=adb_path, timeout=8.0)
    commands_run.append("adb " + " ".join(wake_args))
    if code_w != 0:
        raise RuntimeError(f"ADB wakeup failed on {serial}: {out_w}")

    if _check_is_locked(serial, adb_path=adb_path):
        menu_args = ["-s", serial, "shell", "input", "keyevent", "KEYCODE_MENU"]
        mobile_adb.run_adb(menu_args, custom_path=adb_path, timeout=8.0)
        commands_run.append("adb " + " ".join(menu_args))

        swipe_args = ["-s", serial, "shell", "input", "swipe", "540", "2200", "540", "700", "250"]
        mobile_adb.run_adb(swipe_args, custom_path=adb_path, timeout=8.0)
        commands_run.append("adb " + " ".join(swipe_args))

    view_args = [
        "-s",
        serial,
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        url,
        "com.android.chrome",
    ]
    code_v, out_v = mobile_adb.run_adb(view_args, custom_path=adb_path, timeout=10.0)
    commands_run.append("adb " + " ".join(view_args))
    if code_v != 0:
        raise RuntimeError(f"ADB Chrome launch failed on {serial}: {out_v}")

    return commands_run


def _collect_db_counts(db_path: str | Path) -> Dict[str, int]:
    """Return current row counts across Phase 3 SQLite tables."""
    tables = [
        "p3_sessions",
        "p3_decisions_rewards",
        "p3_cgnat_slots",
        "p3_forecasts",
        "p3_farm_devices",
        "p3_calibration_reports",
    ]
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        counts: Dict[str, int] = {}
        for tbl in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                counts[tbl] = int(row[0]) if row else 0
            except sqlite3.Error:
                counts[tbl] = 0
        return counts
    finally:
        conn.close()


async def run_step2_e2e(
    *,
    device_id: str = "RZCX21WTS9E",
    domain: str = "loanraaj.com",
    url: str = "https://loanraaj.com",
    steps: int = 5,
    wait_seconds: float = 10.0,
    config_path: Optional[str] = None,
    adb_path: str = "",
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute full Step 2 live-device paper-mode orchestration."""
    load_dotenv_into_environ()
    cfg: Phase3Config = load_phase3_config(config_path)
    configure_json_logging(level=cfg.phase3.log_level)

    db_path = Path(cfg.phase3.db_path)
    apply_migrations(db_path)
    store = Phase3Store(db_path)

    device_adapter = Phase1DeviceAdapter(cfg, adb_path=adb_path)
    if not device_adapter.is_alive(device_id):
        raise RuntimeError(f"ADB device '{device_id}' is not connected/authorized (--require-device)")

    device_info = device_adapter.get_device_info(device_id)
    ip_info = device_adapter.get_public_ip(timeout=8.0)
    raw_ip = str(ip_info.get("ip") or "").strip()
    if not raw_ip:
        raise RuntimeError(f"Failed to resolve public mobile IP for device '{device_id}': {ip_info}")

    norm_ip, subnet_24, subnet_20 = _derive_subnets(raw_ip)

    usb_port_map = dict(getattr(cfg.b2_farm, "usb_port_map", {}) or {})
    usb_port = next(iter(usb_port_map.keys()), "port_1")
    cdp_port = int(usb_port_map.get(usb_port, 9222))

    # Register farm device & CGNAT carrier subnet slot
    store.upsert_farm_device(
        device_id=device_id,
        usb_port=usb_port,
        cdp_port=cdp_port,
        b1_port=9320,
        status="healthy",
        consecutive_failures=0,
        quarantined_until=0.0,
        total_sessions=0,
        total_clicks=0,
        last_seen_at=time.time(),
    )

    cgnat = CGNATTracker(cfg, store=store)
    cgnat_acquired = cgnat.acquire_slot(device_id, ip_address=norm_ip)

    # Wake device, launch Chrome -> target URL, and wait for full render
    adb_commands = _prepare_device_browser(device_id, url, adb_path=adb_path)
    await asyncio.sleep(max(1.0, float(wait_seconds)))

    orch = Phase3LiveOrchestrator(
        cfg=cfg,
        live=False,
        strict_live=False,
        store=store,
        device_adapter=device_adapter,
        adb_path=adb_path,
        seed=seed,
    )
    bridge = DeviceTouchCaptureBridge(device_adapter, device_id, paper=True)

    # Pre-check A4 RuleFallbackDetector on live device capture
    pre_png = bridge.screenshot()
    pre_xml = bridge.dump_ui()
    pre_det = orch.ai.detect_ads(
        pre_png,
        {"ui_tree": pre_xml, "page_source": pre_xml},
        ui_tree=pre_xml,
    )
    precheck_a4 = {
        "source": pre_det.get("source"),
        "verified": bool(pre_det.get("verified")),
        "confidence": float(pre_det.get("confidence", 0.0)),
        "label": pre_det.get("label"),
        "bbox": pre_det.get("bbox"),
        "xml_len": len(pre_xml),
        "png_bytes": len(pre_png),
    }

    if not precheck_a4["verified"] or precheck_a4["source"] != "rule_fallback":
        log_event(
            logger,
            logging.WARNING,
            "step2_precheck_a4_unverified",
            device_id=device_id,
            precheck=precheck_a4,
        )

    step_results: List[Dict[str, Any]] = []
    try:
        for _ in range(max(1, int(steps))):
            res = await orch.run_step(
                touch=bridge,
                capture=bridge,
                device_id=device_id,
                domain=domain,
                ip_address=norm_ip,
                subnet_24=subnet_24,
                subnet_20=subnet_20,
                session_age_s=30.0,
            )
            step_results.append(res)
            await asyncio.sleep(0.25)
    finally:
        orch.ai.save_weights(device_id=device_id)
        if cgnat_acquired:
            cgnat.release_slot(device_id)

    # Update farm device session counter after completing steps
    with store.connect() as conn:
        row_cnt = conn.execute(
            "SELECT COUNT(*) FROM p3_sessions WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        total_dev_sessions = int(row_cnt[0]) if row_cnt else len(step_results)

    store.upsert_farm_device(
        device_id=device_id,
        usb_port=usb_port,
        cdp_port=cdp_port,
        b1_port=9320,
        status="healthy",
        consecutive_failures=0,
        quarantined_until=0.0,
        total_sessions=total_dev_sessions,
        total_clicks=0,
        last_seen_at=time.time(),
    )

    return {
        "status": "ok",
        "device_id": device_id,
        "device_info": device_info,
        "domain": domain,
        "url": url,
        "ip_info": ip_info,
        "ip_address": norm_ip,
        "subnet_24": subnet_24,
        "subnet_20": subnet_20,
        "cgnat_acquired": cgnat_acquired,
        "adb_commands": adb_commands,
        "precheck_a4": precheck_a4,
        "steps_executed": len(step_results),
        "steps": step_results,
        "db_counts": _collect_db_counts(db_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step 2 live ADB device E2E runner (--paper).")
    p.add_argument("--device", default="RZCX21WTS9E", help="Target ADB device serial")
    p.add_argument("--domain", default="loanraaj.com", help="Target domain")
    p.add_argument("--url", default="https://loanraaj.com", help="URL to open in Chrome")
    p.add_argument("--steps", type=int, default=5, help="Number of orchestrator steps")
    p.add_argument("--wait-seconds", type=float, default=10.0, help="Seconds to wait after Chrome launch")
    p.add_argument("--config", default=None, help="Path to phase3/config.yaml")
    p.add_argument("--adb-path", default="", help="Optional path to adb.exe")
    p.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = asyncio.run(
            run_step2_e2e(
                device_id=args.device,
                domain=args.domain,
                url=args.url,
                steps=args.steps,
                wait_seconds=args.wait_seconds,
                config_path=args.config,
                adb_path=args.adb_path,
                seed=args.seed,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2), file=sys.stderr)
        return 3
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
