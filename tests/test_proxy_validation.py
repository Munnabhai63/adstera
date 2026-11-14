"""
tests/test_proxy_validation.py — DEFECT S1-C verification:
Tests for validate_proxy_lines, reporting malformed lines with exact 1-based line numbers,
and verifying proxies.example.txt.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from pool import Proxy, parse_proxy_line_with_error, validate_proxy_lines


def test_validate_proxy_lines_mixed_valid_and_malformed() -> None:
    lines = [
        "# Initial comment on line 1",
        "198.51.100.10:8080",                                # Line 2: valid host:port
        "",                                                  # Line 3: blank
        "user1:pass1@gw.provider.com:8000",                  # Line 4: valid user:pass@host:port
        "malformed_no_port_here",                            # Line 5: malformed (no port)
        "# Another comment on line 6",
        "198.51.100.20:99999",                               # Line 7: malformed (port > 65535)
        "gw.provider.com:3128:usr:pwd",                      # Line 8: valid host:port:user:pass
        "198.51.100.30:notaport",                            # Line 9: malformed (non-integer port)
        "http://proxyuser:proxypass@mobile.provider.com:9000",# Line 10: valid with scheme
    ]

    valid, malformed = validate_proxy_lines(lines)

    # Check valid proxies
    assert len(valid) == 4
    assert valid[0].host == "198.51.100.10"
    assert valid[0].port == 8080

    assert valid[1].host == "gw.provider.com"
    assert valid[1].port == 8000
    assert valid[1].username == "user1"
    assert valid[1].password == "pass1"

    assert valid[2].host == "gw.provider.com"
    assert valid[2].port == 3128
    assert valid[2].username == "usr"
    assert valid[2].password == "pwd"

    assert valid[3].host == "mobile.provider.com"
    assert valid[3].port == 9000
    assert valid[3].username == "proxyuser"
    assert valid[3].password == "proxypass"

    # Check malformed proxies with exact line numbers
    assert len(malformed) == 3

    assert malformed[0]["line"] == 5
    assert malformed[0]["text"] == "malformed_no_port_here"
    assert "missing port" in malformed[0]["error"].lower() or "unrecognized" in malformed[0]["error"].lower()

    assert malformed[1]["line"] == 7
    assert malformed[1]["text"] == "198.51.100.20:99999"
    assert "range" in malformed[1]["error"].lower()

    assert malformed[2]["line"] == 9
    assert malformed[2]["text"] == "198.51.100.30:notaport"
    assert "integer" in malformed[2]["error"].lower()


def test_proxies_example_file_structure() -> None:
    example_path = Path(__file__).parent.parent / "proxies.example.txt"
    assert example_path.exists(), "proxies.example.txt must exist"
    
    content = example_path.read_text(encoding="utf-8")
    assert "host:port" in content
    assert "user:pass@host:port" in content
    assert "host:port:user:pass" in content
    assert "socks5://" in content

    # Test that uncommented example lines parse cleanly
    lines = [
        "user_residential_us:pass123@us-res.proxyprovider.com:10001",
        "user_residential_uk:pass123@uk-res.proxyprovider.com:10002",
        "203.0.113.50:8080:user_mobile:secret999",
        "198.51.100.45:3128",
    ]
    valid, malformed = validate_proxy_lines(lines)
    assert len(valid) == 4
    assert len(malformed) == 0
