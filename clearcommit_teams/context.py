"""Application context assembly used by the desktop shell, dev server, and tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .bridge import Bridge
from .coaching import CoachingService
from .db import Database
from .demo_data import seed_samples
from .paths import database_path, ensure_data_dir, workspace_dir
from .repository import Repository


@dataclass
class AppContext:
    data_dir: Path
    db: Database
    repo: Repository
    service: CoachingService
    bridge: Bridge


def _samples_enabled(env: Mapping[str, str] | None) -> bool:
    """Sample conversations are opt-in; a real workspace starts empty."""
    source = (env or os.environ).get("CLEARCOMMIT_TEAMS_SEED_SAMPLES", "")
    return source.strip().lower() in {"1", "true", "yes", "on"}


def build_context(
    data_dir: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    provider_factory: Callable | None = None,
) -> AppContext:
    base_dir = ensure_data_dir(data_dir)
    # Personal data is scoped per account. The app opens in the guest
    # workspace, which stays usable before sign-in and offline; signing in
    # switches to that account's own folder via the bridge.
    resolved = workspace_dir(base_dir, None)
    resolved.mkdir(parents=True, exist_ok=True)
    db = Database(database_path(resolved))
    db.initialize()
    if _samples_enabled(env):
        seed_samples(db)
    repo = Repository(db)
    service = CoachingService(repo, provider_factory=provider_factory, env=env)
    bridge = Bridge(repo, service, resolved, base_data_dir=base_dir)
    context = AppContext(
        data_dir=base_dir,
        db=db,
        repo=repo,
        service=service,
        bridge=bridge,
    )
    return context
