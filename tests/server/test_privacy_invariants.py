"""Individual-vs-company privacy invariants.

The product promise: using ClearCommit personally, then joining a company,
must not publish the personal workspace. These tests pin the server-side
guarantee (the UI only reflects it).
"""

from __future__ import annotations


def test_private_insight_stays_private_after_joining_an_organization(
    client, make_actor
) -> None:
    """A personal insight created before joining must not become visible."""
    user = make_actor("solo", "Sam Solo")

    # Personal work first: an organization is created (an account can have one)
    # and the insight is authored as private.
    org = user.data("POST", "/api/orgs", {"name": "Solo Org"})
    org_id = org["org_id"]

    conversation = user.data(
        "POST", f"/api/orgs/{org_id}/conversations", {"title": "Personal call"}
    )
    conversation_id = conversation["conversation_id"]
    lines = user.data(
        "POST",
        f"/api/orgs/{org_id}/conversations/{conversation_id}/utterances",
        {"utterances": [{"speaker": "Customer", "content": "Private details here."}]},
    )
    utterance_id = lines["utterances"][0]["utterance_id"]

    insight = user.data(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": conversation_id,
            "title": "Private observation",
            "observed_issue": "Only for me.",
            "suggested_alternative": "Mine to act on.",
            "evidence": [{"utterance_id": utterance_id, "quote": "Private details here."}],
        },
    )
    assert insight["visibility"] == "private"

    # A teammate joins the same organization.
    teammate = make_actor("mate", "Mia Mate")
    invitation = user.data(
        "POST",
        f"/api/orgs/{org_id}/invitations",
        {"email": teammate.profile["email"], "role": "manager"},
    )
    teammate.data(
        "POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]}
    )

    # The teammate must not see the private insight, its conversation, or its lines.
    assert teammate.call("GET", f"/api/insights/{insight['insight_id']}").status_code == 404
    assert (
        teammate.call(
            "GET", f"/api/orgs/{org_id}/conversations/{conversation_id}"
        ).status_code
        == 404
    )
    shared = teammate.data("GET", f"/api/orgs/{org_id}/insights?scope=shared")
    assert all(row["insight_id"] != insight["insight_id"] for row in shared["insights"])

    # The author still sees it privately.
    mine = user.data("GET", f"/api/orgs/{org_id}/insights?scope=mine")
    assert any(row["insight_id"] == insight["insight_id"] for row in mine["insights"])


def test_sharing_is_explicit_and_one_way(client, make_actor) -> None:
    """Sharing an insight does not share the underlying conversation."""
    owner = make_actor("shareowner", "Sharon Owner")
    reviewer = make_actor("sharereviewer", "Ravi Reviewer")

    org = owner.data("POST", "/api/orgs", {"name": "Share Org"})
    org_id = org["org_id"]
    invitation = owner.data(
        "POST",
        f"/api/orgs/{org_id}/invitations",
        {"email": reviewer.profile["email"], "role": "manager"},
    )
    reviewer.data(
        "POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]}
    )

    conversation = owner.data(
        "POST", f"/api/orgs/{org_id}/conversations", {"title": "Shared call"}
    )
    conversation_id = conversation["conversation_id"]
    lines = owner.data(
        "POST",
        f"/api/orgs/{org_id}/conversations/{conversation_id}/utterances",
        {"utterances": [{"speaker": "Customer", "content": "The quoted line."}]},
    )
    insight = owner.data(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": conversation_id,
            "title": "Shared observation",
            "observed_issue": "Observed.",
            "suggested_alternative": "Suggested.",
            "evidence": [
                {"utterance_id": lines["utterances"][0]["utterance_id"], "quote": "The quoted line."}
            ],
        },
    )

    owner.data("POST", f"/api/insights/{insight['insight_id']}/share", {})

    # The insight is visible; the transcript is not.
    assert reviewer.call("GET", f"/api/insights/{insight['insight_id']}").status_code == 200
    assert (
        reviewer.call(
            "GET", f"/api/orgs/{org_id}/conversations/{conversation_id}"
        ).status_code
        == 404
    )


def test_membership_is_required_to_read_org_data(client, make_actor) -> None:
    """An authenticated user outside the org cannot read it, even with the id."""
    owner = make_actor("gateowner", "Gale Owner")
    outsider = make_actor("gateoutsider", "Owen Outsider")

    org = owner.data("POST", "/api/orgs", {"name": "Gate Org"})
    org_id = org["org_id"]

    assert outsider.call("GET", f"/api/orgs/{org_id}").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}/insights?scope=shared").status_code == 404
    assert outsider.call("GET", f"/api/orgs/{org_id}/playbook").status_code == 404
