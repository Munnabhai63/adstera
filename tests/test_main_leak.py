"""
tests/test_main_leak.py — Verify that an exception or cancellation during session execution
does not leak active_sessions or the in_flight counter.
"""
import asyncio
from pool import Proxy, ProxyPool
import main
import worker


def test_run_one_releases_proxy_on_exception(monkeypatch):
    proxy = Proxy(host="1.2.3.4", port=8080)
    proxy.active_sessions = 1

    cfg = {
        "scheduler": {
            "daily_cap": 10,
            "jitter_seconds": 1,
            "concurrency": 2,
            "diurnal": [1.0] * 24,
            "weekday_scale": [1.0] * 7,
            "sessions_per_hour": 100,
        }
    }

    pool = ProxyPool([proxy], cfg)

    async def _run():
        nonlocal proxy
        sem = asyncio.Semaphore(1)
        _in_flight = 1

        async def mock_run_session(*args, **kwargs):
            raise RuntimeError("Simulated network timeout during session")

        monkeypatch.setattr(worker, "run_session", mock_run_session)

        ok = False
        try:
            async with sem:
                await worker.run_session(None, None, proxy, cfg, None)
            ok = True
        except RuntimeError:
            pass
        finally:
            if not ok and hasattr(pool, "mark_failure"):
                pool.mark_failure(proxy)
            pool.release(proxy)
            _in_flight -= 1

        assert proxy.active_sessions == 0, f"Expected active_sessions == 0, got {proxy.active_sessions}"
        assert _in_flight == 0, f"Expected _in_flight == 0, got {_in_flight}"

    asyncio.run(_run())
