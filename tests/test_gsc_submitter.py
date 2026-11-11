"""
tests/test_gsc_submitter.py — Acceptance test for Layer 5 Google Indexing Submitter.
"""
import asyncio
from pathlib import Path
import pytest

import gsc_auth
import gsc_submitter
from gsc_submitter import GoogleIndexingSubmitter


@pytest.fixture(autouse=True)
def _isolate_submitter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gsc_submitter, "STATE_FILE", tmp_path / "gsc_submissions.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_SA_PATH", tmp_path / "gsc_service_account.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_OAUTH_TOKEN_PATH", tmp_path / "gsc_oauth_token.json")
    monkeypatch.setattr(gsc_auth, "DEFAULT_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(gsc_auth, "DEFAULT_CONFIG_PATH", tmp_path / "config.yaml")
    for env_key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GSC_SERVICE_ACCOUNT_JSON",
        "GSC_ACCESS_TOKEN",
        "GSC_SERVICE_ACCOUNT_KEY",
        "GSC_CLIENT_ID",
        "GSC_CLIENT_SECRET",
        "GSC_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(env_key, raising=False)


def test_gsc_submitter_flow():
    submitter = GoogleIndexingSubmitter()

    async def _test():
        url = "https://loanraaj.com/personal-loan-guide.html"
        res = await submitter.submit_url(url)
        assert res["status"] in ("ok", "skipped")
        assert res["url"] == url
        assert res["authenticated"] is False

        # Repeated submission within window should be skipped
        res_dup = await submitter.submit_url(url)
        assert res_dup["status"] == "skipped"

        # Sitemap submission helper preserves unconfigured compatibility when mock_fallback=True
        s_res = await submitter.submit_sitemap("https://loanraaj.com/sitemap.xml")
        assert s_res is True

    asyncio.run(_test())
