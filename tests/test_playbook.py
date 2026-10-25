from __future__ import annotations

import pytest

from clearcommit_teams.context import build_context
from clearcommit_teams.errors import ConflictError, NotFoundError, ValidationError


def analyzed_insights(ctx):
    refs = [f"E-{index:02d}" for index in range(1, 11)]
    return ctx.service.analyze("s_sample_helio", refs)["insights"]


def objection_insight(ctx):
    return next(item for item in analyzed_insights(ctx) if item["type"] == "objection")


def test_create_playbook_entry_from_insight(ctx) -> None:
    source = objection_insight(ctx)
    entry = ctx.repo.create_playbook_from_insight(source["id"])
    assert entry["created"] is True
    assert entry["status"] == "draft"
    assert entry["insight_id"] == source["id"]
    assert entry["session_id"] == "s_sample_helio"
    assert entry["evidence_refs"] == source["evidence_refs"]
    assert entry["evidence_summary"].startswith("[E-")
    assert entry["approved_by"] is None
    assert entry["reviews"] == []


def test_create_is_idempotent_per_insight(ctx) -> None:
    source = objection_insight(ctx)
    first = ctx.repo.create_playbook_from_insight(source["id"])
    second = ctx.repo.create_playbook_from_insight(source["id"])
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert len(ctx.repo.list_playbook()) == 1


def test_discovery_insight_prefills_discovery_question(ctx) -> None:
    source = next(item for item in analyzed_insights(ctx) if item["type"] == "discovery")
    entry = ctx.repo.create_playbook_from_insight(source["id"])
    assert entry["discovery_questions"] == [source["proposed_alternative"]]
    approved = ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen")
    assert approved["status"] == "approved"


def test_overrides_are_validated_and_applied(ctx) -> None:
    sources = analyzed_insights(ctx)
    source = next(item for item in sources if item["type"] == "objection")
    other = next(item for item in sources if item["id"] != source["id"])
    entry = ctx.repo.create_playbook_from_insight(source["id"], {
        "title": "  Annual price objection  ",
        "scenario": "Renewal call",
        "discovery_questions": ["What budget was approved?", "Who signs?"],
        "category": "objection",
    })
    assert entry["title"] == "Annual price objection"
    assert entry["discovery_questions"] == ["What budget was approved?", "Who signs?"]
    with pytest.raises(ValidationError):
        ctx.repo.create_playbook_from_insight(other["id"], {"category": "made_up"})


def test_approval_requires_named_reviewer_question_and_evidence(ctx) -> None:
    source = objection_insight(ctx)
    entry = ctx.repo.create_playbook_from_insight(source["id"])
    with pytest.raises(ValidationError):
        ctx.repo.approve_playbook_entry(entry["id"], "   ")
    with pytest.raises(ValidationError) as excinfo:
        ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen")
    assert "discovery question" in excinfo.value.message.lower()

    updated = ctx.repo.update_playbook_entry(
        entry["id"],
        {"discovery_questions": ["What would make the annual plan easier to approve?"]},
        reviewer="Maya Chen",
    )
    approved = ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen", "Reviewed in weekly call.")
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "Maya Chen"
    assert approved["approved_at"]
    assert [review["action"] for review in approved["reviews"]] == ["edited", "approved"]
    assert updated["status"] == "draft"

    with pytest.raises(ConflictError):
        ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen")


def test_editing_approved_guidance_reopens_review(ctx) -> None:
    source = objection_insight(ctx)
    entry = ctx.repo.create_playbook_from_insight(source["id"])
    ctx.repo.update_playbook_entry(
        entry["id"], {"discovery_questions": ["What changed since last year?"]}, "Maya Chen"
    )
    approved = ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen")
    reopened = ctx.repo.update_playbook_entry(
        entry["id"], {"approved_response": "A revised response."}, "Jordan Lee"
    )
    assert approved["status"] == "approved"
    assert reopened["status"] == "draft"
    assert reopened["approved_by"] is None
    assert reopened["approved_at"] is None
    assert reopened["approved_response"] == "A revised response."
    assert [review["action"] for review in reopened["reviews"]][-1] == "reopened"
    assert reopened["reviews"][-1]["reviewer"] == "Jordan Lee"


def test_playbook_persists_across_contexts(ctx) -> None:
    source = objection_insight(ctx)
    entry = ctx.repo.create_playbook_from_insight(source["id"])
    ctx.repo.update_playbook_entry(
        entry["id"], {"discovery_questions": ["Who owns the budget?"]}, "Maya Chen"
    )
    ctx.repo.approve_playbook_entry(entry["id"], "Maya Chen", "Approved for the team.")

    reopened = build_context(ctx.data_dir)
    loaded = reopened.repo.get_playbook_entry(entry["id"])
    assert loaded["status"] == "approved"
    assert loaded["approved_by"] == "Maya Chen"
    assert loaded["reviews"][-1]["note"] == "Approved for the team."
    assert reopened.repo.preview()["counts"]["playbook_approved"] == 1
    assert reopened.repo.list_playbook("approved")[0]["id"] == entry["id"]
    with pytest.raises(NotFoundError):
        reopened.repo.get_playbook_entry("pb_missing")
