# Implementation audit — Phase 0

Read-only inspection. No code was modified. Baseline captured before changes.

## Repository state

- Branch `master`, working tree **clean**.
- Commits: `0f413e8` `ba72a0c` `8e58720` `e1d4466` `41c35b7` `dbcae0a` (`a6f8b71` scaffold).
- Original interpreter `D:\new dir` untouched at `bfedc9e`.
- Mirror `E:\ClearCommit-Teams` in sync (`.env` excluded by design).

## Baseline tests (before any change)

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | **136 passed** (3 warnings) |
| `node --test tests\ui_bridge.test.cjs` | **12 passed** |
| `create_app()` route count | 28 paths |
| Migrations | `supabase/migrations/0001_init.sql` (idempotent) |

## What is genuinely implemented

| Area | Status | Evidence |
| --- | --- | --- |
| Desktop shell (pywebview) | Implemented | `clearcommit_teams/app.py` |
| Local workspace (SQLite) | Implemented | 11 tables in `db.py` |
| Local coaching + reports | Implemented | `coaching.py`, rule-based; tested |
| Account-scoped local workspaces | Implemented | `paths.workspace_dir`, `bridge.use_workspace` |
| FastAPI backend (28 routes) | Implemented | local only |
| Supabase Auth (ES256/JWKS) | Implemented, live-verified | real project |
| Organizations / roles / invitations | Implemented | server-enforced |
| Sharing insights, review, playbook | Implemented | tested |
| Company overview | Implemented | real counts |
| Realtime team events | Implemented | WebSocket hub |
| **Hosted website** | **Not deployed** | — |
| **Hosted API** | **Not deployed** | — |
| **Desktop ↔ cloud record sync** | **Not implemented** | see below |
| Audio capture / transcription | **Not implemented** | `docs/audio-roadmap.md` |
| AI provider in network mode | Not implemented | local adapter only |

## The precise missing step (the milestone)

**The desktop workspace and the cloud are two disconnected systems.**

```
Desktop:  ui/js/app.js ──► bridge ──► SQLite `sessions` + `utterances`
Cloud:    ui/js/team.js ──► FastAPI ──► Postgres `conversations` + `utterances`
```

Evidence:

1. `ui/js/app.js` contains **zero** `api/` calls or `ClearCommitNet` usage. Every
   desktop action goes through `bridge.call(...)`.
2. Desktop tables (`sessions`, `analysis_runs`, `insights`) and cloud tables
   (`conversations`, `coaching_insights`) are **different schemas** with no
   shared identifier and no migration between them.
3. The cloud `conversations` table requires `org_id NOT NULL`. An individual
   user with no organization therefore **cannot** create a cloud conversation
   today.
4. Consequence: a conversation created on the desktop **cannot appear on the
   website under any account**, because it is never transmitted anywhere.

So "same record on desktop and web" is not a bug in a working path — the path
does not exist.

## Other defects found during the audit

| # | Severity | Issue |
| --- | --- | --- |
| 1 | High | Desktop never syncs; cloud records only originate from the Team tab |
| 2 | High | Cloud conversation requires `org_id`; no personal cloud space |
| 3 | High | No hosted API; the website cannot work for another machine |
| 4 | Medium | `widget`: cloud `conversations` has no transcript-status/report fields, so "processing status" cannot be represented |
| 5 | Medium | No idempotency on conversation creation (share/approve have it) |
| 6 | Low | LAN access needs Windows Firewall rules + `CLEARCOMMIT_ALLOWED_ORIGINS` |
| 7 | Low | `.env` holds real credentials locally; correctly gitignored |

## Recommended smallest safe change (Phase 4a)

Do **not** merge the two databases. Bridge them with one narrow, additive path:

1. **Allow personal cloud records.** Make `conversations.org_id` nullable
   (migration `0002`), and authorize personal access by `owner_id` alone.
   Organization access still requires membership + sharing. This is additive
   and leaves every existing constraint and policy intact for org records.
2. **Add `POST /api/conversations`** for an owned, personal record
   (`title`, `language`, optional `client_ref`), idempotent via
   `Idempotency-Key`, returning the canonical id.
3. **Add `POST /api/conversations/{id}/utterances`** (bulk, stable order,
   idempotent by `(conversation_id, seq)`), reusing the existing pattern.
4. **Desktop "Save to cloud"** action on an existing local conversation:
   reads local `sessions` + `utterances`, posts once, stores the returned
   `cloud_conversation_id` locally so a retry cannot duplicate.
5. **Tests:** personal record round-trip; second session sees it; another
   account gets 404; retry with the same key creates no duplicate; org records
   unaffected.

This is roughly one focused phase and does not touch audio, AI providers, the
UI framework, or existing org behaviour.

## Note on hosting

- **Vercel `*.vercel.app`** can host `ui/` (static, HTTPS) for testing.
- **Vercel cannot host the FastAPI service** (no long-lived process/WebSockets);
  the API needs Railway/Render/Fly, or a LAN-reachable machine for a local demo.
- A LAN demo (`http://192.168.100.8:8770`) is viable but is **HTTP, no TLS** —
  acceptable only on a trusted network, and requires a firewall rule plus
  `CLEARCOMMIT_ALLOWED_ORIGINS` set to the web origin.

## Phase checklist

- [x] Phase 0 audit (this document)
- [ ] Phase 1 configuration/startup hardening
- [ ] Phase 2 identity consistency (largely proven; re-verify after changes)
- [ ] Phase 3 modes (implemented; covered by tests)
- [ ] Phase 4 canonical records + sync ← proposed next
- [ ] Phase 5 web dashboard
- [ ] Phase 6 AI provider interface
- [ ] Phase 7 audio
- [ ] Phase 8 translation
- [ ] Phase 9 deployment
