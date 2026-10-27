"""Executions: controlled work that ends in a verified outcome, not a claim.

The rules this module enforces, and why each exists:

* **State is validated by code, never by model text.** ``advance`` accepts only
  transitions the machine permits. ``running`` cannot jump to ``succeeded``.
* **Success requires evidence.** ``verify`` records a check against a
  postcondition. Only recorded checks can move an execution out of
  ``verifying``, and the outcome is derived from those checks — one failed
  check makes the whole outcome ``failed`` even if others passed.
* **An approval is bound to one action.** ``approvals`` hashes action, target
  and params into a digest. A reviewer must echo the digest they believe they
  are approving; a mismatch is refused. A materially changed action needs a new
  approval, and an approval is single-use.
* **Cancellation is not rollback.** ``cancel`` stops eligible future work and
  says so. It never implies an external effect was undone.
* **Tenant boundaries are 404.** An execution in another organization is
  indistinguishable from one that does not exist.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..dependencies import (
    REVIEWER_ROLES,
    enforce_rate_limit,
    get_provisioned_principal,
    get_session,
    require_member,
)
from ..errors import ApiError
from ..execution_state import (
    BLOCKED,
    CANCELLED,
    RUNNING,
    STATES,
    SUCCEEDED,
    TERMINAL,
    VERIFYING,
    WAITING_APPROVAL,
    IllegalTransition,
    derive_outcome,
    ensure_transition,
    ensure_verdict,
    is_terminal,
)
from ..models import (
    Approval,
    Execution,
    ExecutionEvent,
    ExecutionStep,
    Profile,
    VerificationRun,
    new_id,
    utcnow,
)
from ..schemas import (
    ApprovalConsumeRequest,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ExecutionAdvanceRequest,
    ExecutionCancelRequest,
    ExecutionCreateRequest,
    ExecutionStepCreateRequest,
    VerificationRequest,
)
from ..security import Principal
from ..serializers import (
    approval_brief,
    execution_brief,
    execution_event_brief,
    step_brief,
    verification_brief,
)

router = APIRouter(tags=["executions"])

# Steps a person or agent must be stopped for. Computing this in one place
# means a new caller cannot accidentally ship a write without an approval gate.
PROTECTED_KINDS = {"write", "notify"}


def action_digest(action: str, target: str, params: dict) -> str:
    """Stable hash of exactly what is being authorised.

    Canonical JSON so key order and whitespace cannot produce two digests for
    one action, and so a changed parameter always produces a different digest.
    """
    payload = json.dumps(
        {"action": action, "target": target, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _expire_if_stale(session: Session, approval: Approval, actor_id: str) -> Approval:
    """Flip a pending approval past its expiry.

    Expiry is applied when read, so a forgotten approval cannot authorise
    anything merely because nobody came back to update it.
    """
    expires = _stamp(approval.expires_at)
    if approval.status == "pending" and expires is not None and expires <= utcnow():
        approval.status = "expired"
        session.add(
            ExecutionEvent(
                id=new_id(),
                execution_id=approval.execution_id,
                org_id=approval.org_id,
                actor_id=actor_id,
                action="approval.expired",
                detail_json=json.dumps({"approval_id": approval.id}),
            )
        )
    return approval


def _load_execution(session: Session, execution_id: str, user_id: str) -> tuple[Execution, str]:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise ApiError("not_found", "No accessible execution with that id.", 404)
    membership = require_member(session, execution.org_id, user_id)
    return execution, membership.role


def _record(
    session: Session,
    execution: Execution,
    actor_id: str,
    action: str,
    from_status: str | None,
    to_status: str | None,
    detail: dict | None = None,
) -> None:
    session.add(
        ExecutionEvent(
            id=new_id(),
            execution_id=execution.id,
            org_id=execution.org_id,
            actor_id=actor_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )


def _apply_status(session: Session, execution: Execution, target: str, actor_id: str, action: str, detail: dict | None = None) -> None:
    """Validate and persist one state change, or refuse it."""
    try:
        ensure_transition(execution.status, target)
    except IllegalTransition as exc:
        raise ApiError(
            "illegal_transition",
            f"An execution cannot move from '{execution.status}' to '{target}'.",
            409,
        ) from exc
    previous = execution.status
    execution.status = target
    if target in TERMINAL:
        execution.closed_at = utcnow()
    _record(session, execution, actor_id, action, previous, target, detail)


def _next_seq(session: Session, execution_id: str) -> int:
    last = (
        session.query(ExecutionStep)
        .filter(ExecutionStep.execution_id == execution_id)
        .order_by(ExecutionStep.seq.desc())
        .first()
    )
    return (last.seq + 1) if last else 1


@router.post("/api/orgs/{org_id}/executions")
def create_execution(
    org_id: str,
    payload: ExecutionCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    enforce_rate_limit(request, principal, bucket="execution-create")

    execution = Execution(
        id=new_id(),
        org_id=org_id,
        goal=payload.goal.strip(),
        status=RUNNING,
        created_by=principal.user_id,
    )
    session.add(execution)
    for index, title in enumerate(payload.steps, start=1):
        session.add(
            ExecutionStep(
                id=new_id(),
                execution_id=execution.id,
                org_id=org_id,
                seq=index,
                title=title.strip(),
                kind="read",
                status="pending",
            )
        )
    audit(
        session,
        org_id,
        principal.user_id,
        "execution.created",
        "execution",
        execution.id,
        {"goal_length": len(execution.goal), "steps": len(payload.steps)},
    )
    _record(session, execution, principal.user_id, "created", None, RUNNING)
    session.commit()
    request.app.state.hub.emit(
        org_id, "execution.created", "execution", execution.id, principal.user_id
    )
    return {"ok": True, "data": execution_brief(execution)}


@router.get("/api/orgs/{org_id}/executions")
def list_executions(
    org_id: str,
    status: str | None = None,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    query = session.query(Execution).filter(Execution.org_id == org_id)
    if status:
        if status not in STATES:
            raise ApiError("invalid_status", "Unknown execution status.", 422)
        query = query.filter(Execution.status == status)
    rows = query.order_by(Execution.created_at.desc()).limit(200).all()
    return {"ok": True, "data": {"executions": [execution_brief(r) for r in rows]}}


@router.get("/api/executions/{execution_id}")
def get_execution(
    execution_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    execution, _role = _load_execution(session, execution_id, principal.user_id)
    steps = (
        session.query(ExecutionStep)
        .filter(ExecutionStep.execution_id == execution.id)
        .order_by(ExecutionStep.seq)
        .all()
    )
    approvals = (
        session.query(Approval)
        .filter(Approval.execution_id == execution.id)
        .order_by(Approval.created_at)
        .all()
    )
    verifications = (
        session.query(VerificationRun)
        .filter(VerificationRun.execution_id == execution.id)
        .order_by(VerificationRun.created_at)
        .all()
    )
    events = (
        session.query(ExecutionEvent)
        .filter(ExecutionEvent.execution_id == execution.id)
        .order_by(ExecutionEvent.created_at)
        .all()
    )
    data = execution_brief(execution)
    data.update(
        {
            "steps": [step_brief(s) for s in steps],
            "approvals": [approval_brief(a) for a in approvals],
            "verifications": [verification_brief(v) for v in verifications],
            "timeline": [execution_event_brief(e) for e in events],
        }
    )
    return {"ok": True, "data": data}


@router.post("/api/executions/{execution_id}/steps")
def add_step(
    execution_id: str,
    payload: ExecutionStepCreateRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    execution, _role = _load_execution(session, execution_id, principal.user_id)
    if is_terminal(execution.status):
        raise ApiError("execution_closed", "This execution is already closed.", 409)
    step = ExecutionStep(
        id=new_id(),
        execution_id=execution.id,
        org_id=execution.org_id,
        seq=_next_seq(session, execution.id),
        title=payload.title.strip(),
        kind=payload.kind,
        postcondition=(payload.postcondition or "").strip() or None,
    )
    session.add(step)
    _record(
        session,
        execution,
        principal.user_id,
        "step.added",
        execution.status,
        execution.status,
        {"step_id": step.id, "kind": step.kind},
    )
    session.commit()
    return {"ok": True, "data": step_brief(step)}


@router.post("/api/executions/{execution_id}/advance")
def advance_execution(
    execution_id: str,
    payload: ExecutionAdvanceRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    execution, role = _load_execution(session, execution_id, principal.user_id)
    target = payload.status

    # A verdict is not an advance: it must come from recorded verification.
    if target in {SUCCEEDED, "failed", "partially_verified", "unknown"}:
        raise ApiError(
            "verification_required",
            "An outcome cannot be set directly. Record verification for this execution.",
            409,
        )
    if target == BLOCKED and role not in REVIEWER_ROLES and execution.created_by != principal.user_id:
        raise ApiError("forbidden", "Your role cannot block this execution.", 403)

    _apply_status(
        session,
        execution,
        target,
        principal.user_id,
        "execution.advanced",
        {"detail": payload.detail} if payload.detail else None,
    )
    audit(
        session,
        execution.org_id,
        principal.user_id,
        "execution.advanced",
        "execution",
        execution.id,
        {"to": target},
    )
    session.commit()
    return {"ok": True, "data": execution_brief(execution)}


@router.post("/api/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: str,
    payload: ExecutionCancelRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    execution, role = _load_execution(session, execution_id, principal.user_id)
    if role not in REVIEWER_ROLES and execution.created_by != principal.user_id:
        raise ApiError("forbidden", "Your role cannot cancel this execution.", 403)
    execution.cancelled_by = principal.user_id
    _apply_status(
        session,
        execution,
        CANCELLED,
        principal.user_id,
        "execution.cancelled",
        {"reason": payload.reason, "rollback": False},
    )
    audit(
        session,
        execution.org_id,
        principal.user_id,
        "execution.cancelled",
        "execution",
        execution.id,
        {"reason": payload.reason},
    )
    session.commit()
    request.app.state.hub.emit(
        execution.org_id, "execution.cancelled", "execution", execution.id, principal.user_id
    )
    data = execution_brief(execution)
    # Stated in the response so no caller can read cancellation as undo.
    data["rollback_performed"] = False
    data["note"] = "Future work is stopped. Actions already taken externally are not reversed."
    return {"ok": True, "data": data}


@router.post("/api/executions/{execution_id}/verify")
def record_verification(
    execution_id: str,
    payload: VerificationRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """Record one independent check of a postcondition.

    This is the only path that can give an execution an outcome. If the
    execution is still ``running`` it first moves to ``verifying``; the outcome
    is then derived from every recorded run, not from the latest one.
    """
    execution, _role = _load_execution(session, execution_id, principal.user_id)
    if is_terminal(execution.status):
        raise ApiError("execution_closed", "This execution is already closed.", 409)
    if execution.status != VERIFYING:
        _apply_status(session, execution, VERIFYING, principal.user_id, "execution.verifying")

    postcondition = (payload.postcondition or "").strip()
    if payload.step_id:
        step = session.get(ExecutionStep, payload.step_id)
        if step is None or step.execution_id != execution.id:
            raise ApiError("not_found", "No accessible step with that id.", 404)
        postcondition = postcondition or (step.postcondition or "")
    if not postcondition:
        raise ApiError(
            "postcondition_required",
            "A verification must state the postcondition it checked.",
            422,
        )

    run = VerificationRun(
        id=new_id(),
        org_id=execution.org_id,
        execution_id=execution.id,
        step_id=payload.step_id,
        postcondition=postcondition,
        result=payload.result,
        source=payload.source,
        evidence_json=json.dumps(payload.evidence, ensure_ascii=False) if payload.evidence else None,
        checked_by=principal.user_id,
    )
    session.add(run)
    session.flush()

    runs = (
        session.query(VerificationRun)
        .filter(VerificationRun.execution_id == execution.id)
        .order_by(VerificationRun.created_at)
        .all()
    )

    # A later check of the same postcondition supersedes an earlier one: an
    # inconclusive check that is resolved by a real read-back should not block
    # the outcome forever. Only the newest result per postcondition counts.
    latest: dict[str, VerificationRun] = {}
    for run in runs:
        latest[run.postcondition] = run
    passed = sum(1 for r in latest.values() if r.result == "passed")
    failed = sum(1 for r in latest.values() if r.result == "failed")
    unknown = sum(1 for r in latest.values() if r.result == "unknown")
    outcome = derive_outcome(passed=passed, failed=failed, unknown=unknown)

    # A conclusion needs every expected postcondition to have a result. The
    # expected set is the postconditions declared on steps, or the one named by
    # the caller when no step declares any. Without this, a single early pass
    # would read as success while the remaining checks had not been recorded.
    steps = (
        session.query(ExecutionStep)
        .filter(ExecutionStep.execution_id == execution.id)
        .all()
    )
    expected_keys = {s.postcondition for s in steps if s.postcondition} or {postcondition}
    complete = expected_keys <= set(latest)

    # A failure is conclusive immediately: one unmet postcondition is enough to
    # make the claim untrue. Success and partial results wait for completeness.
    applied = False
    if failed > 0 or (passed > 0 and complete):
        try:
            ensure_verdict(execution.status, outcome)
        except IllegalTransition as exc:
            raise ApiError("illegal_transition", str(exc), 409) from exc
        execution.outcome_detail = (
            f"{passed} passed, {failed} failed, {unknown} unknown "
            f"from {len(latest)} distinct postcondition(s) of {len(expected_keys)} expected."
        )
        _apply_status(
            session,
            execution,
            outcome,
            principal.user_id,
            "execution.verified",
            {
                "passed": passed,
                "failed": failed,
                "unknown": unknown,
                "verification_id": run.id,
            },
        )
        applied = True
        audit(
            session,
            execution.org_id,
            principal.user_id,
            f"execution.{outcome}",
            "execution",
            execution.id,
            {"passed": passed, "failed": failed, "unknown": unknown},
        )

    session.commit()
    data = verification_brief(run)
    data["outcome_applied"] = applied
    data["current_status"] = execution.status
    data["totals"] = {"passed": passed, "failed": failed, "unknown": unknown}
    return {"ok": True, "data": data}


@router.post("/api/executions/{execution_id}/approvals")
def request_approval(
    execution_id: str,
    payload: ApprovalCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    execution, _role = _load_execution(session, execution_id, principal.user_id)
    if is_terminal(execution.status):
        raise ApiError("execution_closed", "This execution is already closed.", 409)
    enforce_rate_limit(request, principal, bucket="approval-request")

    if payload.step_id:
        step = session.get(ExecutionStep, payload.step_id)
        if step is None or step.execution_id != execution.id:
            raise ApiError("not_found", "No accessible step with that id.", 404)

    approval = Approval(
        id=new_id(),
        org_id=execution.org_id,
        execution_id=execution.id,
        step_id=payload.step_id,
        requested_by=principal.user_id,
        summary=payload.summary.strip(),
        action_digest=action_digest(payload.summary.strip(), payload.target.strip(), payload.params),
        risk=payload.risk,
        status="pending",
        expires_at=utcnow() + timedelta(minutes=payload.ttl_minutes),
    )
    session.add(approval)

    if execution.status == RUNNING:
        _apply_status(
            session, execution, WAITING_APPROVAL, principal.user_id, "execution.awaiting_approval"
        )
    _record(
        session,
        execution,
        principal.user_id,
        "approval.requested",
        execution.status,
        execution.status,
        {"approval_id": approval.id, "digest": approval.action_digest},
    )
    audit(
        session,
        execution.org_id,
        principal.user_id,
        "approval.requested",
        "approval",
        approval.id,
        {"execution_id": execution.id, "risk": approval.risk},
    )
    session.commit()
    request.app.state.hub.emit(
        execution.org_id, "approval.requested", "approval", approval.id, principal.user_id
    )
    return {"ok": True, "data": approval_brief(approval)}


@router.get("/api/orgs/{org_id}/approvals")
def list_approvals(
    org_id: str,
    status: str = "pending",
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    query = session.query(Approval).filter(Approval.org_id == org_id)
    if status != "all":
        query = query.filter(Approval.status == status)
    rows = query.order_by(Approval.created_at.desc()).limit(200).all()
    for row in rows:
        _expire_if_stale(session, row, principal.user_id)
    session.commit()
    return {"ok": True, "data": {"approvals": [approval_brief(r) for r in rows]}}


@router.post("/api/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """Approve or reject one exact action.

    The reviewer must echo the digest they are deciding on. If the requested
    action has changed since they looked at it, the digest differs and the
    decision is refused: silently authorising the new action is precisely the
    failure this check exists to prevent.
    """
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise ApiError("not_found", "No accessible approval with that id.", 404)
    membership = require_member(session, approval.org_id, principal.user_id)
    if membership.role not in REVIEWER_ROLES:
        raise ApiError("forbidden", "Your role cannot decide approvals.", 403)
    if approval.requested_by == principal.user_id:
        raise ApiError(
            "self_approval",
            "You cannot approve an action you requested.",
            403,
        )

    _expire_if_stale(session, approval, principal.user_id)
    if approval.status == "expired":
        raise ApiError("approval_expired", "This approval has expired.", 409)
    if approval.status != "pending":
        raise ApiError(
            "approval_not_pending",
            f"This approval is already '{approval.status}'.",
            409,
        )
    if payload.action_digest != approval.action_digest:
        raise ApiError(
            "approval_scope_mismatch",
            "The action you are deciding on has changed. Review the current scope.",
            409,
        )

    approval.status = payload.decision
    approval.decided_by = principal.user_id
    approval.decided_at = utcnow()
    approval.decision_note = (payload.note or "").strip() or None

    execution = session.get(Execution, approval.execution_id)
    if execution is not None and execution.status == WAITING_APPROVAL:
        if payload.decision == "approved":
            _apply_status(session, execution, RUNNING, principal.user_id, "execution.resumed")
        else:
            _apply_status(session, execution, BLOCKED, principal.user_id, "execution.blocked")

    _record(
        session,
        execution,
        principal.user_id,
        f"approval.{payload.decision}",
        None,
        None,
        {"approval_id": approval.id, "digest": approval.action_digest},
    )
    audit(
        session,
        approval.org_id,
        principal.user_id,
        f"approval.{payload.decision}",
        "approval",
        approval.id,
        {"execution_id": approval.execution_id},
    )
    session.commit()
    return {"ok": True, "data": approval_brief(approval)}


@router.post("/api/approvals/{approval_id}/consume")
def consume_approval(
    approval_id: str,
    payload: ApprovalConsumeRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """Spend an approval on the action it names, exactly once.

    Returns the authorisation the caller needs before performing the protected
    action. Consuming with a different digest is refused, so an old approval
    cannot be reused for new work.
    """
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise ApiError("not_found", "No accessible approval with that id.", 404)
    require_member(session, approval.org_id, principal.user_id)
    _expire_if_stale(session, approval, principal.user_id)

    if approval.status == "expired":
        raise ApiError("approval_expired", "This approval has expired.", 409)
    if approval.status == "used":
        raise ApiError("approval_already_used", "This approval has already been spent.", 409)
    if approval.status != "approved":
        raise ApiError(
            "approval_not_granted",
            f"This approval is '{approval.status}', not 'approved'.",
            409,
        )
    if payload.action_digest != approval.action_digest:
        raise ApiError(
            "approval_scope_mismatch",
            "This approval does not cover the requested action.",
            409,
        )

    approval.status = "used"
    execution = session.get(Execution, approval.execution_id)
    if execution is not None:
        _record(
            session,
            execution,
            principal.user_id,
            "approval.consumed",
            None,
            None,
            {"approval_id": approval.id, "digest": approval.action_digest},
        )
    audit(
        session,
        approval.org_id,
        principal.user_id,
        "approval.consumed",
        "approval",
        approval.id,
        {"execution_id": approval.execution_id},
    )
    session.commit()
    return {
        "ok": True,
        "data": {
            "authorised": True,
            "approval_id": approval.id,
            "action_digest": approval.action_digest,
            "decided_by": approval.decided_by,
            "expires_at": _stamp(approval.expires_at).isoformat() if approval.expires_at else None,
        },
    }
