"""SQLAlchemy models shared by demo (SQLite) and Supabase (PostgreSQL) modes.

Every organization-owned record carries org_id. Authorization is enforced in
the API layer; the supabase/migrations SQL mirrors this schema on PostgreSQL
with row-level security policies for any direct client access.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    # Short human-typeable code an employee uses to join, instead of a UUID.
    join_code: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    # A personal workspace is an organization of one, so membership, audit and
    # RLS apply unchanged without inventing a second tenancy system.
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
        Index("ix_memberships_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitations_org_status", "org_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    invited_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_org_owner", "org_id", "owner_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # NULL for a personal record: an individual needs no organization.
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(12), default="en")
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    source: Mapped[str] = mapped_column(String(20), default="manual")
    client_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Utterance(Base):
    __tablename__ = "utterances"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_utterance_conversation_seq"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(40))
    lang: Mapped[str] = mapped_column(String(12), default="en")
    content: Mapped[str] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoachingInsight(Base):
    __tablename__ = "coaching_insights"
    __table_args__ = (Index("ix_insights_org_visibility", "org_id", "visibility"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(200))
    observed_issue: Mapped[str] = mapped_column(Text)
    suggested_alternative: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlaybookEntry(Base):
    __tablename__ = "playbook_entries"
    __table_args__ = (Index("ix_playbook_org_status", "org_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    insight_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coaching_insights.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    discovery_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ApprovedMessaging(Base):
    __tablename__ = "approved_messaging"
    __table_args__ = (Index("ix_messaging_org_status", "org_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    claim_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    published_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"))
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    action: Mapped[str] = mapped_column(String(60))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(36))
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "key_digest", name="uq_idempotency_user_scope_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(80))
    key_digest: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Commitment(Base):
    """A promise made in a conversation, with its owner and evidence.

    Separate from a decision or an idea: this is someone explicitly accepting
    responsibility. The owner is confirmed by a human, never inferred.
    """

    __tablename__ = "commitments"
    __table_args__ = (
        Index("ix_commitments_org_status", "org_id", "status"),
        Index("ix_commitments_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # Nullable: a personal commitment belongs to one person, not a company.
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(300))
    # The promise in the speaker's own words, and the line it came from.
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_utterance_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_on: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    # awaiting_confirmation until a human names the owner and the date.
    status: Mapped[str] = mapped_column(String(24), default="awaiting_confirmation")
    visibility: Mapped[str] = mapped_column(String(16), default="team")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The promise this one revises. A changed deadline never overwrites the
    # original: the new commitment points back at it.
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("commitments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommitmentEvent(Base):
    """History: one row per change, so a promise can be read back over time."""

    __tablename__ = "commitment_events"
    __table_args__ = (Index("ix_commitment_events_commitment", "commitment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    commitment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("commitments.id", ondelete="CASCADE")
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Execution(Base):
    """One run of controlled work: a goal becoming verified action.

    Status is a closed set validated by ``execution_state``. ``Verifying`` is a
    distinct state because between "the tool returned" and "the business result
    was confirmed" there is a real interval where nobody knows the outcome.
    """

    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_org_status", "org_id", "status"),
        Index("ix_executions_org_created", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # The goal in the requester's words. Never rewritten by the system.
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="running")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    # Set once verification has produced a verdict; the reason it is what it is.
    outcome_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether cancellation has stopped future work. Never implies rollback.
    cancelled_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExecutionStep(Base):
    """A unit of work inside an execution, with its own evidence trail.

    ``postcondition`` is what must be true afterwards. A step may not be marked
    succeeded unless a verification run checked that postcondition and passed.
    """

    __tablename__ = "execution_steps"
    __table_args__ = (
        UniqueConstraint("execution_id", "seq", name="uq_step_execution_seq"),
        Index("ix_steps_execution", "execution_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("executions.id", ondelete="CASCADE")
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    # read | write | notify | approve. A write requires an approval when the
    # action is classified as protected.
    kind: Mapped[str] = mapped_column(String(20), default="read")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # Human or agent identity that performed the step, once performed.
    assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=True
    )
    # What must be observably true in the business system afterwards.
    postcondition: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Approval(Base):
    """An authorisation bound to one exact action.

    ``action_digest`` is a hash of the action's identity, target and parameters.
    A decision is valid only for that digest. A materially different action
    produces a different digest and therefore cannot reuse this approval.
    """

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_org_status", "org_id", "status"),
        Index("ix_approvals_execution", "execution_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("executions.id", ondelete="CASCADE")
    )
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("execution_steps.id", ondelete="CASCADE"), nullable=True
    )
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    # Human-readable statement of the exact action being authorised.
    summary: Mapped[str] = mapped_column(Text)
    # sha256 over canonical {action, target, params}. Immutable after creation.
    action_digest: Mapped[str] = mapped_column(String(64))
    risk: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # An unused approval past this instant can no longer authorise anything.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VerificationRun(Base):
    """One attempt to establish a postcondition from independent evidence.

    A row here is the only thing that may move an execution out of
    ``Verifying``. A model's assertion is not a row here; only a recorded check
    with a pass, fail or unknown result is.
    """

    __tablename__ = "verification_runs"
    __table_args__ = (Index("ix_verification_execution", "execution_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("executions.id", ondelete="CASCADE")
    )
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("execution_steps.id", ondelete="CASCADE"), nullable=True
    )
    # The postcondition this run was testing, copied so later edits cannot
    # retroactively make a past check look like it tested something else.
    postcondition: Mapped[str] = mapped_column(Text)
    # passed | failed | unknown
    result: Mapped[str] = mapped_column(String(16))
    # Where the evidence came from: a read-back, an API response, a query.
    source: Mapped[str] = mapped_column(String(60))
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_by: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionEvent(Base):
    """Append-only history of an execution, so any state can be explained."""

    __tablename__ = "execution_events"
    __table_args__ = (Index("ix_execution_events_execution", "execution_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("executions.id", ondelete="CASCADE")
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
