"""Organization join codes.

A company has one short code. An employee types it to join, which replaces the
"copy this UUID to the other person" step. The code identifies the organization
only: the role is still assigned server-side from the pending invitation, or
defaults to the least-privileged role when there is none.

Codes avoid characters that are easy to misread (0/O, 1/I/L) so they can be
read aloud or written on a whiteboard.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from .models import Organization

# No 0, O, 1, I, L: these are the classic dictation mistakes.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


def normalise(code: str | None) -> str:
    """Uppercase and strip separators so 'acme-7k3p' matches 'ACME7K3P'."""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _random_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


def generate_unique_code(session: Session) -> str:
    """Return a code not already used by another organization."""
    for _ in range(20):
        candidate = _random_code()
        exists = (
            session.query(Organization)
            .filter(Organization.join_code == candidate)
            .one_or_none()
        )
        if exists is None:
            return candidate
    raise RuntimeError("Could not allocate a unique join code.")


def ensure_code(session: Session, organization: Organization) -> str:
    """Give an organization a code if it does not already have one."""
    if organization.join_code:
        return organization.join_code
    organization.join_code = generate_unique_code(session)
    session.flush()
    return organization.join_code


def find_by_code(session: Session, code: str) -> Organization | None:
    cleaned = normalise(code)
    if not cleaned:
        return None
    return (
        session.query(Organization)
        .filter(Organization.join_code == cleaned, Organization.is_personal.is_(False))
        .one_or_none()
    )
