"""A6 CGNAT Mobile-Tower IP Tracker.

Tracks active device IP slots and carrier /24 and /20 subnet cooldowns in SQLite
(`p3_cgnat_slots`) via Phase3Store to avoid carrier-subnet collision patterns.
"""
from __future__ import annotations

import ipaddress
import logging
import time
from typing import Any, Optional, Tuple

from phase3.config_loader import CGNATTrackerConfig, Phase3Config
from phase3.db.migrations.runner import Phase3Store
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.a6_scheduler.cgnat_tracker")


def _extract_cgnat_config(cfg: Any) -> CGNATTrackerConfig:
    defaults = CGNATTrackerConfig()
    if cfg is None:
        return defaults
    if isinstance(cfg, CGNATTrackerConfig):
        return cfg
    if isinstance(cfg, Phase3Config):
        return cfg.cgnat_tracker
    if hasattr(cfg, "cgnat_tracker"):
        sub = getattr(cfg, "cgnat_tracker")
        if isinstance(sub, CGNATTrackerConfig):
            return sub
        if isinstance(sub, dict):
            return _dict_to_cgnat(sub, defaults)
    if isinstance(cfg, dict):
        sub = cfg.get("cgnat_tracker", cfg)
        if isinstance(sub, dict):
            return _dict_to_cgnat(sub, defaults)
    return defaults


def _dict_to_cgnat(data: dict, defaults: CGNATTrackerConfig) -> CGNATTrackerConfig:
    return CGNATTrackerConfig(
        slash24_cooldown_seconds=int(
            data.get("slash24_cooldown_seconds", defaults.slash24_cooldown_seconds)
        ),
        slash20_cooldown_seconds=int(
            data.get("slash20_cooldown_seconds", defaults.slash20_cooldown_seconds)
        ),
        slot_ttl_seconds=int(data.get("slot_ttl_seconds", defaults.slot_ttl_seconds)),
        allow_missing_ip_in_paper=bool(
            data.get("allow_missing_ip_in_paper", defaults.allow_missing_ip_in_paper)
        ),
    )


def _derive_subnets(ip_address: str) -> Tuple[str, str, str]:
    """Parse IP and return (normalized_ip, subnet_24_or_64, subnet_20_or_48)."""
    addr = ipaddress.ip_address(ip_address.strip())
    if isinstance(addr, ipaddress.IPv4Address):
        s24 = str(ipaddress.ip_network(f"{addr}/24", strict=False))
        s20 = str(ipaddress.ip_network(f"{addr}/20", strict=False))
        return str(addr), s24, s20
    s64 = str(ipaddress.ip_network(f"{addr}/64", strict=False))
    s48 = str(ipaddress.ip_network(f"{addr}/48", strict=False))
    return str(addr), s64, s48


class CGNATTracker:
    """Tracks /24 and /20 IPv4 carrier subnets in SQLite via Phase3Store."""

    def __init__(self, cfg: Any = None, store: Optional[Phase3Store] = None) -> None:
        self.cfg = _extract_cgnat_config(cfg)
        if store is None:
            db_path = (
                cfg.phase3.db_path
                if isinstance(cfg, Phase3Config)
                else "state/phase3/phase3.db"
            )
            self.store = Phase3Store(db_path)
        else:
            self.store = store

        self.slash24_cooldown = max(0.0, float(self.cfg.slash24_cooldown_seconds))
        self.slash20_cooldown = max(0.0, float(self.cfg.slash20_cooldown_seconds))
        self.slot_ttl = max(1.0, float(self.cfg.slot_ttl_seconds))
        self.allow_missing_ip_in_paper = bool(self.cfg.allow_missing_ip_in_paper)

    def _expire_stale_slots(self, conn: Any, ts: float) -> None:
        cutoff = ts - self.slot_ttl
        conn.execute(
            """
            UPDATE p3_cgnat_slots
            SET active = 0,
                released_at = COALESCE(released_at, acquired_at + ?)
            WHERE active = 1 AND acquired_at <= ?
            """,
            (self.slot_ttl, cutoff),
        )

    def _subnet_blocked(
        self, conn: Any, subnet_24: str, subnet_20: str, ts: float
    ) -> Tuple[bool, str]:
        row_active = conn.execute(
            """
            SELECT device_id, subnet_24, subnet_20
            FROM p3_cgnat_slots
            WHERE active = 1 AND (subnet_24 = ? OR subnet_20 = ?)
            LIMIT 1
            """,
            (subnet_24, subnet_20),
        ).fetchone()
        if row_active is not None:
            return True, f"active_collision:{row_active['device_id']}"

        if self.slash24_cooldown > 0.0:
            cutoff_24 = ts - self.slash24_cooldown
            row_24 = conn.execute(
                """
                SELECT id FROM p3_cgnat_slots
                WHERE subnet_24 = ? AND COALESCE(released_at, acquired_at) > ?
                LIMIT 1
                """,
                (subnet_24, cutoff_24),
            ).fetchone()
            if row_24 is not None:
                return True, "slash24_cooldown"

        if self.slash20_cooldown > 0.0:
            cutoff_20 = ts - self.slash20_cooldown
            row_20 = conn.execute(
                """
                SELECT id FROM p3_cgnat_slots
                WHERE subnet_20 = ? AND COALESCE(released_at, acquired_at) > ?
                LIMIT 1
                """,
                (subnet_20, cutoff_20),
            ).fetchone()
            if row_20 is not None:
                return True, "slash20_cooldown"

        return False, ""

    def is_subnet_on_cooldown(
        self, ip_address: Optional[str], now_ts: Optional[float] = None
    ) -> bool:
        """Return True if the IP's /24 or /20 subnet is active or within cooldown."""
        if not ip_address or not str(ip_address).strip():
            return False
        try:
            _, subnet_24, subnet_20 = _derive_subnets(str(ip_address))
            ts = time.time() if now_ts is None else float(now_ts)
            with self.store.connect(immediate=True) as conn:
                self._expire_stale_slots(conn, ts)
                blocked, _ = self._subnet_blocked(conn, subnet_24, subnet_20, ts)
                return blocked
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "cgnat_cooldown_check_failed",
                ip_address=str(ip_address),
                error=str(exc),
            )
            return False

    def acquire_slot(
        self,
        device_id: str,
        ip_address: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> bool:
        """Attempt to acquire an exclusive carrier-subnet slot for `device_id`."""
        if not device_id or not str(device_id).strip():
            log_event(logger, logging.WARNING, "cgnat_missing_device_id")
            return False

        dev = str(device_id).strip()
        ts = time.time() if now_ts is None else float(now_ts)

        try:
            if ip_address is None or not str(ip_address).strip():
                if not self.allow_missing_ip_in_paper:
                    log_event(
                        logger, logging.WARNING, "cgnat_missing_ip_blocked", device_id=dev
                    )
                    return False
                with self.store.connect(immediate=True) as conn:
                    self._expire_stale_slots(conn, ts)
                    conn.execute(
                        """
                        UPDATE p3_cgnat_slots
                        SET active = 0, released_at = ?
                        WHERE device_id = ? AND active = 1
                        """,
                        (ts, dev),
                    )
                    conn.execute(
                        """
                        INSERT INTO p3_cgnat_slots
                        (device_id, ip_address, subnet_24, subnet_20, active, acquired_at)
                        VALUES (?, '', '', '', 1, ?)
                        """,
                        (dev, ts),
                    )
                return True

            norm_ip, subnet_24, subnet_20 = _derive_subnets(str(ip_address))
            with self.store.connect(immediate=True) as conn:
                self._expire_stale_slots(conn, ts)
                blocked, reason = self._subnet_blocked(conn, subnet_24, subnet_20, ts)
                if blocked:
                    log_event(
                        logger,
                        logging.INFO,
                        "cgnat_slot_blocked",
                        device_id=dev,
                        ip_address=norm_ip,
                        subnet_24=subnet_24,
                        subnet_20=subnet_20,
                        reason=reason,
                    )
                    return False

                # Release any prior active slot owned by this device before acquiring new one
                conn.execute(
                    """
                    UPDATE p3_cgnat_slots
                    SET active = 0, released_at = ?
                    WHERE device_id = ? AND active = 1
                    """,
                    (ts, dev),
                )
                conn.execute(
                    """
                    INSERT INTO p3_cgnat_slots
                    (device_id, ip_address, subnet_24, subnet_20, active, acquired_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (dev, norm_ip, subnet_24, subnet_20, ts),
                )
                return True
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "cgnat_acquire_failed",
                device_id=dev,
                ip_address=str(ip_address),
                error=str(exc),
            )
            return False

    def release_slot(self, device_id: str, now_ts: Optional[float] = None) -> None:
        """Release any active CGNAT slot held by `device_id`."""
        if not device_id or not str(device_id).strip():
            return
        dev = str(device_id).strip()
        try:
            ts = time.time() if now_ts is None else float(now_ts)
            with self.store.connect(immediate=True) as conn:
                conn.execute(
                    """
                    UPDATE p3_cgnat_slots
                    SET active = 0, released_at = ?
                    WHERE device_id = ? AND active = 1
                    """,
                    (ts, dev),
                )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "cgnat_release_failed",
                device_id=dev,
                error=str(exc),
            )
