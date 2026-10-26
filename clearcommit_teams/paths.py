"""Project-confined paths.

All application writes are required to resolve inside this project's root.
This is a deliberate isolation boundary: the original ClearCommit checkout is
never imported or written, and an externally supplied data directory is
refused rather than silently accepted.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .errors import PathConfinementError

_FROZEN = bool(getattr(sys, "frozen", False))

if _FROZEN:
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    UI_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "ui"
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    UI_DIR = PROJECT_ROOT / "ui"

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DATA_ENV_VAR = "CLEARCOMMIT_TEAMS_DATA_DIR"


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_data_dir(raw: str | os.PathLike | None = None) -> Path:
    """Resolve the data directory and refuse anything outside the project.

    Resolution order: explicit argument, environment variable, default.
    Relative paths are resolved against the project root.
    """
    source = raw if raw not in (None, "") else os.environ.get(DATA_ENV_VAR)
    candidate = Path(source) if source not in (None, "") else DEFAULT_DATA_DIR
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.expanduser().resolve()
    root = PROJECT_ROOT.resolve()
    if not _inside(resolved, root):
        raise PathConfinementError(
            "The workspace data folder must stay inside the ClearCommit Teams project.",
            detail={"data_dir": str(resolved), "project_root": str(root)},
        )
    return resolved


def ensure_data_dir(raw: str | os.PathLike | None = None) -> Path:
    data_dir = resolve_data_dir(raw)
    data_dir.mkdir(parents=True, exist_ok=True)
    if not _inside(data_dir.resolve(), PROJECT_ROOT.resolve()):
        raise PathConfinementError("The workspace data folder escaped the project root.")
    return data_dir


def database_path(data_dir: Path) -> Path:
    resolved = (data_dir / "clearcommit-teams.db").resolve()
    if not _inside(resolved, PROJECT_ROOT.resolve()):
        raise PathConfinementError("The workspace database must stay inside the project.")
    return resolved


WORKSPACES_DIR_NAME = "workspaces"
_SAFE_WORKSPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def workspace_dir(base: Path, account_key: str | None) -> Path:
    """Directory for one account's personal workspace.

    ``account_key`` is a stable, non-secret identifier (never an email or a
    token). ``None`` selects the guest workspace used before sign-in, so the
    app stays usable offline. Every result stays inside the project root.
    """
    key = "guest" if not account_key else str(account_key)
    if not _SAFE_WORKSPACE.match(key):
        raise PathConfinementError(
            "Workspace identifiers may only contain letters, digits, dot, dash and underscore.",
            detail={"account_key": key},
        )
    resolved = (base / WORKSPACES_DIR_NAME / key).resolve()
    if not _inside(resolved, PROJECT_ROOT.resolve()):
        raise PathConfinementError("The workspace folder must stay inside the project.")
    return resolved


def assert_write_allowed(path: str | os.PathLike) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not _inside(resolved, PROJECT_ROOT.resolve()):
        raise PathConfinementError(
            "Writes are restricted to the ClearCommit Teams project folder.",
            detail={"path": str(resolved)},
        )
    return resolved


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
