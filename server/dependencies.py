"""FastAPI dependencies: verified principal, DB session, membership checks.

The verified token is the only identity source. Every protected endpoint
resolves membership server-side; a caller outside an organization receives
404 (no existence leak), and a caller with an insufficient role receives 403.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import Membership
from .security import AuthError, Principal, TokenService

ALL_ROLES = {"owner", "manager", "sales_rep", "marketing"}
REVIEWER_ROLES = {"owner", "manager"}


def get_tokens(request: Request) -> TokenService:
    return request.app.state.tokens


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_principal(
    request: Request, tokens: TokenService = Depends(get_tokens)
) -> Principal:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise AuthError("missing_token", "Include an Authorization: Bearer <token> header.")
    principal = tokens.verify(header[7:].strip())
    request.state.user_id = principal.user_id
    return principal


def enforce_rate_limit(request: Request, principal: Principal, bucket: str = "api") -> None:
    limiter = request.app.state.limiter
    if not limiter.allow(f"{bucket}:{principal.user_id}"):
        raise ApiError(
            "rate_limited",
            "Too many requests. Slow down and retry shortly.",
            429,
            retryable=True,
        )


def membership_for(session: Session, org_id: str, user_id: str) -> Membership | None:
    return (
        session.query(Membership)
        .filter(Membership.org_id == org_id, Membership.user_id == user_id)
        .one_or_none()
    )


def require_member(
    session: Session, org_id: str, user_id: str, roles: set[str] | None = None
) -> Membership:
    membership = membership_for(session, org_id, user_id)
    if membership is None or membership.status != "active":
        raise ApiError("not_found", "No accessible resource with that id.", status=404)
    if roles is not None and membership.role not in roles:
        raise ApiError("forbidden", "Your role cannot perform this action.", status=403)
    return membership
