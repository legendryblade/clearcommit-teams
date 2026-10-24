# Baseline inventory — ClearCommit Teams

Captured before any new application code was written.

## Isolation decision

| Item | Value |
|---|---|
| New project root | `D:\ClearCommit-Teams` |
| New Git root | `D:\ClearCommit-Teams` (initialized empty) |
| Original application (read-only) | `D:\new dir` |
| Original Git root | `D:\new dir` |
| Original Git HEAD | `bfedc9ef61798cef0c3fa33f32a04201beb2cea3` |
| Original Git status | clean except two pre-existing untracked folders: `build_new/`, `dist_new/` |

No files in `D:\new dir` were written, renamed, deleted, staged, committed, or executed during this work.

## Environment

| Item | Value |
|---|---|
| OS | Microsoft Windows 11 Pro 10.0.26200 |
| Architecture | AMD64 |
| Default Python | 3.14.6 |
| Additional Python | 3.11 (64-bit), 3.11 (32-bit) |
| Node | v24.18.0 |
| npm | 11.16.0 |
| Git | 2.55.0.windows.3 |
| pywebview (global, pre-existing) | 6.2.1 |
| pythonnet (global, pre-existing) | 3.2.1 |
| pytest (global, pre-existing) | 9.1.1 |
| Playwright (global, pre-existing) | 1.61.0 with Chromium browsers |

## Original files inspected (read-only)

| File | SHA-256 |
|---|---|
| `README.md` | `F267E0D01961509AC2E9FA4185F5DCF11D7FD288FF6A1FABBBEAD59B98DA999A` |
| `README_PRODUCT.md` | `223D799A20DEFA700F4BB8A8728C66DCE78D887DD7FE92D6D79E09DCDAE6CDAA` |
| `requirements.txt` | `CED4C1BFB007967105C22122B48180C4C390515FFDDC1F6658674D36BE4536E2` |
| `.env.example` | `316725F06E0A38BC147E60A61B69BDB504AA19F715E90E229A89D5FB0FCBC3F1` |
| `.gitignore` | `1354EE8A93C4BC09859A788698E3ED929857B68400A31EB4F93E159635F92903` |
| `handover.md` | `45B4F839853E55CA351343877257899205B3C6603AF1930F3F4ABDC9DF7C5828` |
| `professional_coaching.py` | `011CC83E3697D5A19841453148E51423D24207348FF12F638EFDE5C7E7A17DC0` |
| `ai_providers.py` | `632AE22F1590E71AEE074BB193D0DC2E1CDB28EF33884C6FA4E8F36A297DCE9A` |
| `ai_config.py` | `FB0077DD60D0AAFB19113F468D802D663FC140F428B6D6970DDC49C516243266` |
| `audio_capture.py` | `6B18260D51A80C998BA6050BE35C21E32F6453F9FDDE062CBD213F502DE9F342` |
| `transcriber.py` | `45FFC7F88DE66F8CC710700795FA8CF54B851F5784CDF8E3AE4E9F3A74B4D39A` |
| `clearcommit_integration.py` | `C434D2116FA6C287A8C512ECCE2CE6CC22DA04DC5B665901A74BE4C16EBFC19D` |

## What was learned from the original

- It is a Windows Python desktop app (CustomTkinter) for two-way speech interpretation.
- It already has private coaching analyzers, a grounded assistant, meeting intelligence, a deterministic agreement ledger, and OpenAI-compatible provider adapters.
- It has no `LICENSE` file. Therefore no original source was copied. The new product is implemented independently.
- Its audio path depends on loopback/microphone capture, Groq/Deepgram/ElevenLabs credentials, and local virtual audio devices. Those interfaces were not reused; audio capture is not part of this build.

## Baseline tests

The original test suite was deliberately not executed because pytest writes cache files and imports application modules. To keep the original application untouched, no execution or write was performed against `D:\new dir`.

The new project establishes its own test suite under `tests/` before feature implementation, per the build brief.
