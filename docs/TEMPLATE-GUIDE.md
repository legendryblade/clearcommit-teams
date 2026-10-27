# Forking this project as a template

This repository is a working multi-tenant team app. The next project can reuse
its **architecture and mechanics** while changing the domain. This guide says
what to keep, what to rename, and what to delete.

## 1. Copy the repository

```powershell
git clone https://github.com/legendryblade/clearcommit-teams <new-project>
cd <new-project>
Remove-Item -Recurse -Force .git
git init
git add .
git commit -m "Initial structure from ClearCommit Teams template"
```

Do not copy `.env`, `data/`, `server_data/`, `dist/`, `build/`, or `.venv`.
They are gitignored and regenerate.

## 2. Keep unchanged — these are domain-neutral

| Path | Why it is reusable |
| --- | --- |
| `server/security.py` | Token issue/verify, password hashing, JWKS |
| `server/profiles.py` | Provision a profile from a verified token |
| `server/personal.py` | A personal workspace as an organization of one |
| `server/join_codes.py` | Short, dictation-safe, non-privileging codes |
| `server/dependencies.py` | `require_member`, role gates, the 404 policy |
| `server/rate_limit.py` | Sliding-window limiter |
| `server/idempotency.py` | Replay protection for important writes |
| `server/events.py` | Org-scoped WebSocket hub |
| `server/audit.py` | Append-only audit events |
| `server/errors.py` | Typed errors + response envelope |
| `server/db.py` | Engine, sessions, Postgres RLS row context |
| `clearcommit_teams/paths.py` | Project-confined, per-account paths |
| `ui/js/net.js` | HTTP + WebSocket client, token handling, offline |
| `ui/js/bridge.js` | Desktop/local transport with an allowlist |
| `tests/server/conftest.py` | Two-user, two-org fixtures |
| `supabase/migrations/0001_init.sql` | Tenancy + RLS *pattern* |

Copy these verbatim. They encode decisions that took real debugging: 404 over
403, token-only identity, the WDM-KS capture trap, the pywebview-vs-browser
discriminator, idempotent writes.

## 3. Rename — mechanical

| Old | New | Where |
| --- | --- | --- |
| `clearcommit_teams` | `<your package>` | Python package, imports, `pyproject.toml` |
| `CLEARCOMMIT_*` | `<YOUR>_*` | env vars in `server/config.py`, docs, `.env.example` |
| `ClearCommit Teams` | your product name | UI strings, window title, README |
| `clearcommit-teams.db` | `<product>.db` | `server/` data dir, `clearcommit_teams/paths.py` |

Verify with a search before you start:

```powershell
git grep -n -i "clearcommit" -- . ':!*.md'
```

## 4. Replace — the domain layer

These carry the sales-coaching meaning. Rewrite them for the new domain; keep
their **shape**.

| File | What to change |
| --- | --- |
| `server/models.py` | Entities. Keep `org_id`, timestamps, `visibility`, cascade rules |
| `server/routers/*.py` | Resources and their authorization |
| `server/schemas.py` | Request validation |
| `server/serializers.py` | Response shapes |
| `clearcommit_teams/coaching.py` | Domain rules → your domain logic |
| `clearcommit_teams/providers/` | Model adapter; keep the interface |
| `ui/js/app.js`, `ui/js/team.js` | Views and copy |
| `clearcommit_teams/demo_data.py` | Sample content (keep it opt-in) |

Two domain concepts are worth porting regardless of product:

- **Evidence**: any generated claim stores the source id and the exact quote.
- **Confirmation**: generated records start unconfirmed; a human promotes them.

## 5. Delete

| Path | Why |
| --- | --- |
| `docs/PROJECT-OVERVIEW.md`, `docs/TEMPLATE-GUIDE.md` | Replace with your own |
| `docs/audio-roadmap.md` | Only if you keep audio |
| `clearcommit_teams/audio/` | Only if your product has no audio |
| `supabase/migrations/0002…0005` | Rewrite for your schema |
| `dist/`, `build/` | Build output |

## 6. Reuse the deployment shape

| Piece | Setting |
| --- | --- |
| API | Docker (`Dockerfile`) or `python -m server`; bind `$PORT` on `0.0.0.0` |
| Web | static `ui/` on Vercel; set `window.CLEARCOMMIT_API_BASE` in `js/config.js` |
| DB | Supabase Postgres; **pooler** DSN, never the IPv6-only `db.` host |
| CORS | `CLEARCOMMIT_ALLOWED_ORIGINS`; `null` is required for the desktop app |
| Secrets | environment only; never commit `.env` |

The Render blueprint (`render.yaml`) and `Dockerfile` work unchanged apart from
names.

## 7. Traps this repository already paid for

Read these before changing the corresponding area.

1. **Postgres enforces FKs that SQLite does not.** A missing profile row broke
   invitation acceptance only in production. Provision at the dependency layer.
2. **Supabase signs ES256.** `cryptography` must be installed, and a JWKS
   lookup failure must map to 401, not 500.
3. **Clock skew.** The issuer's clock can lead the host's; without leeway,
   freshly issued tokens fail `iat`.
4. **A browser on `127.0.0.1` is still a browser.** Detect the desktop shell by
   `window.pywebview`, not by hostname, or the web build renders panels it
   cannot use.
5. **Device selection by peak is wrong.** WDM-KS endpoints answer a one-shot
   recording but cannot stream; rank by host API and fall back to the system
   default.
6. **The client bridge has an allowlist.** A new backend method is invisible to
   the UI until it is added to `ui/js/bridge.js`.
7. **CORS `null`.** `file://` pages send `Origin: null`; without it the desktop
   app cannot authenticate against a hosted API.
8. **Sync is not automatic.** Anything local reaches the server only on an
   explicit action.

## 8. Checklist for the new project

- [ ] Rename package, env prefix, product strings
- [ ] Rewrite models, routers, schemas, serializers for the new domain
- [ ] Keep: 404 policy, token-only identity, join codes, audit, idempotency
- [ ] Update RLS policies to match the new tables
- [ ] Rewrite tests for the new domain, keeping the two-user fixtures
- [ ] Replace docs: overview, API, deployment, README
- [ ] Deploy API and web; verify `/health` and `/ready`
- [ ] Verify cross-tenant denial with real tokens
- [ ] Verify the desktop app against the hosted API (CORS `null`)
