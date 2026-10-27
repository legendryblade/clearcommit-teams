"""Desktop entry point for ClearCommit Teams."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .context import build_context
from .paths import PROJECT_ROOT, UI_DIR, display_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clearcommit-teams")
    parser.add_argument("--data-dir", default=None, help="Data folder (must stay inside the project).")
    parser.add_argument("--check", action="store_true", help="Validate the workspace and exit.")
    parser.add_argument("--web", action="store_true", help="Run the loopback development UI instead of the desktop shell.")
    parser.add_argument("--port", type=int, default=8765, help="Port for --web.")
    parser.add_argument("--debug", action="store_true", help="Open the webview with developer tools.")
    parser.add_argument("--version", action="version", version=f"ClearCommit Teams {__version__}")
    return parser


def _launch_webview(context, debug: bool) -> int:
    try:
        import webview  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on desktop runtime
        print(
            "ClearCommit Teams could not load pywebview. Run 'pip install -r requirements.txt' "
            "or use --web for the local browser UI.",
            file=sys.stderr,
        )
        return 1

    index = UI_DIR / "index.html"
    if not index.exists():
        print(f"UI files are missing: {index}", file=sys.stderr)
        return 1

    webview_storage = context.data_dir / "webview2"
    webview_storage.mkdir(parents=True, exist_ok=True)
    # Keep WebView2's profile/cache inside this project as well.
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(webview_storage))

    window = webview.create_window(
        "ClearCommit Teams",
        url=index.as_uri(),
        js_api=context.bridge,
        width=1460,
        height=940,
        min_size=(1120, 720),
        background_color="#f5f3ee",
        text_select=True,
        confirm_close=False,
        easy_drag=False,
    )
    webview.start(
        debug=debug,
        private_mode=False,
        storage_path=str(webview_storage),
    )
    return 0


def _env_candidates() -> list[Path]:
    """Every place a local .env may legitimately live, nearest first.

    Inside a PyInstaller bundle ``__file__`` points into the extracted
    ``_internal`` folder, so ``parent.parent`` is NOT the checkout — it is the
    dist folder next to the exe. That silently stranded the API keys and left
    live capture transcribing nothing. Search the exe/folder the user actually
    launched (and its ancestors) before falling back to the source layout.
    """
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        roots.extend([exe.parent, *exe.parent.parents])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.extend([Path(meipass).resolve(), *Path(meipass).resolve().parents])
    else:
        roots.append(PROJECT_ROOT.resolve())

    candidates: list[Path] = []
    for root in roots:
        path = root / ".env"
        if path not in candidates:
            candidates.append(path)
    return candidates


def _load_local_env() -> list[Path]:
    """Load the first .env that exists so provider keys reach the desktop app."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []
    loaded: list[Path] = []
    for env_path in _env_candidates():
        if env_path.is_file() and load_dotenv(env_path, override=False):
            loaded.append(env_path)
            break
    return loaded


def main(argv: list[str] | None = None) -> int:
    _load_local_env()
    args = _parser().parse_args(argv)
    try:
        context = build_context(args.data_dir)
    except Exception as exc:
        print(f"ClearCommit Teams could not open its workspace: {exc}", file=sys.stderr)
        return 1

    if args.check:
        payload = {
            "ok": True,
            "name": "ClearCommit Teams",
            "version": __version__,
            "project_root": str(PROJECT_ROOT),
            "data_dir": str(context.data_dir),
            "database": str(context.db.path),
            "counts": context.db.counts(),
            "provider": context.bridge._provider_status_payload(),
            "ui": str(UI_DIR / "index.html"),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.web:
        from .devserver import make_server

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

    return _launch_webview(context, args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
