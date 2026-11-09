"""
tests/test_content_and_adv_bot.py — Unit tests for Phase 3 (Content Pipeline) and Phase 4 (Advanced Bot)
"""
import asyncio
import pytest
from trends_fetcher import TrendsFetcher, DOMAIN_NICHES
from content_writer import ContentWriter
from quality_gate import QualityGate
from cf_publisher import CloudflarePublisher, ALL_DOMAINS
from schedule_manager import ScheduleManager
import db


def test_trends_fetcher_brief_generation():
    async def _test():
        tf = TrendsFetcher()
        for domain in ["loanraaj.com", "rechargetak.com", "tazabhav.com"]:
            brief = await tf.get_content_brief(domain)
            assert brief["domain"] == domain
            assert brief["title"]
            assert brief["primary_keyword"]
            assert len(brief["long_tail_keywords"]) >= 1

    asyncio.run(_test())


def test_content_writer_schema_and_length():
    async def _test():
        cw = ContentWriter()
        brief = {
            "domain": "loanraaj.com",
            "title": "Low Interest Personal Loan 2026: Complete Guide",
            "primary_keyword": "personal loan",
            "long_tail_keywords": ["instant loan online", "best loan apps"],
            "niche": "Finance",
        }
        article = await cw.generate_article(brief)
        assert article["word_count"] >= 2000
        assert "schema.org" in article["content"]
        assert "FAQPage" in article["content"]
        assert article["content"].startswith("---")

    asyncio.run(_test())


def test_quality_gate_evaluation():
    async def _test():
        cw = ContentWriter()
        qg = QualityGate()
        brief = {
            "domain": "loanraaj.com",
            "title": "Emergency Instant Cash Loan 2026",
            "primary_keyword": "cash loan",
            "long_tail_keywords": ["instant cash loan", "quick loan app"],
            "niche": "Finance",
        }
        article = await cw.generate_article(brief)
        passed, report = qg.evaluate_article(article)
        assert passed
        assert report["word_count"] >= 2000
        assert report["ai_score_est"] <= 20.0
        assert report["burstiness_cv"] >= 0.45

    asyncio.run(_test())


def test_cloudflare_publisher_site_structure(tmp_path):
    pub = CloudflarePublisher(base_dir=tmp_path)
    for dom in ALL_DOMAINS:
        assert (tmp_path / dom / "content" / "posts").exists()
        assert (tmp_path / dom / "robots.txt").exists()


def test_schedule_manager_caps():
    sm = ScheduleManager()
    can_pub, reason = sm.can_publish_today("loanraaj.com")
    assert isinstance(can_pub, bool)
    assert isinstance(reason, str)
