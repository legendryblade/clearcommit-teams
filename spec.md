# ClearCommit Teams — Technical Specification

## Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Desktop shell | Python 3.11+ / pywebview 6.2.1 | Windows; WebView2 runtime |
| Client UI | Embedded HTML/CSS/vanilla JS | No build step; CSP-restricted |
| Backend | FastAPI 0.162 + Uvicorn | Typed Pydantic schemas |
| ORM | SQLAlchemy 2.1 | SQLite (demo) / PostgreSQL (Supabase) |
| Auth | Demo HS256 or Supabase Auth JWT | ES256 via JWKS or HS256 secret |
| Real-time | Authenticated WebSocket | In-process hub |
| Packaging | PyInstaller | `build.ps1` → `dist\ClearCommitTeams` |

## Process topology

```
pywebview window (file://)
  ├─ local workspace ──► clearcommit_teams.bridge ──► SQLite (data/)
  └─ team workspace ──► HTTP + WS ──► server/ (FastAPI) ──► PostgreSQL/SQLite
```

The local workspace and the network workspace are separate code paths and
separate storage. They are never merged, so an offline local view cannot
masquerade as synchronized team state.

## Data model

`profiles`, `organizations`, `memberships`, `invitations`, `conversations`,
`utterances`, `coaching_insights`, `playbook_entries`, `approved_messaging`,
`audit_events`, `idempotency_records`.

Rules:
- Every org-owned row carries `org_id`; FKs cascade from the organization.
- `playbook_entries.insight_id` is `ON DELETE SET NULL` so approved guidance
  survives insight deletion.
- `utterances` inherit conversation access via an existence subquery in RLS.
- Idempotency is unique per `(user_id, scope, key_digest)`.

## Authorization model

1. **Transport identity.** Bearer token; verified signature and expiry.
2. **Membership resolution.** Every org-scoped route loads the caller's
   membership; non-members receive **404** (no existence leak).
3. **Role checks.** Reviewer-only actions check role; violations are **403**.
4. **Resource-level checks.** Authorship or `visibility = 'shared'` for
   insights and conversations.
5. **Database RLS.** Policies mirror the above for any direct client access.
   The API sets `app.user_id` per transaction when connected to PostgreSQL.

Client-supplied `user_id`, `role`, `approved_by`, and `status` are ignored for
authorization.

## API surface

27 routes; see `docs/api.md`. Envelope:
`{ok:true,data}` / `{ok:false,error:{code,message,retryable,request_id}}`.

## Real-time protocol

`WS /ws?token=…` → verify → subscribe to active orgs → `subscribed` →
`{id,seq,type,resource,resource_id,org_id,actor_id}`. `ping` → `pong` with
recomputed orgs and `changed:true` when the client must reconnect.

## Idempotency

`Idempotency-Key` on share/approve/publish/accept. First success stores the
response under `(user, scope, sha256(key))`; replay returns the stored
response. A unique constraint serializes concurrent duplicates.

## Security controls

- No privileged key in the client; `/api/auth/config` exposes only URL + anon
  key.
- CSP restricts `connect-src` to the configured backend.
- scrypt password hashing (demo mode only).
- Rate limits per user and per IP for auth.
- Structured logs exclude transcript content, tokens, and secrets.
- Bounded HTTP timeouts for external calls.

## Testing strategy

- `tests/` — local workspace (pytest) + Node bridge client.
- `tests/server/` — real FastAPI app and real database; no service-layer
  mocks. Runs on SQLite and, when configured, PostgreSQL.
- Browser automation (headless Chrome via CDP) for the two-client UI workflow
  and offline behavior.
- Live API script for the 43-check two-client acceptance run.

## Deployment

See `docs/deployment.md` (demo, PostgreSQL, Supabase) and
`docs/supabase-go-live.md` (exact switch-over checklist).

## Known limitations

Documented in `README.md` and `docs/network-mode.md`: Supabase Auth and hosted
RLS are implemented but not verified against a live Supabase database in this
environment; invitations are id-based (no email provider); rate limiting is
per-process.

## Release state

Version 0.2.0. Local workspace feature-complete. Team workspace feature-complete
for the documented scope. See the release report for exact test results.
