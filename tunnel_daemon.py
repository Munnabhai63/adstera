"""
tunnel_daemon.py — Autonomous Cloudflare Tunnel Supervisor for rechargekar.com.
Runs bin/cloudflared.exe with the dedicated tunnel token and guarantees zero downtime.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tunnel_daemon")

BASE_DIR = Path(__file__).parent.resolve()
CLOUDFLARED_BIN = BASE_DIR / "bin" / "cloudflared.exe"

TUNNEL_TOKEN = os.environ.get(
    "CLOUDFLARE_TUNNEL_TOKEN",
    "eyJhIjoiMWE1N2JlNzk3ZTJjOGM5ZTZiMjc4NDAwNDZkMTY2MjIiLCJ0IjoiM2ZkNjAxYzctMjg4Zi00OTZjLTlmOTMtZGIwZDM3ODIyMDc2IiwicyI6InJSODBMUGRxOU9mWm5JUW9JcVFUL2pydW9DQjcwbUQyakV4TlNPaXZpKzA9In0=",
)


def run_tunnel() -> None:
    if not CLOUDFLARED_BIN.exists():
        logger.error("cloudflared.exe not found at %s", CLOUDFLARED_BIN)
        sys.exit(1)

    cmd = [
        str(CLOUDFLARED_BIN),
        "tunnel",
        "run",
        "--token",
        TUNNEL_TOKEN,
        "--protocol",
        "quic",
    ]

    logger.info("Starting Cloudflare Tunnel for rechargekar.com (quic)...")
    while True:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            logger.info("Tunnel process spawned (PID: %s)", proc.pid)

            # Stream logs
            if proc.stdout:
                for line in proc.stdout:
                    line_s = line.strip()
                    if line_s:
                        if "Registered tunnel connection" in line_s or "Connection" in line_s:
                            logger.info("[Tunnel Connection] %s", line_s)
                        elif "error" in line_s.lower():
                            logger.warning("[Tunnel Warning] %s", line_s)

            proc.wait()
            logger.warning("Tunnel process exited with code %s. Restarting in 3 seconds...", proc.returncode)
            time.sleep(3)
        except KeyboardInterrupt:
            logger.info("Stopping tunnel daemon...")
            break
        except Exception as exc:
            logger.error("Unexpected error in tunnel daemon: %s. Retrying in 5s...", exc)
            time.sleep(5)


if __name__ == "__main__":
    run_tunnel()
