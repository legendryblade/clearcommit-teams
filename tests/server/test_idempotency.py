"""Idempotency: replaying an important write must not apply it twice."""

from __future__ import annotations


def _shared_insight(org_with_members) -> dict:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    insight = rep.data(
        "POST",
        f"/api/orgs/{org_id}/insights",
        {
            "conversation_id": org_with_members["conversation_id"],
            "title": "Idempotency subject",
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
    return {"org_id": org_id, "rep": rep, "insight": insight}


def test_share_replay_does_not_write_twice(client, org_with_members) -> None:
    context = _shared_insight(org_with_members)
    org_id, rep, insight = context["org_id"], context["rep"], context["insight"]
    key = "share-key-0001"

    first = rep.client.post(
        f"/api/insights/{insight['insight_id']}/share",
        json={},
        headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": key},
    )
    assert first.status_code == 200
    assert first.json()["data"]["visibility"] == "shared"

    second = rep.client.post(
        f"/api/insights/{insight['insight_id']}/share",
        json={},
        headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": key},
    )
    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]

    audit = rep.data("GET", f"/api/orgs/{org_id}/audit") if False else None
    # Owners/managers can read the audit trail; the rep cannot, so verify the
    # effect through the record itself instead.
    detail = rep.data("GET", f"/api/insights/{insight['insight_id']}")
    assert detail["visibility"] == "shared"


def test_share_replay_emits_one_audit_event(client, org_with_members) -> None:
    context = _shared_insight(org_with_members)
    org_id, rep, insight = context["org_id"], context["rep"], context["insight"]
    manager = org_with_members["manager"]
    key = "share-key-audit"

    for _ in range(3):
        rep.client.post(
            f"/api/insights/{insight['insight_id']}/share",
            json={},
            headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": key},
        )

    audit = manager.data("GET", f"/api/orgs/{org_id}/audit")
    shared = [
        event
        for event in audit["events"]
        if event["action"] == "insight.shared" and event["resource_id"] == insight["insight_id"]
    ]
    assert len(shared) == 1


def test_approval_replay_is_single_approval(client, org_with_members) -> None:
    org_id = org_with_members["org_id"]
    manager = org_with_members["manager"]
    rep = org_with_members["rep"]

    draft = rep.data(
        "POST",
        f"/api/orgs/{org_id}/playbook",
        {
            "title": "Replay approval",
            "scenario": "s",
            "response": "r",
            "discovery_questions": ["q"],
        },
    )
    key = "approve-key-1"
    headers = {"Authorization": f"Bearer {manager.token}", "Idempotency-Key": key}

    first = client.post(f"/api/playbook/{draft['entry_id']}/approve", json={}, headers=headers)
    second = client.post(f"/api/playbook/{draft['entry_id']}/approve", json={}, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["approved_at"] == second.json()["data"]["approved_at"]

    audit = manager.data("GET", f"/api/orgs/{org_id}/audit")
    approvals = [
        event
        for event in audit["events"]
        if event["action"] == "playbook.approved" and event["resource_id"] == draft["entry_id"]
    ]
    assert len(approvals) == 1


def test_distinct_keys_are_independent(client, org_with_members) -> None:
    context = _shared_insight(org_with_members)
    rep, insight = context["rep"], context["insight"]
    a = rep.client.post(
        f"/api/insights/{insight['insight_id']}/share",
        json={},
        headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": "key-aaa"},
    )
    b = rep.client.post(
        f"/api/insights/{insight['insight_id']}/share",
        json={},
        headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": "key-bbb"},
    )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["data"]["visibility"] == "shared"


def test_overlong_key_is_rejected(client, org_with_members) -> None:
    context = _shared_insight(org_with_members)
    rep, insight = context["rep"], context["insight"]
    response = rep.client.post(
        f"/api/insights/{insight['insight_id']}/share",
        json={},
        headers={"Authorization": f"Bearer {rep.token}", "Idempotency-Key": "x" * 500},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_idempotency_key"
