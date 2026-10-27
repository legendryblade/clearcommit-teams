# Forking this project as a template

Reuse the **architecture and mechanics**, change the domain. This guide says
what to keep, rename, and delete.

## 1. Copy

```powershell
git clone https://github.com/legendryblade/clearcommit-teams <new-project>
cd <new-project>
Remove-Item -Recurse -Force .git; git init
git add .; git commit -m "Initial structure from ClearCommit Teams template"
```

Do not copy `.env`, `data/`, `server_data/`, `dist/`, `build/`, `.venv` — they
are gitignored and regenerate.

## 2. Keep verbatim — domain-neutral

| Path | Why |
| --- | --- |
| `server/security.py` | Token issue/verify, hashing, JWKS |
| `server/profiles.py` | Provision a profile from a verified token |
| `server/personal.py` | A personal workspace as an org of one |
| `server/join_codes.py` | Short, dictation-safe, non-privileging codes |
| `server/dependencies.py` | `require_member`, role gates, 404 policy |
| `server/rate_limit.py` | Sliding-window limiter |
| `server/idempotency.py` | Replay protection |
| `server/events.py` | Org-scoped WebSocket hub |
| `server/audit.py` | Append-only audit events |
| `server/errors.py` | Typed errors + envelope |
| `server/db.py` | Engine, sessions, RLS row context |
| `clearcommit_teams/paths.py` | Project-confined, per-account paths |
| `ui/js/net.js` | HTTP + WS client, token handling, offline |
| `ui/js/bridge.js` | Desktop transport with an allowlist |
| `tests/server/conftest.py` | Two-user, two-org fixtures |
| `supabase/migrations/0001_init.sql` | Tenancy + RLS *pattern* |

These encode decisions that took real debugging — see §7.

## 3. Rename — mechanical

| Old | New | Where |
| --- | --- | --- |
| `clearcommit_teams` | `<package>` | imports, `pyproject.toml` |
| `CLEARCOMMIT_*` | `<YOUR>_*` | `server/config.py`, docs, `.env.example` |
| `ClearCommit Teams` | product name | UI strings, window title, README |
| `clearcommit-teams.db` | `<product>.db` | `server/`, `paths.py` |

```powershell
git grep -n -i "clearcommit" -- . ':!*.md'
```

## 4. Replace — the domain layer

Keep the **shape**, rewrite the meaning.

| File | Change |
| --- | --- |
| `server/models.py` | Entities; keep `org_id`, timestamps, `visibility`, cascades |
| `server/routers/*.py` | Resources and their authorization |
| `server/schemas.py` / `serializers.py` | Validation / response shapes |
| `clearcommit_teams/coaching.py` | Domain rules |
| `clearcommit_teams/providers/` | Model adapter; keep the interface |
| `ui/js/app.js`, `ui/js/team.js` | Views and copy |
| `clearcommit_teams/demo_data.py` | Sample content (keep it opt-in) |

Two concepts port to any product:

- **Evidence** — every generated claim stores the source id and exact quote.
- **Confirmation** — generated records start unconfirmed; a human promotes them.

## 5. Delete

`docs/PROJECT-OVERVIEW.md`, `docs/TEMPLATE-GUIDE.md` (write your own);
`docs/audio-roadmap.md` and `clearcommit_teams/audio/` if you drop audio;
`supabase/migrations/0002…0005` (rewrite); `dist/`, `build/`.

## 6. Deployment shape

| Piece | Setting |
| --- | --- |
| API | `Dockerfile` or `python -m server`; bind `$PORT` on `0.0.0.0` |
| Web | static `ui/` on Vercel; set `window.CLEARCOMMIT_API_BASE` in `js/config.js` |
| DB | Supabase Postgres; **pooler** DSN, never the IPv6-only `db.` host |
| CORS | `CLEARCOMMIT_ALLOWED_ORIGINS`; `null` required for the desktop app |
| Secrets | environment only; never commit `.env` |

`render.yaml` and `Dockerfile` work unchanged apart from names.

## 7. Traps already paid for

1. **Postgres enforces FKs SQLite does not.** A missing profile row broke
   invitation acceptance only in production. Provision at the dependency layer.
2. **Supabase signs ES256.** Install `cryptography`; map JWKS lookup failure to
   401, not 500.
3. **Clock skew.** Without `jwt_leeway_seconds`, freshly issued tokens fail
   `iat`.
4. **A browser on `127.0.0.1` is still a browser.** Detect the desktop shell by
   `window.pywebview`, not hostname.
5. **Device selection by peak is wrong.** WDM-KS endpoints answer a one-shot
   recording but cannot stream; rank by host API, fall back to the default.
6. **The bridge has an allowlist.** A new backend method is invisible to the UI
   until added to `ui/js/bridge.js`.
7. **CORS `null`.** `file://` pages send `Origin: null`.
8. **Sync is not automatic.** Local data reaches the server only on an explicit
   action.

## 8. Checklist

- [ ] Rename package, env prefix, product strings
- [ ] Rewrite models, routers, schemas, serializers
- [ ] Keep: 404 policy, token-only identity, join codes, audit, idempotency
- [ ] Update RLS for the new tables
- [ ] Rewrite tests, keep the two-user fixtures
- [ ] Replace docs: overview, API, deployment, README
- [ ] Deploy; verify `/health` and `/ready`
- [ ] Verify cross-tenant denial with real tokens
- [ ] Verify the desktop app against the hosted API (CORS `null`)
