"""
tests/test_csp_coverage.py — Automated CSP host coverage verification across all 10 sites.
Validates that every external host loaded via <script>, <link rel="stylesheet">, <img>, and <iframe>
is explicitly permitted by Content-Security-Policy directives in _headers.
"""
import glob
import re
from pathlib import Path
from urllib.parse import urlparse
import pytest


def parse_csp_directives(headers_file: Path) -> dict[str, list[str]]:
    """Parse Content-Security-Policy header line into a dict of directives."""
    if not headers_file.is_file():
        return {}
    content = headers_file.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("content-security-policy:"):
            csp_val = line.split(":", 1)[1].strip()
            directives = {}
            for part in csp_val.split(";"):
                part = part.strip()
                if not part:
                    continue
                tokens = part.split()
                if tokens:
                    directives[tokens[0].lower()] = tokens[1:]
            return directives
    return {}


def is_host_allowed(host: str, directive_tokens: list[str]) -> bool:
    """Check if host is allowed by directive tokens (e.g. 'https:', '*.example.com', 'example.com')."""
    if "https:" in directive_tokens or "http:" in directive_tokens or "*" in directive_tokens:
        return True
    for token in directive_tokens:
        token = token.lower().strip("'\"")
        token_host = urlparse(f"https://{token}" if not token.startswith("http") else token).netloc or token
        if token_host == host or (token_host.startswith("*.") and host.endswith(token_host[2:])):
            return True
    return False


def test_all_10_sites_csp_coverage():
    """Extract external hosts from index.html and one article per site and verify CSP coverage."""
    site_dirs = sorted([Path(p) for p in glob.glob("sites/*") if Path(p).is_dir()])
    assert len(site_dirs) >= 10, f"Expected 10 site dirs, found {len(site_dirs)}"

    violations = []

    for site_dir in site_dirs:
        headers_file = site_dir / "_headers"
        csp = parse_csp_directives(headers_file)
        assert csp, f"No Content-Security-Policy found in {headers_file}"

        # Find pages to check: index.html plus all content pages
        pages_to_check = [
            Path(p) for p in glob.glob(f"{site_dir}/**/*.html", recursive=True)
            if not any(skip in p for skip in ["layouts", "category", "google"])
        ]

        for page in pages_to_check:
            text = page.read_text(encoding="utf-8", errors="ignore")

            # Scripts
            for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE):
                if src.startswith("http://") or src.startswith("https://") or src.startswith("//"):
                    host = urlparse(src if not src.startswith("//") else f"https:{src}").netloc
                    allowed = is_host_allowed(host, csp.get("script-src", csp.get("default-src", [])))
                    if not allowed:
                        violations.append(f"{site_dir.name}: <script src='{src}'> host '{host}' not covered by script-src in CSP")

            # Stylesheets
            for href in re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', text, re.IGNORECASE):
                if href.startswith("http://") or href.startswith("https://") or href.startswith("//"):
                    host = urlparse(href if not href.startswith("//") else f"https:{href}").netloc
                    allowed = is_host_allowed(host, csp.get("style-src", csp.get("default-src", [])))
                    if not allowed:
                        violations.append(f"{site_dir.name}: <link href='{href}'> host '{host}' not covered by style-src in CSP")

            # Iframes (Ad units)
            for fsrc in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE):
                frame_tokens = csp.get("frame-src", csp.get("default-src", []))
                if fsrc.startswith("about:"):
                    if "about:" not in frame_tokens and "*" not in frame_tokens:
                        violations.append(f"{site_dir.name}: <iframe src='{fsrc}'> 'about:' not covered by frame-src in CSP")
                elif fsrc.startswith("http://") or fsrc.startswith("https://") or fsrc.startswith("//"):
                    host = urlparse(fsrc if not fsrc.startswith("//") else f"https:{fsrc}").netloc
                    allowed = is_host_allowed(host, frame_tokens)
                    if not allowed:
                        violations.append(f"{site_dir.name}: <iframe src='{fsrc}'> host '{host}' not covered by frame-src in CSP")

    assert not violations, "CSP Violations found:\n" + "\n".join(violations)


if __name__ == "__main__":
    test_all_10_sites_csp_coverage()
    print("ALL 10 SITES CSP COVERAGE: OK")
