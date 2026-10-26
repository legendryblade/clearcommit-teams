"""Run the ClearCommit Teams backend: python -m server"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from .config import ConfigError, load_settings
from .main import create_app


def _load_local_env() -> None:
    """Load .env from the project root if python-dotenv is available.

    Real environment variables always win; this only fills the gaps so the
    documented `python -m server` works straight after writing a .env.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _load_local_env()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"ClearCommit Teams server cannot start: {exc}", file=sys.stderr)
        return 1

    app = create_app(settings)
    # Hosting platforms inject $PORT and expect a 0.0.0.0 bind. Explicit
    # CLEARCOMMIT_* values still win so local use is unchanged.
    host = os.environ.get("CLEARCOMMIT_SERVER_HOST") or (
        "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    )
    port = int(
        os.environ.get("CLEARCOMMIT_SERVER_PORT")
        or os.environ.get("PORT")
        or "8770"
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
