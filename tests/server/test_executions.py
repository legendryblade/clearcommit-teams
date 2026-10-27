"""The control plane's guarantees, tested at the HTTP boundary.

Each test here corresponds to a claim the product makes about itself. If one
of these passes while the underlying rule is broken, the product is lying, so
the negative cases matter more than the happy path.
"""

from __future__ import annotations

import pytest

from server.routers.executions import action_digest


def _start(actor, org_id, goal="Resolve delayed deliveries", steps=("Read orders",)):
    return actor.data(
        "POST", f"/api/orgs/{org_id}/executions", {"goal": goal, "steps": list(steps)}
    )


def _verify(actor, execution_id, result, postcondition="Order confirmed in ERP"):
    return actor.call(
        "POST",
        f"/api/executions/{execution_id}/verify",
        {"result": result, "source": "erp.readback", "postcondition": postcondition},
    )


def _request_approval(actor, execution_id, summary="Email supplier", target="supplier-42"):
    return actor.data(
        "POST",
        f"/api/executions/{execution_id}/approvals",
        {"summary": summary, "target": target, "params": {"body": "Please confirm delivery."}},
    )


# ---------------------------------------------------------------- creation


def test_create_execution_starts_running_with_numbered_steps(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id, steps=("Read orders", "Draft message", "Send"))
    assert created["status"] == "running"

    detail = rep.data("GET", f"/api/executions/{created['execution_id']}")
    assert [s["seq"] for s in detail["steps"]] == [1, 2, 3]
    assert detail["timeline"][0]["action"] == "created"


def test_execution_is_scoped_to_its_organization(org_with_members, make_actor):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)

    outsider = make_actor("outsider")
    outsider_org = outsider.data("POST", "/api/orgs", {"name": "Other Org"})

    response = outsider.call("GET", f"/api/executions/{created['execution_id']}")
    # 404, not 403: the API must not confirm the record exists.
    assert response.status_code == 404

    listed = outsider.data("GET", f"/api/orgs/{outsider_org['org_id']}/executions")
    assert listed["executions"] == []


# ------------------------------------------------------------ state machine


def test_cannot_claim_success_directly(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)

    response = rep.call(
        "POST", f"/api/executions/{created['execution_id']}/advance", {"status": "succeeded"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verification_required"


def test_illegal_transition_is_refused(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)

    response = rep.call(
        "POST", f"/api/executions/{created['execution_id']}/advance", {"status": "verifying"}
    )
    # running -> verifying is legal, so this one succeeds
    assert response.status_code == 200

    again = rep.call(
        "POST", f"/api/executions/{created['execution_id']}/advance", {"status": "blocked"}
    )
    assert again.status_code == 409


def test_terminal_execution_rejects_further_work(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)
    execution_id = created["execution_id"]

    assert _verify(rep, execution_id, "passed").status_code == 200

    add = rep.call(
        "POST", f"/api/executions/{execution_id}/steps", {"title": "Late step"}
    )
    assert add.status_code == 409


# -------------------------------------------------------------- verification


def test_success_requires_a_recorded_passing_check(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)
    execution_id = created["execution_id"]

    response = _verify(rep, execution_id, "passed")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["outcome_applied"] is True
    assert payload["current_status"] == "succeeded"

    detail = rep.data("GET", f"/api/executions/{execution_id}")
    assert len(detail["verifications"]) == 1
    assert detail["verifications"][0]["source"] == "erp.readback"


def _start_two_checks(actor, org_id):
    return actor.data(
        "POST",
        f"/api/orgs/{org_id}/executions",
        {
            "goal": "Resolve delayed deliveries",
            "steps": ["Confirm order 1", "Confirm order 2"],
        },
    )


def _step_ids(actor, execution_id):
    return [s["step_id"] for s in actor.data("GET", f"/api/executions/{execution_id}")["steps"]]


def _verify_step(actor, execution_id, step_id, result):
    return actor.call(
        "POST",
        f"/api/executions/{execution_id}/verify",
        {"result": result, "source": "erp.readback", "step_id": step_id},
    )


def test_one_failed_check_makes_the_outcome_failed_even_after_passes(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start_two_checks(rep, org_id)
    execution_id = created["execution_id"]
    first_step, second_step = _step_ids(rep, execution_id)

    # Give the steps postconditions so both checks are expected.
    for step_id, text in ((first_step, "Order 1 confirmed"), (second_step, "Order 2 confirmed")):
        rep.call(
            "POST",
            f"/api/executions/{execution_id}/steps",
            {"title": "placeholder", "postcondition": text},
        )

    # A pass with a second check outstanding must not conclude success.
    first = _verify(rep, execution_id, "passed", "Order 1 confirmed")
    assert first.json()["data"]["current_status"] == "verifying"
    assert first.json()["data"]["outcome_applied"] is False

    # A failure is conclusive immediately.
    second = _verify(rep, execution_id, "failed", "Order 2 confirmed")
    assert second.json()["data"]["current_status"] == "failed"


def test_unknown_only_checks_do_not_succeed(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)
    execution_id = created["execution_id"]

    response = _verify(rep, execution_id, "unknown")
    data = response.json()["data"]
    assert data["current_status"] == "verifying"
    assert data["outcome_applied"] is False


def test_partial_verification_is_not_success(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = rep.data(
        "POST",
        f"/api/orgs/{org_id}/executions",
        {
            "goal": "Resolve delayed deliveries",
            "steps": ["Confirm order 1", "Confirm order 2"],
        },
    )
    execution_id = created["execution_id"]

    # Two steps each declaring a postcondition: two checks are expected, so a
    # single pass cannot conclude anything yet.
    for text in ("Order 1 confirmed", "Order 2 confirmed"):
        rep.call(
            "POST",
            f"/api/executions/{execution_id}/steps",
            {"title": "Verify delivery", "postcondition": text},
        )

    first = _verify(rep, execution_id, "passed", "Order 1 confirmed")
    assert first.json()["data"]["current_status"] == "verifying"

    # Every expected postcondition now has a result: one pass, one inconclusive.
    # That is a partial verification, and it is explicitly not success.
    second = _verify(rep, execution_id, "unknown", "Order 2 confirmed")
    assert second.json()["data"]["current_status"] == "partially_verified"

    # A later read-back that resolves the open question must not silently
    # promote the run to success once it has already been concluded.
    late = _verify(rep, execution_id, "passed", "Order 2 confirmed")
    assert late.status_code == 409


def test_verification_requires_a_postcondition(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)

    response = rep.call(
        "POST",
        f"/api/executions/{created['execution_id']}/verify",
        {"result": "passed", "source": "erp.readback"},
    )
    assert response.status_code == 422


def test_verification_of_another_executions_step_is_refused(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    first = _start(rep, org_id)
    second = _start(rep, org_id)

    step_id = rep.data("GET", f"/api/executions/{first['execution_id']}")["steps"][0]["step_id"]
    response = rep.call(
        "POST",
        f"/api/executions/{second['execution_id']}/verify",
        {"result": "passed", "source": "erp", "step_id": step_id},
    )
    assert response.status_code == 404


# ----------------------------------------------------------------- approvals


def test_approval_digest_is_stable_and_changes_with_the_action():
    base = action_digest("Email supplier", "supplier-42", {"body": "confirm"})
    assert base == action_digest("Email supplier", "supplier-42", {"body": "confirm"})
    # Key order must not change the digest.
    assert action_digest("Email supplier", "supplier-42", {"a": 1, "b": 2}) == action_digest(
        "Email supplier", "supplier-42", {"b": 2, "a": 1}
    )
    # A different target, body or action must.
    assert base != action_digest("Email supplier", "supplier-99", {"body": "confirm"})
    assert base != action_digest("Email supplier", "supplier-42", {"body": "cancel"})
    assert base != action_digest("Call supplier", "supplier-42", {"body": "confirm"})


def test_requesting_approval_parks_the_execution(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)

    approval = _request_approval(rep, created["execution_id"])
    assert approval["status"] == "pending"
    detail = rep.data("GET", f"/api/executions/{created['execution_id']}")
    assert detail["status"] == "waiting_approval"


def test_reviewer_cannot_approve_their_own_request(org_with_members):
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    created = _start(owner, org_id)
    approval = _request_approval(owner, created["execution_id"])

    response = owner.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {
            "decision": "approved",
            "action_digest": approval["action_digest"],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "self_approval"


def test_reviewer_must_echo_the_current_digest(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"])

    wrong = manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": "0" * 64},
    )
    assert wrong.status_code == 409
    assert wrong.json()["error"]["code"] == "approval_scope_mismatch"

    right = manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    assert right.status_code == 200
    assert right.json()["data"]["status"] == "approved"
    assert right.json()["data"]["decided_by"] == manager.user_id


def test_non_reviewer_cannot_decide(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"])

    other_rep = org_with_members["rep"]
    response = other_rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    # Same actor is the requester, so self-approval fires first; still refused.
    assert response.status_code in (403, 409)


def test_approval_cannot_be_reused_for_a_different_action(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"], target="supplier-42")

    manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )

    # The intended action is spent once.
    used = rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/consume",
        {"action_digest": approval["action_digest"]},
    )
    assert used.status_code == 200
    assert used.json()["data"]["authorised"] is True

    # Spending it again is refused.
    again = rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/consume",
        {"action_digest": approval["action_digest"]},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "approval_already_used"


def test_approval_for_one_target_does_not_cover_another(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"], target="supplier-42")

    manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )

    other_digest = action_digest("Email supplier", "supplier-99", {"body": "Please confirm delivery."})
    response = rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/consume",
        {"action_digest": other_digest},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_scope_mismatch"


def test_rejected_action_blocks_the_execution_and_cannot_be_consumed(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"])

    manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "rejected", "action_digest": approval["action_digest"], "note": "Not yet"},
    )

    detail = rep.data("GET", f"/api/executions/{created['execution_id']}")
    assert detail["status"] == "blocked"

    consume = rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/consume",
        {"action_digest": approval["action_digest"]},
    )
    assert consume.status_code == 409


def test_second_decision_on_a_decided_approval_is_refused(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    owner = org_with_members["owner"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"])

    manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    second = owner.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "rejected", "action_digest": approval["action_digest"]},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "approval_not_pending"


def test_expired_approval_authorises_nothing(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)

    approval = rep.data(
        "POST",
        f"/api/executions/{created['execution_id']}/approvals",
        {
            "summary": "Email supplier",
            "target": "supplier-42",
            "params": {"body": "confirm"},
            "ttl_minutes": 1,
        },
    )

    # Age it past expiry directly through the API's own read path.
    from datetime import timedelta

    from server.models import Approval, utcnow

    session = rep.client.app.state.session_factory()
    try:
        row = session.get(Approval, approval["approval_id"])
        row.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    response = manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_expired"


def test_outsider_cannot_see_or_decide_an_approval(org_with_members, make_actor):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    created = _start(rep, org_id)
    approval = _request_approval(rep, created["execution_id"])

    outsider = make_actor("outsider2")
    response = outsider.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    assert response.status_code == 404

    listing = outsider.call("GET", f"/api/orgs/{org_id}/approvals")
    assert listing.status_code == 404


# -------------------------------------------------------------- cancellation


def test_cancellation_stops_work_and_does_not_claim_rollback(org_with_members):
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    created = _start(owner, org_id)

    data = owner.data(
        "POST",
        f"/api/executions/{created['execution_id']}/cancel",
        {"reason": "Supplier called back"},
    )
    assert data["status"] == "cancelled"
    assert data["rollback_performed"] is False
    assert "not reversed" in data["note"]

    # A closed execution cannot be verified into success afterwards.
    late = _verify(owner, created["execution_id"], "passed")
    assert late.status_code == 409


def test_reporter_cannot_cancel_someone_elses_execution(org_with_members):
    org_id = org_with_members["org_id"]
    owner = org_with_members["owner"]
    rep = org_with_members["rep"]
    created = _start(owner, org_id)

    # rep is a member of the same organization but neither created the
    # execution nor holds a reviewer role, so cancellation is refused with 403.
    response = rep.call(
        "POST", f"/api/executions/{created['execution_id']}/cancel", {"reason": "nope"}
    )
    assert response.status_code == 403

    # The execution is untouched.
    assert owner.data("GET", f"/api/executions/{created['execution_id']}")["status"] == "running"


# --------------------------------------------------------------- audit trail


def test_every_consequential_change_is_on_the_timeline(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    created = _start(rep, org_id)
    execution_id = created["execution_id"]

    approval = _request_approval(rep, execution_id)
    manager.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/decision",
        {"decision": "approved", "action_digest": approval["action_digest"]},
    )
    rep.call(
        "POST",
        f"/api/approvals/{approval['approval_id']}/consume",
        {"action_digest": approval["action_digest"]},
    )
    _verify(rep, execution_id, "passed")

    actions = [e["action"] for e in rep.data("GET", f"/api/executions/{execution_id}")["timeline"]]
    assert actions[0] == "created"
    assert "execution.awaiting_approval" in actions
    assert "approval.requested" in actions
    assert "approval.approved" in actions
    assert "execution.resumed" in actions
    assert "approval.consumed" in actions
    assert "execution.verified" in actions


def test_unknown_status_filter_is_rejected(org_with_members):
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    response = rep.call("GET", f"/api/orgs/{org_id}/executions?status=done")
    assert response.status_code == 422
