"""
tests/test_freellmapi_client.py — Tests for FreeLLMClient and AI synthesis routines.
"""

import os
from pathlib import Path
from unittest.mock import patch
import pytest
from freellmapi_client import FreeLLMClient


@pytest.fixture
def ensure_dummy_token(monkeypatch):
    """Ensure a valid test token is present if none exists in env or .env."""
    if not (os.environ.get("FREELLMAPI_TOKEN") or os.environ.get("FREELLMAPI_KEY")):
        monkeypatch.setenv("FREELLMAPI_TOKEN", "ci-dummy-token-not-a-secret")


def test_freellmapi_client_init_requires_token(monkeypatch):
    """When token is missing from environment and .env, init must raise ValueError."""
    monkeypatch.delenv("FREELLMAPI_TOKEN", raising=False)
    monkeypatch.delenv("FREELLMAPI_KEY", raising=False)
    with patch.object(Path, "read_text", return_value=""):
        with pytest.raises(ValueError, match="FREELLMAPI_TOKEN environment variable is not set"):
            FreeLLMClient()


def test_freellmapi_client_init_with_token(monkeypatch):
    """Token must come from FREELLMAPI_TOKEN environment variable, not hardcoded secrets."""
    test_token = "ci-test-token-xyz"
    monkeypatch.setenv("FREELLMAPI_TOKEN", test_token)
    client = FreeLLMClient()
    assert client.api_url.startswith("http")
    assert client.api_key == test_token
    assert client.enabled is True


def test_freellmapi_availability_and_completion(ensure_dummy_token):
    client = FreeLLMClient()
    available = client.is_available()
    if not available:
        pytest.skip("FreeLLMAPI local cluster not running on localhost:3001 (CI / headless environment)")
    assert available is True

    # Test quick generation
    res = client.generate_completion(
        prompt="Reply with exactly the word SUCCESS",
        system_prompt="You follow instructions precisely.",
        max_tokens=10,
        temperature=0.1
    )
    assert res is not None
    assert len(res) > 0


def test_loan_inquiry_purpose_generation(ensure_dummy_token):
    client = FreeLLMClient()
    purpose = client.generate_loan_inquiry_purpose("loanraaj.com", "Personal Loans")
    assert isinstance(purpose, str)
    assert len(purpose) > 10


def test_search_query_variation_generation(ensure_dummy_token):
    client = FreeLLMClient()
    query = client.generate_search_query_variation("instant personal loan", "loanraaj.com")
    assert isinstance(query, str)
    assert len(query) > 5


def test_fallback_when_disabled(ensure_dummy_token):
    client = FreeLLMClient()
    client.enabled = False

    # Completion should immediately return None without HTTP call
    res = client.generate_completion("Hello")
    assert res is None

    # Domain methods must gracefully fall back to heuristics
    purpose = client.generate_loan_inquiry_purpose("loanraaj.com", "Personal Loans")
    assert isinstance(purpose, str)
    assert len(purpose) > 10

