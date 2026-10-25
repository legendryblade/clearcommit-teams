"""Supabase-mode token verification (offline; no project credentials needed).

These tests exercise the verification path with locally generated keys. They
prove the backend rejects tokens it cannot verify with a clean 401 instead of
crashing, which is the failure that shipped before the release sprint.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from server.config import load_settings
from server.security import AuthError, TokenService


def _settings(**overrides):
    env = {
        "CLEARCOMMIT_SUPABASE_URL": "https://example.supabase.co",
        "CLEARCOMMIT_SUPABASE_JWKS_URL": "https://example.supabase.co/auth/v1/.well-known/jwks.json",
        "CLEARCOMMIT_DATABASE_URL": "sqlite:///unused.db",
    }
    env.update(overrides)
    return load_settings(env)


def _es256_token(private_key, *, kid: str = "test-kid", expires_in: int = 600) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "https://example.supabase.co/auth/v1",
            "sub": "11111111-1111-1111-1111-111111111111",
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now,
            "exp": now + expires_in,
            "email": "user@example.com",
        },
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


def test_supabase_mode_is_selected_by_url() -> None:
    assert _settings().mode == "supabase"


def test_supabase_mode_requires_verification_material() -> None:
    with pytest.raises(Exception) as excinfo:
        load_settings(
            {
                "CLEARCOMMIT_SUPABASE_URL": "https://example.supabase.co",
                "CLEARCOMMIT_DATABASE_URL": "sqlite:///unused.db",
            }
        )
    assert "JWT_SECRET" in str(excinfo.value) or "JWKS" in str(excinfo.value)


def test_unknown_signing_key_is_a_401_not_a_crash(monkeypatch) -> None:
    service = TokenService(_settings())
    foreign_key = ec.generate_private_key(ec.SECP256R1())
    token = _es256_token(foreign_key, kid="not-in-jwks")

    with pytest.raises(AuthError) as excinfo:
        service.verify(token)
    assert excinfo.value.code == "invalid_token"
    assert excinfo.value.status == 401


def test_hs256_secret_mode_round_trips(monkeypatch) -> None:
    settings = _settings(
        CLEARCOMMIT_SUPABASE_JWT_SECRET="a-test-secret-value",
        CLEARCOMMIT_SUPABASE_JWKS_URL="",
    )
    service = TokenService(settings)
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "22222222-2222-2222-2222-222222222222",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 600,
            "email": "secret-mode@example.com",
        },
        "a-test-secret-value",
        algorithm="HS256",
    )
    principal = service.verify(token)
    assert principal.user_id == "22222222-2222-2222-2222-222222222222"
    assert principal.email == "secret-mode@example.com"


def test_missing_cryptography_is_reported_as_server_misconfiguration(monkeypatch) -> None:
    """A deployment that forgot the cryptography package gets a clear 500 code."""
    service = TokenService(_settings())
    key = ec.generate_private_key(ec.SECP256R1())
    token = _es256_token(key)

    import server.security as security_module

    def raise_missing(*args, **kwargs):
        raise security_module.MissingCryptographyError("ES256 requires 'cryptography'")

    monkeypatch.setattr(service._jwks_client or type("X", (), {}), "get_signing_key_from_jwt", raise_missing, raising=False)
    monkeypatch.setattr(
        "jwt.PyJWKClient.get_signing_key_from_jwt", staticmethod(raise_missing), raising=False
    )

    with pytest.raises(AuthError) as excinfo:
        service.verify(token)
    assert excinfo.value.code == "auth_misconfigured"
    assert excinfo.value.status == 500
