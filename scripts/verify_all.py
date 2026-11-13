"""
scripts/verify_all.py — Verify all 10 acceptance criteria from Part 6.
"""
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(str(REPO_ROOT))


def run(cmd: list[str]) -> tuple[int, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout


def main():
    py = sys.executable
    print("=" * 70)
    print("RUNNING FINAL 10-POINT ACCEPTANCE VERIFICATION")
    print("=" * 70)

    results = []

    # Check 1: Core imports
    code1 = "import main, worker, db, pool, fingerprint, human, autopublish_daemon, autopublish_engine, seo_pipeline, topic_intelligence; print('OK')"
    rc, out = run([py, "-c", code1])
    c1 = (rc == 0 and "OK" in out)
    results.append(("1. Core Modules Import", c1, "Exit code 0" if c1 else f"Failed: {out.strip()}"))

    # Check 2: Audit checks (26 checks)
    rc, out = run([py, "tests/audit.py", "--allow-no-transport"])
    c2 = (rc == 0 and "All audit checks PASSED [OK]" in out)
    results.append(("2. Pre-flight Audit (26 checks)", c2, "All 26 checks passed" if c2 else f"Failed: {out.strip()}"))

    # Check 3: Autopublish daemon dry-run
    rc, out = run([py, "autopublish_daemon.py", "--dry-run", "--site", "loanraaj"])
    wc_match = re.search(r"Word count:\s*(\d+)", out) or re.search(r"words?=(\d+)", out)
    score_match = re.search(r"Quality score:\s*([\d.]+)", out) or re.search(r"score=([\d.]+)", out)
    wc = int(wc_match.group(1)) if wc_match else 0
    score = float(score_match.group(1)) if score_match else 0.0
    c3 = (rc == 0 and wc >= 1200 and score >= 90.0)
    results.append(("3. Autopublish Dry-run (loanraaj)", c3, f"Exit 0, wc={wc}, score={score}" if c3 else f"Failed: {out.strip()}"))

    # Check 4: Images self-hosted >= 5, 0 zero-image, 0 hotlinks
    zero_img_count = 0
    sub_5_count = 0
    hotlink_count = 0
    tot_articles = 0
    for site_dir in sorted(glob.glob("sites/*")):
        if not os.path.isdir(site_dir):
            continue
        for f in glob.glob(f"{site_dir}/**/*.html", recursive=True):
            if "layouts" in f or "category" in f or "google31976c4df01121b2" in f:
                continue
            if f.endswith("index.html") and Path(f).parent == Path(site_dir):
                continue
            tot_articles += 1
            content = open(f, encoding="utf-8", errors="ignore").read()
            imgs = re.findall(r'<img[^>]+src="([^"]+)"', content)
            imgs = [i for i in imgs if "logo" not in i.lower()]
            if not imgs:
                zero_img_count += 1
            if len(imgs) < 5:
                sub_5_count += 1
            for i in imgs:
                if any(x in i.lower() for x in ["unsplash.com", "bazartak", "kamtak"]):
                    hotlink_count += 1

    c4 = (zero_img_count == 0 and hotlink_count == 0 and sub_5_count == 0)
    results.append(("4. Article Images Self-Hosted", c4, f"Articles={tot_articles}, 0-img={zero_img_count}, <5-img={sub_5_count}, hotlinks={hotlink_count}"))

    # Check 5: 0 broken meta descriptions
    broken_meta = 0
    for site_dir in sorted(glob.glob("sites/*")):
        if not os.path.isdir(site_dir):
            continue
        for f in glob.glob(f"{site_dir}/**/*.html", recursive=True):
            if "layouts" in f or "category" in f or "google31976c4df01121b2" in f:
                continue
            if f.endswith("index.html") and Path(f).parent == Path(site_dir):
                continue
            content = open(f, encoding="utf-8", errors="ignore").read()
            m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', content)
            if m:
                d = m.group(1).strip()
                if "..." in d or "{" in d or "page-link" in d or len(d) < 30 or len(d) > 165:
                    broken_meta += 1
    c5 = (broken_meta == 0)
    results.append(("5. Clean Meta Descriptions", c5, f"0 broken descriptions (found {broken_meta})" if c5 else f"{broken_meta} broken descriptions"))

    # Check 6: Clean URLs (<slug>/index.html) and 301 redirects
    flat_slug_html = 0
    missing_redirects = 0
    for site_dir in sorted(glob.glob("sites/*")):
        if not os.path.isdir(site_dir):
            continue
        domain = os.path.basename(site_dir)
        # Check flat html files
        for f in glob.glob(f"{site_dir}/*.html"):
            if not f.endswith("index.html") and not f.endswith("google31976c4df01121b2.html"):
                flat_slug_html += 1
        # Check _redirects
        red_path = os.path.join(site_dir, "_redirects")
        if not os.path.exists(red_path):
            missing_redirects += 1
        else:
            red_content = open(red_path, encoding="utf-8", errors="ignore").read()
            if "/:slug.html /:slug 301" not in red_content:
                missing_redirects += 1
    c6 = (flat_slug_html == 0 and missing_redirects == 0)
    results.append(("6. Clean URLs & 301 Redirects", c6, f"0 flat slug files, all 10 _redirects active" if c6 else f"flat={flat_slug_html}, bad_redirects={missing_redirects}"))

    # Check 7: No leaked token in git repo
    rc, out = run(["git", "grep", "freellmapi-ceb0"])
    c7 = (rc != 0 or not out.strip())
    results.append(("7. Secret Token Protection", c7, "0 occurrences in repo" if c7 else "LEAKED TOKEN FOUND"))

    # Check 8: CRM lock security on UI endpoints
    code8 = """
from admin_ui.profile_auth import is_crm_locked, set_password
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    sdir = Path(tmpdir)
    set_password('Admin@12345678', confirm_password='Admin@12345678', state_dir=sdir)
    locked = is_crm_locked(None, state_dir=sdir)
    print('LOCKED:', locked)
"""
    rc, out = run([py, "-c", code8])
    c8 = (rc == 0 and "LOCKED: True" in out)
    results.append(("8. CRM Lock Security Default", c8, "Locked by default when credentials configured (True)" if c8 else f"Failed: {out.strip()}"))

    # Check 9: Mobile fingerprint hardware coherence
    import fingerprint
    from pool import Proxy
    mobile_ok = True
    for i in range(10, 40):
        proxy = Proxy(host=f"10.0.0.{i}", port=8080)
        fp = fingerprint.build(proxy, force_mobile=True)
        if fp.device_memory < 4 or fp.hardware_concurrency not in (4, 8):
            mobile_ok = False
            break
    c9 = mobile_ok
    results.append(("9. Mobile Hardware Coherence", c9, "cores in (4,8) and mem>=4GB" if c9 else "Violated mobile limits"))

    # Check 10: Pytest test suite >= baseline 411
    rc, out = run([py, "-m", "pytest", "-q"])
    passed_m = re.search(r"(\d+) passed", out)
    passed_cnt = int(passed_m.group(1)) if passed_m else 0
    c10 = (rc == 0 and passed_cnt >= 411)
    results.append(("10. Pytest Suite Regressions", c10, f"{passed_cnt} passed (>= baseline 411)" if c10 else f"Failed: {passed_cnt} passed, exit {rc}"))

    print("\n" + "-" * 70)
    all_passed = True
    for name, status, detail in results:
        status_str = "[PASS]" if status else "[FAIL]"
        print(f"{status_str:7} | {name:<32} | {detail}")
        if not status:
            all_passed = False
    print("-" * 70)

    if all_passed:
        print("\nALL 10 ACCEPTANCE CHECKS PASSED PERFECTLY [OK]")
        return 0
    else:
        print("\nSOME CHECKS FAILED [ERR]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
