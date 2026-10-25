"""Authentication primitives.

- demo mode: this server issues and verifies its own signed tokens and stores
  scrypt password hashes locally. Local demo flow only, labeled as such.
- supabase mode: only Supabase Auth tokens are accepted and verified against
  the configured JWT secret or JWKS endpoint. Client-supplied user ids,
  emails, or roles are never trusted; the token is the sole identity source.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

import httpx
import jwt as pyjwt
from jwt.exceptions import MissingCryptographyError

from .config import Settings


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    mode: str


def _demo_secret_path(settings: Settings):
    return settings.server_data_dir / "demo_jwt_secret.key"


def load_or_create_demo_secret(settings: Settings) -> bytes:
    path = _demo_secret_path(settings)
    settings.server_data_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        secret = path.read_bytes().strip()
        if secret:
            return secret
    secret = os.urandom(48).hex().encode("ascii")
    path.write_bytes(secret)
    return secret


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


class TokenService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._demo_secret = (
            load_or_create_demo_secret(settings) if settings.mode == "demo" else None
        )
        self._jwks_client: pyjwt.PyJWKClient | None = None

    def issue_demo_token(self, user_id: str, email: str) -> str:
        now = int(time.time())
        payload = {
            "iss": "clearcommit-teams-demo",
            "sub": user_id,
            "email": email,
            "iat": now,
            "exp": now + self.settings.token_ttl_minutes * 60,
        }
        return pyjwt.encode(payload, self._demo_secret, algorithm="HS256")

    def verify(self, token: str) -> Principal:
        try:
            if self.settings.mode == "demo":
                claims = pyjwt.decode(
                    token,
                    self._demo_secret,
                    algorithms=["HS256"],
                    issuer="clearcommit-teams-demo",
                    options={"require": ["exp", "iat", "sub", "iss"]},
                )
            else:
                claims = self._verify_supabase(token)
        except pyjwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired", "Your session expired. Sign in again.") from exc
        except pyjwt.InvalidTokenError as exc:
            raise AuthError("invalid_token", "The session token is not valid.") from exc

        sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip()
        if not sub:
            raise AuthError("invalid_token", "The session token carries no subject.")
        return Principal(user_id=sub, email=email, mode=self.settings.mode)

    def _verify_supabase(self, token: str) -> dict:
        options = {"require": ["exp", "sub"]}
        if self.settings.supabase_jwt_secret:
            return pyjwt.decode(
                token,
                self.settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options=options,
            )
        if self._jwks_client is None:
            url = self.settings.supabase_jwks_url or (
                f"{self.settings.supabase_url}/auth/v1/.well-known/jwks.json"
            )
            self._jwks_client = pyjwt.PyJWKClient(url, cache_keys=True)
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except pyjwt.PyJWKClientError as exc:
            # Unknown key id, unreachable JWKS, or a token that is not signed
            # by this project. This is a rejected credential, not a crash.
            raise pyjwt.InvalidTokenError(str(exc)) from exc
        except MissingCryptographyError as exc:
            raise AuthError(
                "auth_misconfigured",
                "This server cannot verify Supabase tokens: install the 'cryptography' package.",
                500,
            ) from exc
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            options=options,
        )

    def check_reachable(self) -> bool:
        """Ready-check: verify configured external dependencies respond."""
        if self.settings.mode != "supabase":
            return True
        try:
            url = f"{self.settings.supabase_url}/auth/v1/health"
            response = httpx.get(url, timeout=self.settings.request_timeout_seconds)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
