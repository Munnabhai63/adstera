"""
freellmapi_daemon.py — Autonomous FreeLLMAPI Supervisor & Health Watchdog.
Ensures local FreeLLMAPI router daemon (port 3001) is running and auto-recovers from faults.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("freellmapi_daemon")

FREELLM_DIR = Path(r"F:\UserData\Downloads\ai-power-tools\freellmapi\server")
SERVER_INDEX = FREELLM_DIR / "dist" / "index.js"


def is_server_healthy() -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get("http://localhost:3001/v1/models", headers={"Authorization": "Bearer freellmapi-ceb04983702628b4439a5a1d9e9bf34484f948c29dbe8b4f"})
            return r.status_code == 200
    except Exception:
        return False


def run_daemon() -> None:
    if not SERVER_INDEX.exists():
        logger.error("FreeLLMAPI build not found at %s", SERVER_INDEX)
        sys.exit(1)

    logger.info("FreeLLMAPI Watchdog starting (listening on http://localhost:3001)...")

    while True:
        if is_server_healthy():
            time.sleep(15)
            continue

        logger.warning("FreeLLMAPI not responding on port 3001 — launching server process...")
        try:
            proc = subprocess.Popen(
                ["node", "dist/index.js"],
                cwd=str(FREELLM_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            logger.info("Spawned FreeLLMAPI (PID: %d)", proc.pid)

            # Wait for startup
            for _ in range(15):
                time.sleep(1)
                if is_server_healthy():
                    logger.info("FreeLLMAPI is online and healthy!")
                    break

            proc.wait()
            logger.warning("FreeLLMAPI server exited with code %s. Restarting in 5s...", proc.returncode)
            time.sleep(5)
        except Exception as e:
            logger.error("Error managing FreeLLMAPI process: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    run_daemon()
