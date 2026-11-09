"""
session_tracer.py — Step 5.1: Playwright Session Trace Recording & Replay

Records Playwright traces for degraded/failed sessions so you can replay
them visually like a video to debug exactly what went wrong.

Usage:
    # View a trace:
    playwright show-trace traces/session_proxy_abc_1699999999.zip

Features:
    - Only records traces when debug_traces=true in config (zero overhead normally)
    - Traces are saved ONLY for degraded sessions (saves disk space)
    - Auto-rotate: keeps only last 50 traces (configurable)
    - Trace contains: screenshots, DOM snapshots, network requests, console logs
    - Telegram alert with trace filename when session degrades
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TRACES_DIR = Path("traces")
TRACES_DIR.mkdir(exist_ok=True)


class SessionTracer:
    """
    Context-aware Playwright trace recorder.

    Wraps a BrowserContext to start/stop tracing with auto-save on failure.

    Usage in worker.py:
        tracer = SessionTracer(cfg, proxy_id)
        await tracer.start(context)
        ...  # session runs
        await tracer.stop(context, status="degraded")  # saves only if degraded
    """

    def __init__(self, cfg: dict, proxy_id: str) -> None:
        self.enabled: bool = cfg.get("debug_traces", False)
        self.proxy_id: str = proxy_id
        self.max_traces: int = int(cfg.get("max_traces", 50))
        self._started: bool = False
        self._trace_path: Path | None = None

    async def start(self, context) -> None:
        """Start recording trace on the browser context."""
        if not self.enabled:
            return
        try:
            await context.tracing.start(
                screenshots=True,   # Capture screenshots at each step
                snapshots=True,     # Capture DOM snapshots
                sources=True,       # Include source files
            )
            self._started = True
            logger.debug("Trace started for proxy %s", self.proxy_id)
        except Exception as exc:
            logger.debug("Trace start failed: %s", exc)
            self._started = False

    async def stop(
        self,
        context,
        status: str = "ok",
        session_id: int | None = None,
    ) -> Path | None:
        """
        Stop recording. Saves trace file ONLY if session status == 'degraded'.
        Returns the saved trace path, or None if not saved.
        """
        if not self.enabled or not self._started:
            return None

        self._started = False

        if status != "degraded":
            # Discard trace — no need to save successful sessions
            try:
                await context.tracing.stop()
            except Exception:
                pass
            return None

        # Build trace filename
        ts = int(time.time())
        import re
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", self.proxy_id)
        filename = f"session_{safe_id}_{ts}.zip"
        trace_path = TRACES_DIR / filename
        self._trace_path = trace_path

        try:
            await context.tracing.stop(path=str(trace_path))
            logger.info(
                "Trace saved → %s (view: playwright show-trace %s)",
                trace_path, trace_path
            )
            self._rotate_old_traces()
            return trace_path
        except Exception as exc:
            logger.debug("Trace save failed: %s", exc)
            return None

    def _rotate_old_traces(self) -> None:
        """Keep only the last N trace files, delete older ones."""
        try:
            all_traces = sorted(
                TRACES_DIR.glob("session_*.zip"),
                key=lambda p: p.stat().st_mtime,
            )
            excess = len(all_traces) - self.max_traces
            if excess > 0:
                for old in all_traces[:excess]:
                    old.unlink(missing_ok=True)
                    logger.debug("Rotated old trace: %s", old.name)
        except Exception as exc:
            logger.debug("Trace rotation error: %s", exc)

    @property
    def last_trace_path(self) -> Path | None:
        return self._trace_path


def list_traces() -> list[dict]:
    """
    List all saved trace files with metadata.
    Used by UI dashboard to show recent failures.
    """
    traces = []
    for f in sorted(TRACES_DIR.glob("session_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = f.stat()
            traces.append({
                "filename": f.name,
                "path": str(f),
                "size_kb": round(stat.st_size / 1024, 1),
                "mtime": stat.st_mtime,
                "view_cmd": f"playwright show-trace {f}",
            })
        except Exception:
            pass
    return traces


def build_from_config(cfg: dict, proxy_id: str) -> SessionTracer:
    """Build a SessionTracer from config."""
    return SessionTracer(cfg=cfg, proxy_id=proxy_id)
