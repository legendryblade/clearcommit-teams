# Supabase go-live checklist

Everything below is written; this is the exact sequence to switch the project
from verified demo mode to verified Supabase mode.

## What you need from the Supabase dashboard

| Value | Where | Used by |
| --- | --- | --- |
| Project URL | Project Settings → API | backend + client |
| `anon` public key | Project Settings → API | **client** (safe to expose) |
| JWT secret (legacy HS256) **or** JWKS URL | Project Settings → API → JWT Settings | **backend only** |
| Database connection string | Project Settings → Database | **backend only** |

**Never** put the `service_role` key in the desktop client, the repo, or any
frontend config. The backend does not need it: it connects with a dedicated
non-superuser role and enforces authorization itself.

## Steps

1. **Create the database role and apply the schema**

   ```powershell
   $env:CLEARCOMMIT_DATABASE_URL = "postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres"
   & ".venv\Scripts\python.exe" -m pip install "psycopg[binary]"
   psql "$env:CLEARCOMMIT_DATABASE_URL" -f supabase\migrations\0001_init.sql
   ```

   Expected: `11` tables and `21` RLS policies in `public`. The migration is
   idempotent and does not override Supabase's own `auth` schema.

2. **Create the backend service role** (Run in the SQL editor)

   ```sql
   create role clearcommit_service login password '<strong-password>' nosuperuser nobypassrls;
   grant usage on schema public to clearcommit_service;
   grant select, insert, update, delete on all tables in schema public to clearcommit_service;
   grant execute on all functions in schema public, auth to clearcommit_service;
   ```

   `nobypassrls` matters: it keeps the policies meaningful even for the API's
   own connection.

3. **Configure the backend**

   ```powershell
   $env:CLEARCOMMIT_SUPABASE_URL = "https://<project>.supabase.co"
   $env:CLEARCOMMIT_SUPABASE_ANON_KEY = "<anon key>"
   $env:CLEARCOMMIT_SUPABASE_JWT_SECRET = "<jwt secret>"
   # or, instead of the secret:
   # $env:CLEARCOMMIT_SUPABASE_JWKS_URL = "https://<project>.supabase.co/auth/v1/.well-known/jwks.json"
   $env:CLEARCOMMIT_DATABASE_URL = "postgresql+psycopg://clearcommit_service:<password>@db.<project>.supabase.co:5432/postgres"
   & ".venv\Scripts\python.exe" -m server
   ```

4. **Confirm the mode**

   ```powershell
   curl.exe http://127.0.0.1:8770/ready
   # {"ok":true,"status":"ready","mode":"supabase","database":"ok"}
   curl.exe http://127.0.0.1:8770/api/auth/config
   # returns the project URL + anon key only
   ```

5. **Create real users**

   The client now calls Supabase Auth directly (`/auth/v1/token`,
   `/auth/v1/signup`). Create the first account in the Team workspace with
   **Create account**; Supabase may require email confirmation before the
   first sign-in. The backend provisions the matching `profiles` row from the
   verified token on first call to `/api/auth/me`.

6. **Run the two-user acceptance test** (`docs/deployment.md` §5). In
   Supabase mode, invitation acceptance still matches on the verified email
   claim, so it works the same way.

7. **Re-run the suites in Supabase mode**

   ```powershell
   $env:CLEARCOMMIT_SUPABASE_URL = "https://<project>.supabase.co"
   & ".venv\Scripts\python.exe" -m pytest tests\server -q
   ```

   The tests create their own organizations and users, so use a disposable
   project or a dedicated schema for this pass.

## What is verified today vs. what this unlocks

| Item | Status |
| --- | --- |
| Schema + 21 RLS policies on real PostgreSQL 16 | **verified** |
| Cross-tenant RLS denial (read + write) | **verified** |
| 19 backend tests against real PostgreSQL | **verified** |
| Idempotent important writes | **verified** |
| Supabase Auth sign-in/sign-up code paths | written, **not executed** (no project) |
| Supabase JWT verification | written, **not executed** (no project) |

## Common failures

| Error | Cause |
| --- | --- |
| `Supabase mode requires ... CLEARCOMMIT_SUPABASE_JWT_SECRET` | no way to verify tokens |
| `Supabase mode requires CLEARCOMMIT_DATABASE_URL` | DB pointer missing |
| `401 invalid_token` | anon key/secret mismatch, or token from another project |
| `/ready` → `auth: unreachable` | project paused or URL wrong |
| RLS denies the backend's own writes | role was created with `bypassrls` off **and** `app.user_id` not set — the API sets it; if calling SQL directly, `set app.user_id = '...'` |
| `password authentication failed` | use the **service role** credentials for the API, not the anon key |
