"""
tests/test_freellmapi_client.py — Tests for FreeLLMClient and AI synthesis routines.
"""

import pytest
from freellmapi_client import FreeLLMClient


def test_freellmapi_client_init():
    client = FreeLLMClient()
    assert client.api_url.startswith("http")
    assert client.api_key.startswith("freellmapi-")
    assert client.enabled is True


def test_freellmapi_availability_and_completion():
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


def test_loan_inquiry_purpose_generation():
    client = FreeLLMClient()
    purpose = client.generate_loan_inquiry_purpose("loanraaj.com", "Personal Loans")
    assert isinstance(purpose, str)
    assert len(purpose) > 10


def test_search_query_variation_generation():
    client = FreeLLMClient()
    query = client.generate_search_query_variation("instant personal loan", "loanraaj.com")
    assert isinstance(query, str)
    assert len(query) > 5


def test_fallback_when_disabled():
    client = FreeLLMClient()
    client.enabled = False

    # Completion should immediately return None without HTTP call
    res = client.generate_completion("Hello")
    assert res is None

    # Domain methods must gracefully fall back to heuristics
    purpose = client.generate_loan_inquiry_purpose("loanraaj.com", "Personal Loans")
    assert isinstance(purpose, str)
    assert len(purpose) > 10
