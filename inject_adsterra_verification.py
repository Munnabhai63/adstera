"""
inject_adsterra_verification.py — Injects Adsterra verification meta tag & content
across all 10 publisher sites and templates.
Tag: <meta name="adsterra-verification" content="A8B6C3">
"""
import re
from pathlib import Path

VERIFICATION_META = '<meta name="adsterra-verification" content="A8B6C3">'
VERIFICATION_COMMENT = '<!-- Verification: A8B6C3 -->'

sites_dir = Path("sites")
modified_count = 0
total_html = 0

for html_file in sites_dir.rglob("*.html"):
    total_html += 1
    try:
        content = html_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Error reading {html_file}: {e}")
        continue

    changed = False

    # 1. Option 1: Inject meta tag in <head> if not present
    if 'name="adsterra-verification"' not in content:
        if "<head>" in content:
            content = content.replace("<head>", f"<head>\n    {VERIFICATION_META}", 1)
            changed = True
        elif "<HEAD>" in content:
            content = content.replace("<HEAD>", f"<HEAD>\n    {VERIFICATION_META}", 1)
            changed = True

    # 2. Option 2: Add direct verification text in footer/body if not present
    if "Verification: A8B6C3" not in content and "A8B6C3" not in content:
        if "</body>" in content:
            content = content.replace("</body>", f"    <span style=\"display:none;opacity:0;\">Verification: A8B6C3</span>\n</body>", 1)
            changed = True
        elif "</BODY>" in content:
            content = content.replace("</BODY>", f"    <span style=\"display:none;opacity:0;\">Verification: A8B6C3</span>\n</BODY>", 1)
            changed = True

    if changed:
        html_file.write_text(content, encoding="utf-8")
        modified_count += 1

print(f"Scanned {total_html} HTML files. Injected Adsterra verification into {modified_count} files.")
