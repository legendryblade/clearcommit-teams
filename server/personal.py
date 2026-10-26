"""Personal workspaces.

An individual needs a cloud place for their own records without joining a
company. Rather than invent a second tenancy system, a personal workspace is
an organization of one member, flagged ``is_personal``. Membership checks,
audit events and row-level security therefore apply unchanged.

Personal records stay private: no other user is ever added to this workspace,
so organization-based sharing can never expose them.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .audit import audit
from .models import Membership, Organization, new_id


def get_personal_organization(session: Session, user_id: str) -> Organization | None:
    return (
        session.query(Organization)
        .filter(Organization.created_by == user_id, Organization.is_personal.is_(True))
        .one_or_none()
    )


def ensure_personal_organization(session: Session, user_id: str, display_name: str) -> Organization:
    """Return the caller's personal workspace, creating it once if needed."""
    existing = get_personal_organization(session, user_id)
    if existing is not None:
        return existing

    org = Organization(
        id=new_id(),
        name=f"{display_name or 'Personal'} (personal)",
        created_by=user_id,
        is_personal=True,
    )
    session.add(org)
    session.flush()
    session.add(
        Membership(id=new_id(), org_id=org.id, user_id=user_id, role="owner")
    )
    audit(
        session,
        org.id,
        user_id,
        "personal_workspace.created",
        "organization",
        org.id,
        {"personal": True},
    )
    session.commit()
    return org
