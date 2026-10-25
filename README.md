# ClearCommit Teams

A local Windows desktop workspace that turns finished sales-conversation transcripts into evidence-linked coaching, then into a team playbook that a manager reviews and approves.

This is an independent implementation. No source code was copied from the original `D:\new dir` application, which has no license file. The product framing and screens were rebuilt from scratch around a finalized-transcript workflow. See `docs/baseline-inventory.md` for the isolation record.

## What it does

1. **Conversation desk** - open a seeded sample or create a conversation, then import a finalized transcript or add one line at a time.
2. **Select evidence** - tick the exact lines the coach should read. Every observation must cite those lines.
3. **Sales coach** - the demo coach returns observations, an exact quote, why it matters, a suggested alternative, a recommended action, and the limits of the inference. Filter by objection, unanswered question, ambiguity, discovery, or next step.
4. **Ask the evidence** - ask a question about up to six selected lines and get an answer with citations. Answers are kept per conversation.
5. **Team playbook** - promote an observation into a draft entry, edit the scenario, response, discovery questions, and reviewer, then approve it. Editing approved guidance reopens review. Every approval is recorded locally with the reviewer name and a timestamp.
6. **Team signals** - an aggregate preview of approved guidance, conversation evidence, and coaching mix. It never ranks individual employees.

## Scope and guardrails

- **Finalized transcripts only.** This build does not open a microphone, claim a live transcription state, or run machine translation. Translations are supplied with the text.
- **The demo coach is deterministic and offline.** It uses rules over the selected words only. It cannot hear tone and does not claim to know customer intent.
- **A real provider is optional.** An OpenAI-compatible chat-completions endpoint can be configured in Settings. The API key is read only from the environment variable `CLEARCOMMIT_TEAMS_API_KEY`; it is never stored in the database, returned by the bridge, or written to logs.
- **Local review, not accounts.** Approval records a reviewer name in the local workspace. There are no accounts, authentication, cloud sync, or simulated teammates.
- **The workspace stays inside the project.** Data defaults to `data/clearcommit-teams.db`. A `--data-dir` or `CLEARCOMMIT_TEAMS_DATA_DIR` override is accepted only inside the project root.

## Quick start (Windows)

Requirements: Windows 10/11 with the Microsoft Edge WebView2 runtime (included with current Windows/Edge), Python 3.11 or newer.

Double-click `launch.bat`. On first run it creates `.venv`, installs the pinned desktop dependency, and opens the app.

Or from a terminal in the project folder:

```powershell
py -3 -m venv .venv
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

The first launch seeds three clearly labeled fictional sample conversations. The app is usable immediately with no account or network connection.

### Useful commands

```powershell
# Environment and database check (no window)
& ".venv\Scripts\python.exe" -m clearcommit_teams --check

# Same UI in a loopback-only browser dev server (default port 8765)
& ".venv\Scripts\python.exe" -m clearcommit_teams --web

# Use a separate workspace folder (must stay inside the project)
& ".venv\Scripts\python.exe" -m clearcommit_teams --data-dir data\scratch

# Version
& ".venv\Scripts\python.exe" -m clearcommit_teams --version
```

To reset the workspace, close the app and delete `data\clearcommit-teams.db`. The samples are seeded again on the next launch.

## Provider configuration

Open the provider chip in the top-right corner (or the gear button) and choose **Configured provider**. Enter a base URL such as `https://api.example.com/v1`, the model name, and a timeout. Then set the key in the environment before launching:

```powershell
$env:CLEARCOMMIT_TEAMS_API_KEY = "..."
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

Only the lines you explicitly select are sent to the endpoint. The bridge never returns the key, and the status panel reports only whether it is present. If the provider is not configured, the app says which fields are missing and the demo coach remains available.

## Development

```powershell
# Python tests
& ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".venv\Scripts\python.exe" -m pytest -q

# Bridge client tests (Node 22+)
node --test tests\ui_bridge.test.cjs
```

Build a Windows app (optional):

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

The script installs PyInstaller into `.venv` if needed and writes `dist\ClearCommitTeams\ClearCommitTeams.exe`, which runs without Python installed and keeps its workspace in `data\` next to the executable. It needs the Edge WebView2 runtime, included with current Windows and Edge.

Project layout:

```text
app_entry.py        packaged-build entry point
build.ps1           PyInstaller build script
clearcommit_teams\
  app.py            pywebview desktop entry
  bridge.py         public bridge methods and response envelope
  coaching.py       analysis, assistant, and playbook service
  repository.py     SQLite persistence and sample seeding
  models.py         validation and finalized-transcript parser
  devserver.py      loopback-only --web server
  providers\        mock coach, OpenAI-compatible adapter, registry
  demo_data.py      three fictional sample conversations
ui\
  index.html        app shell and dialogs
  styles.css        editorial design system
  js\bridge.js      pywebview/HTTP bridge client
  js\app.js         view rendering and workflows
tests\              pytest suite and Node bridge tests
docs\               isolation and baseline record
```

## Privacy notes

- The database, WebView2 profile, and any provider configuration live under the project's `data` folder.
- The desktop app loads local files. The optional `--web` server binds only to `127.0.0.1` and is meant for local development.
- The app never sends audio. With the demo coach, no network request is made at all.

## Status

Version 0.2.0.

Two workspaces share one desktop client:

- **Local workspace** (up to v0.1.0): transcript intake, selection, analysis, grounded questions, playbook draft/review/approval, team signals, local persistence. Works offline.
- **Team workspace** (new): FastAPI backend, accounts, organizations, invitations, roles, private conversations, explicit insight sharing, review/approval, shared playbook, approved messaging, audit trail, live events, offline honesty.

See [`docs/network-mode.md`](docs/network-mode.md) for the architecture, privacy model, and honest limitation list; [`docs/api.md`](docs/api.md) for the API; [`docs/deployment.md`](docs/deployment.md) for setup and the two-user acceptance test.

Real Supabase Auth and the PostgreSQL RLS migration are implemented but were **not** executed in this environment because no Supabase project credentials were available. Demo mode is a real networked multi-user service with local credentials, and is labeled as such in the UI.
