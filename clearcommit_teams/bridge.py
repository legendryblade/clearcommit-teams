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
