"""Authentication endpoints.

Demo mode only: /api/auth/demo/*. In Supabase mode the desktop client
authenticates against Supabase Auth and presents the resulting JWT; this
backend verifies it. /api/auth/me provisions the local profile row on first
 sighting in either mode.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import Settings
from ..dependencies import get_principal, get_session, get_tokens
from ..errors import ApiError
from ..models import Membership, Organization, Profile, new_id
from ..schemas import SignInRequest, SignUpRequest
from ..security import Principal, hash_password, verify_password
from ..serializers import organization_brief, profile_brief

router = APIRouter(tags=["auth"])


def _limit_auth(request: Request) -> None:
    limiter = request.app.state.limiter
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(f"auth:{client}"):
        raise ApiError(
            "rate_limited", "Too many attempts. Wait a minute and try again.", 429, retryable=True
        )


def _org_summaries(session: Session, user_id: str) -> list[dict]:
    rows = (
        session.query(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .filter(Membership.user_id == user_id, Membership.status == "active")
        .order_by(Organization.name)
        .all()
    )
    return [{**organization_brief(org), "role": membership.role} for membership, org in rows]


@router.get("/api/auth/config")
def auth_config(request: Request):
    """Public client configuration for authentication.

    Only values that are safe in a browser are returned: the Supabase project
    URL and the *anon* (public) key. The service-role key and the JWT secret
    are never exposed here.
    """
    settings: Settings = request.app.state.settings
    if not settings.is_supabase:
        return {"ok": True, "data": {"mode": "demo", "supabase_url": None, "anon_key": None}}
    return {
        "ok": True,
        "data": {
            "mode": "supabase",
            "supabase_url": settings.supabase_url,
            "anon_key": settings.supabase_anon_key,
        },
    }


@router.post("/api/auth/demo/sign-up")
def demo_sign_up(
    payload: SignUpRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    settings: Settings = request.app.state.settings
    if settings.is_supabase:
        raise ApiError(
            "demo_auth_disabled",
            "Demo sign-up is only available in demo mode (no Supabase configured).",
            400,
        )
    _limit_auth(request)
    email = payload.email.strip().lower()
    if session.query(Profile).filter(Profile.email == email).one_or_none():
        raise ApiError("email_taken", "An account with that email already exists.", 409)
    profile = Profile(
        id=new_id(),
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    session.add(profile)
    session.commit()
    token = request.app.state.tokens.issue_demo_token(profile.id, profile.email)
    return {
        "ok": True,
        "data": {"token": token, "mode": "demo", "profile": profile_brief(profile)},
    }


@router.post("/api/auth/demo/sign-in")
def demo_sign_in(
    payload: SignInRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    settings: Settings = request.app.state.settings
    if settings.is_supabase:
        raise ApiError(
            "demo_auth_disabled",
            "Demo sign-in is only available in demo mode (no Supabase configured).",
            400,
        )
    _limit_auth(request)
    email = payload.email.strip().lower()
    profile = session.query(Profile).filter(Profile.email == email).one_or_none()
    if profile is None or not verify_password(payload.password, profile.password_hash):
        raise ApiError("invalid_credentials", "Email or password is incorrect.", 401)
    token = request.app.state.tokens.issue_demo_token(profile.id, profile.email)
    return {
        "ok": True,
        "data": {"token": token, "mode": "demo", "profile": profile_brief(profile)},
    }


@router.get("/api/auth/me")
def me(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    tokens=Depends(get_tokens),
):
    profile = session.get(Profile, principal.user_id)
    if profile is None:
        # Supabase mode: first sighting of a verified token provisions the
        # local profile row. The verified token remains the identity source.
        email = principal.email.strip().lower()
        if not email:
            raise ApiError("profile_missing", "The token does not carry an email claim.", 404)
        display_name = email.split("@", 1)[0]
        profile = Profile(id=principal.user_id, email=email, display_name=display_name)
        session.add(profile)
        session.commit()
    return {
        "ok": True,
        "data": {
            "profile": profile_brief(profile),
            "mode": principal.mode,
            "organizations": _org_summaries(session, profile.id),
        },
    }
