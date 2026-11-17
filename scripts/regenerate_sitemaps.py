"""
Regenerate sitemaps across all 10 publisher domains.
Removes all 221 purged/redirected URLs while preserving all kept articles,
categories, calculators, and legal trust pages.
"""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = PROJECT_ROOT / "sites"
REDIRECTS_FILE = PROJECT_ROOT / "data" / "redirects_round20.json"

def regenerate_sitemaps():
    with open(REDIRECTS_FILE, "r", encoding="utf-8") as f:
        redirects = json.load(f)

    # Set of doomed URLs per domain
    doomed_urls = set()
    for entry in redirects:
        d = entry["domain"]
        fs = entry["from_slug"]
        doomed_urls.add(f"https://{d}/{fs}")
        doomed_urls.add(f"http://{d}/{fs}")
        doomed_urls.add(f"https://{d}/{fs}/")
        doomed_urls.add(f"http://{d}/{fs}/")

    sitemap_counts = {}
    removed_total = 0

    for domain_dir in sorted(SITES_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue
        sitemap_path = domain_dir / "sitemap.xml"
        if not sitemap_path.exists():
            continue

        raw = sitemap_path.read_text(encoding="utf-8", errors="ignore")
        # Parse XML
        # Register namespaces to preserve format
        ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
        root = ET.fromstring(raw)

        # xmlns prefix
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls_to_remove = []

        for url_elem in root.findall("sm:url", ns):
            loc_elem = url_elem.find("sm:loc", ns)
            if loc_elem is not None and loc_elem.text:
                loc = loc_elem.text.strip().rstrip("/")
                if loc in doomed_urls or f"{loc}/" in doomed_urls:
                    urls_to_remove.append(url_elem)

        for elem in urls_to_remove:
            root.remove(elem)
            removed_total += 1

        remaining_count = len(root.findall("sm:url", ns))
        sitemap_counts[domain_dir.name] = remaining_count

        # Re-serialize cleanly with LF
        xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
        xml_str = xml_str.replace("\r\n", "\n")
        if not xml_str.endswith("\n"):
            xml_str += "\n"

        sitemap_path.write_bytes(xml_str.encode("utf-8"))

    print(f"Removed {removed_total} doomed URLs across 10 sitemaps.")
    print("Sitemap entries remaining per domain:")
    for d, c in sorted(sitemap_counts.items()):
        print(f"  {d}: {c} entries")

    assert removed_total == 221, f"Expected 221 removals from sitemaps, got {removed_total}"
    return sitemap_counts

if __name__ == "__main__":
    regenerate_sitemaps()
