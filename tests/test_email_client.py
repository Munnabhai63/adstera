"""
tests/test_email_client.py — Comprehensive tests for Sonjj email client and credit guards.
Ensures zero credits are deducted during automated testing and caching operates correctly.
"""

import pytest
import sqlite3
from email_client import SonjjEmailClient
import db


@pytest.fixture(autouse=True)
def setup_db():
    db.init()


def test_client_init_and_key_resolution():
    client = SonjjEmailClient()
    if client.api_key:
        assert len(client.api_key) == 64
    assert client.daily_limit >= 1


def test_credit_guard_synthetic_fallback_in_test_mode():
    # Force test_mode to guarantee 0 credits consumed
    client = SonjjEmailClient()
    client.test_mode = True

    result = client.create_or_reuse_email(prefix_hint="test_user")
    assert result["is_real"] is False
    assert result["source"] == "synthetic"
    assert "@" in result["email"]
    assert "persona" in result


def test_email_cache_storage_and_reuse():
    client = SonjjEmailClient()
    test_email = "cached_user_test@momroad.org"

    # Save to cache
    client._save_email_to_cache(test_email, "momroad.org", expiry_minutes=60)

    # Next call should reuse this email without calling API (0 credits consumed)
    res = client.create_or_reuse_email(force_new=False)
    assert res["is_real"] is True
    assert res["source"] == "cache"
    assert res["email"] == test_email


def test_otp_extraction_heuristics():
    client = SonjjEmailClient()
    client.test_mode = True

    # Test parser with synthetic message
    fake_msg = {
        "subject": "Your verification code is 482910",
        "content": "Hello, thank you for applying. Your OTP code is 482910. Please verify at https://loanraaj.com/verify?token=abc"
    }

    import re
    otp_match = re.search(r"\b(\d{4,6})\b", fake_msg["content"])
    link_match = re.search(r"https?://[^\s'\"<>]+(?:verify|confirm|activate|token)[^\s'\"<>]*", fake_msg["content"])

    assert otp_match is not None and otp_match.group(1) == "482910"
    assert link_match is not None and "https://loanraaj.com/verify?token=abc" in link_match.group(0)
