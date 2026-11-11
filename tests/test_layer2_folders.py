"""Layer 2 acceptance tests: canonical `sites/<domain>.com` consolidation & code hygiene."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import merge_site_folders
from network_registry import NETWORK_REGISTRY, canonical_site_key, get_canonical_site_dir


def test_consolidate_merges_unique_files_and_unions_sitemap(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    src = sites_root / "loanraaj"
    dst = sites_root / "loanraaj.com"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)

    (src / "index.html").write_text("<html><title>LoanRaaj Home</title></html>", encoding="utf-8")
    (src / "google31976c4df01121b2.html").write_text("google-site-verification: test\n", encoding="utf-8")
    (src / "post-only-src.html").write_text("<html>src post</html>", encoding="utf-8")
    (src / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url><loc>https://loanraaj.com/a.html</loc></url>\n"
        "  <url><loc>https://loanraaj.com/b.html</loc></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )

    (dst / "hugo.toml").write_text('title = "LoanRaaj"\n', encoding="utf-8")
    (dst / "_headers").write_text("/*\n  X-Frame-Options: SAMEORIGIN\n", encoding="utf-8")
    (dst / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url><loc>https://loanraaj.com/b.html</loc></url>\n"
        "  <url><loc>https://loanraaj.com/c.html</loc></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )

    summary = merge_site_folders.consolidate_all_site_folders(sites_dir=sites_root, dry_run=False)
    assert not src.exists()
    assert (dst / "hugo.toml").is_file()
    assert (dst / "_headers").is_file()
    assert (dst / "index.html").is_file()
    assert (dst / "google31976c4df01121b2.html").is_file()
    assert (dst / "post-only-src.html").is_file()

    root = ET.fromstring((dst / "sitemap.xml").read_text(encoding="utf-8"))
    locs = {el.text.strip() for el in root.iter() if el.tag.split("}")[-1] == "loc" and el.text}
    assert locs == {
        "https://loanraaj.com/a.html",
        "https://loanraaj.com/b.html",
        "https://loanraaj.com/c.html",
    }
    assert summary["remaining_dirs"] == ["loanraaj.com"]

    # Idempotent second run when already consolidated
    second = merge_site_folders.consolidate_all_site_folders(sites_dir=sites_root, dry_run=False)
    assert second["totals"]["consolidated_domains"] == 0
    assert second["totals"]["already_consolidated"] == len(NETWORK_REGISTRY)


def test_consolidate_dry_run_makes_no_disk_changes(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    src = sites_root / "karzseva"
    dst = sites_root / "karzseva.com"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "extra.html").write_text("<html>extra</html>", encoding="utf-8")

    summary = merge_site_folders.consolidate_all_site_folders(sites_dir=sites_root, dry_run=True)
    assert summary["totals"]["copied_new"] == 1
    assert src.is_dir()
    assert not (dst / "extra.html").exists()


def test_network_registry_canonical_site_helpers() -> None:
    assert canonical_site_key("loanraaj") == "loanraaj"
    assert canonical_site_key("loanraaj.com") == "loanraaj"
    assert canonical_site_key("https://www.loanraaj.com/some-page.html") == "loanraaj"
    assert get_canonical_site_dir("https://karzseva.com/abc") == Path("sites") / "karzseva.com"
    with pytest.raises(ValueError):
        canonical_site_key("nonexistent-domain.org")


def test_live_sites_dir_has_exact_ten_canonical_domains() -> None:
    sites_root = ROOT_DIR / "sites"
    expected_dirs = sorted(f"{site_id}.com" for site_id in NETWORK_REGISTRY)
    actual_dirs = sorted(p.name for p in sites_root.iterdir() if p.is_dir())
    assert actual_dirs == expected_dirs

    loanraaj_dir = sites_root / "loanraaj.com"
    assert (loanraaj_dir / "index.html").is_file()
    assert (loanraaj_dir / "google31976c4df01121b2.html").is_file()
    assert (loanraaj_dir / "21-machines-to-start-a-profitable-home-business.html").is_file()


def test_active_modules_use_canonical_com_directories() -> None:
    autopublish = (ROOT_DIR / "autopublish_daemon.py").read_text(encoding="utf-8")
    assert 'os.path.join("sites", site_id),' not in autopublish
    assert 'os.path.join("sites", f"{site_id}.com")' in autopublish

    indexer = (ROOT_DIR / "instant_indexer.py").read_text(encoding="utf-8")
    assert "os.path.join(sites_dir, site_key)" not in indexer
    assert "os.path.join(sites_dir, site_id)" not in indexer
    assert 'os.path.join("sites", site_key)' not in indexer
    assert 'os.path.join("sites", f"{site_key}.com")' in indexer

    banners = (ROOT_DIR / "inject_display_banners.py").read_text(encoding="utf-8")
    assert 'SITES_DIR / f"{site_id}.com"' in banners
    assert "\n        site_dir = SITES_DIR / site_id\n" not in banners

    ui_src = (ROOT_DIR / "ui.py").read_text(encoding="utf-8")
    assert "(sites_root / canonical_folder / \"index.html\").resolve()" in ui_src
    assert 'Path("sites") / folder_name / clean_p' not in ui_src
    assert "is_relative_to(sites_root)" in ui_src


def test_live_ui_routes_canonical_and_short_site_paths() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/api/adsterra/banners", timeout=8) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read().decode("utf-8"))
        assert payload.get("status") == "ok"
        assert len(payload.get("domains", [])) == 10

    for route in ("/sites/loanraaj", "/sites/loanraaj.com"):
        with urllib.request.urlopen(f"http://127.0.0.1:5050{route}", timeout=8) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8", errors="replace")
            assert "LoanRaaj" in body
