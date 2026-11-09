"""
tests/test_gsc_submitter.py — Acceptance test for Step 3.4 (PUB-3): Google Indexing Submitter.
"""
import asyncio
from pathlib import Path
import tempfile
from gsc_submitter import GoogleIndexingSubmitter


def test_gsc_submitter_flow():
    submitter = GoogleIndexingSubmitter()

    async def _test():
        url = "https://loanraaj.com/personal-loan-guide.html"
        res = await submitter.submit_url(url)
        assert res["status"] in ("ok", "skipped")
        assert res["url"] == url

        # Repeated submission within window should be skipped
        res_dup = await submitter.submit_url(url)
        assert res_dup["status"] == "skipped"

        # Sitemap ping test
        s_res = await submitter.submit_sitemap("https://loanraaj.com/sitemap.xml")
        assert s_res is True

    asyncio.run(_test())
