# Live audio capture — implementation roadmap (not implemented)

**Status: not implemented.** ClearCommit Teams has no microphone access, no
system-audio capture, and no live transcription. The application works only
from finalsed transcripts that a user imports or types. Nothing in the shipped
app opens an audio device.

This document exists so the plan is concrete and honest. It is not a claim
that any of it exists.

## Why it is not in this release

Adding capture touches packaging (PortAudio/DLL bundling), device permissions,
Windows-specific APIs, and a network transcription provider. Those are
multi-day risks to a working build. The release instead proves the full
transcript → coaching → review → shared playbook workflow with real accounts.

## Verified facts about the current build

| Question | Answer |
| --- | --- |
| Any audio dependency? | No. `sounddevice`, `PyAudioWPatch`, `numpy` are absent. |
| Any capture code? | No `clearcommit_teams/audio/` module exists. |
| Microphone opened at startup? | No. `bridge.py` states the finalized-transcript policy. |
| Live transcription? | No. |
| Raw audio uploaded? | No audio is produced at all. |

## Reference implementation available in the original interpreter

`D:\new dir` (read-only reference, never modified) has a working Windows audio
stack worth studying:

| File | Approach |
| --- | --- |
| `audio_capture.py` | `MicCapture` via `sounddevice`; device enumeration helpers; 16 kHz mono WAV chunks |
| `loopback_capture.py` | System audio via `PyAudioWPatch` WASAPI loopback, 20 ms chunks, local VAD (threshold 0.02, 0.7 s silence) |
| `transcriber.py` | Groq `whisper-large-v3` behind a small class with API-key rotation |
| `setup_wizard.py` | Detects VB-CABLE; used for *output* routing, not capture |

Both capture modules import only stdlib plus `numpy` and lazy device libraries,
so their structure is adoptable. Their code is not copied into this project.

## Proposed architecture

```
clearcommit_teams/audio/          (feature-flagged: CLEARCOMMIT_TEAMS_AUDIO=1)
  __init__.py      exposes availability; absent libs degrade gracefully
  devices.py       enumerate mics and loopback endpoints
  capture.py       mic + loopback; start / pause / resume / stop
  vad.py           local silence gate; prevents empty chunks billing a provider
  segments.py      timestamped transcript segments
  providers.py     transcription adapter interface
```

Data flow, preserving the existing seams:

```
audio module → transcript segments → existing bridge → existing conversation
workflow → existing authenticated sharing (net.js → FastAPI → Postgres/RLS)
```

Python must not gain a second upload path. Segments enter through the same
conversation workflow the importer already uses.

## Capture decisions

- **Microphone:** `sounddevice` (PortAudio). Reliable, small API, Windows-friendly.
- **System audio:** `PyAudioWPatch` WASAPI loopback. Captures the output device
  directly; VB-CABLE is **not required** and stays optional for users who route
  audio between applications.
- **Device switching:** enumerate before start; treat a device disappearing
  mid-session as a recoverable error, not a crash.
- **No auto-start.** Capture begins only on an explicit user action, with a
  visible indicator while active.

## Transcription

Keep the provider behind an interface so the vendor is replaceable:

```python
class TranscriptionProvider(Protocol):
    def transcribe(self, wav_bytes: bytes, language: str | None) -> Segment: ...
```

Groq Whisper is a reasonable first adapter (low latency, language
auto-detection, generous free tier). Keys stay server-side or in the local
environment; never in the UI bundle.

## Privacy requirements (must ship with capture)

- Never start capturing automatically.
- Raw audio stays local; delete buffers after transcription.
- Upload only transcript text, and only when the user chooses to save/share.
- Show capture state at all times.
- Respect workplace recording policy; require explicit consent before first use.
- Private conversations remain private until explicitly shared.

## Packaging risks

- PyInstaller must bundle PortAudio and WASAPI shims. Missing DLLs must fail
  gracefully, not prevent the app from starting.
- Audio libraries must be optional imports so machines without them still run
  the transcript workflow.

## Tests required before claiming capture works

1. Enumerate with 0, 1, and N devices.
2. Start/stop each source independently; verify the device is released.
3. Switch devices mid-session.
4. Unplug a device mid-capture; app survives and reports the failure.
5. Silence produces no fabricated transcript.
6. Unrelated system audio produces no fabricated transcript.
7. Provider timeout/error surfaces honestly; nothing is saved.
8. End-to-end latency measured on real hardware (report actual numbers).
9. Capture stops within a bounded time after the stop action.
10. Full existing regression suite still passes.

Do not claim diarization, speaker identification, or language coverage beyond
what is measured.
