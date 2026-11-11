"""Verification tests for Vuexy CRM Component U4 (Monetization, Display Banner Vault & CPL Leads)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from admin_ui.shell import render_crm_shell
from admin_ui.views.monetization import render_monetization_view


def test_monetization_view_structure_and_a11y_contracts() -> None:
    html = render_monetization_view()
    assert 'id="view-monetization"' in html
    assert 'id="u4BannerVaultCard"' in html
    assert 'id="u4BannerForm"' in html
    assert 'id="u4BvSnippet"' in html
    assert 'aria-describedby="u4BvSnippetErr"' in html

    # Accessible Toolbar & Responsive Table Regions per modern-web-guidance
    assert 'role="toolbar"' in html
    assert 'focusgroup="toolbar wrap"' in html
    assert 'role="separator" aria-orientation="vertical"' in html
    assert 'role="region"' in html
    assert 'aria-labelledby="u4BvCaption"' in html

    # Tabbed Revenue & Lead Streams with hidden="until-found"
    assert 'id="u4StreamTabs"' in html
    assert 'role="tablist"' in html
    assert 'hidden="until-found"' in html
    for btn_id in (
        "u4BtnRunFunnel",
        "u4BtnSyncApi",
        "u4BtnSyncPlacements",
        "u4BtnInjectLocal",
        "u4BtnDeployCf",
        "u4BtnSaveSnippet",
        "u4BtnSimLead",
        "u4BtnRefreshSerp",
        "u4BtnGenAccount",
    ):
        assert f'id="{btn_id}"' in html


def test_crm_shell_embeds_u4_and_removes_monetization_placeholder() -> None:
    shell_html = render_crm_shell()
    assert 'id="view-monetization"' in shell_html
    assert '<script src="/crm-assets/js/crm-monetization.js"></script>' in shell_html
    assert "Open Working Banner Vault (/)" not in shell_html
    assert "Monetization, Adsterra Vault &amp; CPL Leads (Layer U4)" not in shell_html


def test_live_u4_routes_and_non_destructive_apis() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as resp:
        assert resp.status == 200
        crm_html = resp.read().decode("utf-8", errors="ignore")
    assert 'id="u4BannerVaultCard"' in crm_html
    assert "/crm-assets/js/crm-monetization.js" in crm_html

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/js/crm-monetization.js", timeout=5) as js_resp:
        assert js_resp.status == 200
        js_text = js_resp.read().decode("utf-8", errors="ignore")
    assert "executeCopy" in js_text
    assert "CommandEvent" in js_text
    assert "a.password" not in js_text

    # Read-only APIs serving U4
    for endpoint, key in (
        ("/api/adsterra/funnel", "status"),
        ("/api/adsterra/banners", "domains"),
        ("/api/leads", "leads"),
        ("/api/serp/preview", "queries"),
        ("/api/accounts", "accounts"),
    ):
        with urllib.request.urlopen(f"http://127.0.0.1:5050{endpoint}", timeout=8) as api_resp:
            assert api_resp.status == 200
            data = json.loads(api_resp.read().decode("utf-8"))
        assert key in data, f"Missing {key!r} from {endpoint}"

    # Invalid banner snippet must be rejected cleanly (HTTP 400) without mutating vault
    bad_req = urllib.request.Request(
        "http://127.0.0.1:5050/api/adsterra/banners/save",
        data=json.dumps({"domain": "loanraaj.com", "slot": "auto", "snippet": "not a script"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(bad_req, timeout=5)
        raise AssertionError("Expected HTTP 400 for invalid banner snippet")
    except urllib.error.HTTPError as err:
        assert err.code == 400

    # Root / serves U4 Vault in Vuexy CRM; legacy /classic#bannerVaultCard remains intact
    with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=5) as root_resp:
        assert root_resp.status == 200
        root_html = root_resp.read().decode("utf-8", errors="ignore")
    assert 'id="u4BannerVaultCard"' in root_html

    with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=5) as cls_resp:
        assert cls_resp.status == 200
        cls_html = cls_resp.read().decode("utf-8", errors="ignore")
    assert 'id="bannerVaultCard"' in cls_html
