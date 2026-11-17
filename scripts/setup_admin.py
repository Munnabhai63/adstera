"""scripts/setup_admin.py — Set up or rotate operator admin credentials securely."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def setup_admin(
    email: str | None = None,
    password: str | None = None,
    state_dir: Path | None = None,
) -> bool:
    env = _load_env_file(PROJECT_ROOT / ".env")
    final_email = (email or os.environ.get("ADMIN_EMAIL") or env.get("ADMIN_EMAIL", "")).strip()
    final_pw = (password or os.environ.get("ADMIN_PASSWORD") or env.get("ADMIN_PASSWORD", "")).strip()

    if not final_email or "@" not in final_email:
        print("ERROR: Invalid admin email. Email must contain '@'.", file=sys.stderr)
        return False

    if len(final_pw) < 12:
        print("ERROR: Password too short. Password must be at least 12 characters.", file=sys.stderr)
        return False

    from admin_ui import profile_auth

    # As CLI root admin tool, allow setting credentials even if a prior hash exists on disk
    raw = profile_auth._load_raw_profile(state_dir)
    auth = raw.get("auth", {})
    if auth.get("password_hash") and auth.get("password_salt"):
        auth["password_hash"] = ""
        auth["password_salt"] = ""
        profile_auth._save_raw_profile(raw, state_dir)

    ok, msg, _ = profile_auth.set_password(
        final_pw, confirm_password=final_pw, require_login=True, state_dir=state_dir
    )
    if not ok:
        print(f"ERROR: Failed to set password: {msg}", file=sys.stderr)
        return False

    ok_prof, msg_prof, _ = profile_auth.save_profile({"email": final_email}, state_dir=state_dir)
    if not ok_prof:
        print(f"ERROR: Failed to update profile email: {msg_prof}", file=sys.stderr)
        return False

    print(f"ADMIN READY: {final_email} / password not echoed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup admin credentials securely")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password (min 12 chars)")
    args = parser.parse_args()

    success = setup_admin(args.email, args.password)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
