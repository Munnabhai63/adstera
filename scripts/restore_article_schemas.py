#!/usr/bin/env python3
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
import re

SITES = Path("sites")
STATIC = {
    "about-us", "contact-us", "privacy-policy", "terms-and-conditions",
    "disclaimer", "calculator", "emi-calculator", "gold-calculator",
    "fd-calculator", "sip-calculator", "personal-loan-guide", "credit-card-apply"
}

def main():
    restored = 0
    for p in sorted(SITES.glob("*/*/index.html")):
        if p.parent.name in STATIC:
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'"@type"\s*:\s*"Article"', raw):
            continue
        rel = str(p.as_posix())
        try:
            old_raw = subprocess.check_output(["git", "show", f"687cc75:{rel}"], encoding="utf-8", errors="ignore")
        except Exception:
            continue
        soup_old = BeautifulSoup(old_raw, "html.parser")
        art_script = None
        for s in soup_old.find_all("script", type="application/ld+json"):
            if '"Article"' in (s.string or ""):
                art_script = str(s)
                break
        if art_script:
            soup_curr = BeautifulSoup(raw, "html.parser")
            head = soup_curr.find("head")
            if head:
                head.append(BeautifulSoup(art_script, "html.parser"))
                p.write_text(str(soup_curr), encoding="utf-8")
                restored += 1
                print(f"Restored Article schema for {p.parent.parent.name}/{p.parent.name}")

    print(f"\nTotal restored Article schemas: {restored}")

if __name__ == "__main__":
    main()
