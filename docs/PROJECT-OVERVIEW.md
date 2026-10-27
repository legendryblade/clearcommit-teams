# ClearCommit Teams — project overview

A working, tested reference for a **multi-tenant team app with a desktop
client**: real accounts, orgs, roles, privacy boundaries, and a reviewed
knowledge loop. Written so the next project can copy the architecture instead
of reinventing it.

## Product

A sales conversation is captured or imported and turned into evidence-linked
observations, each citing the exact line it came from. The author may share an
observation; a manager reviews it; approved guidance becomes team playbook.
Promises made become tracked commitments with an owner, due date, and history.

## Two surfaces, one backend

```
DESKTOP (pywebview)                  WEB (browser)
local SQLite, no account needed      no local state, team data only
audio, coaching, interpretation
        └──────────────┬──────────────────────┘
                       ▼
              FastAPI + Supabase
        accounts · orgs · roles · RLS
```

The surfaces never talk to each other. They share identity and a database. A
desktop conversation reaches the team only on *Save to cloud*.

## Layers

| Layer | Responsibility | Where |
| --- | --- | --- |
| Identity | Sign-up, tokens, provisioning | Supabase Auth, `security.py` |
| Tenancy | Orgs, memberships, roles, invitations, join codes | `routers/orgs.py`, `join_codes.py` |
| Authorization | Membership check per route, 404 across tenants | `dependencies.py` |
| Privacy | Private until shared; personal workspace | `personal.py` |
| Work records | Conversations, utterances, insights, playbook | `models.py` |
| Commitments | Owner, due date, status, history, reminders | `routers/commitments.py` |
| Real-time | Authenticated, org-scoped WebSocket | `events.py` |
| Local workspace | Per-account SQLite, offline-first | `clearcommit_teams/` |
| Audio | Capture, transcription, interpretation | `audio/` |
| Client | One UI for both surfaces, role-aware | `ui/` |
| Execution control | States, approvals, verification, timeline | `routers/executions.py`, `execution_state.py` |

## Five decisions worth copying

1. **Cross-tenant is 404, not 403.** The API never confirms a record exists
   outside your org. Role violations *inside* your org get 403.
2. **The token is the only identity.** No route trusts a client-supplied
   `user_id`, `role`, or `org_id`.
3. **A code is not a permission.** A join code picks the org; the role comes
   from a pending invitation matched to the verified email, else `sales_rep`. A
   leaked code cannot make someone a manager.
4. **Nothing confirms itself.** Commitments start `awaiting_confirmation`;
   insights start `private`. A model proposes, a human accepts.
5. **Sync is explicit.** No background upload, no raw audio transfer.

## Data model

```
profiles ──< memberships >── organizations
                                 │
     ┌───────────────┬───────────┼──────────────┬─────────────┐
conversations  coaching_insights  playbook_entries  approved_messaging
     │                │                 │
utterances       evidence_json    insight_id (set null)
     │
commitments ──< commitment_events
invitations      audit_events · idempotency_records
```

Every org-owned row carries `org_id` and cascades from the org. `utterances`
inherit access via an existence subquery in RLS. `playbook_entries.insight_id`
is `ON DELETE SET NULL`, so approved guidance outlives the insight.
`commitment_events` is append-only.

## Security posture

| Control | Implementation |
| --- | --- |
| Token verification | JWKS (ES256) or shared secret, expiry checked |
| Tenant isolation | API membership checks + Postgres RLS |
| Nested access | Utterance policies follow the parent conversation |
| Client secrets | None; anon key only, service-role never used |
| Passwords | scrypt (demo mode only) |
| Writes | Audited; important ones accept `Idempotency-Key` |
| Rate limiting | Per user and per IP |
| Logging | Structured, request ids, no transcript content |

## Testing

`pytest` 275 · `node --test` 12 (bridge client). The backend suite runs against
a real FastAPI app and a real database — SQLite by default, PostgreSQL when
configured. No service-layer mocks. Headless Chrome over CDP covers the
two-client UI flow.

## Execution control plane

Executions turn a goal into work that ends in a verified outcome rather than an
assertion. `server/execution_state.py` is a closed state machine; the API is the
only thing that moves a run and it refuses illegal transitions.

- **States** — `running`, `waiting_approval`, `blocked`, `verifying`, and the
  five distinct endings `succeeded`, `partially_verified`, `failed`, `unknown`,
  `cancelled`. None collapse into a generic "done".
- **Verification is the only path to an outcome.** A run cannot be advanced
  straight to `succeeded`. The result is derived from recorded checks against
  named postconditions; one failed check makes the outcome `failed` even after
  passes. A later check supersedes an earlier one about the same postcondition,
  and nothing is concluded until every expected postcondition has a result.
- **Approvals are bound to one action.** `action_digest` hashes the action,
  target and parameters. The reviewer must echo the digest they are deciding on;
  a changed action is refused. Approvals expire, are single-use, and cannot be
  self-granted.
- **Cancellation is not rollback.** The response says so explicitly and reports
  `rollback_performed: false`.

This is the same evidence-over-assertion rule the rest of the product follows,
applied to execution rather than conversation. Decision records live in
[`engineering/DECISIONS.md`](engineering/DECISIONS.md).

## Known limitations

1. Live capture streams on the default device; quality is not fully
   characterised on this hardware.
2. Interpretation is one-directional per turn.
3. No email delivery, CRM integration, or join-code rotation.
4. Rate limiting is per-process.
5. No performance scoring, by design — the data cannot support it.
6. The execution control plane has no connector behind it yet: verification
   checks are recorded by an authenticated caller, not fetched by the platform.
   `0006_execution_control.sql` has not been executed against hosted Postgres.
7. Workflow state is persisted, but there is no durable scheduler; a restart
   preserves history and never re-runs a step, it simply does not resume one.

## Stack

Python 3.11+ · FastAPI 0.162 · SQLAlchemy 2.1 · pywebview 6.2.1 · Supabase
Auth + Postgres · vanilla HTML/CSS/JS · PyInstaller · Vercel · Render.

See also: [`TEMPLATE-GUIDE.md`](TEMPLATE-GUIDE.md) · [`cloud-architecture.md`](cloud-architecture.md) · [`api.md`](api.md) · [`deployment.md`](deployment.md)
