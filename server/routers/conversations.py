"""Conversation and utterance endpoints.

Conversations are private to their owner by default. Other organization
members can see a conversation only after its owner explicitly shares it.
Sharing an insight does not share the underlying conversation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..dependencies import get_principal, get_session, require_member
from ..errors import ApiError
from ..models import Conversation, Profile, Utterance, new_id
from ..schemas import ConversationCreateRequest, UtteranceBulkRequest
from ..security import Principal
from ..serializers import conversation_brief, utterance_brief

router = APIRouter(tags=["conversations"])


def load_conversation(
    session: Session,
    org_id: str,
    conversation_id: str,
    user_id: str,
    *,
    owner_only: bool = False,
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.org_id != org_id:
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    if owner_only:
        if conversation.owner_id != user_id:
            raise ApiError("forbidden", "Only the conversation owner can change it.", 403)
    elif conversation.owner_id != user_id and conversation.visibility != "shared":
        raise ApiError("not_found", "No accessible resource with that id.", 404)
    return conversation


@router.post("/api/orgs/{org_id}/conversations")
def create_conversation(
    org_id: str,
    payload: ConversationCreateRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    conversation = Conversation(
        id=new_id(),
        org_id=org_id,
        owner_id=principal.user_id,
        title=payload.title.strip(),
        language=payload.language,
    )
    session.add(conversation)
    audit(
        session,
        org_id,
        principal.user_id,
        "conversation.created",
        "conversation",
        conversation.id,
        {"title": conversation.title},
    )
    session.commit()
    return {"ok": True, "data": conversation_brief(conversation, line_count=0)}


@router.get("/api/orgs/{org_id}/conversations")
def list_conversations(
    org_id: str,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    rows = (
        session.query(Conversation)
        .filter(
            Conversation.org_id == org_id,
            (Conversation.owner_id == principal.user_id) | (Conversation.visibility == "shared"),
        )
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    ids = [row.id for row in rows]
    counts: dict[str, int] = {}
    if ids:
        counts = dict(
            session.query(Utterance.conversation_id, func.count(Utterance.id))
            .filter(Utterance.conversation_id.in_(ids))
            .group_by(Utterance.conversation_id)
            .all()
        )
    owners = {}
    owner_ids = {row.owner_id for row in rows}
    if owner_ids:
        owners = {
            profile.id: profile
            for profile in session.query(Profile).filter(Profile.id.in_(owner_ids)).all()
        }
    payload = []
    for row in rows:
        data = conversation_brief(row, line_count=counts.get(row.id, 0))
        data["is_mine"] = row.owner_id == principal.user_id
        owner = owners.get(row.owner_id)
        data["owner_name"] = owner.display_name if owner else None
        payload.append(data)
    return {"ok": True, "data": {"conversations": payload}}


@router.get("/api/orgs/{org_id}/conversations/{conversation_id}")
def get_conversation(
    org_id: str,
    conversation_id: str,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    conversation = load_conversation(session, org_id, conversation_id, principal.user_id)
    utterances = (
        session.query(Utterance)
        .filter(Utterance.conversation_id == conversation.id)
        .order_by(Utterance.seq)
        .all()
    )
    data = conversation_brief(conversation, line_count=len(utterances))
    data["is_mine"] = conversation.owner_id == principal.user_id
    data["utterances"] = [utterance_brief(row) for row in utterances]
    return {"ok": True, "data": data}


@router.post("/api/orgs/{org_id}/conversations/{conversation_id}/utterances")
def append_utterances(
    org_id: str,
    conversation_id: str,
    payload: UtteranceBulkRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    conversation = load_conversation(
        session, org_id, conversation_id, principal.user_id, owner_only=True
    )
    next_seq = (
        session.query(func.max(Utterance.seq))
        .filter(Utterance.conversation_id == conversation.id)
        .scalar()
        or 0
    ) + 1
    created = []
    for offset, item in enumerate(payload.utterances):
        utterance = Utterance(
            id=new_id(),
            conversation_id=conversation.id,
            seq=next_seq + offset,
            speaker=item.speaker.strip(),
            lang=item.lang,
            content=item.content,
            translation=item.translation,
        )
        session.add(utterance)
        created.append(utterance)
    audit(
        session,
        org_id,
        principal.user_id,
        "conversation.lines_added",
        "conversation",
        conversation.id,
        {"count": len(created)},
    )
    session.commit()
    return {"ok": True, "data": {"utterances": [utterance_brief(row) for row in created]}}


@router.post("/api/orgs/{org_id}/conversations/{conversation_id}/share")
def share_conversation(
    org_id: str,
    conversation_id: str,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
):
    require_member(session, org_id, principal.user_id)
    conversation = load_conversation(
        session, org_id, conversation_id, principal.user_id, owner_only=True
    )
    if conversation.visibility != "shared":
        conversation.visibility = "shared"
        audit(
            session,
            org_id,
            principal.user_id,
            "conversation.shared",
            "conversation",
            conversation.id,
            {"title": conversation.title},
        )
        session.commit()
        request.app.state.hub.emit(
            org_id, "conversation.shared", "conversation", conversation.id, principal.user_id
        )
    return {"ok": True, "data": conversation_brief(conversation)}
