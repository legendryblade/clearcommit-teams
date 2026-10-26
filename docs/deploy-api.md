# Deploying the ClearCommit Teams API

Status: **code is ready; no public API has been deployed.** The steps below are
the ones that remain, and they need your hosting account.

## What must run

One long-lived Python process serving `server/`. Vercel cannot host it (no
persistent process or WebSockets), so use Railway or Render.

The service is stateless: Supabase PostgreSQL is the source of truth, so a
restart or redeploy loses nothing. Nothing is written to the container disk.

## Required environment variables

| Variable | Required | Example / note |
| --- | --- | --- |
| `CLEARCOMMIT_SUPABASE_URL` | yes | `https://<project>.supabase.co` |
| `CLEARCOMMIT_SUPABASE_ANON_KEY` | yes | public anon key (safe for the client) |
| `CLEARCOMMIT_SUPABASE_JWKS_URL` | yes | `https://<project>.supabase.co/auth/v1/.well-known/jwks.json` |
| `CLEARCOMMIT_DATABASE_URL` | yes | `postgresql+psycopg://...` Supabase pooler DSN |
| `CLEARCOMMIT_ALLOWED_ORIGINS` | yes | `https://ui-five-blue.vercel.app` |
| `PORT` | injected | the platform sets it; the app binds it on `0.0.0.0` |

Never set the service-role key: the API does not need it.

The database DSN must use the **pooler** host, not the direct `db.` host: the
direct host is IPv6-only and unreachable from most hosts.

## Railway (recommended)

1. New project → Deploy from repo → set **Root Directory** to the repo root.
2. Railway detects the `Procfile` (`web: python -m server`). If not, set the
   start command to `python -m server`.
3. Add the environment variables above.
4. Generate a public domain, then copy it.
5. Verify:
   - `https://<api>/health` → `{"ok":true,"status":"live",...}`
   - `https://<api>/ready` → `{"ok":true,"status":"ready","mode":"supabase","database":"ok"}`

## Render

- Type: **Web Service**; Runtime: Python.
- Build: `pip install -r requirements-server.txt`
- Start: `python -m server`
- Health check path: `/health`
- Add the same environment variables.

## Point the website at it

Edit `ui/js/config.js`:

```js
window.CLEARCOMMIT_API_BASE = "https://<your-api-domain>";
```

Then redeploy the frontend:

```powershell
vercel deploy --prod --yes --cwd ui
```

Also add the site's origin to `CLEARCOMMIT_ALLOWED_ORIGINS` on the API, or the
browser will block the requests.

## Tests to run after deploying

- `GET /health` and `GET /ready` return 200 on the public domain.
- Sign up on the website, create an organization, add an employee by email.
- Sign in as the employee in a second browser profile: the invitation appears
  under Team → Organization without any id being shared.
- Join, then confirm a share/approve round trip across the two sessions.

## Known preconditions

- The `0001_init.sql` and `0002_personal_conversations.sql` migrations must be
  applied to the target database (both are already applied to the project in
  use here).
- Supabase Auth must allow the sign-up method you intend to demo. Email
  confirmation is currently disabled on this project.
