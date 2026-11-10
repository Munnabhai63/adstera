"""
tests/test_competitor_intel.py — Acceptance & Invariant Tests for Step 7.4:
Competitor Intelligence Scraper and Monetization Layout Auditing.
"""
import pytest
import sqlite3
from pathlib import Path
from competitor_intel import CompetitorIntelScraper
import db

TEST_DB = Path("test_competitor_intel.db")
FIXTURE_PATH = Path("tests/fixtures/competitor_page.html")


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    if TEST_DB.exists():
        TEST_DB.unlink()
    monkeypatch.setattr(db, "_DB_PATH", TEST_DB)
    db.init()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_detect_ad_networks_from_fixture():
    """Verify scraper detects both Google AdSense and Adsterra ad network tags."""
    scraper = CompetitorIntelScraper()
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    networks = scraper.detect_ad_networks(html)

    assert "google_adsense" in networks
    assert "adsterra" in networks


def test_analyze_ad_units_and_placements():
    """Verify ad units count and placement layout identification."""
    scraper = CompetitorIntelScraper()
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    ads = scraper.analyze_ad_units(html)

    assert ads["total_ad_units"] >= 3
    assert ads["adsense_tags"] >= 2
    assert ads["ad_iframes"] >= 1
    placements = ads["placements_detected"]
    assert "above_the_fold_header" in placements
    assert "in_content" in placements
    assert "sticky_footer" in placements


def test_content_and_high_cpc_keyword_extraction():
    """Verify metadata extraction and identification of high commercial intent keywords."""
    scraper = CompetitorIntelScraper()
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    content = scraper.extract_keywords_and_metadata(html)

    assert "Fast Personal Loans" in content["title"]
    assert "Compare the best instant personal loan" in content["description"]
    assert len(content["headings_h1"]) == 1
    assert len(content["headings_h2"]) >= 2
    assert content["word_count"] > 80

    kws = content["commercial_keywords"]
    assert "personal loan" in kws
    assert "cash advance" in kws
    assert "credit repair" in kws
    assert "debt consolidation" in kws


def test_end_to_end_competitor_analysis_and_db_logging():
    """Verify end-to-end analyze method writes report and persists to SQLite."""
    scraper = CompetitorIntelScraper()
    report = scraper.analyze(str(FIXTURE_PATH))

    assert report["domain"] == "competitor_page.html"
    assert report["ad_unit_count"] >= 3
    assert report["ad_density_per_1k_words"] > 0.0
    assert "OPTIMAL" in report["monetization_strategy"] or "AGGRESSIVE" in report["monetization_strategy"]

    # Verify database persistence
    saved_records = db.get_competitor_intel(limit=5)
    assert len(saved_records) >= 1
    rec = saved_records[0]
    assert rec["domain"] == "competitor_page.html"
    assert "google_adsense" in rec["detected_networks"]
    assert rec["ad_unit_count"] >= 3
    assert len(rec["top_keywords"]) >= 1


def test_cli_execution_with_fixture():
    """Verify CLI tool executes cleanly against fixture with returncode 0."""
    import subprocess
    import sys
    cmd = [sys.executable, "competitor_intel.py", "--fixture", str(FIXTURE_PATH)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0
    assert "COMPETITOR INTELLIGENCE AUDIT REPORT" in res.stdout
    assert "Detected Networks: google_adsense, adsterra" in res.stdout
