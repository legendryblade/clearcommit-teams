# START HERE

Everything you need to run and demo ClearCommit Teams, in one place.

## Run it (60 seconds)

**Desktop app** — the individual workspace:

```powershell
cd D:\ClearCommit-Teams
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

**Team workspace (local web + API)** — manager and employee views:

```powershell
D:\ClearCommit-Teams\launch-team.bat
```

That starts the API on `127.0.0.1:8770` and the web UI on
`http://127.0.0.1:8765`, then opens the browser. No cloud, no sign-in delay.

## Demo accounts (already in the database)

| Who | Email | Password | Role |
| --- | --- | --- | --- |
| Manager | `manager.52624@clearcommit-demo.com` | `DemoTeam2026!` | Owner |
| Employee | `employee.52624@clearcommit-demo.com` | `DemoTeam2026!` | Sales rep |

Company: **Northwind Demo Ltd** · join code **`Z9D9GRE7`**

## What exists, screen by screen

### Desktop app
| Area | What it does |
| --- | --- |
| Onboarding | Choose "on my own" or "work with my team" |
| Conversation desk | Import a transcript, or load a labelled example call |
| Live capture | Microphone and/or system audio; speaker labels come from which stream the audio arrived on |
| Interpretation | Two columns: what they said translated for you, what you said translated for them (optionally voiced) |
| Sales coach | Evidence-linked observations; Groq when a key is present, rule engine otherwise |
| Playbook | Draft, review, approve |
| Save to cloud | Publishes a conversation into your company so the team can see it |

### Team workspace (runs locally or hosted)
| Tab | Employee sees | Manager sees |
| --- | --- | --- |
| Overview | Their shared work and counts | Team counts and what needs a decision |
| Calls | **My calls** | **Team calls**, grouped by teammate |
| Insights | Their private and shared insights | Shared insights from everyone |
| Playbook | Approved guidance | Approved guidance plus approve actions |
| Team | Members | Members, roles, invitations, per-member view |
| Settings | Companies and join code | Same |

## Verified behaviour

- Manager and employee sessions render different Calls headings and notes.
- A manager sees an employee's shared call; private calls return 404.
- Join by code works, is idempotent, and cannot grant manager rights.
- Translation: English to Urdu 0.46s; English to Arabic spoken 2.09s.
- Speaker labels come from the audio source (microphone = you, system = them).
- 173 automated tests pass.

## Known gaps — state these honestly

1. **Live microphone capture** was fixed (voice threshold 0.012 to 0.004) and
   returned a transcript once, but a full conversation has not been toured on
   this hardware.
2. **Translation UI** is two columns; the API path is verified, the new layout
   has not been exercised in a browser.
3. **Sync is explicit.** A desktop conversation reaches the team only when the
   user presses *Save to cloud*.
4. No performance scores or employee rankings: the data cannot support them and
   the product must not imply them.
5. No email invitations (join codes instead), no CRM, no rate limiting on codes.
6. The hosted API at `clearcommit-teams-api.onrender.com` needs a redeploy to
   pick up the CORS fix that lets the desktop app authenticate against it.

## Where things live

```
clearcommit_teams\        desktop app (Python + pywebview)
  audio\                  capture, transcription, interpretation
server\                   FastAPI team backend
supabase\migrations\      database schema and RLS
ui\                       the interface, shared by desktop and web
tests\                    173 tests
docs\                     architecture, deployment, release status
dist\ClearCommitTeams\    packaged Windows build
```

Commits: `1382e1c` is the current head.
