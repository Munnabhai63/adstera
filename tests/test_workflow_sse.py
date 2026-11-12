"""Tests for WorkflowEventHub, SSE formatting, and live workflow streaming."""
import json
import queue
import time
import pytest

from admin_ui.workflow_events import WorkflowEventHub, get_event_hub, PIPELINE_NODES


def test_event_hub_singleton():
    hub1 = get_event_hub()
    hub2 = WorkflowEventHub()
    assert hub1 is hub2


def test_event_hub_broadcast_and_subscribe():
    hub = get_event_hub()
    q = hub.subscribe()
    try:
        payload = hub.broadcast(
            node_id="A4_VISION",
            status="success",
            message="Found test bbox",
            data={"bbox": [10, 20, 300, 250]},
            run_id="test_run_1",
        )
        assert payload["node_id"] == "A4_VISION"
        assert payload["status"] == "success"
        assert payload["message"] == "Found test bbox"
        assert payload["data"]["bbox"] == [10, 20, 300, 250]

        event = q.get(timeout=2.0)
        assert event["node_id"] == "A4_VISION"
        assert event["run_id"] == "test_run_1"
    finally:
        hub.unsubscribe(q)


def test_sse_formatting():
    data = {"node_id": "CAPTURE", "status": "processing"}
    sse_text = WorkflowEventHub.format_sse(data, event_name="pipeline")
    assert "event: pipeline\n" in sse_text
    assert "data: " in sse_text
    assert '"node_id": "CAPTURE"' in sse_text
    assert sse_text.endswith("\n\n")


def test_history_buffering():
    hub = get_event_hub()
    hub.clear_history()
    hub.broadcast("CAPTURE", "idle", "Ready")
    hub.broadcast("A4_VISION", "processing", "Scanning")
    history = hub.get_history(limit=10)
    assert len(history) == 2
    assert history[0]["node_id"] == "CAPTURE"
    assert history[1]["node_id"] == "A4_VISION"


def test_async_workflow_run():
    hub = get_event_hub()
    q = hub.subscribe()
    try:
        run_id = hub.trigger_run_async(mode="paper", steps=1, domain="test.com", device_id="dev-test")
        assert run_id.startswith("run_")

        # Collect events for at least the start and some nodes
        events = []
        start_time = time.time()
        while time.time() - start_time < 5.0:
            try:
                ev = q.get(timeout=1.0)
                events.append(ev)
                if ev.get("node_id") == "WORKFLOW_FINISH":
                    break
            except queue.Empty:
                break

        node_ids = [e["node_id"] for e in events]
        assert "WORKFLOW_START" in node_ids
        assert "CAPTURE" in node_ids
        assert "A4_VISION" in node_ids
    finally:
        hub.unsubscribe(q)


def test_phase4_server_workflow_endpoints(tmp_path):
    import threading
    import urllib.request
    from admin_ui.phase4_server import create_phase4_server
    from admin_ui.phase4_data import Phase4DashboardConfig

    cfg = Phase4DashboardConfig(
        host="127.0.0.1",
        port=0,
        phase3_db_path=str(tmp_path / "p3.db"),
    )
    server = create_phase4_server(config=cfg, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        host, port = server.server_address[:2]
        base_url = f"http://{host}:{port}"

        # 1. Test /api/phase4/workflow/history
        with urllib.request.urlopen(f"{base_url}/api/phase4/workflow/history", timeout=3.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert isinstance(data["history"], list)

        # 2. Test /api/phase4/workflow/trigger
        req = urllib.request.Request(
            f"{base_url}/api/phase4/workflow/trigger",
            data=json.dumps({"mode": "paper", "steps": 1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            assert resp.status == 200
            trigger_data = json.loads(resp.read().decode("utf-8"))
            assert trigger_data["ok"] is True
            assert trigger_data["mode"] == "paper"
            assert "run_id" in trigger_data

        # 3. Test /api/phase4/live-workflow-stream (read first event)
        with urllib.request.urlopen(f"{base_url}/api/phase4/live-workflow-stream", timeout=4.0) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type
            first_line = resp.readline().decode("utf-8")
            # First line can be 'event: connected' or ': ping'
            assert first_line.startswith("event:") or first_line.startswith(":")
    finally:
        server.shutdown()
        server.server_close()

