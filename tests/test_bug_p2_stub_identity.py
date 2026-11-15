"""
tests/test_bug_p2_stub_identity.py — Regression test for 301 redirect stub byte-for-byte identity.
Verifies:
1. render_301_stub output matches on-disk file byte-for-byte (LF-only, 405 B, SHA256 db82e810...).
2. Quarantine invariants: noindex, canonical to target, word count < 200, zero BANNED_LEAK_PHRASES.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from bs4 import BeautifulSoup

from content_quality_gate import BANNED_LEAK_PHRASES
from scripts.repair_leaked_articles import is_leak, render_301_stub

EXPECTED_STUB_SHA256 = "db82e810c6152910507bdca09ca40383da1b84b8a7c7f99fce3f39a29010a658"


def test_render_301_stub_matches_on_disk_bytes():
    p = Path("sites/loanraaj.com/intermodal-cargo-insurance-guide-marine-rail-highway-fr/index.html")
    assert p.exists(), f"Quarantined stub file not found at {p}"

    generated = render_301_stub("loanraaj.com", "commercial-auto-insurance").encode("utf-8")
    disk_bytes = p.read_bytes()

    assert generated == disk_bytes, "Generated stub bytes must match on-disk file byte-for-byte"
    assert b"\r\n" not in generated, "Generated stub contains Windows CRLF line endings"
    assert generated.count(b"\n") == 6, f"Expected 6 LF line endings, found {generated.count(b'\n')}"
    assert len(generated) == 405, f"Expected exactly 405 bytes, got {len(generated)}"
    assert hashlib.sha256(generated).hexdigest() == EXPECTED_STUB_SHA256


def test_render_301_stub_quarantine_invariants():
    html_text = render_301_stub("loanraaj.com", "commercial-auto-insurance")
    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Robots noindex, nofollow
    meta_robots = soup.find("meta", attrs={"name": "robots"})
    assert meta_robots is not None, "Missing meta robots tag"
    robots_content = meta_robots.get("content", "").lower()
    assert "noindex" in robots_content
    assert "nofollow" in robots_content

    # 2. Canonical points to target
    link_canonical = soup.find("link", attrs={"rel": "canonical"})
    assert link_canonical is not None, "Missing canonical link"
    assert link_canonical.get("href") == "https://loanraaj.com/commercial-auto-insurance"

    # 3. Refresh header
    meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
    assert meta_refresh is not None, "Missing meta refresh header"
    assert "/commercial-auto-insurance" in meta_refresh.get("content", "")

    # 4. Word count < 200
    text = soup.get_text()
    word_count = len(text.split())
    assert word_count < 200, f"Stub word count {word_count} exceeds maximum 200 words"

    # 5. Zero banned leak phrases
    detected_leaks = is_leak(text)
    assert not detected_leaks, f"Stub contains banned leak phrases: {detected_leaks}"
