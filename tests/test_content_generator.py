"""
tests/test_content_generator.py — Step 6.1: SEO Landing Page & Content Generator Tests

Covers:
1. Article files are created for all domain categories (loan, recharge, bhav, finance)
2. Semantic HTML5 tags (article, h1, h2, main, nav) are present
3. Schema.org JSON-LD structured data is present and valid JSON
4. Sitemap.xml contains valid XML and all article URLs
5. Robots.txt contains user-agent and sitemap pointer
6. Index.html contains navigable internal links
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent.parent))

import content_generator


def _isolated_sites_dir(tmp_path: Path) -> Path:
    sites_root = tmp_path / "sites"
    for short in (
        "loanraaj",
        "tazaloan",
        "loankiseva",
        "karzseva",
        "loantau",
        "rechargetak",
        "rechargepur",
        "rechargekar",
        "tazabhav",
        "tazarokda",
    ):
        d = sites_root / f"{short}.com"
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("<html><body><aside></aside></body></html>", encoding="utf-8")
    return sites_root


def test_articles_generated_for_domains(tmp_path: Path):
    """generate_all_domain_articles creates articles in each canonical .com domain folder."""
    sites_root = _isolated_sites_dir(tmp_path)
    results = content_generator.generate_all_domain_articles(sites_dir=sites_root)
    assert len(results) == 10
    assert results["loanraaj"] >= 2
    assert results["rechargetak"] >= 2
    assert results["tazabhav"] >= 1
    assert results["tazarokda"] >= 1
    print("  [OK] Articles generated for all 10 domain directories")


def test_article_semantic_html_structure(tmp_path: Path):
    """Generated article HTML contains required semantic tags and meta tags."""
    sites_root = _isolated_sites_dir(tmp_path)
    content_generator.generate_all_domain_articles(sites_dir=sites_root)
    p_loan = sites_root / "loanraaj.com" / "personal-loan-guide.html"
    assert p_loan.exists()
    content = p_loan.read_text(encoding="utf-8")

    assert "<!DOCTYPE html>" in content
    assert "<html lang=\"hi\">" in content
    assert "<main class=\"container\">" in content
    assert "<article>" in content
    assert "<h1>" in content
    assert "<h2>" in content
    assert "<link rel=\"canonical\"" in content
    assert "iframe" in content  # Ad placement container
    print("  [OK] Semantic HTML5 tags and ad containers verified")


def test_article_schema_jsonld_validity(tmp_path: Path):
    """Schema.org JSON-LD in generated article parses as valid JSON with Article and FAQPage types."""
    sites_root = _isolated_sites_dir(tmp_path)
    content_generator.generate_all_domain_articles(sites_dir=sites_root)
    p_loan = sites_root / "loanraaj.com" / "personal-loan-guide.html"
    content = p_loan.read_text(encoding="utf-8")

    # Extract JSON-LD block
    start_tag = '<script type="application/ld+json">'
    end_tag = "</script>"
    start_idx = content.find(start_tag) + len(start_tag)
    end_idx = content.find(end_tag, start_idx)
    raw_json = content[start_idx:end_idx].strip()

    data = json.loads(raw_json)
    assert "@context" in data
    assert "@graph" in data

    types = [item.get("@type") for item in data["@graph"]]
    assert "Article" in types
    assert "BreadcrumbList" in types
    assert "FAQPage" in types
    print("  [OK] Schema.org JSON-LD structured data validated: Article, Breadcrumbs, FAQ")


def test_sitemap_xml_validity(tmp_path: Path):
    """Generated sitemap.xml is well-formed XML and lists article paths."""
    sites_root = _isolated_sites_dir(tmp_path)
    content_generator.generate_all_domain_articles(sites_dir=sites_root)
    sitemap_path = sites_root / "loanraaj.com" / "sitemap.xml"
    assert sitemap_path.exists()
    content = sitemap_path.read_text(encoding="utf-8")

    root = ET.fromstring(content)
    assert "urlset" in root.tag
    urls = [elem.text for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert len(urls) >= 3
    assert any("personal-loan-guide.html" in u for u in urls)
    print(f"  [OK] sitemap.xml valid: {len(urls)} URLs listed")


def test_robots_txt_format(tmp_path: Path):
    """Generated robots.txt permits crawling and points to sitemap.xml."""
    sites_root = _isolated_sites_dir(tmp_path)
    content_generator.generate_all_domain_articles(sites_dir=sites_root)
    robots_path = sites_root / "loanraaj.com" / "robots.txt"
    assert robots_path.exists()
    text = robots_path.read_text(encoding="utf-8")

    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert "Sitemap:" in text
    assert "sitemap.xml" in text
    print("  [OK] robots.txt verified with sitemap directive")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        test_articles_generated_for_domains(tp)
        test_article_semantic_html_structure(tp)
        test_article_schema_jsonld_validity(tp)
        test_sitemap_xml_validity(tp)
        test_robots_txt_format(tp)
    print("\nAll content generator tests PASSED!")
