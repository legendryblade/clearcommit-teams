"""Run the ClearCommit Teams backend: python -m server"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from .config import ConfigError, load_settings
from .main import create_app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"ClearCommit Teams server cannot start: {exc}", file=sys.stderr)
        return 1

    app = create_app(settings)
    host = os.environ.get("CLEARCOMMIT_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("CLEARCOMMIT_SERVER_PORT", "8770"))
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
