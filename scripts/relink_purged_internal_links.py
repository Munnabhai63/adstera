"""
Relink internal links that point to purged/doomed slugs across HTML files.
Uses regex replacement on raw text to guarantee zero reformatting of surrounding HTML.
"""
from pathlib import Path
import json
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = PROJECT_ROOT / "sites"
REDIRECTS_FILE = PROJECT_ROOT / "data" / "redirects_round20.json"

def relink(dry_run: bool = False):
    with open(REDIRECTS_FILE, "r", encoding="utf-8") as f:
        redirects = json.load(f)

    dest_map = {}
    for entry in redirects:
        d = entry["domain"]
        fs = entry["from_slug"]
        ts = entry["to_slug"]
        dest_map[(d, fs)] = "/" + ts.lstrip("/")

    doomed_paths = {
        str(SITES_DIR / e["domain"] / e["from_slug"] / "index.html").replace("\\", "/").lower()
        for e in redirects
    }

    files_modified = 0
    links_updated = 0

    for html_file in sorted(SITES_DIR.rglob("*.html")):
        norm_p = str(html_file).replace("\\", "/").lower()
        if norm_p in doomed_paths:
            continue

        rel = html_file.relative_to(SITES_DIR)
        domain = rel.parts[0]

        raw_text = html_file.read_text(encoding="utf-8", errors="ignore")
        updated_text = raw_text
        file_changes = 0

        # Replace hrefs for this domain's doomed slugs
        for entry in redirects:
            if entry["domain"] != domain:
                continue
            fs = entry["from_slug"]
            target = dest_map[(domain, fs)]

            # Patterns:
            # href="/fs" or href="/fs/"
            # href="https://domain/fs" or href="https://domain/fs/"
            patterns = [
                (re.compile(r'(href=["\'])/' + re.escape(fs) + r'/?(["\'])'), r'\1' + target + r'\2'),
                (re.compile(r'(href=["\']https?://' + re.escape(domain) + r')/' + re.escape(fs) + r'/?(["\'])'), r'\1' + target + r'\2')
            ]

            for pat, repl in patterns:
                matches = len(pat.findall(updated_text))
                if matches > 0:
                    updated_text = pat.sub(repl, updated_text)
                    file_changes += matches

        if file_changes > 0:
            files_modified += 1
            links_updated += file_changes
            if not dry_run:
                # Save with exact LF
                new_bytes = updated_text.encode("utf-8").replace(b"\r\n", b"\n")
                html_file.write_bytes(new_bytes)

    print(f"[{'DRY-RUN' if dry_run else 'APPLIED'}] Files modified: {files_modified}, Links updated: {links_updated}")
    return files_modified, links_updated

if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    relink(dry_run=dry)
