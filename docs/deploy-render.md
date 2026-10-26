# Deploying the API on Render

Status: **code is ready; nothing has been deployed.** These are the clicks.

## Why Render works here

- It runs a normal long-lived Python process, so WebSockets keep working.
- Vercel cannot do this, which is why the site has no API yet.
- Free tier sleeps after ~15 minutes idle; the first request after that takes
  ~30–60 s. Fine for a demo, not for production.

## One-time setup

1. Render dashboard → **New + → Web Service**.
2. Connect the GitHub repo that contains this project.
3. Settings:

| Field | Value |
| --- | --- |
| Language | Python 3 |
| Branch | your branch |
| Build Command | `pip install -r requirements-server.txt` |
| Start Command | `python -m server` |
| Health Check Path | `/health` |
| Instance | Free |

`runtime.txt` pins Python 3.11.9. Every dependency installs on 3.11 (verified
locally in a clean venv).

4. **Environment variables** (Environment → Add):

| Key | Value |
| --- | --- |
| `CLEARCOMMIT_SUPABASE_URL` | `https://<project>.supabase.co` |
| `CLEARCOMMIT_SUPABASE_ANON_KEY` | the public anon key |
| `CLEARCOMMIT_SUPABASE_JWKS_URL` | `https://<project>.supabase.co/auth/v1/.well-known/jwks.json` |
| `CLEARCOMMIT_DATABASE_URL` | `postgresql+psycopg://...` **pooler** DSN |
| `CLEARCOMMIT_ALLOWED_ORIGINS` | `https://ui-five-blue.vercel.app` |

`PORT` is injected by Render; the server binds it on `0.0.0.0` automatically
and it takes precedence over any local port setting.

Use the **pooler** host for `CLEARCOMMIT_DATABASE_URL`. The direct `db.` host
resolves to IPv6 only and is unreachable from Render.

Never add a service-role key. The API does not use one.

5. Create the service and wait for the first build.

## Verify

```text
https://<service>.onrender.com/health
  {"ok":true,"status":"live","version":"0.2.0"}

https://<service>.onrender.com/ready
  {"ok":true,"status":"ready","mode":"supabase","database":"ok"}
```

If `/ready` reports `"auth": "unreachable"`, the Supabase URL or anon key is
wrong. If it reports `database: unavailable`, the DSN is wrong or still uses
the IPv6-only host.

## Point the website at it

Edit `ui/js/config.js`:

```js
window.CLEARCOMMIT_API_BASE = "https://<service>.onrender.com";
```

Redeploy the frontend:

```powershell
vercel deploy --prod --yes --cwd ui
```

## Fallback if Render is unavailable: a tunnel to this laptop

Only for a live demo; the laptop must stay awake and online.

```powershell
# 1. run the API locally
& ".venv\Scripts\python.exe" -m server

# 2. expose it securely
cloudflared tunnel --url http://127.0.0.1:8770
```

Copy the generated `https://<random>.trycloudflare.com` URL, set it in
`ui/js/config.js`, add that same origin to `CLEARCOMMIT_ALLOWED_ORIGINS`, and
redeploy. The tunnel URL changes each run, so treat this as demo-only.
