#!/usr/bin/env python3
"""
scripts/init_state.py — State Initialisation Routine.
Creates state/ directory, initialises sqlite database tables via autopublish_daemon.init_db(),
and ensures login_attempts.json exists with {}. Idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import autopublish_daemon


def init_state() -> list[str]:
    state_dir = PROJECT_ROOT / "state"
    created_paths = []
    if not state_dir.exists():
        state_dir.mkdir(parents=True, exist_ok=True)
        created_paths.append(str(state_dir))

    # Initialize sqlite database schema (published_posts, topic_queue)
    autopublish_daemon.init_db()

    db_path = state_dir / "autopublish.db"
    created_paths.append(str(db_path))

    # Initialize login_attempts.json as {} if absent
    attempts_file = state_dir / "login_attempts.json"
    if not attempts_file.exists():
        attempts_file.write_text("{}", encoding="utf-8")
        created_paths.append(str(attempts_file))

    # Query tables in database to verify
    tables = []
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]

    print(f"State paths: {created_paths}")
    print(f"Tables in autopublish.db: {tables}")
    return tables


if __name__ == "__main__":
    tables = init_state()
    print("Init state completed successfully.")
    sys.exit(0)
