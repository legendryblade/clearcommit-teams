# Cloud architecture: current state and deployment boundary

**Status: not deployed.** This documents what exists, what is verified, and what
remains blocked. No public URL is claimed.

## What runs today

```
Windows desktop (pywebview)  ──┐
  ui/ embedded HTML/CSS/JS     ├──► FastAPI 127.0.0.1:8770 ──► Supabase
Browser at 127.0.0.1:8765 (dev)┘     (server/)                (Auth + Postgres)
        │
        └── local per-account workspace (SQLite under data/workspaces/<key>/)
```

| Piece | Verified | Notes |
| --- | --- | --- |
| HTML/CSS/vanilla JS UI | Yes | Shared by desktop and browser; no build step |
| FastAPI backend | Yes | 27 routes; runs locally |
| Supabase Auth | Yes | ES256 via JWKS, real accounts, live verified |
| Supabase Postgres + RLS | Yes | 11 tables, 21 policies; RLS tested on hosted DB |
| Account/organization isolation | Yes | Cross-org 404, revoked member 404 |
| Account-scoped local workspace | Yes | Guest workspace + per-account folders |
| **Public website** | **No** | Not hosted |
| **Public API** | **No** | Not hosted; only 127.0.0.1 |
| **Custom domain / TLS** | **No** | None configured |
| **Audio capture / transcription** | **No** | `docs/audio-roadmap.md` only |
| **Web↔desktop record sync** | **No** | Only team records sync; personal calls are local |

## Trust boundary

- The desktop never holds a privileged key. It holds a Supabase session token.
- The service-role key and DB password are **not** in the client or repo.
- `/api/auth/config` exposes only the project URL and the public anon key.
- Authorization is server-side. UI hiding is not a control.

## Configuration added for deployment

| Variable | Purpose | Default |
| --- | --- | --- |
| `CLEARCOMMIT_ALLOWED_ORIGINS` | Comma-separated CORS origins | loopback dev origins |
| `CLEARCOMMIT_API_BASE` (host page, `window.CLEARCOMMIT_API_BASE`) | API base injected into the UI | `http://127.0.0.1:8770` |
| `CLEARCOMMIT_SUPABASE_URL` | Enables Supabase mode | unset → demo mode |
| `CLEARCOMMIT_SUPABASE_ANON_KEY` | Public client key | — |
| `CLEARCOMMIT_SUPABASE_JWKS_URL` | Token verification | project JWKS |
| `CLEARCOMMIT_DATABASE_URL` | PostgreSQL DSN (server only) | SQLite demo |
| `CLEARCOMMIT_SERVER_HOST` / `_PORT` | Bind address | `127.0.0.1:8770` |

`CLEARCOMMIT_ALLOWED_ORIGINS=*` is refused at startup.

## What a real deployment requires (blocked on credentials)

1. **API host** (Railway/Render/Fly): run `python -m server` with the Supabase
   variables and `CLEARCOMMIT_ALLOWED_ORIGINS=https://<app-domain>`. Bind
   `0.0.0.0`. TLS terminated by the platform.
2. **Web host** (Vercel/Netlify/Cloudflare Pages): serve `ui/` as static files.
   Inject `window.CLEARCOMMIT_API_BASE = "https://<api-domain>"` before
   `net.js` (a one-line generated config script), or set the server URL in the UI.
3. **DNS**: two A/CNAME records. Not configured.
4. **Secrets**: set in the host's secret manager, never in the repo.

Nothing above has been executed. No account was created, no domain registered.

## Migration safety

`supabase/migrations/0001_init.sql` is idempotent and verified on PostgreSQL 16
and on the hosted Supabase project. It does not override Supabase's `auth`
schema and does not drop data.

## Honest gap list

1. **No public deployment** — cannot verify from another device.
2. **Personal calls are local-only.** Only team records (conversations,
   insights, playbook) live in Postgres and sync. There is no cloud `calls`
   table, no transcript sync, no offline upload queue.
3. **RLS is verified via `app.user_id` on the hosted DB**, not via PostgREST
   client tokens end to end.
4. **No installer/signing**; a PyInstaller folder build exists.
5. **No audio**; capture is documented only.

## Not proposed here

Microservices, Kubernetes, Redis, a second auth system, or a frontend rewrite.
None is needed to reach the milestone above.
