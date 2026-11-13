from __future__ import annotations

import re
from pathlib import Path


def test_no_flat_html_files_except_index():
    base = Path("sites")
    flat_non_index = [
        f for f in base.glob("*/*.html")
        if f.name != "index.html" and f.is_file()
    ]
    assert len(flat_non_index) == 0, f"Found flat article html files: {flat_non_index}"


def test_no_href_html_extension_links():
    base = Path("sites")
    pattern = re.compile(r'href=["\']/[a-z0-9-]+\.html["\']', re.IGNORECASE)
    violating_files = []
    for p in base.glob("**/*.html"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            violating_files.append(str(p))
    assert len(violating_files) == 0, f"Files with href=...html links: {violating_files}"


def test_all_redirects_have_slug_html_rule():
    base = Path("sites")
    for site_dir in base.iterdir():
        if site_dir.is_dir() and (site_dir / "index.html").exists():
            redirects_file = site_dir / "_redirects"
            assert redirects_file.exists(), f"Missing _redirects in {site_dir}"
            content = redirects_file.read_text(encoding="utf-8")
            assert "/:slug.html /:slug 301" in content, f"Missing 301 rule in {redirects_file}"
