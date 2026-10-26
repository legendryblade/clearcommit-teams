"""Typed bridge between the HTML frontend and Python application logic.

Every public method returns a stable envelope:

    {"ok": true, "data": ...}
    {"ok": false, "error": {"code", "message", "retryable", "detail"?}}

pywebview invokes these methods from its own worker threads, so a blocking
provider call never blocks the rendered interface. The development HTTP server
uses the same bridge for browser-based smoke tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Mapping

from . import BRIDGE_VERSION, __version__
from .coaching import (
    MAX_ASSISTANT_EVIDENCE,
    MAX_EVIDENCE,
    MAX_INSIGHTS,
    CoachingService,
)
from .repository import Repository
from .errors import BridgeError, ValidationError, error_payload
from .models import (
    evidence_ref,
    parse_refs,
    parse_settings_input,
    parse_transcript,
)
from .paths import database_path, display_path, workspace_dir
from .providers import ProviderSettings, build_provider, provider_status

logger = logging.getLogger("clearcommit_teams.bridge")

PUBLIC_METHODS = (
    "ping",
    "bootstrap",
    "list_sessions",
    "get_session",
    "create_session",
    "rename_session",
    "delete_session",
    "add_utterance",
    "import_transcript",
    "list_insights",
    "get_insight",
    "analyze",
    "ask_assistant",
    "list_assistant_notes",
    "list_playbook",
    "get_playbook",
    "create_playbook",
    "save_playbook",
    "approve_playbook",
    "save_settings",
    "provider_status",
    "test_provider",
    "refresh_preview",
    "use_workspace",
    "interpret_status",
    "interpret",
    "audio_status",
    "audio_devices",
    "audio_start",
    "audio_poll",
    "audio_stop",
    "get_cloud_link",
    "set_cloud_link",
    "transcript_payload",
)


def _payload(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError("The request payload must be an object.")
    return value


def _required_id(payload: Mapping[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} is required.")
    return value.strip()


class Bridge:
    def __init__(
        self,
        repo: Repository,
        service: CoachingService,
        data_dir: Path,
        base_data_dir: Path | None = None,
    ) -> None:
        self.repo = repo
        self.service = service
        self.data_dir = data_dir
        self.base_data_dir = base_data_dir or data_dir
        self.db = repo.db
        self._capture = None
        self._capture_source = None

    # ------------------------------------------------------------------ #
    # Envelope handling
    # ------------------------------------------------------------------ #
    def _execute(self, name: str, func: Callable[[Mapping[str, Any]], Any], payload: Any) -> dict:
        try:
            return {"ok": True, "data": func(_payload(payload))}
        except Exception as exc:  # noqa: BLE001 - envelopes are the boundary
            if not hasattr(exc, "code"):
                logger.exception("Bridge method failed: %s", name)
            return {"ok": False, "error": error_payload(exc)}

    def _settings_payload(self) -> dict:
        settings = self.repo.settings()
        return {
            "provider_mode": settings.get("provider_mode", "mock"),
            "base_url": settings.get("base_url", ""),
            "model": settings.get("model", ""),
            "timeout_s": settings.get("timeout_s", 25),
            "reviewer_name": settings.get("reviewer_name", ""),
        }

    def _provider_status_payload(self) -> dict:
        return provider_status(ProviderSettings.from_dict(self.repo.settings()))

    # ------------------------------------------------------------------ #
    # Public bridge methods
    # ------------------------------------------------------------------ #
    def ping(self, payload: Any = None) -> dict:
        return self._execute("ping", self._ping, payload)

    def _ping(self, payload: Mapping[str, Any]) -> dict:
        return {
            "name": "ClearCommit Teams",
            "version": __version__,
            "bridge_version": BRIDGE_VERSION,
            "data_dir": display_path(self.data_dir),
            "write_root": display_path(self.data_dir),
        }

    def bootstrap(self, payload: Any = None) -> dict:
        return self._execute("bootstrap", self._bootstrap, payload)

    def _bootstrap(self, payload: Mapping[str, Any]) -> dict:
        return {
            "app": {
                "name": "ClearCommit Teams",
                "version": __version__,
                "bridge_version": BRIDGE_VERSION,
                "data_dir": display_path(self.data_dir),
                "local_only": True,
                "tagline": "Turn individual conversations into better communication across the team.",
            },
            "sessions": self.repo.list_sessions(),
            "settings": self._settings_payload(),
            "provider": self._provider_status_payload(),
            "preview": self.repo.preview(),
            "capabilities": {
                "audio_capture": False,
                "audio_reason": (
                    "This build uses a finalized transcript workflow. It does not open a microphone "
                    "or claim a live transcription state."
                ),
                "live_transcription": False,
                "machine_translation": False,
                "translation_note": (
                    "Translations are provided with each utterance or sample. No machine translation "
                    "service runs in this build."
                ),
                "real_provider": True,
                "mock_provider": True,
                "playbook": True,
                "team_accounts": False,
                "team_review_note": (
                    "Approval is a local review action recorded with the reviewer name you enter. "
                    "This build does not implement accounts, authentication, or simulated teammates."
                ),
            },
            "limits": {
                "max_evidence": MAX_EVIDENCE,
                "max_assistant_evidence": MAX_ASSISTANT_EVIDENCE,
                "max_insights": MAX_INSIGHTS,
            },
        }

    def list_sessions(self, payload: Any = None) -> dict:
        return self._execute("list_sessions", lambda _: self.repo.list_sessions(), payload)

    def get_session(self, payload: Any = None) -> dict:
        return self._execute("get_session", self._get_session, payload)

    def _get_session(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        result = self.repo.get_session(session_id)
        result["assistant_notes"] = self.repo.list_assistant_notes(session_id)
        return result

    def create_session(self, payload: Any = None) -> dict:
        return self._execute("create_session", self._create_session, payload)

    def _create_session(self, payload: Mapping[str, Any]) -> dict:
        return self.repo.create_session(payload, source="manual")

    def rename_session(self, payload: Any = None) -> dict:
        return self._execute("rename_session", self._rename_session, payload)

    def _rename_session(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        title = payload.get("title")
        if not isinstance(title, str):
            raise ValidationError("A conversation title is required.")
        return self.repo.rename_session(session_id, title)

    def delete_session(self, payload: Any = None) -> dict:
        return self._execute("delete_session", self._delete_session, payload)

    def _delete_session(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        return self.repo.delete_session(session_id)

    def add_utterance(self, payload: Any = None) -> dict:
        return self._execute("add_utterance", self._add_utterance, payload)

    def _add_utterance(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        return self.repo.add_utterance(session_id, payload)

    def import_transcript(self, payload: Any = None) -> dict:
        return self._execute("import_transcript", self._import_transcript, payload)

    def _import_transcript(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        text = payload.get("transcript")
        if not isinstance(text, str):
            raise ValidationError("Paste transcript lines before importing.")
        session = self.repo.get_session(session_id)["session"]
        default_language = payload.get("language") or session["customer_language"]
        rows = parse_transcript(text, default_language)
        return self.repo.add_utterances(session_id, rows)

    def list_insights(self, payload: Any = None) -> dict:
        return self._execute("list_insights", self._list_insights, payload)

    def _list_insights(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        return self.repo.list_insights(session_id)

    def get_insight(self, payload: Any = None) -> dict:
        return self._execute("get_insight", self._get_insight, payload)

    def _get_insight(self, payload: Mapping[str, Any]) -> dict:
        insight_id = _required_id(payload, "insight_id", "An insight ID")
        return self.repo.get_insight(insight_id)

    def analyze(self, payload: Any = None) -> dict:
        return self._execute("analyze", self._analyze, payload)

    def _analyze(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        refs = parse_refs(payload)
        return self.service.analyze(session_id, refs)

    def ask_assistant(self, payload: Any = None) -> dict:
        return self._execute("ask_assistant", self._ask_assistant, payload)

    def _ask_assistant(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        refs = parse_refs(payload)
        return self.service.ask(session_id, refs, payload.get("question"))

    def list_assistant_notes(self, payload: Any = None) -> dict:
        return self._execute("list_assistant_notes", self._list_assistant_notes, payload)

    def _list_assistant_notes(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        return self.repo.list_assistant_notes(session_id)

    def list_playbook(self, payload: Any = None) -> dict:
        return self._execute("list_playbook", self._list_playbook, payload)

    def _list_playbook(self, payload: Mapping[str, Any]) -> dict:
        status = payload.get("status")
        if status in ("", None):
            status = None
        return self.repo.list_playbook(status)

    def get_playbook(self, payload: Any = None) -> dict:
        return self._execute("get_playbook", self._get_playbook, payload)

    def _get_playbook(self, payload: Mapping[str, Any]) -> dict:
        entry_id = _required_id(payload, "entry_id", "A playbook entry ID")
        return self.repo.get_playbook_entry(entry_id)

    def create_playbook(self, payload: Any = None) -> dict:
        return self._execute("create_playbook", self._create_playbook, payload)

    def _create_playbook(self, payload: Mapping[str, Any]) -> dict:
        insight_id = _required_id(payload, "insight_id", "An insight ID")
        return self.repo.create_playbook_from_insight(
            insight_id, payload.get("entry") or payload.get("fields") or {}
        )

    def save_playbook(self, payload: Any = None) -> dict:
        return self._execute("save_playbook", self._save_playbook, payload)

    def _save_playbook(self, payload: Mapping[str, Any]) -> dict:
        entry_id = _required_id(payload, "entry_id", "A playbook entry ID")
        reviewer = payload.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            reviewer = self.repo.settings().get("reviewer_name") or "Local editor"
        return self.repo.update_playbook_entry(
            entry_id, payload.get("fields") or {}, reviewer
        )

    def approve_playbook(self, payload: Any = None) -> dict:
        return self._execute("approve_playbook", self._approve_playbook, payload)

    def _approve_playbook(self, payload: Mapping[str, Any]) -> dict:
        entry_id = _required_id(payload, "entry_id", "A playbook entry ID")
        return self.repo.approve_playbook_entry(
            entry_id, payload.get("reviewer"), payload.get("note") or ""
        )

    def save_settings(self, payload: Any = None) -> dict:
        return self._execute("save_settings", self._save_settings, payload)

    def _save_settings(self, payload: Mapping[str, Any]) -> dict:
        current = self.repo.settings()
        values = parse_settings_input(payload, current)
        saved = self.repo.save_settings(values)
        return {
            "settings": {
                "provider_mode": saved.get("provider_mode", "mock"),
                "base_url": saved.get("base_url", ""),
                "model": saved.get("model", ""),
                "timeout_s": saved.get("timeout_s", 25),
                "reviewer_name": saved.get("reviewer_name", ""),
            },
            "provider": self._provider_status_payload(),
        }

    def provider_status(self, payload: Any = None) -> dict:
        return self._execute("provider_status", lambda _: self._provider_status_payload(), payload)

    def test_provider(self, payload: Any = None) -> dict:
        return self._execute("test_provider", self._test_provider, payload)

    def _test_provider(self, payload: Mapping[str, Any]) -> dict:
        settings = ProviderSettings.from_dict(self.repo.settings())
        provider = build_provider(settings)
        result = provider.test_connection()
        result["provider"] = {
            "mode": provider.descriptor.mode,
            "name": provider.descriptor.name,
            "model": provider.descriptor.model,
        }
        return result

    def refresh_preview(self, payload: Any = None) -> dict:
        return self._execute("refresh_preview", lambda _: self.repo.preview(), payload)

    def get_cloud_link(self, payload: Any = None) -> dict:
        return self._execute("get_cloud_link", self._get_cloud_link, payload)

    def _get_cloud_link(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        value = self.db.get_meta("cloud:" + session_id, "")
        return {"session_id": session_id, "cloud_conversation_id": value or None}

    def set_cloud_link(self, payload: Any = None) -> dict:
        return self._execute("set_cloud_link", self._set_cloud_link, payload)

    def _set_cloud_link(self, payload: Mapping[str, Any]) -> dict:
        session_id = _required_id(payload, "session_id", "A conversation ID")
        cloud_id = str(payload.get("cloud_conversation_id") or "").strip()
        if not cloud_id:
            raise ValidationError("A cloud conversation ID is required.")
        if len(cloud_id) > 64:
            raise ValidationError("That cloud conversation ID is too long.")
        self.db.set_meta("cloud:" + session_id, cloud_id)
        return {"session_id": session_id, "cloud_conversation_id": cloud_id}

    def transcript_payload(self, payload: Any = None) -> dict:
        return self._execute("transcript_payload", self._transcript_payload, payload)

    def _transcript_payload(self, payload: Mapping[str, Any]) -> dict:
        """Everything needed to create the cloud record, in one read."""
        session_id = _required_id(payload, "session_id", "A conversation ID")
        detail = self.repo.get_session(session_id)
        session = detail["session"]
        lines = detail["utterances"]
        return {
            "session_id": session_id,
            "title": session["title"],
            "language": session.get("customer_language") or "en",
            "utterances": [
                {
                    "speaker": "customer" if row.get("speaker") == "customer" else "rep",
                    "content": row.get("original_text") or row.get("text") or "",
                    "lang": row.get("language") or session.get("customer_language") or "en",
                    "translation": row.get("translation") or None,
                }
                for row in lines
                if (row.get("original_text") or row.get("text"))
            ],
        }

    # ---- Interpretation: translate + speak (opt-in) ---- #
    def interpret_status(self, payload: Any = None) -> dict:
        return self._execute("interpret_status", self._interpret_status, payload)

    def _interpret_status(self, _payload: Mapping[str, Any]) -> dict:
        from .audio import interpret

        data = interpret.status()
        data["outputs"] = [
            {"index": idx, "name": name} for idx, name in interpret.output_devices()
        ]
        return data

    def interpret(self, payload: Any = None) -> dict:
        return self._execute("interpret", self._interpret, payload)

    def _interpret(self, payload: Mapping[str, Any]) -> dict:
        """Translate text and optionally speak it out of a chosen device."""
        from .audio import interpret

        text = str(payload.get("text") or "")
        target = str(payload.get("target") or "ur").strip().lower()
        source = str(payload.get("source") or "").strip().lower() or None
        speak = bool(payload.get("speak"))
        device = payload.get("device")
        if device is not None:
            try:
                device = int(device)
            except (TypeError, ValueError) as exc:
                raise ValidationError("The output device must be an index.") from exc

        result = interpret.translate(text, target, source)
        spoken = False
        duration = None
        if speak:
            audio = interpret.synthesise(result.text, target)
            data, rate = interpret._decode_audio(audio)
            duration = round(len(data) / float(rate or 1), 2)
            interpret.speak_to_device(audio, device)
            spoken = True
        return {
            "source_text": text,
            "translated_text": result.text,
            "target": result.target,
            "target_name": result.target_name,
            "spoken": spoken,
            "audio_seconds": duration,
        }

    # ---- Audio capture (opt-in; nothing starts automatically) ---- #
    def audio_status(self, payload: Any = None) -> dict:
        return self._execute("audio_status", self._audio_status, payload)

    def _audio_status(self, _payload: Mapping[str, Any]) -> dict:
        from .audio import availability, default_loopback_available
        from .audio.transcribe import provider_status

        state = availability()
        return {
            "capture": {
                "available": state.available,
                "missing": list(state.missing),
                "detail": state.detail,
                "system_audio": default_loopback_available(),
            },
            "transcription": provider_status(),
            "active": bool(self._capture is not None and self._capture.active),
            "source": self._capture_source,
        }

    def audio_devices(self, payload: Any = None) -> dict:
        return self._execute("audio_devices", self._audio_devices, payload)

    def _audio_devices(self, _payload: Mapping[str, Any]) -> dict:
        from .audio import (
            availability,
            loopback_devices,
            preferred_microphone,
            probe_microphones,
        )

        state = availability()
        if not state.available:
            return {"available": False, "detail": state.detail, "microphones": [], "outputs": []}
        # Probe each input so the UI can rank the ones that hear sound first. A
        # silent Windows default is the usual reason capture produces nothing.
        measured = probe_microphones()
        measured.sort(key=lambda row: -row[2])
        return {
            "available": True,
            "detail": state.detail,
            "preferred_microphone": preferred_microphone(),
            "microphones": [
                {"index": idx, "name": name, "peak": peak} for idx, name, peak in measured
            ],
            # Only WASAPI loopback endpoints capture what the machine plays, so
            # these are the only valid choices for the "call audio" side.
            "outputs": [{"index": idx, "name": name} for idx, name in loopback_devices()],
        }

    def audio_start(self, payload: Any = None) -> dict:
        return self._execute("audio_start", self._audio_start, payload)

    def _audio_start(self, payload: Mapping[str, Any]) -> dict:
        from .audio import CaptureSession

        if self._capture is not None and self._capture.active:
            raise ValidationError("A recording is already in progress.")
        source = str(payload.get("source") or "microphone").strip().lower()
        include_system = bool(payload.get("include_system")) or source == "both"
        if source == "both":
            source = "microphone"
        if source not in ("microphone", "system"):
            raise ValidationError("source must be microphone, system or both.")
        device = payload.get("device")
        if device is not None:
            try:
                device = int(device)
            except (TypeError, ValueError) as exc:
                raise ValidationError("The device must be a device index.") from exc
        system_device = payload.get("system_device")
        if system_device is not None:
            try:
                system_device = int(system_device)
            except (TypeError, ValueError) as exc:
                raise ValidationError("The system device must be a device index.") from exc

        # In a 1:1 call we listen to both sides at once: the microphone is the
        # person using ClearCommit, the system audio is the other participant.
        session = CaptureSession(
            source,
            device if source == "microphone" else None,
            system_device=system_device,
            include_system=include_system,
        )
        session.start()
        self._capture = session
        self._capture_source = "both" if include_system else source
        return {
            "active": True,
            "source": self._capture_source,
            "system": session._system_capture is not None,
            "microphone": session._capture is not None,
        }

    def audio_poll(self, payload: Any = None) -> dict:
        return self._execute("audio_poll", self._audio_poll, payload)

    def _audio_poll(self, payload: Mapping[str, Any]) -> dict:
        """Transcribe whatever accumulated since the last poll.

        When both sides are being captured, the source of each chunk is the
        speaker: microphone is the ClearCommit user ('rep'), system audio is
        the other participant ('customer'). That labelling is exact, whereas
        model-based diarization would only be a guess between two channels.
        """
        if self._capture is None:
            return {"active": False, "segments": 0, "text": "", "turns": []}
        from .audio.transcribe import get_transcriber

        provider = str(payload.get("provider") or "groq").strip().lower()
        pairs = self._capture.drain_both()
        if not pairs:
            return {
                "active": self._capture.active,
                "segments": 0,
                "text": "",
                "turns": [],
            }

        transcriber = get_transcriber(provider)
        texts: list[str] = []
        turns: list[dict] = []
        for source, wav in pairs:
            if hasattr(transcriber, "transcribe_turns"):
                segments = transcriber.transcribe_turns(wav)
            else:
                segments = [transcriber.transcribe(wav)]
            for segment in segments:
                if not segment.text:
                    continue
                texts.append(segment.text)
                turns.append(
                    {
                        "speaker": "rep" if source == "microphone" else "customer",
                        "source": source,
                        "text": segment.text,
                        "model_speaker": getattr(segment, "speaker", None),
                    }
                )
        return {
            "active": self._capture.active,
            "segments": len(texts),
            "text": " ".join(texts).strip(),
            "turns": turns,
            "provider": provider,
        }

    def audio_stop(self, payload: Any = None) -> dict:
        return self._execute("audio_stop", self._audio_stop, payload)

    def _audio_stop(self, _payload: Mapping[str, Any]) -> dict:
        if self._capture is None:
            return {"active": False}
        self._capture.stop()
        self._capture = None
        self._capture_source = None
        return {"active": False}

    def use_workspace(self, payload: Any = None) -> dict:
        return self._execute("use_workspace", self._use_workspace, payload)

    def _use_workspace(self, payload: Mapping[str, Any]) -> dict:
        """Switch the active personal workspace to one account's folder.

        ``account_key`` must be a stable, non-secret identifier chosen by the
        caller (never an email address or a token). Passing ``None`` selects the
        guest workspace, which keeps the app usable before sign-in and offline.
        """
        raw = payload.get("account_key")
        if raw in (None, ""):
            key = None
        elif isinstance(raw, str):
            key = raw.strip() or None
        else:
            raise ValidationError("account_key must be a string or omitted.")

        target = workspace_dir(self.base_data_dir, key)

        # Build against the base directory (which resolves to the guest
        # workspace), then rebind to the account's own folder. Resolving in two
        # steps would nest workspaces inside each other.
        from .db import Database
        from .repository import Repository
        from .coaching import CoachingService

        target.mkdir(parents=True, exist_ok=True)
        db = Database(database_path(target))
        db.initialize()
        repo = Repository(db)
        service = CoachingService(repo)
        # Swap atomically only after the new workspace opened successfully.
        self.db = db
        self.repo = repo
        self.service = service
        self.data_dir = target
        return {
            "workspace": str(target),
            "account_key": key or "guest",
            "counts": db.counts(),
        }


def public_method_names() -> tuple[str, ...]:
    return PUBLIC_METHODS


def fallback_evidence_ref(seq: int) -> str:
    return evidence_ref(seq)
