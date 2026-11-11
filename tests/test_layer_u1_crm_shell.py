"""Verification tests for Vuexy CRM Shell Component U1 and zero legacy regressions."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from admin_ui.shell import render_crm_shell


def test_render_crm_shell_contains_six_workspaces_and_theme_controls() -> None:
    html = render_crm_shell()
    for view_id in (
        'id="view-overview"',
        'id="view-autopublish"',
        'id="view-monetization"',
        'id="view-network"',
        'id="view-growth"',
        'id="view-settings"',
    ):
        assert view_id in html

    for theme_val in ('data-bs-theme-value="light"', 'data-bs-theme-value="dark"', 'data-bs-theme-value="system"'):
        assert theme_val in html

    assert '<meta name="color-scheme" content="light dark"' in html
    assert 'data-assets-path="/crm-assets/"' in html
    assert "GTM-5J3LMKC" not in html
    assert "btn-buy-now" not in html


def test_live_crm_shell_routes_assets_and_legacy_coexistence() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8", errors="ignore")
    assert "AdsterraFleet CRM |" in body

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/vendor/css/core.css", timeout=5) as css_resp:
        assert css_resp.status == 200
        assert "text/css" in css_resp.headers.get("Content-Type", "")

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/js/crm-shell.js", timeout=5) as js_resp:
        assert js_resp.status == 200
        assert "javascript" in js_resp.headers.get("Content-Type", "")

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/json/search-vertical.json", timeout=5) as json_resp:
        assert json_resp.status == 200
        payload = json.loads(json_resp.read().decode("utf-8"))
        assert "workspaces" in payload["navigation"]

    # Path traversal blocked cleanly
    try:
        urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/../../.env", timeout=5)
        raise AssertionError("Traversal unexpectedly succeeded")
    except urllib.error.HTTPError as err:
        assert err.code == 404

    # Root (/) now serves the Vuexy CRM; /classic preserves legacy HTML fallback
    with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=5) as root_resp:
        assert root_resp.status == 200
        root_html = root_resp.read().decode("utf-8", errors="ignore")
    assert "AdsterraFleet CRM |" in root_html

    with urllib.request.urlopen("http://127.0.0.1:5050/classic", timeout=5) as cls_resp:
        assert cls_resp.status == 200
        cls_html = cls_resp.read().decode("utf-8", errors="ignore")
    assert 'href="/"' in cls_html
    assert 'id="bannerVaultCard"' in cls_html
