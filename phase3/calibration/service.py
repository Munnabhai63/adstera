"""Background calibration service and CLI entrypoint.

Usage:
    python -m phase3.calibration.service --once
    python -m phase3.calibration.service
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase3.calibration.monitor import (
    CalibrationConfig,
    CalibrationMonitor,
    load_calibration_config,
)
from phase3.logging_utils import configure_json_logging, log_event

logger = logging.getLogger("phase3.calibration.service")


class CalibrationService:
    """Async periodic calibration runner with graceful SIGTERM/SIGINT shutdown."""

    def __init__(
        self,
        cfg: Optional[CalibrationConfig] = None,
        *,
        monitor: Optional[CalibrationMonitor] = None,
        config_path: Optional[str | Path] = None,
        db_path: Optional[str | Path] = None,
        legacy_db_path: Optional[str | Path] = None,
        interval_seconds: Optional[int] = None,
    ) -> None:
        self.cfg = cfg if cfg is not None else load_calibration_config(config_path)
        if db_path is not None:
            self.cfg.db_path = str(db_path)
        if legacy_db_path is not None:
            self.cfg.legacy_db_path = str(legacy_db_path)
        if interval_seconds is not None:
            self.cfg.check_interval_seconds = max(1, int(interval_seconds))
        self.monitor = (
            monitor
            if monitor is not None
            else CalibrationMonitor(
                self.cfg,
                db_path=db_path,
                legacy_db_path=legacy_db_path,
            )
        )
        self._stop_event: Optional[asyncio.Event] = None
        self._stopped = False
        self.last_report: Optional[Dict[str, Any]] = None

    def stop(self) -> None:
        """Request graceful shutdown of the service loop."""
        self._stopped = True
        if self._stop_event is not None:
            self._stop_event.set()
        log_event(logger, logging.INFO, "calibration_service_stop_requested")

    def run_once(self) -> Dict[str, Any]:
        """Execute a single calibration check synchronously."""
        report = self.monitor.run_check()
        self.last_report = report
        return report

    async def run_forever(self, *, max_cycles: Optional[int] = None) -> List[Dict[str, Any]]:
        """Run periodic calibration checks until stopped or ``max_cycles`` reached."""
        self._stop_event = asyncio.Event()
        if self._stopped:
            self._stop_event.set()

        reports: List[Dict[str, Any]] = []
        cycles = 0
        interval = max(1, int(self.cfg.check_interval_seconds))

        log_event(
            logger,
            logging.INFO,
            "calibration_service_started",
            interval_seconds=interval,
            db_path=self.cfg.db_path,
        )

        while not self._stop_event.is_set():
            report = await asyncio.to_thread(self.run_once)
            reports.append(report)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=float(interval))
            except asyncio.TimeoutError:
                continue

        log_event(
            logger,
            logging.INFO,
            "calibration_service_stopped",
            cycles_completed=cycles,
        )
        return reports


def _install_signal_handlers(service: CalibrationService) -> None:
    def _handle_sig(*_args: Any) -> None:
        service.stop()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, service.stop)
            except (NotImplementedError, RuntimeError, ValueError):
                signal.signal(sig, _handle_sig)
    except RuntimeError:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handle_sig)
            except (ValueError, OSError):
                pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase3.calibration.service",
        description="Phase 4 Calibration & Drift Monitoring Service",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single calibration check and exit.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to calibration config.yaml.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional override path to phase3.db.",
    )
    parser.add_argument(
        "--legacy-db-path",
        type=str,
        default=None,
        help="Optional override path to legacy sessions.db.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override check interval in seconds for daemon mode.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit non-zero when --once detects model drift.",
    )
    return parser


async def _run_daemon(service: CalibrationService) -> None:
    _install_signal_handlers(service)
    await service.run_forever()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = load_calibration_config(args.config)
    configure_json_logging(cfg.log_level)

    service = CalibrationService(
        cfg=cfg,
        db_path=args.db_path,
        legacy_db_path=args.legacy_db_path,
        interval_seconds=args.interval,
    )

    if args.once:
        report = service.run_once()
        print(json.dumps(report, ensure_ascii=False, default=str))
        if args.fail_on_drift and report.get("drift_detected"):
            return 2
        return 0

    try:
        asyncio.run(_run_daemon(service))
    except KeyboardInterrupt:
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
