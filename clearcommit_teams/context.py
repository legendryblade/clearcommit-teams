"""Application context assembly used by the desktop shell, dev server, and tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .bridge import Bridge
from .coaching import CoachingService
from .db import Database
from .demo_data import seed_samples
from .paths import database_path, ensure_data_dir
from .repository import Repository


@dataclass
class AppContext:
    data_dir: Path
    db: Database
    repo: Repository
    service: CoachingService
    bridge: Bridge


def build_context(
    data_dir: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    provider_factory: Callable | None = None,
) -> AppContext:
    resolved = ensure_data_dir(data_dir)
    db = Database(database_path(resolved))
    db.initialize()
    seed_samples(db)
    repo = Repository(db)
    service = CoachingService(repo, provider_factory=provider_factory, env=env)
    bridge = Bridge(repo, service, resolved)
    return AppContext(
        data_dir=resolved,
        db=db,
        repo=repo,
        service=service,
        bridge=bridge,
    )
