"""
persistence.py — Model weight persistence for LinTS Contextual Bandit.

Saves and loads precision matrix A and reward vector b per device and globally
using atomic JSON files with base64 encoded binary arrays.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class WeightStore:
    """Saves and loads LinTS model weights (matrix A and vector b) per device and globally.

    Attributes:
        store_dir: Base directory where weight files are stored.
    """

    def __init__(self, store_dir: str | Path = "state/ai_engine/weights") -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        (self.store_dir / "global").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize(name: str) -> str:
        """Sanitize a device or arm identifier for safe filename usage."""
        if not name:
            return "default"
        return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)

    def _path_for(self, device_id: str, arm_id: str) -> Path:
        sanitized_arm = self._sanitize(arm_id)
        if not device_id or device_id.lower() == "global":
            folder = self.store_dir / "global"
        else:
            folder = self.store_dir / self._sanitize(device_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{sanitized_arm}.json"

    def save(self, device_id: str, arm_id: str, A: np.ndarray, b: np.ndarray) -> None:
        """Save precision matrix A and reward vector b for an arm and device.

        Args:
            device_id: ADB serial or device identifier (empty/global for global).
            arm_id:    Arm identifier string.
            A:         Precision matrix (n_features x n_features).
            b:         Reward vector (n_features,).
        """
        path = self._path_for(device_id, arm_id)
        A_arr = np.ascontiguousarray(A, dtype=np.float64)
        b_arr = np.ascontiguousarray(b, dtype=np.float64)

        payload: dict[str, Any] = {
            "arm_id": arm_id,
            "device_id": device_id or "global",
            "shape_A": list(A_arr.shape),
            "shape_b": list(b_arr.shape),
            "dtype": str(A_arr.dtype),
            "A_b64": base64.b64encode(A_arr.tobytes()).decode("ascii"),
            "b_b64": base64.b64encode(b_arr.tobytes()).decode("ascii"),
        }

        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_path.replace(path)
            logger.debug("WeightStore: saved %s for device %s", arm_id, device_id)
        except Exception as exc:
            logger.error("WeightStore: failed to save %s: %s", path, exc)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def load(self, device_id: str, arm_id: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Load precision matrix A and reward vector b for an arm and device.

        Falls back to global weights if device-specific weights are not found.

        Args:
            device_id: ADB serial or device identifier.
            arm_id:    Arm identifier string.

        Returns:
            Tuple of (A, b) as numpy arrays, or None if not found.
        """
        path = self._path_for(device_id, arm_id)
        if not path.exists():
            if device_id and device_id.lower() != "global":
                return self.load_global(arm_id)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            dtype = np.dtype(data.get("dtype", "float64"))
            A_bytes = base64.b64decode(data["A_b64"])
            b_bytes = base64.b64decode(data["b_b64"])
            A = np.frombuffer(A_bytes, dtype=dtype).reshape(data["shape_A"]).copy()
            b = np.frombuffer(b_bytes, dtype=dtype).reshape(data["shape_b"]).copy()
            return A, b
        except Exception as exc:
            logger.error("WeightStore: failed to load %s: %s", path, exc)
            if device_id and device_id.lower() != "global":
                return self.load_global(arm_id)
            return None

    def save_global(self, arm_id: str, A: np.ndarray, b: np.ndarray) -> None:
        """Save precision matrix A and reward vector b to the global arm pool."""
        self.save("global", arm_id, A, b)

    def load_global(self, arm_id: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Load precision matrix A and reward vector b from the global arm pool."""
        path = self._path_for("global", arm_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            dtype = np.dtype(data.get("dtype", "float64"))
            A_bytes = base64.b64decode(data["A_b64"])
            b_bytes = base64.b64decode(data["b_b64"])
            A = np.frombuffer(A_bytes, dtype=dtype).reshape(data["shape_A"]).copy()
            b = np.frombuffer(b_bytes, dtype=dtype).reshape(data["shape_b"]).copy()
            return A, b
        except Exception as exc:
            logger.error("WeightStore: failed to load global %s: %s", path, exc)
            return None

    def list_arms(self, device_id: str = "") -> list[str]:
        """List all arm ids stored for a device (or global if device_id='')."""
        if not device_id or device_id.lower() == "global":
            folder = self.store_dir / "global"
        else:
            folder = self.store_dir / self._sanitize(device_id)

        if not folder.exists():
            if device_id and device_id.lower() != "global":
                folder = self.store_dir / "global"
            if not folder.exists():
                return []

        arms: set[str] = set()
        for p in folder.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                arms.add(data.get("arm_id", p.stem))
            except Exception:
                arms.add(p.stem)

        return sorted(arms)
