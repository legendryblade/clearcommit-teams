"""Tenant isolation, authorization, and privacy tests.

These are the tests the addendum asks for: a user in Organization A must not
be able to read, modify, or delete Organization B's data even with a valid
record id, and a revoked member must lose access immediately.
"""

from __future__ import annotations


def _make_private_insight(org_with_members) -> dict:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    return rep.data(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": org_with_members["conversation_id"],
            "title": "Private observation",
            "observed_issue": "Observed.",
            "suggested_alternative": "Suggested.",
            "evidence": [
                {
                    "utterance_id": org_with_members["utterance_ids"][0],
                    "quote": "Who owns setup after we sign?",
                }
            ],
        },
    )


def test_foreign_org_cannot_read_known_ids(client, org_with_members, make_actor) -> None:
    outsider = make_actor("outsider", "Otto Outsider")
    outsider_org = outsider.data("POST", "/api/orgs", {"name": "Other Org"})

    insight = _make_private_insight(org_with_members)
    org_id = org_with_members["org_id"]
    conversation_id = org_with_members["conversation_id"]

    # Guessed ids, valid ids, all denied.
    assert outsider.call("GET", f"/api/insights/{insight['insight_id']}").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}/conversations").status_code == 404
    assert (
        outsider.call("GET", f"/api/orgs/{org_id}/conversations/{conversation_id}").status_code
        == 404
    )
    assert outsider.call("GET", f"/api/orgs/{org_id}/playbook").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}/audit").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}/messaging").status_code == 404
    assert outsider_org["org_id"] != org_id


def test_foreign_org_cannot_write_to_known_ids(client, org_with_members, make_actor) -> None:
    outsider = make_actor("outsider2", "Ola Outsider")
    outsider.data("POST", "/api/orgs", {"name": "Other Org 2"})

    insight = _make_private_insight(org_with_members)
    org_id = org_with_members["org_id"]

    # Cannot share someone else's insight, nor write into their org.
    assert (
        outsider.call("POST", f"/api/insights/{insight['insight_id']}/share", {}).status_code
        == 404
    )
    assert (
        outsider.call(
            "POST",
            f"/api/orgs/{org_id}/conversations",
            {"title": "Injected"},
        ).status_code
        == 404
    )
    assert (
        outsider.call(
            "POST",
            f"/api/orgs/{org_id}/playbook",
            {
                "title": "Injected",
                "scenario": "x",
                "response": "y",
                "discovery_questions": ["z"],
            },
        ).status_code
        == 404
    )
    assert (
        outsider.call(
            "POST",
            f"/api/orgs/{org_id}/invitations",
            {"email": outsider.profile["email"], "role": "manager"},
        ).status_code
        == 404
    )

    # And cannot invite themselves into the org by id.
    invitation = outsider.call(
        "POST", f"/api/orgs/{org_id}/invitations", {"email": outsider.profile["email"], "role": "manager"}
    )
    assert invitation.status_code == 404


def test_invitation_is_bound_to_the_invited_email(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    intruder = make_actor("intruder", "Iris Intruder")

    invitation = owner.data(
        "POST",
        f"/api/orgs/{org_id}/invitations",
        {"email": "someone-else@example.com", "role": "manager"},
    )
    response = intruder.call(
        "POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_your_invitation"


def test_revoked_member_loses_access_immediately(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    manager = org_with_members["manager"]

    assert manager.call("GET", f"/api/orgs/{org_id}/playbook").status_code == 200
    owner.data("DELETE", f"/api/orgs/{org_id}/members/{manager.user_id}")

    assert manager.call("GET", f"/api/orgs/{org_id}/playbook").status_code == 404
    assert manager.call("GET", f"/api/orgs/{org_id}").status_code == 404

    # The token itself is still valid for the user's own account.
    assert manager.call("GET", "/api/auth/me").status_code == 200


def test_last_owner_cannot_be_revoked(client, make_actor) -> None:
    owner = make_actor("solo", "Solo Owner")
    org = owner.data("POST", "/api/orgs", {"name": "Solo Org"})
    response = owner.call("DELETE", f"/api/orgs/{org['org_id']}/members/{owner.user_id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_owner"


def test_private_conversation_is_not_visible_to_teammates(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    conversation_id = org_with_members["conversation_id"]

    assert (
        manager.call("GET", f"/api/orgs/{org_id}/conversations/{conversation_id}").status_code
        == 404
    )
    listing = manager.data("GET", f"/api/orgs/{org_id}/conversations")
    assert all(row["conversation_id"] != conversation_id for row in listing["conversations"])

    # Sharing an insight does not share the conversation.
    insight = _make_private_insight(org_with_members)
    org_with_members["rep"].data("POST", f"/api/insights/{insight['insight_id']}/share", {})
    assert (
        manager.call("GET", f"/api/orgs/{org_id}/conversations/{conversation_id}").status_code
        == 404
    )


def test_evidence_must_belong_to_the_conversation(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    response = rep.call(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": org_with_members["conversation_id"],
            "title": "Bad evidence",
            "observed_issue": "x",
            "suggested_alternative": "y",
            "evidence": [{"utterance_id": "not-a-real-utterance", "quote": "fabricated"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_evidence"


def test_unauthenticated_requests_are_rejected(client) -> None:
    for path in ("/api/orgs", "/api/auth/me", "/api/orgs/whatever/playbook"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] in {"missing_token", "invalid_token"}


def test_forged_token_is_rejected(client) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_client_supplied_role_is_ignored(client, org_with_members) -> None:
    """A rep sending role=owner in any payload gains nothing."""
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    draft = rep.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "title": "Self-approved?",
            "scenario": "s",
            "response": "r",
            "discovery_questions": ["q"],
            "role": "owner",
            "approved_by": rep.user_id,
            "status": "approved",
        },
    )
    assert draft["status"] == "draft"
    assert draft["approved_by"] is None
    assert rep.call("POST", f"/api/playbook/{draft['entry_id']}/approve", {}).status_code == 403


def test_marketing_sees_published_only(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    manager = org_with_members["manager"]
    marketer = make_actor("marketer", "Mia Marketing")
    invitation = owner.data(
        "POST", f"/api/orgs/{org_id}/invitations", {"email": marketer.profile["email"], "role": "marketing"}
    )
    marketer.data("POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]})

    draft = marketer.data(
        "POST",
        f"/api/orgs/{org_id}/messaging",
        {"title": "Claim", "claim_text": "We confirm the setup date in writing."},
    )
    published_only = owner.data("GET", f"/api/orgs/{org_id}/messaging")
    assert any(row["messaging_id"] == draft["messaging_id"] for row in published_only["entries"])

    manager.data("POST", f"/api/messaging/{draft['messaging_id']}/publish", {})
    assert (
        marketer.call("PATCH", f"/api/messaging/{draft['messaging_id']}", {"title": "x", "claim_text": "y"}).status_code
        == 409
    )
