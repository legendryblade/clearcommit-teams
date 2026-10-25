# Setup and deployment

## 1. Local demo (fastest, no external services)

Requires Windows 10/11, Python 3.11+, and Edge WebView2 (bundled with current Windows/Edge).

```powershell
# Desktop client environment
py -3 -m venv .venv
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m pip install -r requirements-server.txt

# Backend (demo mode: no Supabase configured)
& ".venv\Scripts\python.exe" -m server
#   http://127.0.0.1:8770/health   /ready   /api/docs

# Desktop client
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

Demo mode is labeled in the UI. Accounts, tokens, and data are local to this server.

Data locations:

| Path | Contents |
| --- | --- |
| `server_data/clearcommit-server.db` | Demo database (gitignored) |
| `server_data/demo_jwt_secret.key` | Demo signing secret (gitignored) |
| `data/clearcommit-teams.db` | Local single-user workspace |

Reset the backend: stop it, delete `server_data/`.

## 2. Supabase / PostgreSQL

1. Create a Supabase project (or any PostgreSQL 15+).
2. Apply the schema and RLS policies:

```powershell
psql "$env:CLEARCOMMIT_DATABASE_URL" -f supabase\migrations\0001_init.sql
```

Or paste `supabase/migrations/0001_init.sql` into the Supabase SQL editor.

3. Create a dedicated service role **without** `superuser`/`bypassrls`:

```sql
create role clearcommit_service login password '<strong-password>' nosuperuser nobypassrls;
grant usage on schema public to clearcommit_service;
grant select, insert, update, delete on all tables in schema public to clearcommit_service;
```

4. Set the environment (never commit it):

```powershell
$env:CLEARCOMMIT_SUPABASE_URL = "https://<project>.supabase.co"
$env:CLEARCOMMIT_DATABASE_URL = "postgresql+psycopg://clearcommit_service:<password>@<host>:5432/postgres"
$env:CLEARCOMMIT_SUPABASE_JWT_SECRET = "<project JWT secret>"   # or use JWKS
# $env:CLEARCOMMIT_SUPABASE_JWKS_URL = "https://<project>.supabase.co/auth/v1/.well-known/jwks.json"
```

`psycopg` is needed for PostgreSQL connections:

```powershell
& ".venv\Scripts\python.exe" -m pip install "psycopg[binary]"
```

5. Start the backend. `GET /ready` reports `"mode": "supabase"` when it is live in Supabase mode.

Authentication then happens against Supabase Auth; the desktop client presents the resulting JWT and the backend verifies it. Demo sign-up routes return `demo_auth_disabled`.

## 3. Exposing the backend to a team

```powershell
$env:CLEARCOMMIT_SERVER_HOST = "0.0.0.0"
$env:CLEARCOMMIT_SERVER_PORT = "8770"
& ".venv\Scripts\python.exe" -m server
```

Put TLS in front of it (Caddy, nginx, or a cloud load balancer). Bearer tokens travel in headers; plain HTTP is acceptable only on a trusted LAN.

Client: set the server URL in the Team workspace, or `CLEARCOMMIT_SERVER_URL`.

## 4. Packaging the desktop app

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
# -> dist\ClearCommitTeams\ClearCommitTeams.exe
```

The packaged app stores its local workspace next to the executable. The Team workspace still needs the backend URL.

## 5. Verification checklist

```powershell
& ".venv\Scripts\python.exe" -m pytest tests -q
node --test tests\ui_bridge.test.cjs
curl.exe http://127.0.0.1:8770/health
curl.exe http://127.0.0.1:8770/ready
```

Two-user acceptance (manual):

1. Start the backend; open the desktop app.
2. User A: Team workspace → create account → create organization → create a conversation → create an insight → **Share with team**.
3. User A (owner): record an invitation for user B's email (role `manager`); copy the invitation id.
4. User B (second machine or second `--web` browser): create an account with that email → **Accept a pending invitation**.
5. User B: shared insights are visible → draft a playbook entry → **Approve**.
6. User A: the approved entry appears in the shared playbook **without a manual refresh** (live event) — and after a refresh if the event was missed.
7. User C in another organization must receive 404 for every id from organization A.
8. Revoke user B as owner; B's next request returns 404.
9. Stop the backend: the Team view shows offline, disables writes, and reports that nothing was saved.
10. Restart the backend: the view returns to Live and refetches.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `The team server is unreachable` | Backend not running, wrong URL, or CSP blocking a non-default host — the client CSP allows 127.0.0.1/localhost:8770; rebuild/proxy for other hosts |
| `/ready` returns 503 with `auth: unreachable` | Supabase URL configured but unreachable |
| 401 `invalid_token` | Token expired or signed by a different secret |
| 403 `forbidden` | Correct organization, insufficient role |
| 404 on a known id | Not a member of that organization (by design) |
| `psycopg` missing | `pip install "psycopg[binary]"` for PostgreSQL |
