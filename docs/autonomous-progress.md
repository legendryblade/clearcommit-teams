# Autonomous progress

Updated: mission start.

## Completed this session (uncommitted)

- **Supabase live**: project reachable, migration applied (11 tables, 21 RLS policies), 20/20 live API checks passed against hosted Postgres.
- **Fixed: profile provisioning** — Supabase users had no `profiles` row before `/api/auth/me`, so invitation acceptance violated `audit_events_actor_id_fkey` (Postgres-only; SQLite hid it). Now provisioned in a dependency (`server/profiles.py`).
- **Fixed: `/ready` false outage** — health probe sent no `apikey`, Supabase returned 401.
- **Fixed: `.env` never loaded** — server read `os.environ` only.
- **Fixed: ES256/JWKS crash** — missing `cryptography` caused HTTP 500; JWKS lookup errors now return 401.
- **Fixed: clock-skew 401s** — Supabase `iat` leads local clock; ~50% of fresh tokens were rejected. Added `jwt_leeway_seconds` (default 60). Verified 10/10 accepted.
- **Fixed: sign-out / account switch** — 401 left a dead token and stale account UI; `clearAccountState()` now clears token, socket, orgs, data.
- **Changed: sample seeding is opt-in** (`CLEARCOMMIT_TEAMS_SEED_SAMPLES=1`); new installs start empty. Existing data untouched.
- **Fixed: CSP** blocked `https://*.supabase.co`, breaking browser sign-in.
- **Tests**: 124 passing (was 117), plus new profile-provisioning regression test.

## Current state
- Backend runs in Supabase mode from `.env` (gitignored).
- Dev server on 8765 for UI automation.
- Uncommitted changes present (see `git status`).

## Known gaps
- No audio capture subsystem (documented plan only).
- Team signals still labelled as local aggregate; verify copy.
- Packaged exe not rebuilt since these changes.

## Next action
1. Full regression + packaged rebuild.
2. Account-isolation verification (tap-through, logout, cross-org).
3. UI pass on Individual vs Company clarity.
4. Document audio roadmap.
5. Commit + release report.
