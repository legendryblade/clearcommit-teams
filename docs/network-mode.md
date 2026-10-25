# ClearCommit Teams — Networked Team Workspace

A shared workspace where a team turns everyday work into reviewed, reusable guidance. Two people on different machines, in the same organization, can share an insight, review it, and publish it to a common playbook — with tenant isolation enforced server-side.

The original interpreter at `D:\new dir` is untouched and independent. This project has its own repository, environment, database, and configuration.

## What is implemented

| Capability | Status |
| --- | --- |
| FastAPI service with typed schemas | Implemented |
| Authentication (demo mode; Supabase config-gated) | Implemented — see [Authentication](#authentication) |
| Organizations, invitations, memberships, roles | Implemented |
| Server-side authorization on every protected route | Implemented |
| Conversations (private by default) + utterances | Implemented |
| Coaching insights with evidence references | Implemented |
| Explicit insight share flow + audit trail | Implemented |
| Playbook draft → review → approve → revise | Implemented |
| Approved messaging (marketing drafts, reviewer publishes) | Implemented |
| Real-time events over authenticated WebSocket | Implemented |
| Offline state that never claims synchronization | Implemented |
| Row-level security SQL migrations | Implemented (apply to Supabase/Postgres) |
| Desktop client network view | Implemented |

Not implemented, deliberately: live audio capture, automatic transcription, performance scoring of individuals, Slack/Teams integrations, cloud object storage, AI provider calls beyond the existing local rule engine and the optional OpenAI-compatible adapter on the local workspace.

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│ Windows desktop client      │        │ FastAPI backend              │
│ pywebview + embedded HTML   │  HTTPS │  · bearer-token auth         │
│  ┌───────────────────────┐  │ ─────► │  · membership authorization  │
│  │ local workspace       │  │        │  · audit events              │
│  │ (SQLite, offline)     │  │        │  · rate limits, request ids  │
│  ├───────────────────────┤  │        └───────────┬──────────────────┘
│  │ team workspace        │  │◄──────┐            │ SQL
│  │ (network mode)        │  │  WS   │            ▼
│  └───────────────────────┘  │       │  ┌──────────────────────────┐
└─────────────────────────────┘       │  │ PostgreSQL (Supabase)    │
                                      │  │ + RLS policies           │
                                      │  └──────────────────────────┘
```

Two deliberately separate workspaces live in one client:

- **Local workspace** (Conversation desk, Sales coach, Team playbook, Team signals) — single user, SQLite, works with no network.
- **Team workspace** — server-authoritative, shared across machines, requires the backend.

They are never merged, so an offline local view can never masquerade as synchronized team data.

## Quick start (demo mode)

Demo mode is a real networked multi-user backend with server-issued credentials. It is **not** production authentication and the UI says so.

```powershell
# 1. install backend dependencies (same venv as the desktop client)
& ".venv\Scripts\python.exe" -m pip install -r requirements-server.txt

# 2. start the backend (loopback by default)
& ".venv\Scripts\python.exe" -m server
#    -> http://127.0.0.1:8770   (/health, /ready, /api/docs)

# 3. start the desktop app (or launch.bat)
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

Then open **Team workspace** in the left rail, create an account, create an organization, and share an insight.

To demo two users: run the app on a second machine (or a second browser window at `http://127.0.0.1:8765/` after `--web`), sign in as a second account, have the owner record an invitation, and accept it with the invitation id. No email is sent — the id is the handoff.

### Serving other machines

```powershell
$env:CLEARCOMMIT_SERVER_HOST = "0.0.0.0"
& ".venv\Scripts\python.exe" -m server
```

In the client, set the team server URL to `http://<host>:8770`. Use TLS (a reverse proxy) for anything beyond a trusted LAN — bearer tokens are sent in headers.

## Authentication

`CLEARCOMMIT_SUPABASE_URL` selects the mode:

- **unset → demo mode.** The server signs its own HS256 tokens (`server_data/demo_jwt_secret.key`, gitignored) and stores scrypt password hashes. Clearly labeled demo authentication.
- **set → Supabase mode.** Only Supabase Auth tokens are accepted, verified with `CLEARCOMMIT_SUPABASE_JWT_SECRET` or the project JWKS endpoint. No demo sign-up route is enabled in this mode.

In both modes the token is the only identity source. A user id, role, or organization id in a request body is never trusted.

## Data model

`organizations`, `profiles`, `memberships`, `invitations`, `conversations`, `utterances`, `coaching_insights`, `playbook_entries`, `approved_messaging`, `audit_events`.

Every organization-owned row carries `org_id`. Foreign keys cascade from the organization; playbook entries survive insight deletion (`set null`) so approved guidance is not lost; editing approved guidance creates a new version rather than overwriting history.

## Privacy model

- Conversations are private to their author by default. Teammates see one only after the author shares it.
- Sharing an insight shares the selected evidence quotes only — **not** the conversation.
- Managers get no blanket access to raw transcripts.
- The event stream carries ids and types, never transcript content.
- No audio is captured or transmitted anywhere.

## Tests

```powershell
& ".venv\Scripts\python.exe" -m pytest tests -q          # desktop + backend
node --test tests\ui_bridge.test.cjs                     # bridge client
```

Backend tests in `tests/server/` run against the real FastAPI app and a real database. When Supabase env vars are set they run against that database; otherwise against SQLite in demo mode. No service-layer mocks are used. Mock-only tests, if added, are named `test_mock_*`.

Live checks used during development (not part of pytest): a 43-check two-client API script and a browser-driven two-client UI script, both against a running server.

## Environment

See `.env.example`. Nothing is required for demo mode.

| Variable | Purpose |
| --- | --- |
| `CLEARCOMMIT_SUPABASE_URL` | Enables Supabase mode |
| `CLEARCOMMIT_DATABASE_URL` | PostgreSQL/Supabase connection string |
| `CLEARCOMMIT_SUPABASE_JWT_SECRET` | Verify Supabase tokens (HS256) |
| `CLEARCOMMIT_SUPABASE_JWKS_URL` | Verify Supabase tokens (JWKS) |
| `CLEARCOMMIT_SERVER_HOST` / `_PORT` | Bind address (default 127.0.0.1:8770) |
| `CLEARCOMMIT_RATE_LIMIT_PER_MINUTE` | Per-user request budget |
| `CLEARCOMMIT_SERVER_URL` | Client-side backend URL |

## Known limitations

1. **Supabase was not configured in this environment** (no project URL or keys were available), so Supabase Auth flows and the RLS migration have not been executed against a live Supabase project. Demo credentials and SQLite were used for the verified runs. The migration is written and ready to apply.
2. **Local PostgreSQL 16 is installed but its password was unavailable**, so no PostgreSQL run was performed locally. The schema is portable; set `CLEARCOMMIT_DATABASE_URL` to test it.
3. **Invitations are id-based, not emailed.** There is no email provider configured. The UI states this plainly.
4. **Postgres RLS is defense in depth.** Primary authorization is the API layer, because the desktop client never talks to the database directly.
5. **Rate limiting is in-process** (per process, per user). For multiple backend replicas, move it to shared storage.
6. The desktop application itself requires `pywebview` and WebView2; the Team view is a web surface inside the same shell.
