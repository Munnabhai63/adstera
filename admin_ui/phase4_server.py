"""Phase 4 Autonomous Farm & AI Ops HTTP Dashboard Server."""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from admin_ui.phase4_data import (
    Phase4DashboardConfig,
    Phase4DashboardReader,
    load_phase4_config,
)
from admin_ui.views.phase4_farm import render_phase4_dashboard_page

logger = logging.getLogger("admin_ui.phase4_server")

ASSETS_ROOT = (Path(__file__).resolve().parent / "assets").resolve()

_MIME_OVERRIDES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def resolve_safe_asset_path(
    url_path: str,
    assets_root: Path = ASSETS_ROOT,
) -> Optional[Path]:
    """Resolve ``/crm-assets/<rel>`` safely under *assets_root*, blocking traversal."""
    decoded = unquote(url_path)
    if "\x00" in decoded or "\\" in decoded:
        return None
    if not decoded.startswith("/crm-assets/"):
        return None
    rel = decoded[len("/crm-assets/") :]
    if not rel or rel.startswith("/"):
        return None
    parts = [p for p in rel.split("/") if p]
    if any(part in ("..", ".") for part in parts):
        return None

    root_resolved = assets_root.resolve()
    candidate = (root_resolved / Path(*parts)).resolve()
    try:
        if not candidate.is_relative_to(root_resolved):
            return None
    except AttributeError:  # pragma: no cover
        if root_resolved not in candidate.parents and candidate != root_resolved:
            return None
    if not candidate.is_file():
        return None
    return candidate


class Phase4HTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying Phase 4 dashboard config & SQLite reader."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        reader: Phase4DashboardReader,
        assets_root: Path = ASSETS_ROOT,
    ) -> None:
        self.reader = reader
        self.assets_root = assets_root.resolve()
        super().__init__(server_address, Phase4RequestHandler)


class Phase4RequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for Phase 4 Vuexy dashboard, JSON APIs, and safe static assets."""

    server: Phase4HTTPServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("phase4_http %s - %s", self.address_string(), format % args)

    def _send_bytes(
        self,
        status_code: int,
        content_type: str,
        payload: bytes,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self._send_bytes(status_code, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        req_path = parsed.path

        if req_path in ("/", "/index.html"):
            html = render_phase4_dashboard_page(
                refresh_interval_ms=self.server.reader.config.refresh_interval_ms
            )
            self._send_bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
            return

        if req_path == "/api/phase4/dashboard":
            payload = self.server.reader.get_dashboard_snapshot()
            status_code = 200 if payload.get("ok") else 503
            self._send_json(status_code, payload)
            return

        if req_path == "/api/phase4/health":
            snap = self.server.reader.get_dashboard_snapshot()
            db_status = str(snap.get("db_status", "error"))
            is_unhealthy = db_status in ("locked", "missing", "error") or not snap.get("ok")
            health = {
                "ok": not is_unhealthy,
                "service": "phase4_dashboard",
                "db_ok": bool(snap.get("ok")),
                "db_status": db_status,
                "error": snap.get("error", ""),
                "phase3_db_path": self.server.reader.config.phase3_db_path,
                "safe_mode_active": bool(
                    (snap.get("kpis") or {}).get("safe_mode", {}).get("active", False)
                ),
                "generated_at": snap.get("generated_at", ""),
            }
            self._send_json(503 if is_unhealthy else 200, health)
            return

        if req_path.startswith("/crm-assets/"):
            asset_path = resolve_safe_asset_path(req_path, self.server.assets_root)
            if asset_path is None:
                self._send_json(404, {"ok": False, "error": "Asset not found"})
                return
            ext = asset_path.suffix.lower()
            ctype = _MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
            data = asset_path.read_bytes()
            self._send_bytes(200, ctype, data, cache_control="public, max-age=300")
            return

        self._send_json(404, {"ok": False, "error": f"Route not found: {req_path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        req_path = parsed.path

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length > 0:
            self.rfile.read(length)

        if req_path == "/api/phase4/calibration/run":
            try:
                from phase3.calibration.monitor import CalibrationMonitor

                cfg = self.server.reader.config
                monitor = CalibrationMonitor(
                    db_path=cfg.phase3_db_path,
                    legacy_db_path=cfg.legacy_db_path,
                )
                report = monitor.run_check()
                self._send_json(200, {"ok": True, "report": report})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(404, {"ok": False, "error": f"Route not found: {req_path}"})


def create_phase4_server(
    *,
    config: Optional[Phase4DashboardConfig] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    assets_root: Path = ASSETS_ROOT,
) -> Phase4HTTPServer:
    """Instantiate a configured ``Phase4HTTPServer`` (pass ``port=0`` for ephemeral port)."""
    cfg = config or load_phase4_config()
    bind_host = host if host is not None else cfg.host
    bind_port = port if port is not None else cfg.port
    reader = Phase4DashboardReader(cfg)
    return Phase4HTTPServer((bind_host, int(bind_port)), reader=reader, assets_root=assets_root)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint: ``python -m admin_ui.phase4_server``."""
    parser = argparse.ArgumentParser(description="Phase 4 Vuexy Dashboard Server")
    parser.add_argument("--config", default=None, help="Path to phase4_config.yaml")
    parser.add_argument("--host", default=None, help="Bind host override")
    parser.add_argument("--port", type=int, default=None, help="Bind port override")
    args = parser.parse_args(argv)

    cfg = load_phase4_config(args.config)
    server = create_phase4_server(config=cfg, host=args.host, port=args.port)
    bound_host, bound_port = server.server_address[:2]
    print(f"Phase 4 Dashboard listening on http://{bound_host}:{bound_port}")

    def _handle_signal(signum: int, _frame: Any) -> None:
        logger.info("Received signal %s, shutting down Phase 4 Dashboard...", signum)
        server.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
