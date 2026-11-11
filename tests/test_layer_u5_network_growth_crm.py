"""Verification tests for Vuexy CRM Component U5 (Network, Proxies, ADB, Config, GSC, Push & Telegram)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from admin_ui.shell import render_crm_shell
from admin_ui.views import render_growth_view, render_network_view, render_settings_view


def test_network_and_growth_view_structure_and_a11y_contracts() -> None:
    net_html = render_network_view()
    assert 'id="view-network"' in net_html
    assert 'id="u5ConfigForm"' in net_html
    assert 'id="u5TargetUrls"' in net_html
    assert 'id="u5ProxyFetchForm"' in net_html
    assert 'id="u5ProxySaveForm"' in net_html
    assert 'role="toolbar"' in net_html
    assert 'focusgroup="toolbar wrap"' in net_html
    assert 'role="separator" aria-orientation="vertical"' in net_html
    assert '<details class="card u5-acc-item" open id="u5AccProxy">' in net_html
    assert '<details class="card u5-acc-item" open id="u5AccAdb">' in net_html
    assert "u5BtnProbeFailover" in net_html
    assert "u5BtnSwapFailover" in net_html
    assert "u5BtnRotateAdb" in net_html
    assert 'id="u5BtnToggleProxyMask"' in net_html
    assert 'data-masked="true"' in net_html

    growth_html = render_growth_view()
    assert 'id="view-growth"' in growth_html
    assert 'id="u5GrowthTabs"' in growth_html
    assert 'role="tablist"' in growth_html
    assert 'hidden="until-found"' in growth_html
    assert 'id="u5SwitchDeliveryLock"' in growth_html
    assert 'switch' in growth_html
    assert 'command="--copy"' in growth_html
    assert 'commandfor="u5VapidPubCode"' in growth_html
    assert 'id="u5GscCredForm"' in growth_html
    assert 'id="u5OsForm"' in growth_html
    assert 'id="u5BtnToggleOsKey"' in growth_html

    settings_html = render_settings_view()
    assert "Step 6 / 6 Live" in settings_html
    assert "U5" in settings_html
    assert "U6" in settings_html


def test_crm_shell_embeds_u5_and_removes_all_staged_placeholders() -> None:
    shell_html = render_crm_shell()
    assert 'id="view-network"' in shell_html
    assert 'id="view-growth"' in shell_html
    assert '<script src="/crm-assets/js/crm-network-growth.js"></script>' in shell_html
    assert "STAGED WORKSPACE" not in shell_html
    assert "Open Working Network Panel (/)" not in shell_html
    assert "Open Working Growth Tools (/)" not in shell_html


def test_live_u5_routes_and_non_destructive_apis() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as resp:
        assert resp.status == 200
        crm_html = resp.read().decode("utf-8", errors="ignore")
    assert 'id="u5ConfigForm"' in crm_html
    assert 'id="u5GrowthTabs"' in crm_html
    assert "/crm-assets/js/crm-network-growth.js" in crm_html

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/js/crm-network-growth.js", timeout=5) as js_resp:
        assert js_resp.status == 200
        js_text = js_resp.read().decode("utf-8", errors="ignore")
    assert "refreshNetworkData" in js_text
    assert "refreshGrowthData" in js_text
    assert "innerHTML" not in js_text

    # Read-only APIs serving Network & Growth
    for endpoint, key in (
        ("/api/failover/status", "status"),
        ("/api/adb/status", "devices"),
        ("/api/config", "config"),
        ("/api/gsc/status", "domains"),
        ("/api/push/status", "vapid"),
        ("/api/telegram/status", "recent_alerts"),
    ):
        with urllib.request.urlopen(f"http://127.0.0.1:5050{endpoint}", timeout=8) as api_resp:
            assert api_resp.status == 200
            data = json.loads(api_resp.read().decode("utf-8"))
        assert key in data, f"Missing {key!r} from {endpoint}"

    # Validation checks on sensitive POST endpoints (non-destructive)
    bad_gsc = urllib.request.Request(
        "http://127.0.0.1:5050/api/gsc/credentials",
        data=json.dumps({"credentials_json": "invalid-json"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(bad_gsc, timeout=5)
        raise AssertionError("Expected HTTP 400 for invalid GSC JSON")
    except urllib.error.HTTPError as err:
        assert err.code == 400

    bad_fetch = urllib.request.Request(
        "http://127.0.0.1:5050/api/proxies/fetch",
        data=json.dumps({"api_url": ""}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(bad_fetch, timeout=5)
        raise AssertionError("Expected HTTP 400 for empty proxy fetch URL")
    except urllib.error.HTTPError as err:
        assert err.code == 400

    # Layer 6 Testing-Phase Delivery Lock verification
    lock_req = urllib.request.Request(
        "http://127.0.0.1:5050/api/push/deliver-test",
        data=json.dumps({"domain": "loanraaj.com"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(lock_req, timeout=8) as lock_resp:
        assert lock_resp.status == 200
        lock_data = json.loads(lock_resp.read().decode("utf-8"))
    res_obj = lock_data.get("result") or {}
    assert res_obj.get("status") == "blocked_testing_phase" or res_obj.get("blocked") is True
