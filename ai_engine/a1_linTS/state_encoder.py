"""
state_encoder.py – Deterministic AgentState → feature vector encoder for A1 LinTS.
"""
from __future__ import annotations

import numpy as np

# Slot types in a fixed canonical order for one-hot index
_SLOT_TYPES = ["banner", "interstitial", "popunder", "native", "none"]
_N_SLOTS = len(_SLOT_TYPES)

# Default RPM scale matching ai_engine_config.yaml
_DEFAULT_RPM_SCALE = 1000.0


def encode(state, n_features: int = 8, rpm_scale: float = _DEFAULT_RPM_SCALE) -> np.ndarray:
    """Deterministically encode an :class:`AgentState` into a float32 feature vector.

    Features (all normalised to roughly [-1, 1] or [0, 1]):

    ======  =====================================================
    Index   Feature
    ======  =====================================================
    0       ``domain_id`` hash mod 1000 divided by 1000
    1       Slot-type one-hot index divided by ``n_slots``
    2       ``time_of_day_h`` divided by 24
    3       ``recent_ctr`` (raw; typically 0.01–0.10)
    4       ``recent_rpm`` divided by *rpm_scale*
    5       ``device_id_hash`` divided by 1e6 (clamped to [0,1])
    6       ``session_age_s`` divided by 3600 (clamped to [0,1])
    7       ``bbox_confidence`` (already 0–1)
    ======  =====================================================

    Any extra features beyond index 7 are filled with 0.0.

    Args:
        state:      An :class:`~ai_engine.interfaces.AgentState` instance.
        n_features: Output vector dimension. Must be >= 8.
        rpm_scale:  Divisor for recent_rpm normalisation.

    Returns:
        ``np.ndarray`` of shape ``(n_features,)`` and dtype ``float32``.

    Raises:
        ValueError: If *n_features* < 8.
    """
    if n_features < 8:
        raise ValueError(f"n_features must be >= 8, got {n_features}")

    vec = np.zeros(n_features, dtype=np.float32)

    # 0 — domain hash
    vec[0] = float(abs(int(state.domain_id)) % 1000) / 1000.0

    # 1 — slot type one-hot index
    slot = getattr(state, "slot_type", "none") or "none"
    try:
        slot_idx = _SLOT_TYPES.index(slot.lower())
    except ValueError:
        slot_idx = _N_SLOTS - 1  # unknown → "none" bucket
    vec[1] = float(slot_idx) / float(_N_SLOTS)

    # 2 — time of day
    vec[2] = float(max(0, min(23, int(state.time_of_day_h)))) / 24.0

    # 3 — recent CTR (raw; no normalisation needed for LTS)
    vec[3] = float(max(0.0, state.recent_ctr))

    # 4 — recent RPM normalised
    vec[4] = float(max(0.0, state.recent_rpm)) / float(rpm_scale)

    # 5 — device_id_hash
    vec[5] = min(1.0, float(abs(int(state.device_id_hash))) / 1e6)

    # 6 — session age normalised (cap at 1 hour)
    vec[6] = min(1.0, float(max(0.0, state.session_age_s)) / 3600.0)

    # 7 — bbox confidence
    vec[7] = float(max(0.0, min(1.0, state.bbox_confidence)))

    return vec
