"""Commitments: promises made in conversations, tracked to completion.

The rules that make this honest:

* A commitment is created in ``awaiting_confirmation``. The owner and date are
  claims until a person confirms them; a model never names an owner.
* Only a member of the organization can create one.
* The owner, the creator, or a reviewer can change status.
* Every state change writes an audit event.
* Evidence keeps the quote and the line id it came from, so the claim can be
  checked against the transcript later.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

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
from ..models import Commitment, CommitmentEvent, Conversation, Membership, Profile, new_id
from ..schemas import CommitmentCreateRequest, CommitmentUpdateRequest
from ..security import Principal
from ..serializers import commitment_brief, commitment_event_brief

router = APIRouter(tags=["commitments"])

STATUSES = {"awaiting_confirmation", "open", "blocked", "done", "cancelled"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _actor_names(session: Session, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    return {
        profile.id: profile.display_name
        for profile in session.query(Profile).filter(Profile.id.in_(user_ids)).all()
    }


def _record(
    session: Session,
    commitment: Commitment,
    actor_id: str,
    action: str,
    from_status: str | None,
    to_status: str | None,
    detail: dict | None = None,
) -> None:
    import json

    session.add(
        CommitmentEvent(
            id=new_id(),
            commitment_id=commitment.id,
            org_id=commitment.org_id,
            actor_id=actor_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )


def _load(session: Session, commitment_id: str, user_id: str) -> tuple[Commitment, Membership]:
    commitment = session.get(Commitment, commitment_id)
    if commitment is None:
        raise ApiError("not_found", "No accessible commitment with that id.", 404)
    membership = require_member(session, commitment.org_id, user_id)
    if commitment.visibility != "team" and commitment.owner_id != user_id and commitment.created_by != user_id:
        raise ApiError("not_found", "No accessible commitment with that id.", 404)
    return commitment, membership


@router.post("/api/orgs/{org_id}/commitments")
def create_commitment(
    org_id: str,
    payload: CommitmentCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    enforce_rate_limit(request, principal, bucket="commitment-create")

    owner_id = payload.owner_id or principal.user_id
    # Naming someone else as the owner requires them to be in the org.
    if owner_id != principal.user_id:
        their = (
            session.query(Membership)
            .filter(
                Membership.org_id == org_id,
                Membership.user_id == owner_id,
                Membership.status == "active",
            )
            .one_or_none()
        )
        if their is None:
            raise ApiError("invalid_owner", "That person is not in this organization.", 422)

    if payload.due_on and not _DATE.match(payload.due_on):
        raise ApiError("invalid_due_date", "The due date must be YYYY-MM-DD.", 422)

    if payload.conversation_id:
        conversation = session.get(Conversation, payload.conversation_id)
        if conversation is None or conversation.org_id != org_id:
            raise ApiError("not_found", "No accessible conversation with that id.", 404)

    commitment = Commitment(
        id=new_id(),
        org_id=org_id,
        conversation_id=payload.conversation_id,
        owner_id=owner_id,
        created_by=principal.user_id,
        title=payload.title.strip(),
        evidence_quote=(payload.evidence_quote or "").strip() or None,
        evidence_utterance_id=payload.evidence_utterance_id,
        due_on=payload.due_on,
        status="awaiting_confirmation",
        visibility=payload.visibility,
    )
    session.add(commitment)
    audit(
        session,
        org_id,
        principal.user_id,
        "commitment.created",
        "commitment",
        commitment.id,
        {"title": commitment.title, "owner_id": owner_id},
    )
    _record(session, commitment, principal.user_id, "created", None, commitment.status)
    session.commit()
    request.app.state.hub.emit(
        org_id, "commitment.created", "commitment", commitment.id, principal.user_id
    )
    return {"ok": True, "data": commitment_brief(commitment)}


@router.get("/api/orgs/{org_id}/commitments")
def list_commitments(
    org_id: str,
    scope: str = "team",
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    query = session.query(Commitment).filter(Commitment.org_id == org_id)
    if scope == "mine":
        query = query.filter(Commitment.owner_id == principal.user_id)
    elif scope == "team":
        query = query.filter(Commitment.visibility == "team")
    else:
        raise ApiError("invalid_scope", "scope must be 'mine' or 'team'.", 422)

    rows = query.order_by(Commitment.created_at.desc()).all()
    people = _actor_names(session, {r.owner_id for r in rows} | {r.created_by for r in rows})
    payload = []
    for row in rows:
        data = commitment_brief(row)
        data["owner_name"] = people.get(row.owner_id)
        data["created_by_name"] = people.get(row.created_by)
        payload.append(data)
    return {"ok": True, "data": {"commitments": payload}}


@router.patch("/api/commitments/{commitment_id}")
def update_commitment(
    commitment_id: str,
    payload: CommitmentUpdateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    commitment, membership = _load(session, commitment_id, principal.user_id)
    is_reviewer = membership.role in REVIEWER_ROLES
    is_owner = commitment.owner_id == principal.user_id
    is_creator = commitment.created_by == principal.user_id
    if not (is_owner or is_creator or is_reviewer):
        raise ApiError("forbidden", "You cannot change this commitment.", 403)

    previous_status = commitment.status
    changes: dict[str, object] = {}

    if payload.status is not None:
        if payload.status not in STATUSES:
            raise ApiError("invalid_status", "Unknown commitment status.", 422)
        # Only the owner or a reviewer can declare it finished.
        if payload.status == "done" and not (is_owner or is_reviewer):
            raise ApiError("forbidden", "Only the owner or a reviewer can complete it.", 403)
        if payload.status != commitment.status:
            changes["status"] = payload.status
            commitment.status = payload.status
            commitment.completed_at = (
                datetime.now(timezone.utc) if payload.status == "done" else None
            )

    if payload.due_on is not None:
        if payload.due_on and not _DATE.match(payload.due_on):
            raise ApiError("invalid_due_date", "The due date must be YYYY-MM-DD.", 422)
        if payload.due_on != (commitment.due_on or ""):
            changes["due_on"] = payload.due_on
            commitment.due_on = payload.due_on or None

    if payload.owner_id is not None and payload.owner_id != commitment.owner_id:
        their = (
            session.query(Membership)
            .filter(
                Membership.org_id == commitment.org_id,
                Membership.user_id == payload.owner_id,
                Membership.status == "active",
            )
            .one_or_none()
        )
        if their is None:
            raise ApiError("invalid_owner", "That person is not in this organization.", 422)
        changes["owner_id"] = payload.owner_id
        commitment.owner_id = payload.owner_id

    if payload.title is not None and payload.title.strip() != commitment.title:
        changes["title"] = payload.title.strip()
        commitment.title = payload.title.strip()

    # Confirming the owner and the date is the step that turns a suggestion
    # into a real commitment.
    if (
        commitment.status == "awaiting_confirmation"
        and commitment.due_on
        and (is_owner or is_creator or is_reviewer)
    ):
        commitment.status = "open"
        changes["status"] = "open"

    if not changes:
        return {"ok": True, "data": commitment_brief(commitment)}

    audit(
        session,
        commitment.org_id,
        principal.user_id,
        "commitment.updated",
        "commitment",
        commitment.id,
        changes,
    )
    _record(
        session,
        commitment,
        principal.user_id,
        "updated",
        previous_status,
        commitment.status,
        changes,
    )
    session.commit()
    request.app.state.hub.emit(
        commitment.org_id, "commitment.updated", "commitment", commitment.id, principal.user_id
    )
    return {"ok": True, "data": commitment_brief(commitment)}


@router.get("/api/commitments/{commitment_id}")
def get_commitment(
    commitment_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    commitment, _membership = _load(session, commitment_id, principal.user_id)
    data = commitment_brief(commitment)
    people = _actor_names(session, {commitment.owner_id, commitment.created_by})
    data["owner_name"] = people.get(commitment.owner_id)
    data["created_by_name"] = people.get(commitment.created_by)
    return {"ok": True, "data": data}

@router.get("/api/commitments/{commitment_id}/history")
def commitment_history(
    commitment_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    commitment, _membership = _load(session, commitment_id, principal.user_id)
    rows = (
        session.query(CommitmentEvent)
        .filter(CommitmentEvent.commitment_id == commitment.id)
        .order_by(CommitmentEvent.created_at)
        .all()
    )
    people = _actor_names(session, {row.actor_id for row in rows})
    payload = []
    for row in rows:
        data = commitment_event_brief(row)
        data["actor_name"] = people.get(row.actor_id)
        payload.append(data)
    return {"ok": True, "data": {"history": payload}}


@router.get("/api/orgs/{org_id}/reminders")
def reminders(
    org_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """What needs attention now: overdue, due today, and blocked.

    This is a view over commitments the caller may already see. It is not a
    notification system and nothing is sent anywhere.
    """
    from datetime import date

    require_member(session, org_id, principal.user_id)
    today = date.today().isoformat()
    rows = (
        session.query(Commitment)
        .filter(
            Commitment.org_id == org_id,
            Commitment.status.in_(("awaiting_confirmation", "open", "blocked")),
            Commitment.visibility == "team",
        )
        .all()
    )
    people = _actor_names(session, {r.owner_id for r in rows})
    overdue, due_today, blocked, undated = [], [], [], []
    for row in rows:
        data = commitment_brief(row)
        data["owner_name"] = people.get(row.owner_id)
        if row.status == "blocked":
            blocked.append(data)
        elif not row.due_on:
            undated.append(data)
        elif row.due_on < today:
            overdue.append(data)
        elif row.due_on == today:
            due_today.append(data)
    return {
        "ok": True,
        "data": {
            "today": today,
            "overdue": overdue,
            "due_today": due_today,
            "blocked": blocked,
            "undated": undated,
            "counts": {
                "overdue": len(overdue),
                "due_today": len(due_today),
                "blocked": len(blocked),
                "undated": len(undated),
            },
        },
    }
