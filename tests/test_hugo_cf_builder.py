"""
tests/test_hugo_cf_builder.py — Acceptance test for Step 3.1: Hugo Static Site & Cloudflare Pages Setup.
"""
from pathlib import Path
import hugo_cf_builder


def test_hugo_cf_sites_setup(tmp_path: Path):
    isolated_sites = tmp_path / "sites"
    res = hugo_cf_builder.setup_all_hugo_sites(sites_dir=isolated_sites)
    assert len(res) == 10

    live_sites = Path(__file__).parent.parent / "sites"
    for sites_dir in (isolated_sites, live_sites):
        for domain in hugo_cf_builder.DOMAINS_METADATA.keys():
            dom_dir = sites_dir / domain
            assert (dom_dir / "hugo.toml").exists(), f"Missing hugo.toml in {domain}"
            assert (dom_dir / "layouts" / "_default" / "baseof.html").exists()
            assert (dom_dir / "layouts" / "_default" / "single.html").exists()
            assert (dom_dir / "_headers").exists()
            assert (dom_dir / "content" / "posts").is_dir()

            base_html = (dom_dir / "layouts" / "_default" / "baseof.html").read_text(encoding="utf-8")
            assert "<html lang=\"hi\">" in base_html
            assert "schema.org" in base_html
            assert "WebSite" in base_html
