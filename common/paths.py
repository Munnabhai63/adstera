"""Canonical file paths and fail-closed atomic JSON helpers."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

DEFAULT_SAFE_MODE_DIR = "state/phase3/ai_engine"
DEFAULT_SAFE_MODE_PATH = "state/phase3/ai_engine/safe_mode.json"


def get_safe_mode_path(override: Optional[Union[str, Path]] = None) -> Path:
    """Resolve the single source of truth for ``safe_mode.json``."""
    if override is not None and str(override).strip():
        return Path(str(override).strip())
    env_override = os.environ.get("PHASE4_SAFE_MODE_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(DEFAULT_SAFE_MODE_PATH)


def atomic_write_json(path: Union[str, Path], data: Mapping[str, Any]) -> Path:
    """Atomically write *data* as UTF-8 JSON via temp file + fsync + replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = handle.name
            json.dump(dict(data), handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
        tmp_path = None
        return target
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _fail_closed_payload(reason: str, *, fail_closed: bool) -> Dict[str, Any]:
    msg = reason if fail_closed else ""
    return {
        "active": bool(fail_closed),
        "entry_reason": msg,
        "reason": msg,
        "entry_ts": 0.0,
        "clean_window_count": 0,
        "clean_windows": 0,
    }


def read_safe_mode_state(
    path: Optional[Union[str, Path]] = None,
    *,
    fail_closed: bool = True,
) -> Dict[str, Any]:
    """Read ``safe_mode.json`` cleanly, failing closed when missing or invalid."""
    sm_path = get_safe_mode_path(path)
    if not sm_path.is_file():
        return _fail_closed_payload("fail_closed: safe_mode.json missing", fail_closed=fail_closed)
    try:
        raw = json.loads(sm_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _fail_closed_payload(
                "fail_closed: safe_mode.json invalid_format", fail_closed=fail_closed
            )
        reason = str(raw.get("entry_reason") or raw.get("reason") or "")
        clean_windows = int(raw.get("clean_window_count", raw.get("clean_windows", 0)) or 0)
        entry_ts = float(raw.get("entry_ts", 0.0) or 0.0)
        return {
            "active": bool(raw.get("active", fail_closed)),
            "entry_reason": reason,
            "reason": reason,
            "entry_ts": entry_ts,
            "clean_window_count": clean_windows,
            "clean_windows": clean_windows,
        }
    except Exception:
        return _fail_closed_payload(
            "fail_closed: safe_mode.json unreadable_or_corrupt", fail_closed=fail_closed
        )
