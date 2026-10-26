"""Desktop-side hooks for cloud sync.

These cover the local half of the sync path: reading a conversation as a
cloud-ready payload, and remembering which cloud record a local conversation
became so a retry cannot create a duplicate.
"""

from __future__ import annotations


def _session_with_lines(ctx) -> str:
    created = ctx.bridge.create_session(
        {"title": "Sync subject", "customer_language": "en", "rep_language": "en"}
    )
    assert created["ok"] is True
    session_id = created["data"]["session"]["id"]
    ctx.bridge.add_utterance(
        {
            "session_id": session_id,
            "speaker": "customer",
            "original_text": "We need a security review before signing.",
        }
    )
    ctx.bridge.add_utterance(
        {
            "session_id": session_id,
            "speaker": "rep",
            "original_text": "I will send the checklist today.",
        }
    )
    return session_id


def test_transcript_payload_is_cloud_ready(ctx) -> None:
    session_id = _session_with_lines(ctx)
    payload = ctx.bridge.transcript_payload({"session_id": session_id})

    assert payload["ok"] is True
    data = payload["data"]
    assert data["title"] == "Sync subject"
    assert data["language"] == "en"
    assert len(data["utterances"]) == 2
    assert data["utterances"][0]["speaker"] in {"customer", "rep"}
    assert data["utterances"][0]["content"].startswith("We need a security review")


def test_cloud_link_starts_empty(ctx) -> None:
    session_id = _session_with_lines(ctx)
    link = ctx.bridge.get_cloud_link({"session_id": session_id})
    assert link["ok"] is True
    assert link["data"]["cloud_conversation_id"] is None


def test_cloud_link_round_trips_and_survives_reopen(ctx, tmp_path) -> None:
    session_id = _session_with_lines(ctx)
    saved = ctx.bridge.set_cloud_link(
        {"session_id": session_id, "cloud_conversation_id": "cloud-abc-123"}
    )
    assert saved["ok"] is True

    again = ctx.bridge.get_cloud_link({"session_id": session_id})
    assert again["data"]["cloud_conversation_id"] == "cloud-abc-123"

    # Reopening the same workspace must remember the link, otherwise a retry
    # after a restart would duplicate the cloud record.
    from clearcommit_teams.context import build_context

    reopened = build_context(ctx.data_dir)
    remembered = reopened.bridge.get_cloud_link({"session_id": session_id})
    assert remembered["data"]["cloud_conversation_id"] == "cloud-abc-123"


def test_cloud_link_rejects_an_empty_id(ctx) -> None:
    session_id = _session_with_lines(ctx)
    result = ctx.bridge.set_cloud_link({"session_id": session_id, "cloud_conversation_id": ""})
    assert result["ok"] is False
    assert result["error"]["code"] in {"validation_error", "validation"}


def test_links_are_scoped_per_session(ctx) -> None:
    first = _session_with_lines(ctx)
    second = _session_with_lines(ctx)

    ctx.bridge.set_cloud_link({"session_id": first, "cloud_conversation_id": "cloud-first"})
    other = ctx.bridge.get_cloud_link({"session_id": second})
    assert other["data"]["cloud_conversation_id"] is None
