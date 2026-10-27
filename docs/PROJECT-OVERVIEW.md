# ClearCommit Teams — project overview

A working, tested reference for a **multi-tenant team application with a desktop
client**: real accounts, organizations, roles, privacy boundaries, and a
reviewed knowledge loop.

Written so the next project can copy the architecture rather than reinvent it.

## The product in one paragraph

A sales conversation is captured or imported. The app turns it into
evidence-linked observations, each citing the exact line it came from. The
author chooses to share an observation; a manager reviews it; approved guidance
becomes team playbook. Promises made in the conversation become tracked
commitments with an owner, a due date, and a history.

## Two surfaces, one backend

```
DESKTOP (Windows)                     WEB (browser)
python + pywebview                    same HTML/CSS/JS
local SQLite workspace                no local state
audio capture, coaching,              team data only
interpretation, playbook
        │                                     │
        └──────────────┬──────────────────────┘
                       ▼
              FastAPI  +  Supabase
        accounts · orgs · roles · RLS
```

The surfaces do **not** talk to each other. They share identity and a database.
A desktop conversation reaches the team only when the user presses
*Save to cloud*.

## Layers

| Layer | Responsibility | Where |
| --- | --- | --- |
| Identity | Sign-up, sign-in, tokens, verification | Supabase Auth, `server/security.py` |
| Tenancy | Organizations, memberships, roles, invitations, join codes | `server/routers/orgs.py`, `server/join_codes.py` |
| Authorization | Membership resolution on every route, 404 across tenants | `server/dependencies.py` |
| Privacy | Private until shared; separate personal workspace | `server/personal.py`, `conversations.visibility` |
| Work records | Conversations, utterances, insights, playbook | `server/models.py` |
| Commitments | Promises with owner, due date, status, history, reminders | `server/routers/commitments.py` |
| Real-time | Authenticated WebSocket, org-scoped, minimal payloads | `server/events.py` |
| Local workspace | Per-account SQLite, offline-first | `clearcommit_teams/` |
| Audio | Capture, transcription, interpretation | `clearcommit_teams/audio/` |
| Client | One UI for both surfaces, role-aware | `ui/` |

## The five design decisions worth copying

### 1. Cross-tenant access returns 404, not 403
A caller outside an organization gets `not_found`, so the API never confirms
that a record exists. Role violations *inside* your own org get 403. This is
tested on every route.

### 2. The token is the only identity
No endpoint trusts a client-supplied `user_id`, `role`, `owner_id`, or
`org_id`. Supabase tokens are verified server-side (ES256 via JWKS or HS256
secret). `/api/me` provisions a local profile row on first sighting.

### 3. A code is not a permission
A join code identifies which organization. The role comes from a pending
invitation matched to the **verified email**, otherwise `sales_rep` — the least
privileged role. A leaked code cannot make someone a manager.

### 4. Nothing becomes "confirmed" by itself
A commitment is created `awaiting_confirmation`; it opens only when a person
confirms the owner and the date. An insight is `private` until its author
shares it. A model may propose; a human accepts.

### 5. Sync is an explicit action
Local data stays local. `Save to cloud` posts the conversation into the
company and shares it. There is no background upload and no raw audio transfer.

## Data model

```
profiles ──< memberships >── organizations
                                  │
      ┌───────────────┬───────────┼──────────────┬─────────────┐
 conversations   coaching_insights  playbook_entries  approved_messaging
      │                 │                 │
 utterances        evidence_json    insight_id (set null)
      │
 commitments ──< commitment_events
 invitations      audit_events · idempotency_records
```

- Every organization-owned row carries `org_id`; FKs cascade from the org.
- `utterances` inherit conversation access through an existence subquery in RLS.
- `playbook_entries.insight_id` is `ON DELETE SET NULL`, so approved guidance
  survives insight deletion.
- `commitment_events` is append-only: the life of a promise can be read back.

## Security posture

| Control | Implementation |
| --- | --- |
| Token verification | JWKS (ES256) or shared secret; expiry checked |
| Tenant isolation | API membership checks + Postgres RLS policies |
| Nested access | Utterance policies follow the parent conversation |
| Client secrets | None. Service-role key never used; anon key only |
| Password storage | scrypt (demo mode only) |
| Sensitive writes | Audited; important ones support `Idempotency-Key` |
| Rate limiting | Per user and per IP |
| Logging | Structured, request ids, no transcript content |

## Testing

```
pytest          190 tests
node --test      12 tests (bridge client)
```

The backend suite runs against a real FastAPI app and a real database, over
SQLite by default and over PostgreSQL when configured. No service-layer mocks.
Browser automation (headless Chrome over CDP) covers the two-client UI flow.

## Known limitations

1. Live capture is fixed and streams on the default device, but transcription
   quality on this hardware is not fully characterised.
2. Interpretation is one-directional per turn: their speech is shown to you as
   text; your speech is translated and optionally voiced.
3. No email delivery, CRM integration, or join-code rotation.
4. Rate limiting is per-process.
5. No performance scoring, by design — the data cannot support it.

## Stack and versions

Python 3.11+ · FastAPI 0.162 · SQLAlchemy 2.1 · pywebview 6.2.1 · Supabase
(Auth + Postgres) · vanilla HTML/CSS/JS · PyInstaller 6.22 · Vercel · Render.

## Where to read next

- [`docs/TEMPLATE-GUIDE.md`](TEMPLATE-GUIDE.md) — how to fork this for a new product
- [`docs/cloud-architecture.md`](cloud-architecture.md) — deployment boundary
- [`docs/api.md`](api.md) — endpoints
- [`docs/deployment.md`](deployment.md) — setup and hosting
