"""Approved-messaging endpoints (marketing drafts, reviewer publishing)
plus the sales-versus-approved-messaging claim check.

Marketing can author and edit drafts. Only reviewers publish. Published
claims are the reference set for the claim check, which reports its findings
as a simple term-overlap heuristic and never rewrites a claim by itself.
"""

from __future__ import annotations

import re

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
from ..models import ApprovedMessaging, new_id
from ..schemas import CheckClaimsRequest, MessagingCreateRequest
from ..security import Principal
from ..serializers import messaging_brief

router = APIRouter(tags=["messaging"])

AUTHOR_ROLES = {"marketing", "manager", "owner"}
WORD_RE = re.compile(r"[a-z0-9']{4,}")
STOPWORDS = {
    "that", "this", "with", "from", "they", "have", "will", "your", "their",
    "about", "which", "there", "these", "those", "into", "than", "then",
    "when", "what", "where", "more", "most", "also", "been", "were", "does",
}


def _terms(text: str) -> set[str]:
    return {word for word in WORD_RE.findall(text.lower()) if word not in STOPWORDS}


def load_messaging(session: Session, messaging_id: str, user_id: str) -> ApprovedMessaging:
    entry = session.get(ApprovedMessaging, messaging_id)
    if entry is None:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    require_member(session, entry.org_id, user_id)
    return entry


@router.post("/api/orgs/{org_id}/messaging")
def create_messaging(
    org_id: str,
    payload: MessagingCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles=AUTHOR_ROLES)
    entry = ApprovedMessaging(
        id=new_id(),
        org_id=org_id,
        title=payload.title.strip(),
        claim_text=payload.claim_text.strip(),
        status="draft",
        created_by=principal.user_id,
    )
    session.add(entry)
    audit(
        session,
        org_id,
        principal.user_id,
        "messaging.drafted",
        "approved_messaging",
        entry.id,
        {"title": entry.title},
    )
    session.commit()
    request.app.state.hub.emit(
        org_id, "messaging.drafted", "approved_messaging", entry.id, principal.user_id
    )
    return {"ok": True, "data": messaging_brief(entry)}


@router.get("/api/orgs/{org_id}/messaging")
def list_messaging(
    org_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    membership = require_member(session, org_id, principal.user_id)
    query = session.query(ApprovedMessaging).filter(ApprovedMessaging.org_id == org_id)
    if membership.role not in AUTHOR_ROLES:
        query = query.filter(ApprovedMessaging.status == "published")
    rows = query.order_by(ApprovedMessaging.updated_at.desc()).all()
    return {"ok": True, "data": {"entries": [messaging_brief(row) for row in rows]}}


@router.patch("/api/messaging/{messaging_id}")
def update_messaging(
    messaging_id: str,
    payload: MessagingCreateRequest,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    entry = load_messaging(session, messaging_id, principal.user_id)
    require_member(session, entry.org_id, principal.user_id, roles=AUTHOR_ROLES)
    if entry.status != "draft":
        raise ApiError(
            "published_immutable",
            "Published messaging cannot be edited in place. Create a new draft instead.",
            409,
        )
    entry.title = payload.title.strip()
    entry.claim_text = payload.claim_text.strip()
    audit(
        session,
        entry.org_id,
        principal.user_id,
        "messaging.edited",
        "approved_messaging",
        entry.id,
        {"title": entry.title},
    )
    session.commit()
    return {"ok": True, "data": messaging_brief(entry)}


@router.post("/api/messaging/{messaging_id}/publish")
def publish_messaging(
    messaging_id: str,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    entry = load_messaging(session, messaging_id, principal.user_id)
    require_member(session, entry.org_id, principal.user_id, roles=REVIEWER_ROLES)
    enforce_rate_limit(request, principal, bucket="publish")
    if entry.status == "published":
        return {"ok": True, "data": messaging_brief(entry)}
    from datetime import datetime, timezone

    entry.status = "published"
    entry.published_by = principal.user_id
    entry.published_at = datetime.now(timezone.utc)
    audit(
        session,
        entry.org_id,
        principal.user_id,
        "messaging.published",
        "approved_messaging",
        entry.id,
        {"title": entry.title},
    )
    session.commit()
    request.app.state.hub.emit(
        entry.org_id, "messaging.published", "approved_messaging", entry.id, principal.user_id
    )
    return {"ok": True, "data": messaging_brief(entry)}


@router.post("/api/orgs/{org_id}/messaging/check-claims")
def check_claims(
    org_id: str,
    payload: CheckClaimsRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    enforce_rate_limit(request, principal, bucket="check-claims")
    published = (
        session.query(ApprovedMessaging)
        .filter(ApprovedMessaging.org_id == org_id, ApprovedMessaging.status == "published")
        .all()
    )
    text_terms = _terms(payload.text)
    results = []
    for entry in published:
        claim_terms = _terms(entry.claim_text)
        if not claim_terms:
            continue
        overlap = sorted(text_terms & claim_terms)
        ratio = len(overlap) / len(claim_terms)
        if ratio >= 0.6:
            status = "aligned"
            explanation = "This wording closely tracks the published claim."
        elif ratio >= 0.3:
            status = "partial"
            explanation = "Some of the published claim is missing from this wording."
        else:
            status = "not_covered"
            explanation = "This published claim is not reflected in the wording."
        results.append(
            {
                "messaging_id": entry.id,
                "title": entry.title,
                "status": status,
                "matched_terms": overlap[:20],
                "coverage": round(ratio, 2),
                "explanation": explanation,
                "claim_text": entry.claim_text,
            }
        )
    return {
        "ok": True,
        "data": {
            "method": "term-overlap heuristic; review with a human before using",
            "results": results,
            "unmatched_terms": sorted(text_terms - {t for r in results for t in r["matched_terms"]})[:40],
        },
    }
