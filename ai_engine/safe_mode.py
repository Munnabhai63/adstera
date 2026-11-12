"""
safe_mode.py — SAFE MODE state machine for the AI Decision Engine.

SAFE MODE is a protective operational state entered when the A2 anomaly
detector flags a CRITICAL anomaly.  While active:

* Ad clicks are paused (enforced by the caller checking :meth:`is_active`).
* Session spawn rate is throttled to ``config.throttle_session_rate`` of normal.
* All windows are assessed; after ``exit_clean_windows`` consecutive clean
  windows the machine auto-exits.

State is persisted to ``state/ai_engine/safe_mode.json`` so restarts do not
accidentally exit SAFE MODE prematurely.

Usage::

    from ai_engine.safe_mode import SafeModeStateMachine
    from ai_engine.config import load_ai_config

    cfg = load_ai_config("ai_engine_config.yaml")
    sm = SafeModeStateMachine(cfg.a2_anomaly.safe_mode, store=store)
    sm.tick(is_clean=True)
    if sm.is_active():
        factor = sm.get_throttle_factor()
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from common.paths import atomic_write_json, get_safe_mode_path, read_safe_mode_state

if TYPE_CHECKING:
    from ai_engine.config import SafeModeConfig
    from ai_engine.store import AIStore

logger = logging.getLogger(__name__)

_STATE_FILENAME = "safe_mode.json"


class SafeModeStateMachine:
    """SAFE MODE state machine with persistent state.

    Args:
        config:    :class:`~ai_engine.config.SafeModeConfig` instance.
        store:     Optional :class:`~ai_engine.store.AIStore` for logging
                   entry / exit events.
        state_dir: Directory where ``safe_mode.json`` is persisted.
                   Defaults to ``state/ai_engine``.
    """

    def __init__(
        self,
        config: "SafeModeConfig",
        store: Optional["AIStore"] = None,
        state_dir: Optional[str | Path] = None,
        state_file: Optional[str | Path] = None,
    ) -> None:
        self._cfg = config
        self._store = store
        if state_file is not None:
            self._state_file = Path(state_file)
            self._state_dir = self._state_file.parent
        elif state_dir is not None:
            self._state_dir = Path(state_dir)
            self._state_file = self._state_dir / _STATE_FILENAME
        else:
            self._state_file = get_safe_mode_path()
            self._state_dir = self._state_file.parent
        self._state_dir.mkdir(parents=True, exist_ok=True)

        # In-memory state (overwritten by _load below; fail-closed if file missing/corrupt)
        self._active: bool = True
        self._entry_reason: str = "fail_closed: uninitialized"
        self._entry_ts: float = 0.0
        self._clean_window_count: int = 0

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load persisted state from disk, failing closed if missing or corrupt."""
        state = read_safe_mode_state(self._state_file, fail_closed=True)
        self._active = bool(state["active"])
        self._entry_reason = str(state["entry_reason"])
        self._entry_ts = float(state["entry_ts"])
        self._clean_window_count = int(state["clean_window_count"])
        if not self._state_file.exists():
            logger.warning(
                "safe_mode: state file missing at %s — failing closed (active=True)",
                self._state_file,
            )
        else:
            logger.info(
                "safe_mode: loaded state — active=%s, clean_windows=%d",
                self._active,
                self._clean_window_count,
            )

    def _save(self) -> None:
        """Persist current state to disk atomically."""
        data = {
            "active": self._active,
            "entry_reason": self._entry_reason,
            "entry_ts": self._entry_ts,
            "clean_window_count": self._clean_window_count,
        }
        try:
            atomic_write_json(self._state_file, data)
        except Exception as exc:
            logger.error("safe_mode: could not persist state — %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enter(self, reason: str) -> None:
        """Activate SAFE MODE.

        If already active, the call is a no-op (re-entrancy is safe).

        Args:
            reason: Human-readable description of why SAFE MODE is being entered.
        """
        if self._active:
            logger.debug("safe_mode: already active — ignoring enter(%r)", reason)
            return

        self._active = True
        self._entry_reason = reason
        self._entry_ts = time.time()
        self._clean_window_count = 0
        self._save()

        logger.warning("safe_mode: ENTERED — reason: %s", reason)

        if self._store is not None:
            try:
                self._store.log_safe_mode(entry_reason=reason, ts=self._entry_ts)
            except Exception as exc:
                logger.error("safe_mode: failed to log entry to store — %s", exc)

    def exit(self, reason: str) -> None:
        """Deactivate SAFE MODE immediately (bypasses clean-window requirement).

        Prefer allowing :meth:`tick` to trigger auto-exit via clean windows.
        Use this method only for operator-forced exits.

        Args:
            reason: Human-readable description of why SAFE MODE is being exited.
        """
        if not self._active:
            logger.debug("safe_mode: not active — ignoring exit(%r)", reason)
            return

        duration_s = time.time() - self._entry_ts
        self._active = False
        self._clean_window_count = 0
        self._save()

        logger.warning(
            "safe_mode: EXITED — reason: %s, duration=%.1fs", reason, duration_s
        )

        if self._store is not None:
            try:
                self._store.log_safe_mode(
                    entry_reason=self._entry_reason,
                    exit_reason=reason,
                    duration_s=duration_s,
                    ts=time.time(),
                )
            except Exception as exc:
                logger.error("safe_mode: failed to log exit to store — %s", exc)

    def tick(self, is_clean: bool) -> None:
        """Advance the state machine by one monitoring window.

        Call this once per ``window_seconds`` interval with the result of the
        latest anomaly check.  When ``exit_clean_windows`` consecutive clean
        ticks accumulate, SAFE MODE is auto-exited.

        Args:
            is_clean: ``True`` when the latest window produced no anomalies.
        """
        if not self._active:
            # Not in SAFE MODE — nothing to do
            return

        if is_clean:
            self._clean_window_count += 1
            logger.info(
                "safe_mode: clean window %d/%d",
                self._clean_window_count,
                self._cfg.exit_clean_windows,
            )
        else:
            if self._clean_window_count > 0:
                logger.info(
                    "safe_mode: anomaly in window — resetting clean counter (was %d)",
                    self._clean_window_count,
                )
            self._clean_window_count = 0

        self._save()

        if self._clean_window_count >= self._cfg.exit_clean_windows:
            self.exit(
                f"auto-exit after {self._clean_window_count} consecutive clean windows"
            )

    def is_active(self) -> bool:
        """Return ``True`` when SAFE MODE is currently active.

        Returns:
            Boolean flag.
        """
        return self._active

    def get_throttle_factor(self) -> float:
        """Return the session-rate multiplier to apply.

        Returns:
            ``1.0`` when SAFE MODE is **not** active; the configured
            ``throttle_session_rate`` (e.g. ``0.3``) when it **is** active.
        """
        if self._active:
            return float(self._cfg.throttle_session_rate)
        return 1.0

    @property
    def entry_reason(self) -> str:
        """The reason SAFE MODE was entered (empty when not active)."""
        return self._entry_reason

    @property
    def clean_window_count(self) -> int:
        """Number of consecutive clean windows accumulated so far."""
        return self._clean_window_count


# Backward-compatibility alias
SafeMode = SafeModeStateMachine

