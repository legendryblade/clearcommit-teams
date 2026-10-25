"""Idempotency protection for important writes.

A client may send ``Idempotency-Key: <opaque string>`` on a write that must
not be applied twice (sharing, approving, publishing, accepting an
invitation). The first successful request records the key against the
responding resource; a replay returns the recorded result instead of acting
again. Two clients racing with the same key are serialized by the unique
constraint, so exactly one write wins.

Keys are scoped per user and endpoint so one user's key can never collide
with another's, and a key is reusable only for the endpoint it was minted on.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import IdempotencyRecord, new_id

HEADER = "idempotency-key"
MAX_KEY_LENGTH = 200


def key_from(request: Request) -> str | None:
    raw = request.headers.get(HEADER)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > MAX_KEY_LENGTH:
        raise ApiError(
            "invalid_idempotency_key",
            "Idempotency-Key must be 200 characters or fewer.",
            422,
        )
    return value


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def lookup(session: Session, user_id: str, scope: str, key: str) -> dict | None:
    record = (
        session.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_digest == _digest(key),
        )
        .one_or_none()
    )
    if record is None:
        return None
    try:
        return json.loads(record.response_json)
    except ValueError:
        return None


def remember(
    session: Session,
    user_id: str,
    scope: str,
    key: str,
    response: dict,
    *,
    commit: bool = True,
) -> None:
    session.add(
        IdempotencyRecord(
            id=new_id(),
            user_id=user_id,
            scope=scope,
            key_digest=_digest(key),
            response_json=json.dumps(response, ensure_ascii=False, default=str),
        )
    )
    if not commit:
        return
    try:
        session.commit()
    except IntegrityError:
        # Another request with the same key committed first. Its response is
        # authoritative; the caller re-reads it on the next request.
        session.rollback()
