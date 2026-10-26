"""Local development / UI-smoke HTTP server.

This is not the desktop shell. It serves the same HTML and calls the same
Python Bridge so browser-based tests exercise the real backend. It binds to
loopback only and exposes only the bridge's public methods.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .bridge import public_method_names
from .context import build_context
from .paths import UI_DIR

MAX_BODY = 3 * 1024 * 1024


class DevHandler(SimpleHTTPRequestHandler):
    bridge = None  # set by make_server

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(UI_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self' http://127.0.0.1:8770 "
            "http://localhost:8770 ws://127.0.0.1:8770 ws://localhost:8770 "
            "https://*.supabase.co; "
            "frame-ancestors 'none'",
        )
        super().end_headers()

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        method = self.path[len("/api/"):].split("?", 1)[0]
        if method not in public_method_names():
            self._json({"ok": False, "error": {
                "code": "unknown_method",
                "message": "That bridge method is not available.",
                "retryable": False,
            }}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._json({"ok": False, "error": {
                "code": "payload_too_large",
                "message": "The request is too large.",
                "retryable": False,
            }}, status=413)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            self._json({"ok": False, "error": {
                "code": "invalid_json",
                "message": "The request body was not valid JSON.",
                "retryable": False,
            }}, status=400)
            return
        handler = getattr(self.bridge, method)
        envelope = handler(payload)
        self._json(envelope, status=200 if envelope.get("ok") else 200)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        if sys.stderr is not None:
            sys.stderr.write("[dev] " + (fmt % args) + "\n")


def make_server(port: int, bridge, directory: Path = UI_DIR) -> ThreadingHTTPServer:
    handler = type("BoundDevHandler", (DevHandler,), {"bridge": bridge})
    server = ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **kw: handler(*a, directory=str(directory), **kw))
    return server


def _load_local_env() -> None:
    """Load .env from the project root so provider keys are available.

    Missing python-dotenv or a missing file is not an error: the app runs
    without live transcription rather than failing to start.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def main(argv: list[str] | None = None) -> int:
    _load_local_env()
    parser = argparse.ArgumentParser(description="ClearCommit Teams local UI server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)
    context = build_context(args.data_dir)
    server = make_server(args.port, context.bridge)
    print(f"ClearCommit Teams dev UI: http://127.0.0.1:{server.server_port}/")
    print("Loopback only. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
