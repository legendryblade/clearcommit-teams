# ClearCommit Teams — Product Requirements

## Personas

- **Riley, sales rep.** Wants to improve without feeling monitored. Will share
  an insight when they choose to.
- **Manny, sales manager.** Wants guidance the team actually agreed to, with
  evidence attached. Does not want to read every transcript.
- **Mia, marketing.** Owns approved product claims and terminology.
- **Olive, owner.** Runs the workspace and controls membership.

## Functional requirements

### F1 — Accounts and membership
- Email-based sign-in.
- An owner creates an organization and invites members by email + role.
- An invitee accepts with the invitation id; acceptance is bound to the
  verified email.
- An owner can revoke a member; the last owner cannot be revoked.
- Roles: `owner`, `manager`, `sales_rep`, `marketing`. The server enforces
  them; a client-supplied role is ignored.

### F2 — Conversations
- Create a conversation in an organization; add finalized lines.
- A conversation is visible only to its author until shared.
- Sharing a conversation is an explicit owner action.

### F3 — Insights
- An insight contains: title, observed issue, suggested alternative,
  recommended action, uncertainty, and evidence references.
- Evidence must reference lines of the source conversation.
- Insights are private to the author by default.
- Sharing an insight is explicit, audited, and shares only the selected
  quotes — never the transcript.

### F4 — Playbook
- A draft can be created from a shared insight or from scratch.
- Approval requires a reviewer role **and** at least one discovery question.
- The approver is recorded server-side from the verified token.
- Editing approved guidance creates a new draft version; history is retained.

### F5 — Approved messaging
- Marketing and reviewers author drafts.
- Only reviewers publish.
- Published claims are immutable; changes require a new draft.
- A claim check compares proposed wording against published claims and
  reports its method honestly.

### F6 — Real-time
- Events are emitted only after the write commits.
- Payloads contain ids and types, never transcript content.
- Delivery is best-effort: clients refetch authoritative state, so duplicate
  or missed events are harmless.
- Clients are subscribed only to organizations their verified session belongs
  to, and reconnect when membership changes.

### F7 — Offline behavior
- When the backend is unreachable, the client shows an offline state, disables
  writes, and states that nothing was saved.
- Recovery refetches authoritative state.

## Non-functional requirements

- **Authorization:** every protected route resolves membership server-side;
  foreign organizations return 404.
- **Data isolation:** database RLS policies as defense in depth.
- **Secrets:** service-role keys, JWT secrets, and provider keys never reach
  the client. The client CSP restricts network destinations.
- **Auditability:** share, approve, publish, invite, revoke, and membership
  changes write audit events.
- **Duplicate protection:** important writes accept an `Idempotency-Key`.
- **Observability:** request ids on every response; structured logs with no
  transcript content.
- **Failure honesty:** provider/network failures surface as errors, never as
  success.

## Acceptance tests

| ID | Test |
| --- | --- |
| A1 | Two clients in one org complete the review workflow |
| A2 | Cross-organization read/write denied with valid ids |
| A3 | Revoked member loses access immediately |
| A4 | Private conversation invisible to teammates until shared |
| A5 | Client-supplied role/approver ignored |
| A6 | Approval blocked without discovery questions |
| A7 | Editing approved guidance creates a new version |
| A8 | Offline: writes disabled, no false success, recovery works |
| A9 | Idempotent replay does not double-apply |
| A10 | Forged/unknown-key tokens rejected with 401 |

## Explicit non-requirements

No live capture, no auto-transcription, no individual scoring, no CRM
integration, no AI in network mode.
