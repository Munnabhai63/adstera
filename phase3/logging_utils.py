"""Structured JSON-lines logging with per-session correlation IDs."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from typing import Any, Dict, Optional

_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "phase3_correlation_id", default=""
)


def new_correlation_id(prefix: str = "p3") -> str:
    """Generate a short unique correlation ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def set_correlation_id(cid: str) -> contextvars.Token[str]:
    """Bind correlation ID to the current async/thread context."""
    return _CORRELATION_ID.set(cid)


def get_correlation_id() -> str:
    """Return active correlation ID or empty string."""
    return _CORRELATION_ID.get()


class JsonLinesFormatter(logging.Formatter):
    """Formats every log record as a single valid JSON line with correlation_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": round(time.time(), 6),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "") or get_correlation_id(),
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_json_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Configure root phase3 logger to emit JSON lines."""
    root = logging.getLogger("phase3")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    fmt = JsonLinesFormatter()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    root.propagate = False


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    correlation_id: Optional[str] = None,
    **fields: Any,
) -> None:
    """Emit a structured JSON log event with arbitrary key-value fields."""
    cid = correlation_id if correlation_id is not None else get_correlation_id()
    logger.log(
        level,
        event,
        extra={"correlation_id": cid, "extra_fields": {"event": event, **fields}},
    )
