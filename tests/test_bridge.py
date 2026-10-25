from __future__ import annotations

import json

import pytest

from clearcommit_teams.bridge import Bridge, PUBLIC_METHODS, public_method_names
from clearcommit_teams.errors import ProviderTimeoutError


def test_ping_and_bootstrap_envelopes(ctx) -> None:
    ping = ctx.bridge.ping({})
    assert ping["ok"] is True
    assert ping["data"]["name"] == "ClearCommit Teams"
    assert ping["data"]["bridge_version"] == "1.0"

    bootstrap = ctx.bridge.bootstrap({})
    assert bootstrap["ok"] is True
    data = bootstrap["data"]
    assert data["app"]["local_only"] is True
    assert data["capabilities"]["audio_capture"] is False
    assert data["capabilities"]["machine_translation"] is False
    assert data["capabilities"]["team_accounts"] is False
    assert data["limits"]["max_evidence"] == 12
    assert data["provider"]["mode"] == "mock"
    assert len(data["sessions"]) == 3


def test_public_method_inventory_has_no_private_helpers() -> None:
    assert public_method_names() == PUBLIC_METHODS
    assert "bootstrap" in PUBLIC_METHODS
    assert "_bootstrap" not in PUBLIC_METHODS
    for name in PUBLIC_METHODS:
        assert callable(getattr(Bridge, name, None))


def test_bridge_crud_flow(ctx) -> None:
    created = ctx.bridge.create_session({
        "title": "Bridge-created call",
        "customer_name": "Dana",
        "customer_language": "en",
        "rep_language": "en",
    })
    assert created["ok"] is True
    session_id = created["data"]["session"]["id"]

    added = ctx.bridge.add_utterance({
        "session_id": session_id,
        "speaker": "customer",
        "original_text": "We need a security review before we can proceed.",
        "display_time": "00:15",
    })
    assert added["ok"] is True
    assert added["data"]["ref"] == "E-01"

    imported = ctx.bridge.import_transcript({
        "session_id": session_id,
        "transcript": "[00:30] Rep: Can you share the review checklist?\n"
                      "[00:45] Customer: I'll send it tomorrow.",
    })
    assert imported["ok"] is True
    assert [item["ref"] for item in imported["data"]["utterances"]] == ["E-01", "E-02", "E-03"]

    analyzed = ctx.bridge.analyze({
        "session_id": "s_sample_helio",
        "evidence_refs": [f"E-{index:02d}" for index in range(1, 11)],
    })
    assert analyzed["ok"] is True
    insights = analyzed["data"]["insights"]
    assert insights
    insight_id = insights[0]["id"]

    listed = ctx.bridge.list_insights({"session_id": "s_sample_helio"})
    assert listed["ok"] is True
    assert any(item["id"] == insight_id for item in listed["data"])

    fetched = ctx.bridge.get_insight({"insight_id": insight_id})
    assert fetched["ok"] is True
    assert fetched["data"]["evidence"]

    entry = ctx.bridge.create_playbook({"insight_id": insight_id})
    assert entry["ok"] is True
    entry_id = entry["data"]["id"]
    assert entry["data"]["status"] == "draft"

    saved = ctx.bridge.save_playbook({
        "entry_id": entry_id,
        "reviewer": "Maya Chen",
        "fields": {"discovery_questions": ["What does the review require?"]},
    })
    assert saved["ok"] is True
    assert saved["data"]["discovery_questions"] == ["What does the review require?"]

    approved = ctx.bridge.approve_playbook({
        "entry_id": entry_id,
        "reviewer": "Maya Chen",
        "note": "Clear and grounded.",
    })
    assert approved["ok"] is True
    assert approved["data"]["status"] == "approved"
    assert approved["data"]["approved_by"] == "Maya Chen"

    playbook = ctx.bridge.list_playbook({"status": "approved"})
    assert playbook["ok"] is True
    assert playbook["data"][0]["id"] == entry_id

    preview = ctx.bridge.refresh_preview({})
    assert preview["ok"] is True
    assert preview["data"]["counts"]["playbook_approved"] == 1


def test_bridge_validation_and_not_found_envelopes(ctx) -> None:
    invalid = ctx.bridge.bootstrap("not-an-object")
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "validation_error"

    missing = ctx.bridge.get_session({"session_id": "s_missing"})
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_found"

    no_evidence = ctx.bridge.analyze({"session_id": "s_sample_helio", "evidence_refs": []})
    assert no_evidence["ok"] is False
    assert no_evidence["error"]["code"] == "insufficient_evidence"

    bad_ref = ctx.bridge.analyze({
        "session_id": "s_sample_helio",
        "evidence_refs": ["E-99"],
    })
    assert bad_ref["ok"] is False
    assert bad_ref["error"]["code"] == "validation_error"
    assert bad_ref["error"]["detail"]["missing"] == ["E-99"]

    bad_settings = ctx.bridge.save_settings({"base_url": "not-a-url"})
    assert bad_settings["ok"] is False
    assert bad_settings["error"]["code"] == "validation_error"

    bad_playbook = ctx.bridge.list_playbook({"status": "pending"})
    assert bad_playbook["ok"] is False
    assert bad_playbook["error"]["code"] == "validation_error"


def test_bridge_maps_provider_failure_and_hides_internal_errors(ctx, monkeypatch) -> None:
    class FailingService:
        def analyze(self, session_id, refs):
            raise ProviderTimeoutError("The provider did not answer.")

        def ask(self, session_id, refs, question):
            raise RuntimeError("secret implementation detail")

    monkeypatch.setattr(ctx.bridge, "service", FailingService())
    timeout = ctx.bridge.analyze({
        "session_id": "s_sample_helio",
        "evidence_refs": ["E-01"],
    })
    assert timeout["ok"] is False
    assert timeout["error"]["code"] == "provider_timeout"
    assert timeout["error"]["retryable"] is True

    internal = ctx.bridge.ask_assistant({
        "session_id": "s_sample_helio",
        "evidence_refs": ["E-01"],
        "question": "What happened?",
    })
    assert internal["ok"] is False
    assert internal["error"]["code"] == "internal_error"
    assert "secret" not in internal["error"]["message"]


def test_provider_test_and_status_through_bridge(ctx) -> None:
    status = ctx.bridge.provider_status({})
    assert status["ok"] is True
    assert status["data"]["mode"] == "mock"

    tested = ctx.bridge.test_provider({})
    assert tested["ok"] is True
    assert tested["data"]["ok"] is True
    assert tested["data"]["provider"]["mode"] == "mock"


def test_settings_round_trip_through_bridge(ctx, monkeypatch) -> None:
    monkeypatch.delenv("CLEARCOMMIT_TEAMS_API_KEY", raising=False)
    saved = ctx.bridge.save_settings({
        "provider_mode": "openai_compatible",
        "base_url": "https://provider.example/v1",
        "model": "example-model",
        "timeout_s": 35,
        "reviewer_name": "Sam Reviewer",
    })
    assert saved["ok"] is True
    assert saved["data"]["settings"]["reviewer_name"] == "Sam Reviewer"
    assert saved["data"]["provider"]["configured"] is False

    bootstrap = ctx.bridge.bootstrap({})
    assert bootstrap["data"]["settings"]["provider_mode"] == "openai_compatible"
    serialized = json.dumps(bootstrap)
    assert "api_key" not in serialized
