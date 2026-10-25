"""The acceptance workflow: insight -> share -> review -> approve -> playbook."""

from __future__ import annotations


def test_health_and_ready(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "live"

    ready = client.get("/ready")
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["ok"] is True
    assert payload["database"] == "ok"
    assert payload["mode"] in {"demo", "supabase"}


def test_two_users_complete_the_review_workflow(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    conversation_id = org_with_members["conversation_id"]
    utterance_ids = org_with_members["utterance_ids"]

    insight = rep.data(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": conversation_id,
            "title": "Setup ownership is unclear",
            "observed_issue": "The customer asks twice who owns setup.",
            "suggested_alternative": "Name the owner and confirm in writing.",
            "recommended_action": "Add an ownership checkpoint.",
            "uncertainty": "One conversation only.",
            "evidence": [
                {"utterance_id": utterance_ids[0], "quote": "Who owns setup after we sign?"},
                {"utterance_id": utterance_ids[2], "quote": "Can you confirm that in writing?"},
            ],
        },
    )
    assert insight["visibility"] == "private"

    # A manager cannot read a private insight.
    assert manager.call("GET", f"/api/insights/{insight['insight_id']}").status_code == 404

    shared = rep.data("POST", f"/api/insights/{insight['insight_id']}/share", {})
    assert shared["visibility"] == "shared"

    # Now the manager sees it in the shared list and can read the evidence.
    shared_list = manager.data("GET", f"/api/orgs/{org_id}/insights?scope=shared")
    assert any(row["insight_id"] == insight["insight_id"] for row in shared_list["insights"])
    detail = manager.data("GET", f"/api/insights/{insight['insight_id']}")
    assert len(detail["evidence"]) == 2

    draft = manager.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "insight_id": insight["insight_id"],
            "title": "Confirm setup ownership in writing",
            "scenario": "Customer asks who owns setup.",
            "response": "Name the owner and confirm in writing.",
            "discovery_questions": ["Who runs setup today?"],
        },
    )
    assert draft["status"] == "draft"

    approved = manager.data("POST", f"/api/playbook/{draft['entry_id']}/approve", {"note": "Reviewed"})
    assert approved["status"] == "approved"
    assert approved["approved_by"] == manager.user_id
    assert approved["approved_by_name"] == "Manny Manager"

    # The author sees the approved entry in the shared playbook.
    playbook = rep.data("GET", f"/api/orgs/{org_id}/playbook?status=approved")
    assert any(row["entry_id"] == draft["entry_id"] for row in playbook["entries"])


def test_approval_requires_discovery_questions(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]

    draft = manager.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "title": "Incomplete guidance",
            "scenario": "Anything.",
            "response": "Something.",
            "discovery_questions": [],
        },
    )
    response = manager.call("POST", f"/api/playbook/{draft['entry_id']}/approve", {})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "discovery_required"


def test_sales_rep_cannot_approve(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]

    draft = rep.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "title": "Rep draft",
            "scenario": "Scenario.",
            "response": "Response.",
            "discovery_questions": ["What happened?"],
        },
    )
    response = rep.call("POST", f"/api/playbook/{draft['entry_id']}/approve", {})
    assert response.status_code == 403
    assert manager.call("GET", f"/api/playbook/{draft['entry_id']}").status_code == 200


def test_editing_an_approved_entry_creates_a_new_version(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]

    draft = manager.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "title": "Original guidance",
            "scenario": "Scenario.",
            "response": "Response.",
            "discovery_questions": ["What happened?"],
        },
    )
    manager.data("POST", f"/api/playbook/{draft['entry_id']}/approve", {})

    revision = manager.data(
        "PATCH", f"/api/playbook/{draft['entry_id']}", {"response": "Improved response."}
    )
    assert revision["entry_id"] != draft["entry_id"]
    assert revision["status"] == "draft"
    assert revision["version"] == 2

    original = manager.data("GET", f"/api/playbook/{draft['entry_id']}")
    assert original["status"] == "approved"
    assert original["response"] == "Response."

    audit = manager.data("GET", f"/api/orgs/{org_id}/audit")
    assert any(event["action"] == "playbook.revised" for event in audit["events"])
