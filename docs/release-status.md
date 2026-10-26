# Release status

Current as of commit `e88c47e` plus the packaging verification.

## Live deployments

| Surface | URL | Verified |
| --- | --- | --- |
| Web app | https://ui-five-blue.vercel.app | Yes — signup + sign-in work |
| API | https://clearcommit-teams-api.onrender.com | Yes — `/health`, `/ready` 200 |
| Database / auth | Supabase (project in use) | Yes — real ES256 tokens, hosted Postgres |

A new account created on the deployed web app authenticates against the
hosted API and is stored in Supabase. This was verified in a browser with a
network trace, not inferred.

## What works

### Desktop
- Import or type a finalized transcript
- **Live capture** from a microphone or Windows system audio (WASAPI loopback)
- Groq Whisper transcription of captured audio
- Evidence-linked coaching that must cite selected lines
- Playbook draft → review → approval
- Per-account local workspaces (guest workspace before sign-in)
- **Save to cloud** — duplicate-safe sync of a conversation to the account
- Packaged `.exe` with audio capture bundled and device enumeration working

### Web
- Account creation and sign-in against the hosted API
- Team workspace: organizations, roles, invitations by email, sharing,
  approvals, live events
- Honest connection states, including a sleeping host waking up

### Team model
- A manager adds an employee by email and picks a role
- The employee signs in and sees the invitation automatically — no id sharing
- Acceptance matches the verified token email; a different account is refused
- Personal records stay private until explicitly shared

## Verified by test

```
pytest -q                155 passed
node --test ui_bridge     12 passed
live API onboarding      11/11 passed (hosted Supabase)
live web signup           passed (browser, network trace)
audio → transcript        'Hello team this is a live capture test of clear commit.'
```

## Not implemented, stated plainly

| Missing | Detail |
| --- | --- |
| Translation | No machine translation. Text is stored as supplied. |
| Speaker diarization | The capture gate emits utterances; it does not separate speakers. |
| Email delivery | Invitations are created in-app; nothing is emailed. |
| CRM integration | None. |
| Manager analytics | Counts from authorized records only; no scoring or trends. |
| Audio retention | Raw audio is discarded after transcription. No recordings are stored. |
| Packaged transcription key | The `.exe` does not read `.env`; set `GROQ_API_KEY` in the environment to enable transcription there. |
| Microphone on this machine | Reported pure silence during testing, so microphone capture is unconfirmed on this hardware. System audio is confirmed. |

## Known behaviour worth knowing

- The Render free tier sleeps after ~15 minutes idle. The app retries with an
  honest "first load can take up to 30 seconds" message instead of claiming to
  be offline.
- Capture is a local operation: no recording starts without pressing Start,
  and nothing is uploaded until you save or share.
