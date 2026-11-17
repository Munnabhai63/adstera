"""
tests/test_bug9_gateway_script.py — Unit tests for scripts/check_llm_gateway.py:
1. mask_token hides the body while exposing the first 3 and last 4 characters.
2. Missing token exits with code 2 and outputs '<MISSING>' without raw token.
3. Gateway returning 0 models exits with code 3 (using mock/monkeypatch, zero live network calls).
"""

from pathlib import Path
import pytest
from scripts.check_llm_gateway import mask_token, main as check_gateway_main


def test_mask_token_preserves_prefix_suffix_and_hides_body():
    token = "abcdefgh12345678"
    masked = mask_token(token)
    assert token not in masked, "Full token must not be exposed"
    assert masked.startswith("abc"), f"Expected prefix 'abc', got {masked}"
    assert masked.endswith("5678"), f"Expected suffix '5678', got {masked}"
    assert "..." in masked, "Masked token must contain ellipsis"
    assert mask_token("") == "<MISSING>", "Empty token must yield '<MISSING>'"


def test_missing_token_exits_code_2_and_prints_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture):
    # Ensure neither env nor any file provides a token
    monkeypatch.delenv("FREELLMAPI_TOKEN", raising=False)
    monkeypatch.delenv("FREELLMAPI_KEY", raising=False)
    
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["check_llm_gateway.py", "--env-file", str(empty_env)])

    rc = check_gateway_main()
    captured = capsys.readouterr()

    assert rc == 2, f"Expected returncode 2 on missing token, got {rc}"
    assert "<MISSING>" in captured.err, f"Expected '<MISSING>' in stderr, got: {captured.err}"


def test_gateway_zero_models_exits_code_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture):
    test_token = "valid-test-token-1234"
    monkeypatch.setenv("FREELLMAPI_TOKEN", test_token)
    
    # Mock query_models_endpoint to return 200 with 0 models (zero network calls)
    def mock_query(url: str, token: str, timeout: float = 8.0):
        return 200, {"data": []}, None

    monkeypatch.setattr("scripts.check_llm_gateway.query_models_endpoint", mock_query)
    
    dummy_env = tmp_path / "test.env"
    dummy_env.write_text(f"FREELLMAPI_TOKEN={test_token}\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["check_llm_gateway.py", "--env-file", str(dummy_env)])

    rc = check_gateway_main()
    captured = capsys.readouterr()

    assert rc == 3, f"Expected returncode 3 when gateway returns 0 models, got {rc}"
    assert "0 models" in captured.err, f"Expected '0 models' in stderr, got: {captured.err}"
