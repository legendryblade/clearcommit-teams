"""Organization, membership, and invitation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..join_codes import ensure_code, find_by_code
from ..dependencies import (
    REVIEWER_ROLES,
    get_provisioned_principal,
    get_session,
    require_member,
)
from ..errors import ApiError
from ..models import Invitation, Membership, Organization, Profile, new_id
from ..schemas import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    JoinCodeRequest,
    OrgCreateRequest,
)
from ..security import Principal
from ..serializers import (
    invitation_brief,
    membership_brief,
    organization_brief,
    profile_brief,
)
from .auth import _org_summaries

router = APIRouter(tags=["orgs"])


@router.post("/api/orgs")
def create_organization(
    payload: OrgCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    org = Organization(id=new_id(), name=payload.name.strip(), created_by=principal.user_id)
    session.add(org)
    session.flush()
    # Every company gets a shareable join code immediately.
    ensure_code(session, org)
    membership = Membership(
        id=new_id(), org_id=org.id, user_id=principal.user_id, role="owner"
    )
    session.add(membership)
    audit(session, org.id, principal.user_id, "org.created", "organization", org.id, {"name": org.name})
    session.commit()
    return {
        "ok": True,
        "data": {**organization_brief(org), "role": "owner", "join_code": org.join_code},
    }


@router.post("/api/workspace")
def ensure_personal_workspace(
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """Return the caller's personal workspace, creating it on first use.

    Idempotent: calling it repeatedly never creates a second workspace.
    """
    from ..personal import ensure_personal_organization

    profile = session.get(Profile, principal.user_id)
    display = profile.display_name if profile is not None else ""
    org = ensure_personal_organization(session, principal.user_id, display)
    return {"ok": True, "data": {**organization_brief(org), "role": "owner"}}


@router.get("/api/orgs")
def list_my_organizations(
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    return {"ok": True, "data": {"organizations": _org_summaries(session, principal.user_id)}}


@router.get("/api/orgs/{org_id}")
def get_organization(
    org_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    org = session.get(Organization, org_id)
    if org is None:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    rows = (
        session.query(Membership, Profile)
        .join(Profile, Profile.id == Membership.user_id)
        .filter(Membership.org_id == org_id, Membership.status == "active")
        .order_by(Profile.display_name)
        .all()
    )
    members = [membership_brief(membership, profile) for membership, profile in rows]
    return {
        "ok": True,
        "data": {**organization_brief(org), "members": members},
    }


@router.post("/api/orgs/{org_id}/invitations")
def create_invitation(
    org_id: str,
    payload: InvitationCreateRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles=REVIEWER_ROLES)
    email = payload.email.strip().lower()
    existing = (
        session.query(Membership, Profile)
        .join(Profile, Profile.email == email)
        .filter(
            Membership.org_id == org_id,
            Membership.user_id == Profile.id,
            Membership.status == "active",
        )
        .one_or_none()
    )
    if existing:
        raise ApiError("already_member", "That email is already a member of this organization.", 409)
    invitation = Invitation(
        id=new_id(),
        org_id=org_id,
        email=email,
        role=payload.role,
        invited_by=principal.user_id,
    )
    session.add(invitation)
    audit(
        session,
        org_id,
        principal.user_id,
        "invitation.created",
        "invitation",
        invitation.id,
        {"email": email, "role": payload.role},
    )
    session.commit()
    return {"ok": True, "data": invitation_brief(invitation)}


@router.get("/api/orgs/{org_id}/invitations")
def list_invitations(
    org_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles=REVIEWER_ROLES)
    rows = (
        session.query(Invitation)
        .filter(Invitation.org_id == org_id, Invitation.status == "pending")
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return {"ok": True, "data": {"invitations": [invitation_brief(row) for row in rows]}}


@router.delete("/api/orgs/{org_id}/invitations/{invitation_id}")
def revoke_invitation(
    org_id: str,
    invitation_id: str,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles=REVIEWER_ROLES)
    invitation = session.get(Invitation, invitation_id)
    if invitation is None or invitation.org_id != org_id:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    if invitation.status != "pending":
        raise ApiError("invitation_not_pending", "Only pending invitations can be revoked.", 409)
    invitation.status = "revoked"
    audit(
        session,
        org_id,
        principal.user_id,
        "invitation.revoked",
        "invitation",
        invitation.id,
        {"email": invitation.email},
    )
    session.commit()
    return {"ok": True, "data": invitation_brief(invitation)}


@router.post("/api/join")
def join_with_code(
    payload: JoinCodeRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    """Join an organization with its shareable code.

    A pending invitation for the verified account email supplies the role. With
    no invitation the caller joins with the least-privileged role, so a stolen
    code cannot grant manager rights. The account must always be verified.
    """
    if not principal.email_verified:
        raise ApiError(
            "email_not_verified",
            "Confirm your email address before joining an organization.",
            403,
        )

    org = find_by_code(session, payload.code)
    if org is None:
        raise ApiError("invalid_code", "That join code does not match any organization.", 404)

    membership = (
        session.query(Membership)
        .filter(Membership.org_id == org.id, Membership.user_id == principal.user_id)
        .one_or_none()
    )
    if membership is not None and membership.status == "active":
        return {
            "ok": True,
            "data": {**membership_brief(membership), "organization": organization_brief(org)},
        }

    # A pending invitation for this email decides the role.
    email = (principal.email or "").strip().lower()
    invitation = (
        session.query(Invitation)
        .filter(
            Invitation.org_id == org.id,
            Invitation.email == email,
            Invitation.status == "pending",
        )
        .one_or_none()
    )
    role = invitation.role if invitation is not None else "sales_rep"

    if membership is None:
        membership = Membership(
            id=new_id(), org_id=org.id, user_id=principal.user_id, role=role
        )
        session.add(membership)
    else:
        membership.status = "active"
        membership.role = role
        membership.revoked_at = None

    detail = {"role": role, "via": "join_code"}
    if invitation is not None:
        from datetime import datetime, timezone

        invitation.status = "accepted"
        invitation.accepted_by = principal.user_id
        invitation.accepted_at = datetime.now(timezone.utc)
        detail["invitation_id"] = invitation.id

    audit(session, org.id, principal.user_id, "member.joined", "membership", membership.id, detail)
    session.commit()
    request.app.state.hub.emit(
        org.id, "member.joined", "membership", membership.id, principal.user_id
    )
    return {
        "ok": True,
        "data": {**membership_brief(membership), "organization": organization_brief(org)},
    }


@router.get("/api/invitations/mine")
def my_invitations(
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    email = (principal.email or "").strip().lower()
    if not email:
        return {"ok": True, "data": {"invitations": []}}
    rows = (
        session.query(Invitation, Organization)
        .join(Organization, Organization.id == Invitation.org_id)
        .filter(Invitation.email == email, Invitation.status == "pending")
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return {
        "ok": True,
        "data": {
            "invitations": [
                {**invitation_brief(invitation), "organization": organization_brief(org)}
                for invitation, org in rows
            ]
        },
    }


@router.post("/api/invitations/accept")
def accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    invitation = session.get(Invitation, payload.invitation_id)
    if invitation is None or invitation.status != "pending":
        raise ApiError("invitation_not_pending", "That invitation is not open.", 404)
    if (principal.email or "").strip().lower() != invitation.email:
        raise ApiError("not_your_invitation", "This invitation was issued to a different email.", 403)
    if not principal.email_verified:
        raise ApiError(
            "email_not_verified",
            "Confirm your email address before joining an organization.",
            403,
        )

    membership = (
        session.query(Membership)
        .filter(Membership.org_id == invitation.org_id, Membership.user_id == principal.user_id)
        .one_or_none()
    )
    if membership is None:
        membership = Membership(
            id=new_id(),
            org_id=invitation.org_id,
            user_id=principal.user_id,
            role=invitation.role,
        )
        session.add(membership)
        event_type = "member.joined"
    elif membership.status == "revoked":
        membership.status = "active"
        membership.role = invitation.role
        membership.revoked_at = None
        event_type = "member.joined"
    else:
        event_type = None

    invitation.status = "accepted"
    invitation.accepted_by = principal.user_id
    invitation.accepted_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    audit(
        session,
        invitation.org_id,
        principal.user_id,
        "invitation.accepted",
        "membership",
        membership.id,
        {"role": membership.role},
    )
    session.commit()
    if event_type:
        request.app.state.hub.emit(
            invitation.org_id, event_type, "membership", membership.id, principal.user_id
        )
    org = session.get(Organization, invitation.org_id)
    return {
        "ok": True,
        "data": {**membership_brief(membership), "organization": organization_brief(org)},
    }


@router.delete("/api/orgs/{org_id}/members/{user_id}")
def revoke_member(
    org_id: str,
    user_id: str,
    request: Request,
    principal: Principal = Depends(get_provisioned_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id, roles={"owner"})
    target = (
        session.query(Membership)
        .filter(Membership.org_id == org_id, Membership.user_id == user_id)
        .one_or_none()
    )
    if target is None or target.status != "active":
        raise ApiError("not_found", "No active member with that id.", 404)
    if target.role == "owner":
        active_owners = (
            session.query(Membership)
            .filter(Membership.org_id == org_id, Membership.role == "owner", Membership.status == "active")
            .count()
        )
        if active_owners <= 1:
            raise ApiError("last_owner", "An organization must keep at least one active owner.", 409)
    target.status = "revoked"
    from datetime import datetime, timezone

    target.revoked_at = datetime.now(timezone.utc)
    audit(
        session,
        org_id,
        principal.user_id,
        "member.revoked",
        "membership",
        target.id,
        {"user_id": user_id},
    )
    session.commit()
    request.app.state.hub.emit(org_id, "member.revoked", "membership", target.id, principal.user_id)
    profile = session.get(Profile, user_id)
    return {"ok": True, "data": membership_brief(target, profile)}
