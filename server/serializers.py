"""Serialization helpers for API payloads."""

from __future__ import annotations

import json

from .models import (
    ApprovedMessaging,
    AuditEvent,
    CoachingInsight,
    Conversation,
    Invitation,
    Membership,
    Organization,
    PlaybookEntry,
    Profile,
    Utterance,
)


def _iso(value):
    return value.isoformat() if value else None


def profile_brief(profile: Profile) -> dict:
    return {
        "user_id": profile.id,
        "email": profile.email,
        "display_name": profile.display_name,
    }


def organization_brief(org: Organization) -> dict:
    return {"org_id": org.id, "name": org.name, "created_at": _iso(org.created_at)}


def membership_brief(membership: Membership, profile: Profile | None = None) -> dict:
    data = {
        "membership_id": membership.id,
        "org_id": membership.org_id,
        "user_id": membership.user_id,
        "role": membership.role,
        "status": membership.status,
        "created_at": _iso(membership.created_at),
        "revoked_at": _iso(membership.revoked_at),
    }
    if profile is not None:
        data["profile"] = profile_brief(profile)
    return data


def invitation_brief(invitation: Invitation) -> dict:
    return {
        "invitation_id": invitation.id,
        "org_id": invitation.org_id,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "created_at": _iso(invitation.created_at),
        "accepted_at": _iso(invitation.accepted_at),
    }


def conversation_brief(conversation: Conversation, line_count: int | None = None) -> dict:
    data = {
        "conversation_id": conversation.id,
        "org_id": conversation.org_id,
        "owner_id": conversation.owner_id,
        "title": conversation.title,
        "language": conversation.language,
        "visibility": conversation.visibility,
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
    }
    if line_count is not None:
        data["line_count"] = line_count
    return data


def utterance_brief(utterance: Utterance) -> dict:
    return {
        "utterance_id": utterance.id,
        "conversation_id": utterance.conversation_id,
        "seq": utterance.seq,
        "speaker": utterance.speaker,
        "lang": utterance.lang,
        "content": utterance.content,
        "translation": utterance.translation,
    }


def insight_brief(insight: CoachingInsight, include_evidence: bool = True) -> dict:
    data = {
        "insight_id": insight.id,
        "org_id": insight.org_id,
        "conversation_id": insight.conversation_id,
        "owner_id": insight.owner_id,
        "title": insight.title,
        "observed_issue": insight.observed_issue,
        "suggested_alternative": insight.suggested_alternative,
        "recommended_action": insight.recommended_action,
        "uncertainty": insight.uncertainty,
        "visibility": insight.visibility,
        "created_at": _iso(insight.created_at),
        "updated_at": _iso(insight.updated_at),
    }
    if include_evidence:
        try:
            data["evidence"] = json.loads(insight.evidence_json or "[]")
        except ValueError:
            data["evidence"] = []
    return data


def playbook_brief(entry: PlaybookEntry, include_questions: bool = True) -> dict:
    data = {
        "entry_id": entry.id,
        "org_id": entry.org_id,
        "insight_id": entry.insight_id,
        "title": entry.title,
        "scenario": entry.scenario,
        "response": entry.response,
        "status": entry.status,
        "version": entry.version,
        "created_by": entry.created_by,
        "approved_by": entry.approved_by,
        "approved_at": _iso(entry.approved_at),
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }
    if include_questions:
        try:
            data["discovery_questions"] = json.loads(entry.discovery_json or "[]")
        except ValueError:
            data["discovery_questions"] = []
    return data


def messaging_brief(entry: ApprovedMessaging) -> dict:
    return {
        "messaging_id": entry.id,
        "org_id": entry.org_id,
        "title": entry.title,
        "claim_text": entry.claim_text,
        "status": entry.status,
        "created_by": entry.created_by,
        "published_by": entry.published_by,
        "published_at": _iso(entry.published_at),
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }


def audit_brief(event: AuditEvent) -> dict:
    detail = None
    if event.detail_json:
        try:
            detail = json.loads(event.detail_json)
        except ValueError:
            detail = None
    return {
        "event_id": event.id,
        "org_id": event.org_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "detail": detail,
        "created_at": _iso(event.created_at),
    }
