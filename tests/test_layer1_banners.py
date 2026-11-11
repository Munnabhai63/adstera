"""
Layer 1 Automated Verification Suite — Display Banner Vault, Templates & Injector.

Every unit test isolates `state/adsterra_banners.json` inside pytest's `tmp_path`
so production banner configuration is never polluted with synthetic test keys.
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request

import pytest

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import adsterra_links  # noqa: E402
import content_quality_gate  # noqa: E402
import import_adsterra_csv  # noqa: E402
import inject_display_banners  # noqa: E402
import network_registry  # noqa: E402
import site_templates  # noqa: E402
import worker  # noqa: E402

KEY_728 = "a1b2c3d4e5f67890123456789abcdef1"
KEY_300 = "b2c3d4e5f67890123456789abcdef1a2"
KEY_NAT = "c3d4e5f67890123456789abcdef1a2b3"

SNIPPET_728 = (
    "<script type=\"text/javascript\">\n"
    "atOptions = {\n"
    f"  'key' : '{KEY_728}',\n"
    "  'format' : 'iframe',\n"
    "  'height' : 90,\n"
    "  'width' : 728,\n"
    "  'params' : {}\n"
    "};\n"
    "</script>\n"
    f"<script type=\"text/javascript\" src=\"//www.highperformanceformat.com/{KEY_728}/invoke.js\"></script>"
)

SNIPPET_300 = (
    "<script type=\"text/javascript\">\n"
    "atOptions = {\n"
    f"  'key' : '{KEY_300}',\n"
    "  'format' : 'iframe',\n"
    "  'height' : 250,\n"
    "  'width' : 300,\n"
    "  'params' : {}\n"
    "};\n"
    "</script>\n"
    f"<script type=\"text/javascript\" src=\"//www.highperformanceformat.com/{KEY_300}/invoke.js\"></script>"
)

SNIPPET_NAT = (
    f"<script async=\"async\" data-cfasync=\"false\" src=\"//pl28000001.effectivegatecpm.com/{KEY_NAT}/invoke.js\"></script>\n"
    f"<div id=\"container-{KEY_NAT}\"></div>"
)


@pytest.fixture()
def isolated_banner_state(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    state_file = tmp_path / "adsterra_banners.json"
    monkeypatch.setattr(adsterra_links, "BANNER_STATE_PATH", state_file)
    adsterra_links._banner_cache["mtime"] = -1.0
    adsterra_links._banner_cache["data"] = {"domains": {}}
    return state_file


def test_unconfigured_slots_emit_only_comment_markers(isolated_banner_state: pathlib.Path) -> None:
    for slot in ("728x90", "300x250", "native"):
        rendered = adsterra_links.render_display_banner("loanraaj.com", slot)
        assert rendered == f"<!-- ADSTERRA_SLOT:{slot} --><!-- /ADSTERRA_SLOT:{slot} -->"
        assert "<div" not in rendered.lower()
        assert "<script" not in rendered.lower()
        assert "placeholder" not in rendered.lower()
        assert "dummy" not in rendered.lower()


def test_register_bulk_and_render_balanced_banners(isolated_banner_state: pathlib.Path) -> None:
    bulk = "\n\n".join([SNIPPET_728, SNIPPET_300, SNIPPET_NAT])
    saved = adsterra_links.register_bulk_snippets("karzseva.com", bulk)
    assert len(saved) == 3
    assert {item["slot"] for item in saved} == {"banner_728x90", "banner_300x250", "native_banner"}

    html_728 = adsterra_links.render_display_banner("karzseva.com", "728x90")
    assert "<!-- ADSTERRA_SLOT:728x90 -->" in html_728
    assert 'data-ad-slot="adsterra-728x90"' in html_728
    assert KEY_728 in html_728
    assert html_728.count("<div") == html_728.count("</div>")

    html_300 = adsterra_links.render_display_banner("karzseva.com", "300x250")
    assert 'data-ad-slot="adsterra-300x250"' in html_300
    assert KEY_300 in html_300
    assert html_300.count("<div") == html_300.count("</div>")

    html_nat = adsterra_links.render_display_banner("karzseva.com", "native")
    assert 'data-ad-slot="adsterra-native"' in html_nat
    assert KEY_NAT in html_nat
    assert html_nat.count("<div") == html_nat.count("</div>")


def test_rejects_dummy_mismatched_and_wrong_slot_snippets(isolated_banner_state: pathlib.Path) -> None:
    dummy_hex = "0" * 32
    dummy_snippet = SNIPPET_300.replace(KEY_300, dummy_hex)
    with pytest.raises(ValueError, match="dummy"):
        adsterra_links.register_banner_snippet("karzseva.com", dummy_snippet)

    mismatched_invoke = SNIPPET_300.replace(
        f"/{KEY_300}/invoke.js",
        f"/{KEY_728}/invoke.js",
    )
    with pytest.raises(ValueError, match="Mismatched"):
        adsterra_links.register_banner_snippet("karzseva.com", mismatched_invoke)

    with pytest.raises(ValueError, match="does not match"):
        adsterra_links.register_banner_snippet("karzseva.com", SNIPPET_728, slot="300x250")

    with pytest.raises(ValueError, match="Unknown network domain"):
        adsterra_links.register_banner_snippet("notarealdomain.example", SNIPPET_300)


def test_site_templates_and_quality_gate_preserve_structure(isolated_banner_state: pathlib.Path) -> None:
    adsterra_links.register_banner_snippet("karzseva.com", SNIPPET_728)
    adsterra_links.register_banner_snippet("karzseva.com", SNIPPET_300)
    adsterra_links.register_banner_snippet("karzseva.com", SNIPPET_NAT)

    cfg = network_registry.NETWORK_REGISTRY["karzseva"]
    sidebar = site_templates.render_sidebar(cfg, recent_articles=[])
    assert "<!-- ADSTERRA_SLOT:300x250 -->" in sidebar
    assert KEY_300 in sidebar

    page_html = site_templates.render_master_page(
        site_config=cfg,
        title="Test Guide",
        desc="Meta description for banner layer test.",
        canonical="https://karzseva.com/test-guide",
        main_body="<main><p>Body paragraph.</p></main>",
    )
    assert "/* Adsterra Responsive Display Banner & Native Slots (Layer 1) */" in page_html
    assert "<!-- ADSTERRA_SLOT:728x90 -->" in page_html
    assert KEY_728 in page_html
    assert page_html.lower().count("<div") == page_html.lower().count("</div>")

    raw_article = "<p>Para one with commercial loan context.</p><p>Para two.</p><p>Para three.</p><p>Para four.</p>"
    formatted_once, _, _ = content_quality_gate.ContentQualityFinishGate.format_editorial_layout(
        raw_article,
        "Test Commercial Guide",
        "karzseva.com",
        "commercial loan",
    )
    assert "<!-- ADSTERRA_SLOT:native -->" in formatted_once
    assert KEY_NAT in formatted_once
    formatted_twice, _, _ = content_quality_gate.ContentQualityFinishGate.format_editorial_layout(
        formatted_once,
        "Test Commercial Guide",
        "karzseva.com",
        "commercial loan",
    )
    assert formatted_twice.count("<!-- ADSTERRA_SLOT:native -->") == 1


def test_inject_display_banners_idempotency_and_in_place_upgrade(tmp_path: pathlib.Path, isolated_banner_state: pathlib.Path) -> None:
    sites_root = tmp_path / "sites"
    site_dir = sites_root / "karzseva"
    site_dir.mkdir(parents=True)

    article_html = (
        "<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>"
        "<nav class=\"nav-wrap\"><ul><li>Home</li></ul></nav>"
        "<div class=\"main\"><article class=\"post-paper\"><div class=\"post-content\">"
        "<p>P1</p><p>P2</p><p>P3</p><p>P4</p>"
        "</div><div class=\"author-card\">Author</div></article>"
        "<aside class=\"sidebar-col\"><!-- Interactive Tool Widget --><div class=\"widget-card\">Calc</div></aside>"
        "</div></body></html>"
    )
    emi_html = (
        "<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>"
        "<header><nav>Links</nav></header>"
        "<main class=\"container\"><p>Calculator</p><aside><div class=\"sidebar-card\">Side</div></aside></main>"
        "</body></html>"
    )
    verify_html = "google-site-verification: google31976c4df01121b2.html"

    (site_dir / "post.html").write_text(article_html, encoding="utf-8")
    (site_dir / "emi-calculator.html").write_text(emi_html, encoding="utf-8")
    (site_dir / "google31976c4df01121b2.html").write_text(verify_html, encoding="utf-8")

    # Pass 1: Unconfigured state inserts invisible comment markers
    res1 = inject_display_banners.inject_all_sites(sites_dir=sites_root)
    assert res1["errors"] == []
    assert res1["files_scanned"] == 2
    assert res1["files_updated"] == 2
    assert res1["files_skipped"] == 1
    assert (site_dir / "google31976c4df01121b2.html").read_text(encoding="utf-8") == verify_html

    post_after_p1 = (site_dir / "post.html").read_text(encoding="utf-8")
    assert "<!-- ADSTERRA_SLOT:728x90 --><!-- /ADSTERRA_SLOT:728x90 -->" in post_after_p1
    assert "<!-- ADSTERRA_SLOT:300x250 --><!-- /ADSTERRA_SLOT:300x250 -->" in post_after_p1
    assert "<!-- ADSTERRA_SLOT:native --><!-- /ADSTERRA_SLOT:native -->" in post_after_p1

    emi_after_p1 = (site_dir / "emi-calculator.html").read_text(encoding="utf-8")
    assert emi_after_p1.index("</header>") < emi_after_p1.index("<!-- ADSTERRA_SLOT:728x90 -->")

    # Pass 2: Re-running immediately makes zero modifications
    res2 = inject_display_banners.inject_all_sites(sites_dir=sites_root)
    assert res2["files_updated"] == 0
    assert (site_dir / "post.html").read_text(encoding="utf-8") == post_after_p1

    # Pass 3: Configure live snippets and verify in-place marker upgrade without duplicates
    adsterra_links.register_bulk_snippets("karzseva.com", "\n".join([SNIPPET_728, SNIPPET_300, SNIPPET_NAT]))
    res3 = inject_display_banners.inject_all_sites(sites_dir=sites_root)
    assert res3["errors"] == []
    assert res3["files_updated"] == 2
    upgraded_post = (site_dir / "post.html").read_text(encoding="utf-8")
    assert upgraded_post.count("<!-- ADSTERRA_SLOT:728x90 -->") == 1
    assert upgraded_post.count("<!-- ADSTERRA_SLOT:300x250 -->") == 1
    assert upgraded_post.count("<!-- ADSTERRA_SLOT:native -->") == 1
    assert KEY_728 in upgraded_post and KEY_300 in upgraded_post and KEY_NAT in upgraded_post
    assert upgraded_post.lower().count("<div") == upgraded_post.lower().count("</div>")

    with pytest.raises(ValueError, match="Unknown network domain filter"):
        inject_display_banners.inject_all_sites(sites_dir=sites_root, domain_filter="notarealdomain.com")


def test_import_adsterra_csv_real_export(isolated_banner_state: pathlib.Path) -> None:
    csv_path = pathlib.Path(r"F:\UserData\Downloads\Pub_Codes_3549341_1794351083.csv")
    if not csv_path.exists():
        pytest.skip("Adsterra CSV export not present on disk")
    report = import_adsterra_csv.run_import(csv_path=str(csv_path), sync_api=False)
    assert report["csv_domains"] == 10
    assert len(report["parity_warnings"]) == 0


def test_worker_ad_selectors_include_display_banners() -> None:
    joined = " ".join(worker._AD_SELECTORS)
    assert "highperformanceformat" in joined
    assert "profitabledisplaynetwork" in joined
    assert "[data-ad-slot^='adsterra-']" in joined


def test_live_ui_banner_vault_endpoint() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5050/api/adsterra/banners", timeout=4) as resp:
            assert resp.status == 200
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert len(payload["domains"]) == 10
        with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=4) as resp_crm:
            assert resp_crm.status == 200
            crm_body = resp_crm.read().decode("utf-8", errors="ignore")
        assert 'id="u4BannerVaultCard"' in crm_body

        with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=4) as resp_html:
            assert resp_html.status == 200
            body = resp_html.read().decode("utf-8", errors="ignore")
        assert 'id="bannerVaultCard"' in body

        # Validation error check (400 on missing snippet) without mutating production state
        req = urllib.request.Request(
            "http://127.0.0.1:5050/api/adsterra/banners/save",
            data=json.dumps({"domain": "karzseva.com", "snippet": ""}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=4)
        assert exc_info.value.code == 400
    except urllib.error.URLError as exc:
        pytest.fail(f"Live UI server not reachable on 127.0.0.1:5050: {exc}")


def test_deploy_cloudflare_sites_uses_utf8_subprocess(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites_root = tmp_path / "sites"
    (sites_root / "karzseva.com").mkdir(parents=True)
    monkeypatch.setattr(inject_display_banners, "SITES_DIR", sites_root)

    seen_kwargs: dict[str, object] = {}

    class DummyProc:
        returncode = 0
        stdout = None
        stderr = None

    def fake_run(cmd, **kwargs):
        seen_kwargs.update(kwargs)
        return DummyProc()

    monkeypatch.setattr(inject_display_banners.subprocess, "run", fake_run)
    results = inject_display_banners.deploy_cloudflare_sites(["karzseva"])
    assert results == [{"site_id": "karzseva", "ok": True, "returncode": 0, "tail": ""}]
    assert seen_kwargs.get("encoding") == "utf-8"
    assert seen_kwargs.get("errors") == "replace"
