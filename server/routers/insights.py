"""Coaching insight endpoints, including the explicit share flow.

Insights are private to their author until the author shares them with the
organization. Evidence references must point at lines of the author's own
conversation; the share action is validated, audited, and only then
announced over the event channel.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..dependencies import enforce_rate_limit, get_provisioned_principal, get_session, require_member
from ..errors import ApiError
from .. import idempotency
from ..models import CoachingInsight, Profile, Utterance, new_id
from ..schemas import InsightCreateRequest
from ..security import Principal
from ..serializers import insight_brief
from .conversations import load_conversation

router = APIRouter(tags=["insights"])


def load_insight(
    session: Session, insight_id: str, user_id: str, *, owner_only: bool = False
) -> CoachingInsight:
    insight = session.get(CoachingInsight, insight_id)
    if insight is None:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    if not owner_only:
        require_member(session, insight.org_id, user_id)
        if insight.owner_id != user_id and insight.visibility != "shared":
            raise ApiError("not_found", "No accessible resource with that id.", 404)
    return insight


@router.post("/api/orgs/{org_id}/insights")
def create_insight(
    org_id: str,
    payload: InsightCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    enforce_rate_limit(request, principal, bucket="insight-create")
    conversation = load_conversation(
        session, org_id, payload.conversation_id, principal.user_id
    )
    valid_ids = {
        row[0]
        for row in session.query(Utterance.id)
        .filter(Utterance.conversation_id == conversation.id)
        .all()
    }
    evidence = []
    for ref in payload.evidence:
        if ref.utterance_id not in valid_ids:
            raise ApiError(
                "invalid_evidence",
                "Every evidence reference must be a line of the selected conversation.",
                422,
            )
        evidence.append({"utterance_id": ref.utterance_id, "quote": ref.quote})
    insight = CoachingInsight(
        id=new_id(),
        org_id=org_id,
        conversation_id=conversation.id,
        owner_id=principal.user_id,
        title=payload.title.strip(),
        observed_issue=payload.observed_issue.strip(),
        suggested_alternative=payload.suggested_alternative.strip(),
        recommended_action=(payload.recommended_action or "").strip() or None,
        uncertainty=(payload.uncertainty or "").strip() or None,
        evidence_json=json.dumps(evidence, ensure_ascii=False),
        visibility="private",
    )
    session.add(insight)
    audit(
        session,
        org_id,
        principal.user_id,
        "insight.created",
        "insight",
        insight.id,
        {"title": insight.title, "evidence_count": len(evidence)},
    )
    session.commit()
    return {"ok": True, "data": insight_brief(insight)}


@router.get("/api/orgs/{org_id}/insights")
def list_insights(
    org_id: str,
    scope: str = "shared",
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    query = session.query(CoachingInsight).filter(CoachingInsight.org_id == org_id)
    if scope == "mine":
        query = query.filter(CoachingInsight.owner_id == principal.user_id)
    elif scope == "shared":
        query = query.filter(CoachingInsight.visibility == "shared")
    else:
        raise ApiError("invalid_scope", "scope must be 'mine' or 'shared'.", 422)
    rows = query.order_by(CoachingInsight.created_at.desc()).all()
    owner_ids = {row.owner_id for row in rows}
    owners = {}
    if owner_ids:
        owners = {
            profile.id: profile
            for profile in session.query(Profile).filter(Profile.id.in_(owner_ids)).all()
        }
    payload = []
    for row in rows:
        data = insight_brief(row, include_evidence=False)
        owner = owners.get(row.owner_id)
        data["author_name"] = owner.display_name if owner else None
        payload.append(data)
    return {"ok": True, "data": {"insights": payload}}


@router.get("/api/insights/{insight_id}")
def get_insight(
    insight_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    insight = load_insight(session, insight_id, principal.user_id)
    data = insight_brief(insight)
    owner = session.get(Profile, insight.owner_id)
    data["author_name"] = owner.display_name if owner else None
    return {"ok": True, "data": data}


@router.post("/api/insights/{insight_id}/share")
def share_insight(
    insight_id: str,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    insight = session.get(CoachingInsight, insight_id)
    if insight is None:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    require_member(session, insight.org_id, principal.user_id)
    enforce_rate_limit(request, principal, bucket="share")
    if insight.owner_id != principal.user_id:
        raise ApiError("forbidden", "Only the author can share this insight.", 403)

    idem_key = idempotency.key_from(request)
    if idem_key:
        recorded = idempotency.lookup(session, principal.user_id, "insight.share", idem_key)
        if recorded is not None:
            return {"ok": True, "data": recorded}

    if insight.visibility == "shared":
        payload = insight_brief(insight)
        if idem_key:
            idempotency.remember(session, principal.user_id, "insight.share", idem_key, payload)
        return {"ok": True, "data": payload}
    insight.visibility = "shared"
    audit(
        session,
        insight.org_id,
        principal.user_id,
        "insight.shared",
        "insight",
        insight.id,
        {"title": insight.title},
    )
    payload = insight_brief(insight)
    if idem_key:
        idempotency.remember(
            session, principal.user_id, "insight.share", idem_key, payload, commit=False
        )
    session.commit()
    request.app.state.hub.emit(
        insight.org_id, "insight.shared", "insight", insight.id, principal.user_id
    )
    return {"ok": True, "data": payload}
