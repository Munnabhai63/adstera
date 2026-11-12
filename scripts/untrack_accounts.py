"""
scripts/untrack_accounts.py - Untrack accounts.txt from Git index.

Ensures sensitive account credentials are removed from Git tracking while preserving
the physical file on disk for local farm use.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def untrack_accounts() -> int:
    cmd = ["git", "rm", "--cached", "accounts.txt"]
    try:
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print("[OK] accounts.txt successfully removed from Git index (untracked).")
            return 0
        elif "did not match any files" in res.stderr or "pathspec" in res.stderr:
            print("[INFO] accounts.txt is already untracked by Git.")
            return 0
        else:
            print(f"[WARN] git rm --cached accounts.txt: {res.stderr.strip()}", file=sys.stderr)
            return res.returncode
    except Exception as exc:
        print(f"[ERROR] Failed to execute git rm: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(untrack_accounts())
