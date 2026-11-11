"""Verification tests for Component U6: Root (/) Cutover onto Vuexy CRM & Legacy /classic Fallback."""

from __future__ import annotations

import json
import urllib.request

from admin_ui.shell import render_crm_shell
from admin_ui.views import (
    render_growth_view,
    render_login_view,
    render_monetization_view,
    render_network_view,
    render_settings_view,
)


def test_u6_tracker_and_classic_links_updated() -> None:
    shell_html = render_crm_shell()
    assert "Step 6 / 6 Live" in shell_html
    assert 'href="/classic"' in shell_html
    assert "Classic UI (/classic)" in shell_html
    assert "Component U1&ndash;U6 Live" in shell_html
    assert "Classic Dashboard (/)" not in shell_html
    assert "Classic UI (/)" not in shell_html

    settings_html = render_settings_view()
    assert "Step 6 / 6 Live" in settings_html
    assert "Live &amp; Active" in settings_html
    assert ">Next<" not in settings_html

    assert 'href="/classic#bannerVaultCard"' in render_monetization_view()
    assert 'href="/classic"' in render_network_view()
    assert 'href="/classic"' in render_growth_view()

    login_html = render_login_view({"has_password": False, "email": "op@local", "display_name": "Op"})
    assert 'href="/classic"' in login_html


def test_live_u6_root_cutover_classic_fallback_and_vhost_preservation() -> None:
    # 1. Root / serves Vuexy CRM with Cache-Control: no-store
    with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=5) as root_resp:
        assert root_resp.status == 200
        assert "no-store" in root_resp.headers.get("Cache-Control", "")
        root_html = root_resp.read().decode("utf-8", errors="ignore")
    for marker in (
        "AdsterraFleet CRM |",
        'id="view-overview"',
        'id="view-autopublish"',
        'id="view-monetization"',
        'id="view-network"',
        'id="view-growth"',
        'id="view-settings"',
        "Step 6 / 6 Live",
    ):
        assert marker in root_html

    # 2. /crm remains active alias for backwards compatibility
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as crm_resp:
        assert crm_resp.status == 200
        assert "AdsterraFleet CRM |" in crm_resp.read().decode("utf-8", errors="ignore")

    # 3. /classic serves legacy dashboard pointing back to /
    with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=5) as cls_resp:
        assert cls_resp.status == 200
        cls_html = cls_resp.read().decode("utf-8", errors="ignore")
    assert 'id="bannerVaultCard"' in cls_html
    assert 'href="/"' in cls_html

    # 4. /autopublish standalone page stays intact
    with urllib.request.urlopen("http://127.0.0.1:5050/autopublish", timeout=5) as ap_resp:
        assert ap_resp.status == 200
        assert len(ap_resp.read().decode("utf-8", errors="ignore")) > 500

    # 5. Ctrl+K search JSON points Classic entries to /classic
    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/json/search-vertical.json", timeout=5) as js_resp:
        assert js_resp.status == 200
        nav = json.loads(js_resp.read().decode("utf-8"))
    classic_urls = [item["url"] for item in nav["navigation"]["classic"]]
    assert "/classic" in classic_urls
    assert "/" not in classic_urls

    # 6. Publisher domain Virtual Host (/) MUST still serve sites/<domain>.com/index.html, never CRM
    vhost_req = urllib.request.Request("http://127.0.0.1:5050/", headers={"Host": "loanraaj.com"})
    with urllib.request.urlopen(vhost_req, timeout=5) as vh_resp:
        assert vh_resp.status == 200
        vh_html = vh_resp.read().decode("utf-8", errors="ignore")
    assert "AdsterraFleet CRM |" not in vh_html
    assert "loanraaj" in vh_html.lower()
