#!/usr/bin/env python3
"""
scripts/verify_round_claims.py — Report Honesty Guard.
Re-runs the four numeric invariants this round depends on and exits non-zero on any mismatch:
1. render_301_stub(...) bytes == on-disk stub bytes
2. ARTICLE_WORD_COUNT_FLOOR == 3000
3. article count from scripts.fix_article_images.get_all_articles == 278
4. layer7 parallel test passes 5 consecutive times (prints layer7: PASS=5 FAIL=0)

Usage: python scripts/verify_round_claims.py
Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def verify_claim_1_stub_bytes() -> tuple[bool, str]:
    from scripts.repair_leaked_articles import render_301_stub

    stub_path = PROJECT_ROOT / "sites" / "loanraaj.com" / "intermodal-cargo-insurance-guide-marine-rail-highway-fr" / "index.html"
    if not stub_path.exists():
        return False, f"Claim 1 FAILED: File not found at {stub_path}"

    gen_bytes = render_301_stub("loanraaj.com", "commercial-auto-insurance").encode("utf-8")
    file_bytes = stub_path.read_bytes()

    if gen_bytes != file_bytes:
        return False, (
            f"Claim 1 FAILED: Byte mismatch (gen len={len(gen_bytes)}, disk len={len(file_bytes)}, "
            f"gen_sha={hashlib.sha256(gen_bytes).hexdigest()[:12]}, disk_sha={hashlib.sha256(file_bytes).hexdigest()[:12]})"
        )
    sha256 = hashlib.sha256(gen_bytes).hexdigest()
    return True, f"Claim 1: stub bytes identical ({len(gen_bytes)} B, LF-only, SHA256={sha256[:16]}...)"


def verify_claim_2_word_floor() -> tuple[bool, str]:
    from content_quality_gate import ARTICLE_WORD_COUNT_FLOOR

    if ARTICLE_WORD_COUNT_FLOOR != 3000:
        return False, f"Claim 2 FAILED: ARTICLE_WORD_COUNT_FLOOR is {ARTICLE_WORD_COUNT_FLOOR}, expected 3000"
    return True, f"Claim 2: ARTICLE_WORD_COUNT_FLOOR == {ARTICLE_WORD_COUNT_FLOOR}"


def verify_claim_3_article_count() -> tuple[bool, str]:
    from scripts.fix_article_images import get_all_articles

    articles = get_all_articles()
    count = len(articles)
    if count != 278:
        return False, f"Claim 3 FAILED: article count is {count}, expected 278"
    return True, f"Claim 3: corpus article count == {count} (excluding 301 stub)"


def verify_claim_4_layer7_concurrency_5x() -> tuple[bool, str]:
    target_test = "tests/test_layer7_autopublish_speed.py::test_parallel_two_domain_batch_concurrency_and_isolation"
    cmd = [sys.executable, "-m", "pytest", target_test, "-q"]

    passes = 0
    fails = 0
    failure_tails: list[str] = []

    for i in range(5):
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if proc.returncode == 0:
            passes += 1
        else:
            fails += 1
            tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()[-5:]
            failure_tails.append("\n".join(tail))

    status_line = f"layer7: PASS={passes} FAIL={fails}"
    print(f"  [{status_line}]")

    if passes != 5 or fails != 0:
        err_msg = f"Claim 4 FAILED: {status_line}"
        if failure_tails:
            err_msg += f"\nLast failure tail:\n{failure_tails[-1]}"
        return False, err_msg
    return True, f"Claim 4: {status_line} (5/5 consecutive passes verified)"


def main() -> int:
    print("--- Running scripts/verify_round_claims.py ---")
    claims = [
        ("claim_1_stub_bytes", verify_claim_1_stub_bytes),
        ("claim_2_word_floor", verify_claim_2_word_floor),
        ("claim_3_article_count", verify_claim_3_article_count),
        ("claim_4_layer7_concurrency", verify_claim_4_layer7_concurrency_5x),
    ]

    for name, func in claims:
        ok, msg = func()
        print(msg)
        if not ok:
            print(f"\nCLAIM FAILED: {name}")
            return 1

    print("\nALL CLAIMS VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
