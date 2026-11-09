"""
tests/test_session_tracer.py — Step 5.1: Playwright Session Trace Recording & Replay Tests

Covers:
1. SessionTracer initialization and enabled flag from config
2. tracer.start() and tracer.stop() lifecycle
3. Trace is NOT saved if status == 'ok'
4. Trace IS saved if status == 'degraded'
5. Trace auto-rotation when exceeding max_traces
6. list_traces() metadata inspection
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_tracer


def test_tracer_config_toggle():
    """Tracer respects debug_traces configuration toggle."""
    cfg_disabled = {"debug_traces": False, "max_traces": 10}
    t_off = session_tracer.build_from_config(cfg_disabled, "proxy_1")
    assert not t_off.enabled

    cfg_enabled = {"debug_traces": True, "max_traces": 25}
    t_on = session_tracer.build_from_config(cfg_enabled, "proxy_2")
    assert t_on.enabled
    assert t_on.max_traces == 25
    print("  [OK] Tracer configuration toggle verified")


def test_tracer_lifecycle_no_save_on_ok():
    """Tracer discards trace when session status is 'ok'."""
    mock_context = AsyncMock()
    mock_context.tracing = AsyncMock()

    t = session_tracer.SessionTracer(cfg={"debug_traces": True}, proxy_id="proxy_ok")

    async def _run():
        await t.start(mock_context)
        assert t._started
        path = await t.stop(mock_context, status="ok")
        return path

    result_path = asyncio.run(_run())
    assert result_path is None
    mock_context.tracing.stop.assert_called_once_with()
    print("  [OK] Trace discarded on status='ok'")


def test_tracer_lifecycle_saves_on_degraded():
    """Tracer saves zip trace when session status is 'degraded'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = session_tracer.TRACES_DIR
        session_tracer.TRACES_DIR = Path(tmpdir)
        try:
            mock_context = AsyncMock()
            mock_context.tracing = AsyncMock()

            # Emulate trace writing on stop(path=...)
            async def mock_stop(path=None):
                if path:
                    Path(path).write_bytes(b"PK\x03\x04mock_trace_bytes")

            mock_context.tracing.stop.side_effect = mock_stop

            t = session_tracer.SessionTracer(
                cfg={"debug_traces": True, "max_traces": 10},
                proxy_id="user:pass@1.2.3.4:8080",
            )

            async def _run():
                await t.start(mock_context)
                return await t.stop(mock_context, status="degraded")

            saved_path = asyncio.run(_run())
            assert saved_path is not None
            assert saved_path.exists()
            assert saved_path.suffix == ".zip"
            assert "1_2_3_4_8080" in saved_path.name

            # Test list_traces
            traces = session_tracer.list_traces()
            assert len(traces) == 1
            assert traces[0]["filename"] == saved_path.name
            print(f"  [OK] Trace saved on status='degraded' -> {saved_path.name}")
        finally:
            session_tracer.TRACES_DIR = original_dir


def test_tracer_rotation():
    """Tracer removes older traces beyond max_traces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = session_tracer.TRACES_DIR
        session_tracer.TRACES_DIR = Path(tmpdir)
        try:
            # Create 5 dummy files
            for i in range(5):
                f = session_tracer.TRACES_DIR / f"session_test_{i}_100{i}.zip"
                f.write_text("dummy")

            t = session_tracer.SessionTracer(
                cfg={"debug_traces": True, "max_traces": 3},
                proxy_id="test_rotate",
            )
            t._rotate_old_traces()

            remaining = list(session_tracer.TRACES_DIR.glob("session_*.zip"))
            assert len(remaining) == 3, f"Expected 3 traces after rotation, got {len(remaining)}"
            print(f"  [OK] Trace rotation pruned to {len(remaining)} items")
        finally:
            session_tracer.TRACES_DIR = original_dir


if __name__ == "__main__":
    test_tracer_config_toggle()
    test_tracer_lifecycle_no_save_on_ok()
    test_tracer_lifecycle_saves_on_degraded()
    test_tracer_rotation()
    print("\nAll session tracer tests PASSED!")
