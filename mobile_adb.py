"""
mobile_adb.py — Android USB Debugging (ADB) Mobile IP Rotation via Airplane Mode.
Provides automatic mobile IP rotation over USB tethering for carrier dynamic IPs.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("mobile_adb")

BASE_DIR = Path(__file__).parent.resolve()
BUNDLED_ADB = BASE_DIR / "bin" / "platform-tools" / "adb.exe"


def get_adb_path(custom_path: str = "") -> str:
    """Resolve the working adb.exe executable path."""
    if custom_path and Path(custom_path).exists():
        return str(Path(custom_path).resolve())

    if BUNDLED_ADB.exists():
        return str(BUNDLED_ADB)

    which = shutil.which("adb")
    if which:
        return which

    raise FileNotFoundError("adb.exe not found on system or in bin/platform-tools")


def run_adb(args: list[str], custom_path: str = "", timeout: float = 12.0) -> tuple[int, str]:
    """Execute an ADB command safely with timeout."""
    try:
        adb_bin = get_adb_path(custom_path)
        cmd = [adb_bin] + args
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return res.returncode, res.stdout.strip()
    except FileNotFoundError as exc:
        return -1, str(exc)
    except subprocess.TimeoutExpired:
        return -1, "ADB command timed out"
    except Exception as exc:
        return -1, f"ADB execution failed: {exc}"


def list_devices(custom_path: str = "") -> list[dict[str, str]]:
    """Return all connected USB debugging devices."""
    code, out = run_adb(["devices"], custom_path=custom_path)
    if code != 0:
        return []

    devices = []
    lines = out.splitlines()
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("List of devices attached") or ln.startswith("*"):
            continue
        parts = re.split(r"\s+", ln)
        if len(parts) >= 2:
            devices.append({"id": parts[0], "status": parts[1]})
    return devices


def get_public_ip(timeout: float = 6.0) -> dict:
    """Fetch the current public IP, ISP/carrier, and geo location."""
    urls = [
        "http://ip-api.com/json/?fields=status,country,countryCode,region,regionName,city,query,org",
        "https://api.ipify.org?format=json",
    ]
    for url in urls:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    ip = data.get("query") or data.get("ip") or ""
                    if ip:
                        return {
                            "ip": ip,
                            "country": data.get("countryCode") or data.get("country") or "IN",
                            "region": data.get("regionName") or data.get("region") or "",
                            "city": data.get("city", "Unknown"),
                            "org": data.get("org", "Cellular Carrier"),
                            "ok": True,
                        }
        except Exception:
            continue
    return {"ip": "", "country": "", "region": "", "city": "", "org": "", "ok": False}


def toggle_airplane_mode(device_id: str = "", wait_seconds: float = 4.0, custom_path: str = "") -> bool:
    """
    Toggle Airplane Mode ON and OFF via ADB to trigger cellular IP renewal.
    Uses multiple fallback commands to support all Android vendor ROMs.
    """
    dev_args = ["-s", device_id] if device_id else []

    # Method 1: cmd connectivity airplane-mode (Android 11+)
    code_on, _ = run_adb(dev_args + ["shell", "cmd", "connectivity", "airplane-mode", "enable"], custom_path)
    if code_on == 0:
        time.sleep(wait_seconds)
        run_adb(dev_args + ["shell", "cmd", "connectivity", "airplane-mode", "disable"], custom_path)
        return True

    # Method 2: global settings + am broadcast (Android 7 - 10)
    run_adb(dev_args + ["shell", "settings", "put", "global", "airplane_mode_on", "1"], custom_path)
    run_adb(dev_args + ["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true"], custom_path)
    time.sleep(wait_seconds)
    run_adb(dev_args + ["shell", "settings", "put", "global", "airplane_mode_on", "0"], custom_path)
    run_adb(dev_args + ["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false"], custom_path)

    # Method 3: direct mobile data toggle fallback (svc data)
    run_adb(dev_args + ["shell", "svc", "data", "disable"], custom_path)
    time.sleep(wait_seconds)
    run_adb(dev_args + ["shell", "svc", "data", "enable"], custom_path)
    return True


def rotate_ip(device_id: str = "", wait_seconds: float = 4.0, custom_path: str = "") -> tuple[bool, str, str, str]:
    """
    Rotate mobile IP, verify that a new cellular IP was assigned, and return:
    (success, old_ip, new_ip, message)
    """
    devices = list_devices(custom_path)
    if not devices:
        return False, "", "", "No Android devices connected via USB debugging (run 'adb devices')"

    # Validate specified or first authorized device
    target_dev = device_id.strip() if device_id else ""
    if target_dev:
        matching = [d for d in devices if d["id"] == target_dev]
        if not matching:
            return False, "", "", f"ADB device {target_dev} not found among connected devices."
        if matching[0]["status"] != "device":
            return False, "", "", f"ADB device {target_dev} is {matching[0]['status']}. Check phone screen to allow USB debugging."
    else:
        auth_devices = [d for d in devices if d["status"] == "device"]
        if not auth_devices:
            return False, "", "", f"Connected device is {devices[0]['status']}. Check phone screen to allow USB debugging."
        target_dev = auth_devices[0]["id"]

    old_info = get_public_ip()
    old_ip = (old_info.get("ip") or "").strip()

    logger.info("Triggering ADB Airplane mode toggle on %s (Current IP: %s)…", target_dev, old_ip)
    toggle_airplane_mode(device_id=target_dev, wait_seconds=wait_seconds, custom_path=custom_path)

    # Wait for tethered mobile data to reconnect and get new IP (up to 15s)
    new_ip = ""
    new_info = {}
    time.sleep(2.0)  # initial settle
    for _ in range(6):
        time.sleep(2.0)
        new_info = get_public_ip(timeout=3.0)
        if new_info.get("ok") and new_info.get("ip"):
            new_ip = new_info["ip"]
            if new_ip != old_ip:
                break

    if not new_ip:
        return False, old_ip, "", "Network did not reconnect after airplane mode toggle"

    if new_ip == old_ip:
        logger.warning("Mobile IP remained the same after rotation: %s", new_ip)
        return True, old_ip, new_ip, f"Carrier re-assigned same IP: {new_ip}"

    logger.info("Mobile IP rotated successfully: %s → %s (%s)", old_ip, new_ip, new_info.get("org", ""))
    return True, old_ip, new_ip, f"IP rotated: {old_ip} → {new_ip} ({new_info.get('org', '')})"

