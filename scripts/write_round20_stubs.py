"""
Write 221 redirect stubs for the purged articles using render_301_stub.
Ensures LF line endings, 301 refresh header, and destination canonical.
"""
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.repair_leaked_articles import render_301_stub
from content_quality_gate import is_redirect_stub
from scripts.seo_onpage_audit import get_all_article_paths
from scripts.fix_article_images import get_all_articles

def write_stubs():
    redirects_file = PROJECT_ROOT / "data" / "redirects_round20.json"
    with open(redirects_file, "r", encoding="utf-8") as f:
        redirects = json.load(f)

    written = 0
    for entry in redirects:
        domain = entry["domain"]
        from_slug = entry["from_slug"]
        to_slug = entry["to_slug"]

        stub_path = PROJECT_ROOT / "sites" / domain / from_slug / "index.html"
        assert stub_path.exists(), f"Doomed article file missing: {stub_path}"

        content = render_301_stub(domain, to_slug)
        content_bytes = content.encode("utf-8")
        assert b"\r\n" not in content_bytes, "CRLF in rendered stub!"

        stub_path.write_bytes(content_bytes)
        assert is_redirect_stub(content), f"is_redirect_stub returned False for {stub_path}"
        written += 1

    print(f"Successfully wrote {written} redirect stubs.")

    # Verify article discovery functions now return exactly 57
    paths = get_all_article_paths(PROJECT_ROOT / "sites")
    articles = get_all_articles(PROJECT_ROOT / "sites")
    print(f"Post-stub get_all_article_paths count: {len(paths)}")
    print(f"Post-stub get_all_articles count: {len(articles)}")
    assert len(paths) == 57, f"Expected 57 articles, got {len(paths)}"
    assert len(articles) == 57, f"Expected 57 articles, got {len(articles)}"
    print("Verification passed: Exactly 57 surviving articles discovered.")

if __name__ == "__main__":
    write_stubs()
