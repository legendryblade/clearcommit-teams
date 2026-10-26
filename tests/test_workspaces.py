"""Per-account local workspaces.

Personal data is scoped by account so two people on one PC do not share a
workspace, and joining a company never publishes what is stored locally.
"""

from __future__ import annotations

from clearcommit_teams.errors import PathConfinementError
from clearcommit_teams.paths import DEFAULT_DATA_DIR, workspace_dir


def _sessions(ctx) -> int:
    return len(ctx.bridge.list_sessions()["data"])


def test_workspace_paths_are_scoped_and_safe() -> None:
    guest = workspace_dir(DEFAULT_DATA_DIR, None)
    account = workspace_dir(DEFAULT_DATA_DIR, "acct-1")
    assert guest.name == "guest"
    assert account.name == "acct-1"
    assert guest != account
    assert guest.parent.name == "workspaces"


def test_workspace_key_cannot_escape_the_project() -> None:
    for bad in ("../../etc", "..", "a/b", "", "  ", "x" * 100):
        if bad.strip() == "":
            continue  # empty means "guest" by design
        try:
            workspace_dir(DEFAULT_DATA_DIR, bad)
        except PathConfinementError:
            continue
        raise AssertionError(f"unsafe workspace key was accepted: {bad!r}")


def test_accounts_do_not_share_sessions(ctx) -> None:
    assert _sessions(ctx) == 3  # seeded samples live in the guest workspace

    ctx.bridge.use_workspace({"account_key": "acct-a"})
    assert _sessions(ctx) == 0
    ctx.bridge.create_session({"title": "Account A private call"})
    assert _sessions(ctx) == 1

    ctx.bridge.use_workspace({"account_key": "acct-b"})
    assert _sessions(ctx) == 0

    ctx.bridge.use_workspace({"account_key": "acct-a"})
    assert _sessions(ctx) == 1

    ctx.bridge.use_workspace({"account_key": None})
    assert _sessions(ctx) == 3  # guest data untouched


def test_switching_back_and_forth_never_nests_workspaces(ctx) -> None:
    ctx.bridge.use_workspace({"account_key": "acct-nest"})
    ctx.bridge.use_workspace({"account_key": None})
    result = ctx.bridge.use_workspace({"account_key": None})
    path = str(result["data"]["workspace"]).replace("\\", "/")
    assert "/workspaces/guest/workspaces" not in path
    assert path.endswith("/workspaces/guest")


def test_workspace_switch_reports_counts(ctx) -> None:
    ctx.bridge.use_workspace({"account_key": "acct-counts"})
    ctx.bridge.create_session({"title": "Counted call"})
    ctx.bridge.use_workspace({"account_key": "acct-counts"})
    result = ctx.bridge.use_workspace({"account_key": "acct-counts"})
    assert result["ok"] is True
    assert result["data"]["counts"]["sessions"] == 1
    assert result["data"]["account_key"] == "acct-counts"


def test_invalid_key_is_rejected_without_losing_the_current_workspace(ctx) -> None:
    before = _sessions(ctx)
    result = ctx.bridge.use_workspace({"account_key": "bad/key"})
    assert result["ok"] is False
    assert result["error"]["code"] in {"path_not_allowed", "path_outside_project", "validation_error", "invalid_path"}
    assert _sessions(ctx) == before
