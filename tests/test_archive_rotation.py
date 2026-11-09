"""
tests/test_archive_rotation.py — Acceptance test for INFRA-3: Sessions.db monthly archive rotation.
"""
from pathlib import Path
import tempfile
import sqlite3
import datetime
import db


def test_archive_old_sessions():
    db.init()
    # Insert an old session older than 35 days
    old_ts = (datetime.datetime.now() - datetime.timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    with db._conn() as con:
        con.execute(
            """
            INSERT INTO sessions (proxy_id, ua, referrer, dwell, pages, ad_clicks, impressions, status, ts, domain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1.2.3.4:8080", "Mozilla/5.0 Test", "https://google.com", 45.0, 1, 0, 1, "ok", old_ts, "loanraaj.com")
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        res = db.archive_old_sessions(retention_days=30, archive_dir=tmpdir)
        assert res["archived_count"] >= 1
        assert Path(res["archive_path"]).exists()

        # Check archive DB contains the archived row
        arch_con = sqlite3.connect(res["archive_path"])
        cur = arch_con.cursor()
        rows = cur.execute("SELECT * FROM sessions WHERE proxy_id = '1.2.3.4:8080'").fetchall()
        assert len(rows) >= 1
        arch_con.close()

        # Check active DB no longer has the old row
        with db._conn() as con:
            cur = con.cursor()
            rem = cur.execute("SELECT * FROM sessions WHERE ts < ?", (res["cutoff_ts"],)).fetchall()
            assert len(rem) == 0
