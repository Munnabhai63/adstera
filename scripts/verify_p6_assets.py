"""
scripts/verify_p6_assets.py — Verify CSP, service worker, and self-hosted images/og:image across all 10 sites.
"""
from pathlib import Path
import re

SITES_DIR = Path("sites")
DOMAINS = [
    "loanraaj.com", "loantau.com", "loankiseva.com", "tazarokda.com", "tazaloan.com",
    "tazabhav.com", "karzseva.com", "rechargekar.com", "rechargepur.com", "rechargetak.com"
]

def check_sw():
    sw_file = SITES_DIR / "loanraaj.com" / "sw.js"
    assert sw_file.exists(), "loanraaj.com/sw.js missing"
    content = sw_file.read_text(encoding="utf-8")
    assert "5gvci.com" not in content, "Found 5gvci.com in loanraaj.com/sw.js!"
    print("PASS: loanraaj.com/sw.js clean, no 5gvci.com")

def check_csp():
    for d in DOMAINS:
        hf = SITES_DIR / d / "_headers"
        assert hf.exists(), f"{d}/_headers missing"
        content = hf.read_text(encoding="utf-8")
        assert "Content-Security-Policy:" in content, f"{d}/_headers missing Content-Security-Policy"
    print(f"PASS: All {len(DOMAINS)} sites have Content-Security-Policy in _headers")

def check_images_and_og():
    external_hotlinks = []
    og_hotlinks = []
    total_articles = 0
    forbidden_hosts = ["unsplash.com", "bazartak", "kamtak", "images.unsplash"]

    for d in DOMAINS:
        dom_dir = SITES_DIR / d
        html_files = list(dom_dir.glob("*.html")) + list(dom_dir.glob("*/*.html"))
        for f in html_files:
            if f.name == "404.html" or (f.parent == dom_dir and f.name == "index.html"):
                continue
            total_articles += 1
            txt = f.read_text(encoding="utf-8", errors="ignore")

            # Check <img> tags
            img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', txt, re.IGNORECASE)
            for s in img_srcs:
                if any(h in s for h in forbidden_hosts):
                    external_hotlinks.append((str(f), s))

            # Check og:image tags
            og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', txt, re.IGNORECASE)
            if og_match:
                og_val = og_match.group(1)
                if any(h in og_val for h in forbidden_hosts):
                    og_hotlinks.append((str(f), og_val))

    assert len(external_hotlinks) == 0, f"Found {len(external_hotlinks)} external image hotlinks: {external_hotlinks[:3]}"
    assert len(og_hotlinks) == 0, f"Found {len(og_hotlinks)} external og:image hotlinks: {og_hotlinks[:3]}"
    print(f"PASS: {total_articles} articles scanned. 0 external hotlinks, 0 external og:images.")

if __name__ == "__main__":
    check_sw()
    check_csp()
    check_images_and_og()
    print("ALL PHASE 6 CHECKS PASSED [OK]")
