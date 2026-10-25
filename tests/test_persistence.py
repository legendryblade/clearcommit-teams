from __future__ import annotations

import json
import uuid

import pytest

from clearcommit_teams.app import main
from clearcommit_teams.context import build_context
from clearcommit_teams.db import Database
from clearcommit_teams.errors import PathConfinementError
from clearcommit_teams.paths import (
    PROJECT_ROOT,
    assert_write_allowed,
    database_path,
    resolve_data_dir,
)


def test_samples_seed_once_with_evidence_refs(ctx) -> None:
    sessions = ctx.repo.list_sessions()
    assert {item["id"] for item in sessions} == {
        "s_sample_helio", "s_sample_northwind", "s_sample_atlas",
    }
    assert sum(item["utterance_count"] for item in sessions) == 26
    helio = ctx.repo.get_session("s_sample_helio")
    assert [item["ref"] for item in helio["utterances"][:3]] == ["E-01", "E-02", "E-03"]
    assert helio["utterances"][0]["translation"].startswith("First of all")


def test_seed_is_idempotent_across_contexts(data_dir) -> None:
    first = build_context(data_dir)
    second = build_context(data_dir)
    assert len(first.repo.list_sessions()) == 3
    assert len(second.repo.list_sessions()) == 3
    assert second.db.counts()["utterances"] == 26


def test_create_session_add_utterance_and_import(ctx) -> None:
    created = ctx.repo.create_session({
        "title": "Discovery call",
        "customer_name": "Dana",
        "company": "Example Co",
        "customer_language": "en",
        "rep_language": "en",
    })
    session_id = created["session"]["id"]
    assert created["session"]["language_pair"] == "English"

    added = ctx.repo.add_utterance(session_id, {
        "speaker": "customer",
        "original_text": "We need a clearer rollout plan.",
        "display_time": "00:10",
    })
    assert added["ref"] == "E-01"

    imported = ctx.repo.add_utterances(session_id, [
        {
            "speaker": "rep",
            "original_text": "I can send one by Friday.",
            "display_time": "00:20",
        },
        {
            "speaker": "customer",
            "original_text": "Friday works.",
            "display_time": "00:30",
        },
    ])
    assert [item["ref"] for item in imported["utterances"]] == ["E-01", "E-02", "E-03"]

    reopened = build_context(ctx.data_dir)
    reloaded = reopened.repo.get_session(session_id)
    assert len(reloaded["utterances"]) == 3
    assert reloaded["session"]["title"] == "Discovery call"


def test_settings_persist_and_never_store_a_key(ctx) -> None:
    saved = ctx.repo.save_settings({
        "provider_mode": "openai_compatible",
        "base_url": "https://provider.example/v1",
        "model": "example-model",
        "timeout_s": "40",
        "reviewer_name": "Sam Reviewer",
        "api_key": "sk-should-never-be-stored",
        "CLEARCOMMIT_TEAMS_API_KEY": "sk-also-not",
    })
    assert saved["provider_mode"] == "openai_compatible"
    assert saved["timeout_s"] == 40.0
    assert saved["reviewer_name"] == "Sam Reviewer"
    assert "api_key" not in saved
    assert "CLEARCOMMIT_TEAMS_API_KEY" not in saved
    serialized = json.dumps(saved)
    assert "sk-should-never-be-stored" not in serialized
    assert "sk-also-not" not in serialized

    reopened = build_context(ctx.data_dir)
    assert reopened.repo.settings()["reviewer_name"] == "Sam Reviewer"


def test_bootstrap_never_echoes_environment_key(ctx, monkeypatch) -> None:
    secret = "sk-test-" + uuid.uuid4().hex
    monkeypatch.setenv("CLEARCOMMIT_TEAMS_API_KEY", secret)
    ctx.repo.save_settings({
        "provider_mode": "openai_compatible",
        "base_url": "https://provider.example/v1",
        "model": "example-model",
    })
    envelope = ctx.bridge.bootstrap({})
    assert envelope["ok"] is True
    serialized = json.dumps(envelope)
    assert secret not in serialized
    assert envelope["data"]["provider"]["key_present"] is True


def test_data_directory_must_stay_inside_project(tmp_path, monkeypatch) -> None:
    with pytest.raises(PathConfinementError):
        resolve_data_dir(tmp_path)
    with pytest.raises(PathConfinementError):
        build_context(tmp_path)
    with pytest.raises(PathConfinementError):
        Database(tmp_path / "outside.db")
    with pytest.raises(PathConfinementError):
        assert_write_allowed(tmp_path / "outside.txt")

    monkeypatch.setenv("CLEARCOMMIT_TEAMS_DATA_DIR", str(tmp_path))
    with pytest.raises(PathConfinementError):
        resolve_data_dir()


def test_relative_data_dir_resolves_under_project(data_dir) -> None:
    relative = data_dir.relative_to(PROJECT_ROOT)
    resolved = resolve_data_dir(relative)
    assert resolved == data_dir.resolve()
    assert database_path(resolved).parent == resolved


def test_check_command_reports_workspace(data_dir, capsys) -> None:
    assert main(["--check", "--data-dir", str(data_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["counts"]["sessions"] == 3
    assert payload["counts"]["utterances"] == 26
    assert payload["provider"]["mode"] == "mock"
    assert str(data_dir.resolve()) == payload["data_dir"]


def test_check_command_refuses_external_directory(tmp_path, capsys) -> None:
    assert main(["--check", "--data-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "could not open its workspace" in captured.err
    assert not (tmp_path / "clearcommit-teams.db").exists()
