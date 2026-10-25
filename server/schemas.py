"""Request schemas (Pydantic v2). Responses are built as envelope dicts."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignUpRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class SignInRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class OrgCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(manager|sales_rep|marketing)$")


class InvitationAcceptRequest(BaseModel):
    invitation_id: str = Field(min_length=8, max_length=64)


class ConversationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="en", max_length=12)


class UtteranceIn(BaseModel):
    speaker: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=20000)
    lang: str = Field(default="en", max_length=12)
    translation: str | None = Field(default=None, max_length=20000)


class UtteranceBulkRequest(BaseModel):
    utterances: list[UtteranceIn] = Field(min_length=1, max_length=500)


class EvidenceRef(BaseModel):
    utterance_id: str = Field(min_length=8, max_length=64)
    quote: str = Field(min_length=1, max_length=2000)


class InsightCreateRequest(BaseModel):
    conversation_id: str = Field(min_length=8, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    observed_issue: str = Field(min_length=1, max_length=20000)
    suggested_alternative: str = Field(min_length=1, max_length=20000)
    recommended_action: str | None = Field(default=None, max_length=20000)
    uncertainty: str | None = Field(default=None, max_length=20000)
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=50)


class PlaybookCreateRequest(BaseModel):
    insight_id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    scenario: str = Field(min_length=1, max_length=20000)
    response: str = Field(min_length=1, max_length=20000)
    discovery_questions: list[str] = Field(default_factory=list, max_length=20)


class PlaybookUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scenario: str | None = Field(default=None, min_length=1, max_length=20000)
    response: str | None = Field(default=None, min_length=1, max_length=20000)
    discovery_questions: list[str] | None = Field(default=None, max_length=20)


class ApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class MessagingCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    claim_text: str = Field(min_length=1, max_length=20000)


class CheckClaimsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
