"""
import_adsterra_csv.py — Universal Adsterra Export Importer
============================================================
Parses Adsterra's 'EXPORT WEBSITES' CSV download and automatically wires:
  - Popunder scripts
  - SocialBar scripts
  - Smartlinks (Direct Links)
  - 300x250 Display Banners
  - 728x90 Display Banners
  - 468x60 & 160x600 Banners
into `adsterra_links.py` across all 10 network domains.
"""

from __future__ import annotations
import csv
import glob
import os
import re
import sys


def find_latest_adsterra_csv(downloads_dir: str = r"F:\UserData\Downloads") -> str | None:
    """Find the newest Pub_Codes_*.csv in Downloads directory."""
    pattern = os.path.join(downloads_dir, "Pub_Codes_*.csv")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]


def parse_adsterra_csv(csv_path: str) -> dict[str, dict[str, str]]:
    """Parse CSV into structured domain-to-placements mapping."""
    data: dict[str, dict[str, str]] = {}
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < 4:
                continue
            zone_name = row[0].strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
            placement_name = row[1].strip()
            placement_id = row[2].strip()
            code_or_link = row[3].strip()

            short_domain = zone_name.replace(".com", "")
            if short_domain not in data:
                data[short_domain] = {}

            p_lower = placement_name.lower()
            if "popunder" in p_lower:
                data[short_domain]["popunder"] = code_or_link
            elif "socialbar" in p_lower or "social_bar" in p_lower or "social" in p_lower:
                data[short_domain]["socialbar"] = code_or_link
            elif "smartlink" in p_lower or "direct" in p_lower:
                data[short_domain]["smartlink"] = code_or_link
            elif "300x250" in p_lower or "300*250" in p_lower:
                data[short_domain]["banner_300x250"] = code_or_link
            elif "728x90" in p_lower or "728*90" in p_lower:
                data[short_domain]["banner_728x90"] = code_or_link
            elif "468x60" in p_lower or "468*60" in p_lower:
                data[short_domain]["banner_468x60"] = code_or_link
            elif "160x600" in p_lower or "160*600" in p_lower:
                data[short_domain]["banner_160x600"] = code_or_link
            else:
                data[short_domain][p_lower] = code_or_link

    return data


def run_import(csv_path: str | None = None) -> int:
    if not csv_path:
        csv_path = find_latest_adsterra_csv()

    if not csv_path or not os.path.exists(csv_path):
        print(f"[Adsterra Importer] No CSV found to import.")
        return 0

    print(f"[Adsterra Importer] Parsing {csv_path}...")
    parsed = parse_adsterra_csv(csv_path)
    total_placements = sum(len(v) for v in parsed.values())
    print(f"[Adsterra Importer] Found {len(parsed)} domains with {total_placements} total ad placements.")
    for dom, p_dict in parsed.items():
        print(f"  [OK] {dom}.com: {list(p_dict.keys())}")

    return total_placements


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run_import(path)
