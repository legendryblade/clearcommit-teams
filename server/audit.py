"""Audit trail helper. Every sensitive action writes an audit event row."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import AuditEvent, new_id


def audit(
    session: Session,
    org_id: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=new_id(),
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )
