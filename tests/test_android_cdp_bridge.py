"""
tests/test_android_cdp_bridge.py — Unit and integration tests for Step 1.1 (B3):
Android Chrome ADB DevTools Bridge & fail-closed worker integration.
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import android_cdp_bridge as bridge_mod
from android_cdp_bridge import (
    ADB_DAEMON_PORT,
    AndroidCdpBridge,
    AndroidCdpSession,
    parse_proc_net_unix,
    probe_cdp_endpoint,
)
from pool import GeoInfo, Proxy
import worker


SAMPLE_PROC_NET_UNIX = """\
Num       RefCount Protocol Flags    Type St Inode Path
0000000000000000: 00000003 00000000 00000000 0001 03 11597081 @chrome_devtools_remote_9999
0000000000000000: 00000002 00000000 00010000 0001 01 14118670 @stetho_com.google.android.apps.messaging_devtools_remote
0000000000000000: 00000002 00000000 00010000 0001 01 14561600 @chrome_devtools_remote_4516
0000000000000000: 00000002 00000000 00010000 0001 01 14561591 @chrome_devtools_remote
0000000000000000: 00000002 00000000 00010000 0001 01 84142 /data/local/tmp/not_abstract
"""


def test_parse_proc_net_unix_filters_listening_and_prioritizes_exact():
    entries = parse_proc_net_unix(SAMPLE_PROC_NET_UNIX)
    assert [e.socket_name for e in entries] == [
        "chrome_devtools_remote",
        "chrome_devtools_remote_4516",
    ]
    assert entries[0].is_listening is True
    assert entries[0].inode == 14561591


def test_resolve_device_serial_aborts_immediately_when_unauthorized(tmp_path):
    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"enabled": True}},
        forward_state_file=tmp_path / "fwd.json",
        owned_targets_file=tmp_path / "targets.json",
    )
    with patch("mobile_adb.list_devices", return_value=[{"id": "RZCX21WTS9E", "status": "unauthorized"}]):
        with pytest.raises(RuntimeError, match="unauthorized"):
            bridge.resolve_device_serial()


def test_cleanup_orphaned_forwards_removes_only_dead_pids(tmp_path):
    fwd_file = tmp_path / "adb_forwards.json"
    bridge = AndroidCdpBridge(
        forward_state_file=fwd_file,
        owned_targets_file=tmp_path / "targets.json",
    )
    bridge_mod._save_json_dict(
        fwd_file,
        {
            "SER1:9225": {"serial": "SER1", "host_port": 9225, "remote_socket": "chrome_devtools_remote", "owner_pid": 999991},
            "SER1:9226": {"serial": "SER1", "host_port": 9226, "remote_socket": "chrome_devtools_remote", "owner_pid": os.getpid()},
        },
    )

    fwd_list_output = (
        "SER1 tcp:9225 localabstract:chrome_devtools_remote\n"
        "SER1 tcp:9226 localabstract:chrome_devtools_remote\n"
        "SER1 tcp:9227 localabstract:other_user_socket\n"
    )
    removed_calls: list[list[str]] = []

    def fake_run_adb(args, custom_path="", timeout=12.0):
        if args == ["forward", "--list"]:
            return 0, fwd_list_output
        if "forward" in args and "--remove" in args:
            removed_calls.append(args)
            return 0, ""
        return 0, ""

    with patch("mobile_adb.run_adb", side_effect=fake_run_adb), patch(
        "android_cdp_bridge._is_pid_alive", side_effect=lambda pid: pid == os.getpid()
    ):
        removed = bridge.cleanup_orphaned_forwards("SER1")

    assert removed == 1
    assert removed_calls == [["-s", "SER1", "forward", "--remove", "tcp:9225"]]
    saved = bridge_mod._load_json_dict(fwd_file)
    assert "SER1:9225" not in saved
    assert "SER1:9226" in saved


def test_setup_forward_skips_active_ports_and_uses_no_rebind(tmp_path):
    fwd_file = tmp_path / "adb_forwards.json"
    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"port_min": 9222, "port_max": 9230}},
        forward_state_file=fwd_file,
        owned_targets_file=tmp_path / "targets.json",
    )
    entry = parse_proc_net_unix(SAMPLE_PROC_NET_UNIX)[0]
    adb_calls: list[list[str]] = []

    def fake_run_adb(args, custom_path="", timeout=12.0):
        adb_calls.append(args)
        if args == ["forward", "--list"]:
            return 0, "SER1 tcp:9222 localabstract:chrome_devtools_remote\n"
        return 0, "9223"

    with patch("mobile_adb.run_adb", side_effect=fake_run_adb), patch(
        "android_cdp_bridge._is_localhost_port_free", return_value=True
    ):
        port = bridge.setup_forward("SER1", entry)

    assert port != ADB_DAEMON_PORT
    assert port == 9223
    assert ["-s", "SER1", "forward", "--no-rebind", "tcp:9223", "localabstract:chrome_devtools_remote"] in adb_calls


@pytest.mark.anyio
async def test_probe_cdp_endpoint_requires_ws_debugger_url():
    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            if url.endswith("/json/version"):
                return FakeResp(200, {"Browser": "Chrome/156.0"})  # missing webSocketDebuggerUrl
            return FakeResp(200, [])

    with patch("android_cdp_bridge.httpx.AsyncClient", FakeClient):
        assert await probe_cdp_endpoint(9225) is None

    class GoodClient(FakeClient):
        async def get(self, url):
            if url.endswith("/json/version"):
                return FakeResp(200, {"Browser": "Chrome/156.0", "webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/browser"})
            return FakeResp(200, [{"id": "1", "type": "page"}])

    with patch("android_cdp_bridge.httpx.AsyncClient", GoodClient):
        ver = await probe_cdp_endpoint(9225)
        assert ver is not None
        assert ver["Browser"] == "Chrome/156.0"


@pytest.mark.anyio
async def test_cleanup_owned_targets_preserves_personal_tabs_and_cookies(tmp_path):
    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"dedicated_device": False}},
        forward_state_file=tmp_path / "fwd.json",
        owned_targets_file=tmp_path / "targets.json",
    )

    personal_page = MagicMock()
    personal_page.close = AsyncMock()
    owned_page = MagicMock()
    owned_page.close = AsyncMock()

    cdp_personal = MagicMock()
    cdp_personal.send = AsyncMock(return_value={"targetInfo": {"targetId": "PERSONAL_TAB_1"}})
    cdp_personal.detach = AsyncMock()

    cdp_owned = MagicMock()
    cdp_owned.send = AsyncMock(return_value={"targetInfo": {"targetId": "OWNED_TAB_9"}})
    cdp_owned.detach = AsyncMock()

    b_cdp = MagicMock()
    b_cdp.send = AsyncMock(return_value={"success": True})
    b_cdp.detach = AsyncMock()

    context = MagicMock()
    context.pages = [personal_page, owned_page]
    context.new_cdp_session = AsyncMock(side_effect=[cdp_personal, cdp_owned])

    browser = MagicMock()
    browser.new_browser_cdp_session = AsyncMock(return_value=b_cdp)
    browser.close = AsyncMock()

    session = AndroidCdpSession(
        serial="SER1",
        host_port=9225,
        remote_socket="chrome_devtools_remote",
        ws_url="ws://127.0.0.1:9225/devtools/browser",
        browser_version="Chrome/156",
        user_agent="Mozilla/5.0 Android",
        browser=browser,
        context=context,
        owned_target_ids=["OWNED_TAB_9"],
        visited_origins={"https://loanraaj.com"},
        _dedicated_device=False,
    )

    await bridge.cleanup_owned_targets(session, keep_cookies=False)

    personal_page.close.assert_not_awaited()
    owned_page.close.assert_awaited_once()
    sent_methods = [call.args[0] for call in b_cdp.send.await_args_list]
    assert "Network.clearBrowserCookies" not in sent_methods
    assert "Storage.clearDataForOrigin" in sent_methods
    clear_args = [call.args[1] for call in b_cdp.send.await_args_list if call.args[0] == "Storage.clearDataForOrigin"][0]
    assert clear_args["origin"] == "https://loanraaj.com"


def test_should_use_android_cdp_routing():
    class FpStub:
        is_mobile = True

    cfg = {"browser": {"engine": "mahi"}, "android_cdp": {"enabled": True, "prefer_for_mobile_only": True}}
    assert worker._should_use_android_cdp(cfg, FpStub(), use_fixture=False) is True
    assert worker._should_use_android_cdp(cfg, FpStub(), use_fixture=True) is False
    FpStub.is_mobile = False
    assert worker._should_use_android_cdp(cfg, FpStub(), use_fixture=False) is False


@pytest.mark.anyio
async def test_worker_fail_closed_when_android_cdp_disconnects(tmp_path):
    proxy = Proxy(host="49.36.120.10", port=0, geo=GeoInfo(country="IN", region="MH", city="Mumbai", timezone="Asia/Kolkata", locale="en-IN"))
    cfg = {
        "target": {
            "url": "https://loanraaj.com",
            "urls": ["https://loanraaj.com"],
            "fixture": "tests/fixtures/page.html",
            "referrers": [""],
            "referrer_weights": [1.0],
            "min_dwell": 25,
            "max_dwell": 30,
            "scroll_prob": 0.5,
            "click_prob": 0.04,
            "ad_clicks_max": 1,
        },
        "session": {"page_depth_min": 1, "page_depth_max": 1, "internal_nav_prob": 0.0, "return_visit_prob": 0.0, "cookie_persist": False},
        "cmp": {"enabled": False, "accept_prob": 0.88},
        "browser": {"engine": "android_cdp", "headless": False, "slow_mo_ms": 0, "block_resources": [], "use_mahi_profiles": False},
        "android_cdp": {"enabled": True, "fail_closed": True, "prefer_for_mobile_only": False, "allow_fixture": False},
        "ab_testing": {"enabled": False},
        "push_notifications": {"enabled": False},
        "payout_safety": {"solo_network": "adsterra", "skip_lead_form_submit": True},
        "stats_csv_path": "",
    }
    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock()
    mock_pw = MagicMock()

    with patch("android_cdp_bridge.AndroidCdpBridge.connect", new=AsyncMock(side_effect=RuntimeError("USB detached"))), patch(
        "worker.db.log_session"
    ):
        res = await worker.run_session(mock_pw, mock_browser, proxy, cfg, random.Random(1), use_fixture=False)

    assert res["status"] == "degraded"
    assert "AndroidCdpUnavailable" in res["error_reason"]
    mock_browser.new_context.assert_not_awaited()


# ── open_owned_tab fallback tests ────────────────────────────────────────────

@pytest.mark.anyio
async def test_open_owned_tab_fast_path_records_target_id(tmp_path):
    """Fast path: context.new_page() succeeds → targetId recorded."""
    from unittest.mock import AsyncMock, MagicMock, patch

    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"enabled": True}},
        forward_state_file=tmp_path / "fwd.json",
        owned_targets_file=tmp_path / "targets.json",
    )

    fake_page = MagicMock()
    fake_page.url = "about:blank"
    fake_cdp = AsyncMock()
    fake_cdp.send = AsyncMock(return_value={"targetInfo": {"targetId": "ABC123"}})
    fake_cdp.detach = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=fake_page)
    mock_context.new_cdp_session = AsyncMock(return_value=fake_cdp)

    session = AndroidCdpSession(
        serial="FAKE001",
        host_port=9222,
        remote_socket="chrome_devtools_remote",
        ws_url="ws://127.0.0.1:9222/devtools/browser",
        browser_version="Chrome/156",
        user_agent="Mozilla/5.0 Android",
        browser=MagicMock(),
        context=mock_context,
        adb_path="",
        _dedicated_device=False,
    )

    page, target_id = await bridge.open_owned_tab(session)

    assert page is fake_page
    assert target_id == "ABC123"
    assert "ABC123" in session.owned_target_ids
    # State file recorded
    import json as _json
    state = _json.loads((tmp_path / "targets.json").read_text())
    assert any("ABC123" in str(v) for v in state.values())


@pytest.mark.anyio
async def test_open_owned_tab_fallback_on_could_not_create(tmp_path):
    """Fallback: new_page() raises 'Could not create a Tab' → am-start path used."""
    from unittest.mock import AsyncMock, MagicMock, patch
    import json as _json

    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"enabled": True}},
        forward_state_file=tmp_path / "fwd.json",
        owned_targets_file=tmp_path / "targets.json",
    )

    # Fake ADB run_adb (do nothing)
    fake_run_adb_calls: list = []

    def fake_run_adb(args, custom_path="", timeout=12.0):
        fake_run_adb_calls.append(args)
        return 0, ""

    # /json/list returns empty before, then one new target after
    list_calls = [0]
    before_resp = _json.dumps([{"id": "PERSONAL_1", "type": "page", "url": "https://example.com"}])
    after_resp = _json.dumps([
        {"id": "PERSONAL_1", "type": "page", "url": "https://example.com"},
        {"id": "NEW_TAB_XYZ", "type": "page", "url": "https://example.com/?_adt_init=aabbcc"},
    ])

    async def fake_httpx_get(self, url, **kw):
        list_calls[0] += 1
        m = MagicMock()
        m.json = lambda: _json.loads(after_resp if list_calls[0] > 1 else before_resp)
        return m

    # Fake page whose targetId matches NEW_TAB_XYZ
    fake_fallback_page = MagicMock()
    fake_fallback_page.url = "https://example.com/?_adt_init=aabbcc"
    fake_cdp = AsyncMock()
    fake_cdp.send = AsyncMock(return_value={"targetInfo": {"targetId": "NEW_TAB_XYZ"}})
    fake_cdp.detach = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(side_effect=Exception("Could not create a Tab"))
    mock_context.new_cdp_session = AsyncMock(return_value=fake_cdp)
    mock_context.pages = [fake_fallback_page]

    session = AndroidCdpSession(
        serial="FAKE002",
        host_port=9223,
        remote_socket="chrome_devtools_remote",
        ws_url="ws://127.0.0.1:9223/devtools/browser",
        browser_version="Chrome/156",
        user_agent="Mozilla/5.0 Android",
        browser=MagicMock(),
        context=mock_context,
        adb_path="",
        _dedicated_device=False,
    )

    with patch("mobile_adb.run_adb", side_effect=fake_run_adb), \
         patch("httpx.AsyncClient.get", new=fake_httpx_get):
        page, target_id = await bridge.open_owned_tab(session)

    assert page is fake_fallback_page
    assert target_id == "NEW_TAB_XYZ"
    assert "NEW_TAB_XYZ" in session.owned_target_ids
    # am start was called
    assert any("am" in str(a) for a in fake_run_adb_calls)


@pytest.mark.anyio
async def test_cleanup_orphaned_targets_prunes_dead_pids(tmp_path):
    """Targets with dead owner PIDs are closed via Target.closeTarget and removed from state."""
    import json as _json

    targets_file = tmp_path / "targets.json"
    targets_file.write_text(_json.dumps({
        "DEAD_TAB_1": {"serial": "SER1", "target_id": "DEAD_TAB_1", "owner_pid": 999991},
        "LIVE_TAB_2": {"serial": "SER1", "target_id": "LIVE_TAB_2", "owner_pid": os.getpid()},
    }))

    bridge = AndroidCdpBridge(
        cfg={"android_cdp": {"enabled": True}},
        forward_state_file=tmp_path / "fwd.json",
        owned_targets_file=targets_file,
    )

    closed_targets: list[str] = []
    fake_b_cdp = AsyncMock()
    async def fake_send(method, params):
        if method == "Target.closeTarget":
            closed_targets.append(params["targetId"])
        return {"success": True}
    fake_b_cdp.send = fake_send
    fake_b_cdp.detach = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_browser_cdp_session = AsyncMock(return_value=fake_b_cdp)

    pruned = await bridge.cleanup_orphaned_targets(mock_browser, "SER1")

    assert pruned == 1
    assert "DEAD_TAB_1" in closed_targets
    state = _json.loads(targets_file.read_text())
    assert "DEAD_TAB_1" not in state
    assert "LIVE_TAB_2" in state
