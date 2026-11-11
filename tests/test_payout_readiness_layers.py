"""
tests/test_payout_readiness_layers.py — Targeted verification for Adsterra payout & ADB IP-rotation layers.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
import yaml
import pytest

import db
import ecpm_feedback
from ecpm_feedback import EcpmFeedbackEngine
from failover_manager import DualTransportManager
import fingerprint as fp_mod
from lead_engine import LeadConversionEngine
import mobile_adb
from pool import GeoInfo, MobileTetherPool, Proxy


def test_mobile_tether_refuses_host_fallback_on_adb_failure(monkeypatch):
    async def _run():
        host_probe_calls = []

        def _fake_rotate(dev_id="", wait_seconds=4.0, custom_path=""):
            return (False, "", "", "No Android devices connected")

        def _fake_ip(timeout=6.0):
            host_probe_calls.append(timeout)
            return {"ip": "203.0.113.99", "country": "IN"}

        monkeypatch.setattr(mobile_adb, "rotate_ip", _fake_rotate)
        monkeypatch.setattr(mobile_adb, "get_public_ip", _fake_ip)

        pool = MobileTetherPool({"network": {"mode": "mobile_tether", "require_ip_rotation": True}})
        proxy = await pool.acquire()
        assert proxy is None
        assert host_probe_calls == []

    asyncio.run(_run())


def test_mobile_tether_retries_unchanged_ip_then_succeeds(monkeypatch):
    async def _run():
        attempts = {"n": 0}

        def _fake_rotate(dev_id="", wait_seconds=4.0, custom_path=""):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return (True, "106.10.10.1", "106.10.10.1", "unchanged")
            return (True, "106.10.10.1", "106.10.20.2", "rotated")

        def _fake_ip(timeout=6.0):
            ip = "106.10.10.1" if attempts["n"] == 1 else "106.10.20.2"
            return {"ip": ip, "country": "IN", "region": "Maharashtra", "city": "Mumbai", "org": "Jio"}

        monkeypatch.setattr(mobile_adb, "rotate_ip", _fake_rotate)
        monkeypatch.setattr(mobile_adb, "get_public_ip", _fake_ip)

        pool = MobileTetherPool({
            "network": {
                "mode": "mobile_tether",
                "airplane_mode_wait": 0.0,
                "require_ip_rotation": True,
                "max_rotation_attempts": 2,
                "reconnect_polls": 1,
                "reconnect_poll_interval": 0.0,
            }
        })
        proxy = await pool.acquire()
        assert proxy is not None
        assert proxy.host == "106.10.20.2"
        assert proxy.geo.country == "IN"
        assert attempts["n"] == 2

    asyncio.run(_run())


def test_mobile_tether_returns_none_when_ip_never_rotates(monkeypatch):
    async def _run():
        monkeypatch.setattr(
            mobile_adb, "rotate_ip",
            lambda dev_id="", wait_seconds=4.0, custom_path="": (True, "106.1.1.1", "106.1.1.1", "stuck"),
        )
        monkeypatch.setattr(
            mobile_adb, "get_public_ip",
            lambda timeout=6.0: {"ip": "106.1.1.1", "country": "IN"},
        )

        pool = MobileTetherPool({
            "network": {
                "mode": "mobile_tether",
                "airplane_mode_wait": 0.0,
                "require_ip_rotation": True,
                "max_rotation_attempts": 2,
                "reconnect_polls": 0,
            }
        })
        proxy = await pool.acquire()
        assert proxy is None

    asyncio.run(_run())


def test_mobile_tether_reconnect_poll_and_missing_adb_and_unverified_baseline(monkeypatch):
    async def _run():
        # 1a. Reconnect timeout from rotate_ip + delayed IP recovery via reconnect_polls succeeds on attempt 1
        rotate_calls = {"n": 0}
        ip_calls = {"n": 0}

        def _rotate_timeout_then_ok(dev_id="", wait_seconds=4.0, custom_path=""):
            rotate_calls["n"] += 1
            if rotate_calls["n"] == 1:
                return (False, "106.10.10.1", "", "Network did not reconnect after airplane mode toggle")
            return (True, "106.10.10.1", "106.10.20.2", "ok")

        def _delayed_public_ip(timeout=6.0):
            ip_calls["n"] += 1
            if ip_calls["n"] <= 2:
                return {"ip": "", "ok": False}
            return {"ip": "106.10.20.2", "country": "IN", "region": "MH", "city": "Mumbai", "org": "Jio", "ok": True}

        monkeypatch.setattr(mobile_adb, "rotate_ip", _rotate_timeout_then_ok)
        monkeypatch.setattr(mobile_adb, "get_public_ip", _delayed_public_ip)

        pool = MobileTetherPool({
            "network": {
                "mode": "mobile_tether",
                "airplane_mode_wait": 0.0,
                "require_ip_rotation": True,
                "max_rotation_attempts": 2,
                "reconnect_polls": 2,
                "reconnect_poll_interval": 0.0,
            }
        })
        px = await pool.acquire()
        assert px is not None and px.host == "106.10.20.2"
        assert rotate_calls["n"] == 1
        assert ip_calls["n"] == 3

        # 1b. When all reconnect_polls on attempt 1 remain empty, attempt 2 runs and recovers
        rotate_calls["n"] = 0
        ip_calls["n"] = 0

        def _delayed_until_attempt2(timeout=6.0):
            ip_calls["n"] += 1
            if rotate_calls["n"] < 2:
                return {"ip": "", "ok": False}
            return {"ip": "106.10.30.3", "country": "IN", "region": "MH", "city": "Mumbai", "org": "Jio", "ok": True}

        monkeypatch.setattr(mobile_adb, "get_public_ip", _delayed_until_attempt2)
        pool_retry = MobileTetherPool({
            "network": {
                "mode": "mobile_tether",
                "airplane_mode_wait": 0.0,
                "require_ip_rotation": True,
                "max_rotation_attempts": 2,
                "reconnect_polls": 1,
                "reconnect_poll_interval": 0.0,
            }
        })
        px2 = await pool_retry.acquire()
        assert px2 is not None and px2.host == "106.10.30.3"
        assert rotate_calls["n"] == 2

        # 2. Missing adb.exe raises FileNotFoundError in get_adb_path -> run_adb and pool.acquire handle safely
        monkeypatch.undo()
        monkeypatch.setattr(mobile_adb, "get_adb_path", lambda custom_path="": (_ for _ in ()).throw(FileNotFoundError("no adb")))
        code, msg = mobile_adb.run_adb(["devices"])
        assert code == -1 and "no adb" in msg

        monkeypatch.setattr(mobile_adb, "rotate_ip", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("no adb")))
        pool_no_adb = MobileTetherPool({"network": {"mode": "mobile_tether"}})
        assert await pool_no_adb.acquire() is None

        # 3. Empty pre-toggle old_ip must NOT bypass require_ip_rotation on stationary IP
        monkeypatch.setattr(mobile_adb, "rotate_ip", lambda *a, **kw: (True, "", "203.0.113.55", "no old ip"))
        monkeypatch.setattr(mobile_adb, "get_public_ip", lambda timeout=6.0: {"ip": "203.0.113.55", "country": "IN", "ok": True})
        pool_stuck = MobileTetherPool({
            "network": {
                "mode": "mobile_tether",
                "airplane_mode_wait": 0.0,
                "require_ip_rotation": True,
                "max_rotation_attempts": 2,
                "reconnect_polls": 0,
            }
        })
        assert await pool_stuck.acquire() is None

    asyncio.run(_run())


def test_proxy_url_encodes_credentials_and_failover_blocks_local_direct():
    px = Proxy(host="gw.example.com", port=10000, username="user@name", password="pa:ss/1")
    assert px.proxy_url == "http://user%40name:pa%3Ass%2F1@gw.example.com:10000"

    async def _run():
        mgr = DualTransportManager({"failover": {"enabled": True}})
        mgr.set_sub_pools(mobile_pool=None, proxy_pool=None)
        assert await mgr.acquire_transport() is None

        mgr_opt_in = DualTransportManager({"failover": {"enabled": True, "allow_local_direct_fallback": True}})
        mgr_opt_in.set_sub_pools(mobile_pool=None, proxy_pool=None)
        direct = await mgr_opt_in.acquire_transport()
        assert direct is not None and direct.host == "127.0.0.1"

    asyncio.run(_run())


def test_ecpm_feedback_numeric_domain_id_and_singular_impression(tmp_path, monkeypatch):
    monkeypatch.setattr(ecpm_feedback, "STATE_FILE", tmp_path / "dynamic_ecpm_weights.json")
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test_ecpm_numeric.db")
    db.init()

    isolated_cfg = {
        "target": {
            "domains": [
                {"domain": "rechargetak.com", "target_cpm": 3.0},
                {"domain": "karzseva.com", "target_cpm": 2.5},
            ]
        }
    }
    engine = EcpmFeedbackEngine(config=isolated_cfg)
    engine.api_client.fetch_daily_stats = AsyncMock(return_value={
        "status": "ok",
        "items": [
            {"domain": 6190678, "impression": 40, "cpm": 0.12, "revenue": 0.005},
            {"domain": "unconfigured-other.com", "impression": 500, "cpm": 99.0, "revenue": 49.5},
        ],
    })

    weights = asyncio.run(engine.fetch_and_update_weights(force_mock=False))
    assert set(weights.keys()) == {"rechargetak.com", "karzseva.com"}
    saved = json.loads((tmp_path / "dynamic_ecpm_weights.json").read_text(encoding="utf-8"))
    assert saved["top_domain"] == "rechargetak.com"
    assert saved["ecpms"]["rechargetak.com"] == 0.12
    assert saved["ecpms"]["karzseva.com"] == round(0.12 * 0.8, 4)

    # Zero-CPM with positive revenue+impressions uses rev/imps*1000 fallback
    engine.api_client.fetch_daily_stats = AsyncMock(return_value={
        "status": "ok",
        "items": [
            {"domain": "karzseva.com", "impression": 500, "cpm": 0.0, "revenue": 0.50},
            {"domain": 6190678, "impression": 100, "cpm": 0.20, "revenue": 0.0},
            {"domain": 6190678, "impression": 50, "cpm": 0.0, "revenue": 0.0},
        ],
    })
    asyncio.run(engine.fetch_and_update_weights(force_mock=False))
    saved2 = json.loads((tmp_path / "dynamic_ecpm_weights.json").read_text(encoding="utf-8"))
    assert saved2["ecpms"]["karzseva.com"] == 1.0
    assert saved2["ecpms"]["rechargetak.com"] == 0.2


def test_payout_safety_config_and_lead_skip():
    import random
    import cpa_stacker

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert cfg["network"]["mode"] == "mobile_tether"
    assert cfg["network"]["require_ip_rotation"] is True
    assert cfg["browser"]["block_resources"] == []
    assert cfg["payout_safety"]["solo_network"] == "adsterra"
    assert cfg["payout_safety"]["skip_cpa_stacking"] is True
    assert cfg["lead_engine"]["enabled"] is True
    assert cfg["lead_engine"]["payout_safe_skip_submit"] is True

    assert cpa_stacker.should_attempt_cpa(
        random.Random(1),
        {"cpa_stacking": {"enabled": True, "attempt_prob": 1.0}, "payout_safety": {"skip_cpa_stacking": True}},
        proxy_id="p1",
    ) is False

    engine = LeadConversionEngine()
    assert engine.enabled is True
    assert engine.payout_safe_skip_submit is True


def test_fingerprint_screen_prototype_and_chrome_native():
    from playwright.async_api import async_playwright

    async def _run():
        proxy = Proxy(
            host="106.20.30.40",
            port=0,
            geo=GeoInfo(country="IN", region="MH", city="Mumbai", timezone="Asia/Kolkata", locale="en-IN"),
        )
        fp = fp_mod.build(proxy, force_mobile=True)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_init_script(fp_mod.init_script(fp))
            page = await context.new_page()
            res = await page.evaluate("""() => ({
                ownColor: Object.prototype.hasOwnProperty.call(screen, 'colorDepth'),
                ownAvailH: Object.prototype.hasOwnProperty.call(screen, 'availHeight'),
                protoColorNative: Object.getOwnPropertyDescriptor(Screen.prototype, 'colorDepth').get.toString().includes('[native code]'),
                protoAvailHNative: Object.getOwnPropertyDescriptor(Screen.prototype, 'availHeight').get.toString().includes('[native code]'),
                csiNative: window.chrome.csi.toString().includes('[native code]'),
                loadTimesNative: window.chrome.loadTimes.toString().includes('[native code]'),
                mobSendNative: window.chrome.runtime.sendMessage.toString().includes('[native code]'),
                mobConnNative: window.chrome.runtime.connect.toString().includes('[native code]'),
                colorDepthVal: screen.colorDepth
            })""")
            await browser.close()

        assert res["ownColor"] is False
        assert res["ownAvailH"] is False
        assert res["protoColorNative"] is True
        assert res["protoAvailHNative"] is True
        assert res["csiNative"] is True
        assert res["loadTimesNative"] is True
        assert res["mobSendNative"] is True
        assert res["mobConnNative"] is True
        assert res["colorDepthVal"] == 24

    asyncio.run(_run())


def test_worker_solo_network_and_skip_lead_submit(tmp_path, monkeypatch):
    from playwright.async_api import async_playwright
    import random
    import persist
    import worker

    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test_worker_solo.db")
    monkeypatch.setattr(persist, "_STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(worker, "ACTIVE_UA_PATH", tmp_path / "state" / "active_ua.json")
    db.init()

    submit_calls = []

    async def _fail_if_called(self, *args, **kwargs):
        submit_calls.append(True)
        return {"submitted": True}

    monkeypatch.setattr(LeadConversionEngine, "fill_and_submit_lead", _fail_if_called)

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    cfg["target"]["min_dwell"] = 1
    cfg["target"]["max_dwell"] = 2
    cfg["target"]["scroll_prob"] = 0.0
    cfg["target"]["click_prob"] = 1.0
    cfg["session"]["page_depth_max"] = 1
    cfg["session"]["internal_nav_prob"] = 0.0
    cfg["ab_testing"] = {"enabled": False}
    cfg["push_notifications"] = {"enabled": False}
    cfg["stats_csv_path"] = ""
    cfg["payout_safety"] = {"solo_network": "adsterra", "skip_lead_form_submit": True}
    cfg["lead_engine"]["payout_safe_skip_submit"] = False

    async def _run():
        proxy = Proxy(
            host="106.20.30.50",
            port=0,
            geo=GeoInfo(country="IN", region="MH", city="Mumbai", timezone="Asia/Kolkata", locale="en-IN"),
        )
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                res = await worker.run_session(pw, browser, proxy, cfg, random.Random(7), use_fixture=True)
            finally:
                await browser.close()

        assert res["status"] == "ok"
        assert res["ad_network"] == "adsterra"
        assert submit_calls == []

    asyncio.run(_run())

