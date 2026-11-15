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


def verify_claim_5_pytest_collection() -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"Claim 5 FAILED: pytest --collect-only returned code {proc.returncode}"

    import re
    m = re.search(r"(\d+)\s+tests collected", proc.stdout) or re.search(r"collected\s+(\d+)\s+items", proc.stdout)
    if not m:
        return False, f"Claim 5 FAILED: Could not parse test collection count from output"
    count = int(m.group(1))
    if count != 542:
        return False, f"Claim 5 FAILED: Expected 542 tests collected, got {count}"
    return True, f"Claim 5: pytest --collect-only == {count} tests (exit 0)"


def verify_claim_6_word_count_floor_expansion() -> tuple[bool, str]:
    from scripts.seo_onpage_audit import run_full_onpage_audit

    summary = run_full_onpage_audit()
    details = summary.get("details", [])
    if details:
        prose_counts = [r["prose_words"] for r in details]
        ge_3000 = sum(1 for c in prose_counts if c >= 3000)
    else:
        ge_3000 = summary.get("distribution", {}).get("ge_3000", 0)
    target = 38
    if ge_3000 < target:
        return False, f"Claim 6 FAILED: Expected >= {target} articles >= 3000 words, found {ge_3000}"
    return True, f"Claim 6: on-page audit >= 3000 word articles == {ge_3000} (>= {target} target verified)"


def verify_claim_7_duplicate_headings_count() -> tuple[bool, str]:
    from scripts.seo_onpage_audit import run_full_onpage_audit

    summary = run_full_onpage_audit()
    dup_fails = summary.get("failures", {}).get("duplicate_headings", 0)
    if dup_fails != 0:
        return False, f"Claim 7 FAILED: Expected 0 duplicate H2/FAQ blocks, found {dup_fails}"
    return True, f"Claim 7: corpus-wide duplicate-H2/FAQ count == {dup_fails} (0 verified)"


def verify_claim_8_ten_slugs_unique_and_strictly_increasing() -> tuple[bool, str]:
    from bs4 import BeautifulSoup
    import re
    from content_quality_gate import normalize_h2_key

    ten_slugs = [
        "karzseva.com/budgeting-framework-for-low-income-earners",
        "loankiseva.com/annapurna-scheme-for-food-catering-businesses-equipment",
        "loanraaj.com/21-machines-business",
        "loantau.com/commercial-fleet-insurance-bundling-discounts",
        "rechargekar.com/best-budget-prepaid-plans-for-students",
        "rechargepur.com/best-apps-for-utility-bill-cashback",
        "rechargetak.com/28-day-vs-84-day-recharge-math",
        "tazabhav.com/agricultural-commodity-trading-ncdex",
        "tazaloan.com/boost-cibil-score-from-650-to-750",
        "tazarokda.com/api-banking-for-bulk-payroll-transfers",
    ]

    for slug in ten_slugs:
        p = PROJECT_ROOT / "sites" / slug / "index.html"
        if not p.exists():
            return False, f"Claim 8 FAILED: {slug} not found"
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        pc = soup.find("div", class_="post-content") or soup.find("article") or soup
        h2s = [re.sub(r"\s+", " ", h.get_text()).strip() for h in pc.find_all("h2")]

        # 1. Exactly one FAQ H2
        faqs = [h for h in h2s if "frequently asked questions" in normalize_h2_key(h)]
        if len(faqs) != 1:
            return False, f"Claim 8 FAILED: {slug} has {len(faqs)} FAQ H2s, expected exactly 1"

        # 2. No duplicate H2 text
        norm_keys = [normalize_h2_key(h) for h in h2s]
        dups = [k for k in set(norm_keys) if norm_keys.count(k) > 1]
        if dups:
            return False, f"Claim 8 FAILED: {slug} has duplicate H2s: {dups}"

        # 3. Strictly increasing numbering
        numbers = []
        for h in h2s:
            m = re.match(r"^(\d+)[.)]\s*", h)
            if m:
                numbers.append(int(m.group(1)))
        if not numbers:
            return False, f"Claim 8 FAILED: {slug} has no numbered H2 headings"
        for i in range(len(numbers) - 1):
            if numbers[i] >= numbers[i + 1]:
                return False, f"Claim 8 FAILED: {slug} numbering not strictly increasing: {numbers}"

    return True, f"Claim 8: all 10 previously-broken slugs have exactly 1 FAQ H2 and strictly increasing numbering (verified)"


def verify_claim_9_domain_distribution_at_least_two() -> tuple[bool, str]:
    from scripts.seo_onpage_audit import run_full_onpage_audit
    from network_registry import NETWORK_REGISTRY

    summary = run_full_onpage_audit()
    details = summary.get("details", [])
    domain_counts: dict[str, int] = {}
    for r in details:
        if r.get("prose_words", 0) >= 3000:
            d = r.get("domain", "")
            domain_counts[d] = domain_counts.get(d, 0) + 1

    all_domains = [f"{k}.com" for k in NETWORK_REGISTRY.keys()]
    under_two = {d: domain_counts.get(d, 0) for d in all_domains if domain_counts.get(d, 0) < 2}
    if under_two:
        return False, f"Claim 9 FAILED: Domains with < 2 at-floor articles: {under_two} (counts: {domain_counts})"
    return True, f"Claim 9: all 10 domains have >= 2 at-floor articles (verified live: {domain_counts})"


def verify_claim_10_bug_suite_passes() -> tuple[bool, str]:
    import glob
    bug_files = sorted(glob.glob(str(PROJECT_ROOT / "tests" / "test_bug*.py")))
    if not bug_files:
        return False, "Claim 10 FAILED: No test_bug*.py files found"
    cmd = [sys.executable, "-m", "pytest", *bug_files, "-q"]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"Claim 10 FAILED: pytest tests/test_bug*.py returned code {proc.returncode}\n{proc.stderr}\n{proc.stdout}"
    if "28 passed" not in proc.stdout:
        return False, f"Claim 10 FAILED: Expected '28 passed', got:\n{proc.stdout}"
    return True, f"Claim 10: direct pytest bug suite == 28 passed (exit 0)"


def main() -> int:
    print("--- Running scripts/verify_round_claims.py ---")
    claims = [
        ("claim_1_stub_bytes", verify_claim_1_stub_bytes),
        ("claim_2_word_floor", verify_claim_2_word_floor),
        ("claim_3_article_count", verify_claim_3_article_count),
        ("claim_4_layer7_concurrency", verify_claim_4_layer7_concurrency_5x),
        ("claim_5_pytest_collection", verify_claim_5_pytest_collection),
        ("claim_6_word_floor_expansion", verify_claim_6_word_count_floor_expansion),
        ("claim_7_duplicate_headings_count", verify_claim_7_duplicate_headings_count),
        ("claim_8_ten_slugs_strictly_increasing", verify_claim_8_ten_slugs_unique_and_strictly_increasing),
        ("claim_9_domain_distribution_at_least_two", verify_claim_9_domain_distribution_at_least_two),
        ("claim_10_bug_suite_passes", verify_claim_10_bug_suite_passes),
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
