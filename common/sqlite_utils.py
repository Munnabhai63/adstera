"""Shared SQLite WAL, busy_timeout, and BEGIN IMMEDIATE write helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

DEFAULT_BUSY_TIMEOUT_MS = 10000


def configure_sqlite_write_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    foreign_keys: bool = True,
    temp_store_memory: bool = False,
) -> sqlite3.Connection:
    """Configure a SQLite write connection for concurrent multi-device WAL access."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)};")
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys=ON;")
    if temp_store_memory:
        conn.execute("PRAGMA temp_store=MEMORY;")
    return conn


@contextmanager
def sqlite_write_context(
    db_path: Union[str, Path],
    *,
    timeout_s: float = 15.0,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    immediate: bool = False,
    check_same_thread: bool = False,
    foreign_keys: bool = True,
    temp_store_memory: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection configured with WAL + busy_timeout, optionally in BEGIN IMMEDIATE."""
    if immediate:
        conn = sqlite3.connect(
            str(db_path),
            timeout=timeout_s,
            isolation_level=None,
            check_same_thread=check_same_thread,
        )
    else:
        conn = sqlite3.connect(
            str(db_path),
            timeout=timeout_s,
            check_same_thread=check_same_thread,
        )
    try:
        configure_sqlite_write_connection(
            conn,
            busy_timeout_ms=busy_timeout_ms,
            foreign_keys=foreign_keys,
            temp_store_memory=temp_store_memory,
        )
        if immediate:
            conn.execute("BEGIN IMMEDIATE;")
        yield conn
        if immediate:
            if conn.in_transaction:
                conn.execute("COMMIT;")
        else:
            conn.commit()
    except Exception:
        try:
            if immediate:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
            else:
                conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()
