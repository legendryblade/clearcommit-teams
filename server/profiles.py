"""Profile provisioning for verified identities.

Supabase Auth is the identity source; this module guarantees a local
`profiles` row exists before any route writes data that references it.

SQLite tolerated a missing row (foreign keys were not enforced the same way),
but PostgreSQL rejects it, so provisioning at the dependency boundary is the
only reliable place. It is idempotent and cheap after the first call.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Profile, new_id
from .security import Principal


def ensure_profile(session: Session, principal: Principal) -> Profile:
    """Return the profile for this verified principal, creating it if absent."""
    profile = session.get(Profile, principal.user_id)
    if profile is not None:
        return profile

    email = (principal.email or "").strip().lower()
    display_name = email.split("@", 1)[0] if email else "Teammate"
    profile = Profile(
        id=principal.user_id,
        email=email or f"{principal.user_id}@unknown.invalid",
        display_name=display_name,
    )
    session.add(profile)
    session.commit()
    return profile
