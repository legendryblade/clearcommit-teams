"""Commitments: a promise with an owner, a date, and evidence.

What must hold: nothing is confirmed automatically, only members can create
one, only the owner or a reviewer can complete it, and every change is
audited.
"""

from __future__ import annotations


def _create(client, actor, org_id, **overrides):
    body = {
        "title": "Send the revised estimate",
        "due_on": "2026-11-06",
        **overrides,
    }
    return actor.call("POST", f"/api/orgs/{org_id}/commitments", body)


def test_commitment_starts_awaiting_confirmation(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]

    response = _create(client, rep, org_id)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # The due date is stated, so confirming it can promote the status.
    assert data["status"] == "awaiting_confirmation"
    assert data["owner_id"] == rep.user_id
    assert data["evidence_quote"] is None


def test_owner_and_date_confirmation_opens_it(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    commitment = _create(client, rep, org_id, due_on=None).json()["data"]
    assert commitment["status"] == "awaiting_confirmation"

    confirmed = rep.data(
        "PATCH",
        f"/api/commitments/{commitment['commitment_id']}",
        {"due_on": "2026-11-13"},
    )
    assert confirmed["status"] == "open"
    assert confirmed["due_on"] == "2026-11-13"


def test_manager_can_assign_a_teammate(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    rep = org_with_members["rep"]

    created = _create(client, manager, org_id, owner_id=rep.user_id).json()["data"]
    assert created["owner_id"] == rep.user_id


def test_owner_must_be_a_member(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    outsider = make_actor("co-outsider", "Oz Outside")

    response = _create(client, manager, org_id, owner_id=outsider.user_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_owner"


def test_rep_cannot_complete_someone_elses_commitment(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    rep = org_with_members["rep"]

    created = _create(client, manager, org_id, owner_id=manager.user_id).json()["data"]
    response = rep.call(
        "PATCH", f"/api/commitments/{created['commitment_id']}", {"status": "done"}
    )
    assert response.status_code == 403


def test_owner_can_block_and_complete(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _create(client, rep, org_id).json()["data"]

    blocked = rep.data(
        "PATCH", f"/api/commitments/{created['commitment_id']}", {"status": "blocked"}
    )
    assert blocked["status"] == "blocked"

    done = rep.data(
        "PATCH", f"/api/commitments/{created['commitment_id']}", {"status": "done"}
    )
    assert done["status"] == "done"
    assert done["completed_at"] is not None


def test_scopes_separate_mine_from_team(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]

    _create(client, rep, org_id)
    private = _create(client, manager, org_id, visibility="private").json()["data"]

    mine = rep.data("GET", f"/api/orgs/{org_id}/commitments?scope=mine")
    assert all(c["owner_id"] == rep.user_id for c in mine["commitments"])

    team = rep.data("GET", f"/api/orgs/{org_id}/commitments?scope=team")
    assert all(
        c["commitment_id"] != private["commitment_id"] for c in team["commitments"]
    )


def test_private_commitment_hidden_from_teammates(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    rep = org_with_members["rep"]

    private = _create(client, manager, org_id, visibility="private").json()["data"]
    assert (
        rep.call("GET", f"/api/commitments/{private['commitment_id']}").status_code == 404
    )


def test_every_change_is_audited(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _create(client, rep, org_id).json()["data"]

    rep.data(
        "PATCH", f"/api/commitments/{created['commitment_id']}", {"status": "done"}
    )
    events = manager.data("GET", f"/api/orgs/{org_id}/audit")["events"]
    actions = [e["action"] for e in events if e["resource_id"] == created["commitment_id"]]
    assert "commitment.created" in actions
    assert "commitment.updated" in actions


def test_bad_due_date_is_refused(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    # Too long for the field, so schema validation refuses it first; a
    # wrong-but-short date is refused by the router. Both are 422.
    response = _create(client, rep, org_id, due_on="2026/11/06")
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"invalid_due_date", "invalid_request"}


def test_outsider_cannot_create_in_a_foreign_org(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    outsider = make_actor("co-nobody", "Nia Nobody")
    outsider.data("POST", "/api/orgs", {"name": "Elsewhere"})
    response = _create(client, outsider, org_id)
    assert response.status_code == 404


def test_conversation_evidence_round_trips(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _create(
        client,
        rep,
        org_id,
        conversation_id=org_with_members["conversation_id"],
        evidence_quote="Who owns setup after we sign?",
        evidence_utterance_id=org_with_members["utterance_ids"][0],
    ).json()["data"]
    assert created["evidence_quote"] == "Who owns setup after we sign?"
    assert created["conversation_id"] == org_with_members["conversation_id"]
