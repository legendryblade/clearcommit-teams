# ClearCommit Teams

Turn a finished sales conversation into evidence-linked coaching, then into
guidance a manager reviews and the team actually follows.

Two surfaces share one backend:

- **Desktop app** (Windows, Python + pywebview) — works on a conversation
  locally: transcript, coaching, commitments, playbook, live interpretation.
- **Team workspace** (web + FastAPI + Supabase) — accounts, organizations,
  roles, shared calls, commitments, review and approved playbooks.

This is an independent implementation. No source was copied from the original
`D:\new dir` interpreter, which has no license. See
[`docs/baseline-inventory.md`](docs/baseline-inventory.md) for the isolation
record.

## Run it

### Desktop app (fastest path)

```powershell
launch.bat
```

That creates `.venv`, installs the dependencies on first run, and opens the app.

Live capture needs one API key. Put it in a `.env` file in the repository root:

```powershell
COPY .env.example .env
# then edit .env and set:
# GROQ_API_KEY=gsk_...
```

`.env` is read from the repo root when running from source, and from the folder
next to `ClearCommitTeams.exe` when running a packaged build (the build copies
it automatically). Without a key the app still runs — capture records, but
transcription reports that the key is missing instead of staying silent.

Other optional keys: `DEEPGRAM_API_KEY` (speaker separation),
`ELEVENLABS_API_KEY` (natural voice for interpretation).

Manually, without the batch file:

```powershell
py -3 -m venv .venv
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m clearcommit_teams
```

### Building the Windows exe

```powershell
.\build.ps1
```

Produces `dist\ClearCommitTeams\ClearCommitTeams.exe`, copies `.env` beside it,
and fails the build if the audio runtime is missing. The build is windowed
(no console); if it ever starts and exits immediately, rebuild with
`--console` instead of `--windowed` to read the traceback.

### Team workspace (local, no cloud)

```powershell
launch-team.bat
```

Starts the API on `127.0.0.1:8770` and the web UI on
`http://127.0.0.1:8765`, then opens the browser. Data lives in Supabase; the
service is stateless.

### Hosted

- Web: https://ui-five-blue.vercel.app
- API: https://clearcommit-teams-api.onrender.com

## What each surface does

**Desktop** (needs the local Python bridge):

| Area | Purpose |
| --- | --- |
| Conversation desk | Import or type a finalized transcript |
| Live capture | Microphone and/or system audio → transcript |
| Sales coach | Evidence-linked observations; every claim cites a line |
| Ask the evidence | Questions over selected lines, with citations |
| Interpretation | Two columns: their speech translated for you, your speech translated for them, optionally voiced |
| Playbook | Draft → reviewer → approval |
| Team workspace | Same web view, inside the app |

**Web** (team only — a browser has no audio or local database):

| Tab | Purpose |
| --- | --- |
| Overview | Needs attention, team counts |
| Calls | My calls (employee) or Team calls by teammate (manager) |
| Insights | Private and shared observations |
| Commitments | Promises with owner, due date, status, history |
| Playbook | Approved guidance and the review queue |
| Team | Members, roles, invitations, per-member view |
| Settings | Companies and join code |

## Choosing transcript and voice models

Open **Workspace settings** (the provider chip, or the gear icon) to set:

| Setting | Default | Notes |
| --- | --- | --- |
| Transcription provider | Groq Whisper | Deepgram adds speaker separation |
| Transcription model | `whisper-large-v3` | The accurate model, not the faster turbo variant |
| Speaking voice | ElevenLabs Sarah | Any ElevenLabs voice id |
| Speech model | `eleven_turbo_v2_5` | ElevenLabs model id |

Blank fields fall back to `.env`, then to these defaults, so leaving them empty
is always safe. The capture panel and the Interpretation tab both show which
model is actually in use, so a misconfiguration is visible rather than silent.

You can also pin models in `.env`:

```powershell
CLEARCOMMIT_STT_MODEL_GROQ=whisper-large-v3
CLEARCOMMIT_STT_MODEL_DEEPGRAM=nova-3
CLEARCOMMIT_TTS_MODEL=eleven_turbo_v2_5
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
```

## Navigating the app

The left rail switches between views and keeps your place:

| View | Desktop | Web |
| --- | --- | --- |
| Conversation desk | ✓ | — |
| Sales coach | ✓ | — |
| Playbook | ✓ | — |
| Signals | ✓ | — |
| Interpretation | ✓ | — |
| Team workspace | ✓ | ✓ |

A conversation must be open before you can import a transcript or record.
Recording appends to the open conversation; press **Stop recording** to save
the captured lines to its transcript.


A manager creates a company and gets a short code (for example `Z9D9GRE7`).
An employee signs in, types the code, and is in. The code identifies the
company only; the role comes from a pending invitation matched to the verified
email, otherwise it defaults to `sales_rep`. A leaked code cannot grant
manager rights.

## Verified behaviour

- Two accounts in one organization; manager and employee UIs differ
- Private conversations return 404 to teammates, including managers, until shared
- Cross-organization access denied on every tested route
- A commitment is created as *needs confirmation* and only opens when a person
  confirms the owner and the date
- Every commitment change is written to a history table
- Join codes are idempotent; wrong codes are refused
- 280 automated tests

## Development

```powershell
& ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".venv\Scripts\python.exe" -m pytest -q          # 280 tests
node --test tests\ui_bridge.test.cjs              # bridge client
```

Deployment: [`docs/deployment.md`](docs/deployment.md) ·
Supabase: [`docs/supabase-go-live.md`](docs/supabase-go-live.md) ·
API: [`docs/api.md`](docs/api.md) ·
Architecture: [`docs/cloud-architecture.md`](docs/cloud-architecture.md) ·
Audio: [`docs/audio-roadmap.md`](docs/audio-roadmap.md)

## Privacy

- Conversations are private to their author until explicitly shared.
- Sharing an insight shares the selected quotes, never the transcript.
- Managers see shared work and counts, never private coaching or scores.
- Raw audio is transcribed locally and not stored.
- Provider keys are read from the environment and never stored, returned, or
  logged.

## Known limitations

1. **Live capture needs a streamable host API.** Most Windows inputs stream
   fine (MME, DirectSound, WASAPI); WDM-KS endpoints answer a one-shot
   recording but cannot stream, so they are filtered out of the device list.
2. **Interpretation** works through the API (English→Urdu 0.46s, English→Arabic
   with speech 2.09s); the two-column view is new and not fully exercised.
3. **Sync is explicit.** A desktop conversation reaches the team only when the
   user presses *Save to cloud*.
4. No email invitations (join codes instead), no CRM, no rate limit on code
   attempts, no code rotation.
5. No employee performance scores. The available data cannot support them and
   the product must not imply them.

## License

MIT — see [LICENSE](LICENSE).
