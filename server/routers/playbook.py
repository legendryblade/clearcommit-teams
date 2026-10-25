"""Playbook endpoints: draft, review, approve, revise, and audit history.

Approval is a reviewer action: the approver is always taken from the verified
token, discovery questions are required before approval, and editing an
approved entry creates a new draft version instead of erasing history.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..dependencies import (
    REVIEWER_ROLES,
    enforce_rate_limit,
    get_principal,
    get_session,
    require_member,
)
from ..errors import ApiError
from .. import idempotency
from ..models import AuditEvent, CoachingInsight, PlaybookEntry, Profile, new_id
from ..schemas import ApproveRequest, PlaybookCreateRequest, PlaybookUpdateRequest
from ..security import Principal
from ..serializers import audit_brief, playbook_brief

router = APIRouter(tags=["playbook"])


def load_entry(session: Session, entry_id: str, user_id: str) -> PlaybookEntry:
    entry = session.get(PlaybookEntry, entry_id)
    if entry is None:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    require_member(session, entry.org_id, user_id)
    return entry


@router.post("/api/orgs/{org_id}/playbook")
def create_entry(
    org_id: str,
    payload: PlaybookCreateRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    if payload.insight_id:
        insight = session.get(CoachingInsight, payload.insight_id)
        if insight is None or insight.org_id != org_id:
            raise ApiError("not_found", "No accessible insight with that id.", 404)
        if insight.owner_id != principal.user_id and insight.visibility != "shared":
            raise ApiError("not_found", "No accessible insight with that id.", 404)
    entry = PlaybookEntry(
        id=new_id(),
        org_id=org_id,
        insight_id=payload.insight_id,
        title=payload.title.strip(),
        scenario=payload.scenario.strip(),
        response=payload.response.strip(),
        discovery_json=json.dumps(
            [q.strip() for q in payload.discovery_questions if q.strip()], ensure_ascii=False
        ),
        status="draft",
        created_by=principal.user_id,
    )
    session.add(entry)
    audit(
        session,
        org_id,
        principal.user_id,
        "playbook.drafted",
        "playbook_entry",
        entry.id,
        {"title": entry.title, "insight_id": payload.insight_id},
    )
    session.commit()
    request.app.state.hub.emit(
        org_id, "playbook.drafted", "playbook_entry", entry.id, principal.user_id
    )
    return {"ok": True, "data": playbook_brief(entry)}


@router.get("/api/orgs/{org_id}/playbook")
def list_entries(
    org_id: str,
    status: str | None = None,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    query = session.query(PlaybookEntry).filter(PlaybookEntry.org_id == org_id)
    if status:
        if status not in {"draft", "approved"}:
            raise ApiError("invalid_status", "status must be 'draft' or 'approved'.", 422)
        query = query.filter(PlaybookEntry.status == status)
    rows = query.order_by(PlaybookEntry.updated_at.desc()).all()
    people = {profile.id: profile for profile in session.query(Profile).all()}
    payload = []
    for row in rows:
        data = playbook_brief(row)
        author = people.get(row.created_by)
        data["author_name"] = author.display_name if author else None
        approver = people.get(row.approved_by) if row.approved_by else None
        data["approved_by_name"] = approver.display_name if approver else None
        payload.append(data)
    return {"ok": True, "data": {"entries": payload}}


@router.get("/api/playbook/{entry_id}")
def get_entry(
    entry_id: str,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    entry = load_entry(session, entry_id, principal.user_id)
    return {"ok": True, "data": playbook_brief(entry)}


@router.post("/api/playbook/{entry_id}/approve")
def approve_entry(
    entry_id: str,
    payload: ApproveRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    entry = load_entry(session, entry_id, principal.user_id)
    require_member(session, entry.org_id, principal.user_id, roles=REVIEWER_ROLES)
    enforce_rate_limit(request, principal, bucket="approve")

    idem_key = idempotency.key_from(request)
    if idem_key:
        recorded = idempotency.lookup(session, principal.user_id, "playbook.approve", idem_key)
        if recorded is not None:
            return {"ok": True, "data": recorded}

    if entry.status == "approved":
        payload = playbook_brief(entry)
        if idem_key:
            idempotency.remember(
                session, principal.user_id, "playbook.approve", idem_key, payload
            )
        return {"ok": True, "data": payload}
    questions = []
    try:
        questions = json.loads(entry.discovery_json or "[]")
    except ValueError:
        questions = []
    if not [q for q in questions if str(q).strip()]:
        raise ApiError(
            "discovery_required",
            "Add at least one discovery question before approving this entry.",
            422,
        )
    from datetime import datetime, timezone

    entry.status = "approved"
    entry.approved_by = principal.user_id
    entry.approved_at = datetime.now(timezone.utc)
    audit(
        session,
        entry.org_id,
        principal.user_id,
        "playbook.approved",
        "playbook_entry",
        entry.id,
        {"title": entry.title, "note": payload.note, "version": entry.version},
    )
    approver = session.get(Profile, principal.user_id)
    result = playbook_brief(entry)
    result["approved_by_name"] = approver.display_name if approver else None
    if idem_key:
        idempotency.remember(
            session, principal.user_id, "playbook.approve", idem_key, result, commit=False
        )
    session.commit()
    request.app.state.hub.emit(
        entry.org_id, "playbook.approved", "playbook_entry", entry.id, principal.user_id
    )
    return {"ok": True, "data": result}


@router.patch("/api/playbook/{entry_id}")
def update_entry(
    entry_id: str,
    payload: PlaybookUpdateRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    entry = load_entry(session, entry_id, principal.user_id)
    membership = require_member(session, entry.org_id, principal.user_id)
    is_reviewer = membership.role in REVIEWER_ROLES
    if entry.status == "draft" and entry.created_by != principal.user_id and not is_reviewer:
        raise ApiError("forbidden", "Only the author or a reviewer can edit this draft.", 403)
    if entry.status == "approved" and not is_reviewer:
        raise ApiError("forbidden", "Only a reviewer can revise approved guidance.", 403)
    if entry.status == "approved":
        revision = PlaybookEntry(
            id=new_id(),
            org_id=entry.org_id,
            insight_id=entry.insight_id,
            title=(payload.title or entry.title).strip(),
            scenario=(payload.scenario or entry.scenario).strip(),
            response=(payload.response or entry.response).strip(),
            discovery_json=json.dumps(
                [q.strip() for q in (payload.discovery_questions or json.loads(entry.discovery_json or "[]")) if str(q).strip()],
                ensure_ascii=False,
            ),
            status="draft",
            version=entry.version + 1,
            created_by=principal.user_id,
        )
        session.add(revision)
        audit(
            session,
            entry.org_id,
            principal.user_id,
            "playbook.revised",
            "playbook_entry",
            revision.id,
            {"supersedes": entry.id, "version": revision.version},
        )
        session.commit()
        request.app.state.hub.emit(
            entry.org_id, "playbook.drafted", "playbook_entry", revision.id, principal.user_id
        )
        return {"ok": True, "data": playbook_brief(revision)}
    if payload.title is not None:
        entry.title = payload.title.strip()
    if payload.scenario is not None:
        entry.scenario = payload.scenario.strip()
    if payload.response is not None:
        entry.response = payload.response.strip()
    if payload.discovery_questions is not None:
        entry.discovery_json = json.dumps(
            [q.strip() for q in payload.discovery_questions if q.strip()], ensure_ascii=False
        )
    audit(
        session,
        entry.org_id,
        principal.user_id,
        "playbook.edited",
        "playbook_entry",
        entry.id,
        {"version": entry.version},
    )
    session.commit()
    request.app.state.hub.emit(
        entry.org_id, "playbook.updated", "playbook_entry", entry.id, principal.user_id
    )
    return {"ok": True, "data": playbook_brief(entry)}


@router.get("/api/orgs/{org_id}/audit")
def list_audit(
    org_id: str,
    limit: int = 50,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles=REVIEWER_ROLES)
    limit = max(1, min(int(limit), 200))
    rows = (
        session.query(AuditEvent)
        .filter(AuditEvent.org_id == org_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"ok": True, "data": {"events": [audit_brief(row) for row in rows]}}
