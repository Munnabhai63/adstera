"""Step 3 Hardware QA Live Tap Test on physical ADB device RZCX21WTS9E.

Requires ``PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION`` in the environment.
Executes 3 live-mode orchestrator steps against ``https://loanraaj.com`` in Android
Chrome, verifying real ``adb shell input tap`` dispatch, A4 RuleFallbackDetector
bbox alignment, A2 anomaly checks, CTRGuard limits, and SQLite persistence.

Usage:
    PHASE3_LIVE_CONFIRM_TOKEN=CONFIRM_LIVE_EXECUTION python -m phase3.scripts.step3_hardware_qa
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.paths import get_safe_mode_path, read_safe_mode_state
from phase3.a6_scheduler.cgnat_tracker import _derive_subnets
from phase3.adapters.adsterra_feed import load_dotenv_into_environ
from phase3.adapters.phase1_device import DeviceTouchCaptureBridge, Phase1DeviceAdapter
from phase3.config_loader import Phase3Config, load_phase3_config
from phase3.db.migrations.runner import Phase3Store, apply_migrations
from phase3.logging_utils import configure_json_logging
from phase3.scripts.step2_device_e2e import _collect_db_counts, _prepare_device_browser
from phase3.wiring.live_orchestrator import Phase3LiveOrchestrator

logger = logging.getLogger("phase3.scripts.step3_hardware_qa")

def _check_safe_mode_files_inactive() -> Dict[str, Any]:
    """Verify the canonical safe_mode.json file exists and is inactive (fail-closed)."""
    sm_path = get_safe_mode_path()
    state = read_safe_mode_state(sm_path, fail_closed=True)
    info = {
        "exists": sm_path.is_file(),
        "active": bool(state["active"]),
        "entry_reason": state["entry_reason"],
    }
    if state["active"]:
        raise RuntimeError(
            f"SafeMode is active in {sm_path}: {state['entry_reason']}"
        )
    return {str(sm_path): info}


def _point_inside_bbox(px: int, py: int, bbox: Any) -> bool:
    """Return True if *(px, py)* lies strictly inside *(x, y, w, h)*."""
    if not bbox or len(bbox) != 4:
        return False
    bx, by, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    return bx <= px < (bx + bw) and by <= py < (by + bh)


async def run_step3_hardware_qa(
    *,
    device_id: str = "RZCX21WTS9E",
    domain: str = "loanraaj.com",
    url: str = "https://loanraaj.com",
    steps: int = 3,
    wait_seconds: float = 10.0,
    settle_seconds: float = 2.5,
    config_path: Optional[str] = None,
    adb_path: str = "",
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute 3-step live-mode hardware QA on a physical ADB device."""
    load_dotenv_into_environ()
    cfg: Phase3Config = load_phase3_config(config_path)
    configure_json_logging(level=cfg.phase3.log_level)

    if not cfg.is_live_confirmed():
        env_var = cfg.phase3.live_confirm_env_var
        raise PermissionError(
            f"Live mode confirmation required: set {env_var}={cfg.phase3.live_confirm_required_phrase}"
        )

    safe_mode_precheck = _check_safe_mode_files_inactive()

    db_path = Path(cfg.phase3.db_path)
    apply_migrations(db_path)
    store = Phase3Store(db_path)

    device_adapter = Phase1DeviceAdapter(cfg, adb_path=adb_path)
    if not device_adapter.is_alive(device_id):
        raise RuntimeError(f"ADB device '{device_id}' is not connected/authorized")

    device_info = device_adapter.get_device_info(device_id)
    ip_info = device_adapter.get_public_ip(timeout=8.0)
    raw_ip = str(ip_info.get("ip") or "").strip()
    norm_ip, subnet_24, subnet_20 = (
        _derive_subnets(raw_ip) if raw_ip else ("", "", "")
    )

    orch = Phase3LiveOrchestrator(
        cfg=cfg,
        live=True,
        strict_live=True,
        store=store,
        device_adapter=device_adapter,
        adb_path=adb_path,
        seed=seed,
    )
    if orch.mode != "live" or orch.paper is not False:
        raise RuntimeError(f"Expected live mode (paper=False), got mode={orch.mode}, paper={orch.paper}")
    if orch.ai.is_safe_mode():
        raise RuntimeError("Phase2AIAdapter SafeMode is active before QA run")

    bridge = DeviceTouchCaptureBridge(device_adapter, device_id, paper=False)

    adb_sequences: List[Dict[str, Any]] = []
    step_results: List[Dict[str, Any]] = []
    tap_verifications: List[Dict[str, Any]] = []

    try:
        for idx in range(max(1, int(steps))):
            if idx > 0:
                await asyncio.sleep(max(0.5, float(settle_seconds)))

            cmds = _prepare_device_browser(device_id, url, adb_path=adb_path)
            adb_sequences.append({"step": idx + 1, "commands": cmds})
            await asyncio.sleep(max(1.0, float(wait_seconds)))

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

            # Verify all QA invariants per step immediately
            cg = res.get("ctr_guard") or {}
            tap_coords = res.get("tap_coords")
            bbox = res.get("bbox")
            inside = (
                _point_inside_bbox(int(tap_coords[0]), int(tap_coords[1]), bbox)
                if tap_coords
                else False
            )
            tap_verifications.append(
                {
                    "step": idx + 1,
                    "tap_coords": list(tap_coords) if tap_coords else None,
                    "bbox": list(bbox) if bbox else None,
                    "inside_bbox": inside,
                    "a4_source": res.get("a4_source"),
                    "a4_verified": res.get("a4_verified"),
                    "a2_severity": res.get("a2_severity"),
                    "a2_ok": res.get("a2_ok"),
                    "ctr_guard": cg,
                    "action": res.get("action"),
                    "executed_touch": res.get("executed_touch"),
                }
            )

            assert res.get("a2_severity") == "OK", f"Step {idx+1} A2 severity != OK: {res}"
            assert res.get("a2_ok") is True, f"Step {idx+1} a2_ok != True: {res}"
            assert float(cg.get("hard_cap", 0.0)) == 0.045, f"Step {idx+1} hard_cap != 0.045: {cg}"
            assert cg.get("would_breach") is False, f"Step {idx+1} would_breach != False: {cg}"
            assert cg.get("deferred") is False, f"Step {idx+1} deferred != False: {cg}"
            assert res.get("a4_verified") is True, f"Step {idx+1} a4_verified != True: {res}"
            assert res.get("a4_source") == "rule_fallback", f"Step {idx+1} a4_source != rule_fallback: {res}"
            assert res.get("action") == "click", f"Step {idx+1} action != click: {res}"
            assert res.get("executed_touch") is True, f"Step {idx+1} executed_touch != True: {res}"
            assert inside is True, f"Step {idx+1} tap {tap_coords} not strictly inside bbox {bbox}"
    finally:
        orch.ai.save_weights(device_id=device_id)

    assert len(bridge.executed_taps) == int(steps), (
        f"Expected {steps} executed taps on bridge, got {len(bridge.executed_taps)}"
    )

    # Update p3_farm_devices totals from authoritative SQLite counts
    usb_port_map = dict(getattr(cfg.b2_farm, "usb_port_map", {}) or {})
    usb_port = next(iter(usb_port_map.keys()), "port_1")
    cdp_port = int(usb_port_map.get(usb_port, 9222))

    with store.connect() as conn:
        sess_row = conn.execute(
            "SELECT COUNT(*) FROM p3_sessions WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        click_row = conn.execute(
            "SELECT COUNT(*) FROM p3_decisions_rewards WHERE device_id = ? AND executed_touch = 1",
            (device_id,),
        ).fetchone()
        total_exec_row = conn.execute(
            "SELECT COUNT(*) FROM p3_decisions_rewards WHERE executed_touch = 1"
        ).fetchone()
        total_dev_sessions = int(sess_row[0]) if sess_row else 0
        total_dev_clicks = int(click_row[0]) if click_row else 0
        total_executed_touches = int(total_exec_row[0]) if total_exec_row else 0

    store.upsert_farm_device(
        device_id=device_id,
        usb_port=usb_port,
        cdp_port=cdp_port,
        b1_port=9320,
        status="healthy",
        consecutive_failures=0,
        quarantined_until=0.0,
        total_sessions=total_dev_sessions,
        total_clicks=total_dev_clicks,
        last_seen_at=time.time(),
    )

    return {
        "status": "ok",
        "mode": orch.mode,
        "paper": orch.paper,
        "device_id": device_id,
        "device_info": device_info,
        "domain": domain,
        "url": url,
        "ip_address": norm_ip,
        "subnet_24": subnet_24,
        "subnet_20": subnet_20,
        "safe_mode_precheck": safe_mode_precheck,
        "adb_sequences": adb_sequences,
        "bridge_executed_taps": [list(t) for t in bridge.executed_taps],
        "tap_verifications": tap_verifications,
        "steps_executed": len(step_results),
        "steps": step_results,
        "executed_touch_1_count": total_executed_touches,
        "device_totals": {
            "total_sessions": total_dev_sessions,
            "total_clicks": total_dev_clicks,
        },
        "db_counts": _collect_db_counts(db_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step 3 Hardware QA Live Tap Test.")
    p.add_argument("--device", default="RZCX21WTS9E", help="Target ADB device serial")
    p.add_argument("--domain", default="loanraaj.com", help="Target domain")
    p.add_argument("--url", default="https://loanraaj.com", help="Target URL")
    p.add_argument("--steps", type=int, default=3, help="Number of live tap steps")
    p.add_argument("--wait-seconds", type=float, default=10.0, help="Render wait after Chrome launch")
    p.add_argument("--settle-seconds", type=float, default=2.5, help="Settle wait after physical tap")
    p.add_argument("--config", default=None, help="Path to phase3/config.yaml")
    p.add_argument("--adb-path", default="", help="Optional path to adb.exe")
    p.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = asyncio.run(
            run_step3_hardware_qa(
                device_id=args.device,
                domain=args.domain,
                url=args.url,
                steps=args.steps,
                wait_seconds=args.wait_seconds,
                settle_seconds=args.settle_seconds,
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
