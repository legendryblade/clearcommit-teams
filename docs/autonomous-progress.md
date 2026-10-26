# Autonomous progress

Updated: after release commit `dbcae0a`.

## Delivered (committed)

**Authentication hardening, verified against the live Supabase project**
- Profile provisioning at the dependency boundary (Postgres FK violation fixed)
- JWT clock-skew leeway: 3/8 → 10/10 tokens accepted
- JWKS failures → 401, not 500; missing `cryptography` → clear 500 code
- `/ready` sends `apikey` (was false-reporting an auth outage)
- `.env` is loaded, with real environment taking precedence

**Account isolation (release blocker)**
- Sign-out clears token, socket, and all account-scoped state
- Session-generation guard prevents a previous account's in-flight refresh
  from painting over the new account
- Verified: A signs in → A signs out (A's org gone) → B signs in (B's org only,
  A's org absent)

**Product**
- Sample conversations opt-in; new workspaces start empty, existing data intact
- CSP allows `https://*.supabase.co` (browser sign-in was blocked)
- Team signals copy corrected (computed view, not a "preview")
- `docs/audio-roadmap.md` documents the not-implemented capture subsystem

## Verification

| Check | Result |
|---|---|
| pytest (D: and E:) | 124 passed each |
| Node bridge | 12 passed |
| Backend vs real PostgreSQL 16 | 29 passed |
| Live Supabase API suite | 20/20 passed |
| Account switch / isolation | Pass (A→out→B, no leak) |
| Packaged exe launch | Pass (window present) |
| Migration + rerun | Pass (11 tables, 21 policies) |
| Original interpreter | Untouched, `bfedc9e` |
| D:/E: parity | 89 files identical (only `.env` excluded) |

## Known gaps

1. No live audio capture or transcription — documented only.
2. No Individual-vs-Company onboarding split in the UI (Team tab is the
   company surface; local workspace is individual).
3. Rate limiting is per-process.
4. Invitations are id-based; no email delivery.
5. Supabase RLS is proven on hosted Postgres via `app.user_id`, not via
   PostgREST client tokens end to end.

## Next actions
1. Split onboarding copy: Individual (local) vs Company (org) first-run.
2. Add a manager overview screen using only authorized data.
3. Decide on audio capture scope for the next milestone.
