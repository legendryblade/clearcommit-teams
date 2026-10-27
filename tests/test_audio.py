"""Audio capture and transcription boundaries.

No real device is opened and no paid API is called: the transcriber is a
deterministic fake, so these run anywhere. Hardware behaviour is verified
separately by a manual smoke test.
"""

from __future__ import annotations

from clearcommit_teams.audio import availability
from clearcommit_teams.audio.transcribe import (
    MAX_AUDIO_BYTES,
    GroqTranscriber,
    TranscriptionError,
    TranscriptSegment,
    provider_status,
)


class FakeTranscriber:
    name = "fake"

    def __init__(self, text: str = "hello team", fail: bool = False):
        self.text = text
        self.fail = fail
        self.calls = 0

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> TranscriptSegment:
        self.calls += 1
        if self.fail:
            raise TranscriptionError("provider blew up", code="provider_error", retryable=True)
        return TranscriptSegment(text=self.text, language=language or "en")


def test_availability_reports_without_raising() -> None:
    state = availability()
    assert isinstance(state.available, bool)
    if not state.available:
        assert state.missing
        assert "needs" in state.detail


def test_provider_status_never_leaks_the_key(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-super-secret-value")
    status = provider_status()
    assert status["configured"] is True
    serialized = str(status)
    assert "sk-super-secret-value" not in serialized


def test_provider_status_reports_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CLEARCOMMIT_GROQ_API_KEY", raising=False)
    status = provider_status()
    assert status["configured"] is False
    assert "GROQ_API_KEY" in status["detail"]


def test_transcriber_refuses_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CLEARCOMMIT_GROQ_API_KEY", raising=False)
    try:
        GroqTranscriber(api_key=None)
    except TranscriptionError as exc:
        assert exc.code == "provider_not_configured"
    else:
        raise AssertionError("a missing key must be refused")


def test_empty_audio_is_rejected_before_calling_a_provider() -> None:
    transcriber = GroqTranscriber(api_key="fake-key-not-used")
    try:
        transcriber.transcribe(b"")
    except TranscriptionError as exc:
        assert exc.code == "empty_audio"
    else:
        raise AssertionError("empty audio must be refused")


def test_oversized_audio_is_rejected() -> None:
    transcriber = GroqTranscriber(api_key="fake-key-not-used")
    try:
        transcriber.transcribe(b"0" * (MAX_AUDIO_BYTES + 1))
    except TranscriptionError as exc:
        assert exc.code == "audio_too_large"
    else:
        raise AssertionError("oversized audio must be refused")


def test_fake_transcriber_shape_matches_the_interface() -> None:
    fake = FakeTranscriber("the customer asked who owns setup")
    segment = fake.transcribe(b"RIFF....")
    assert segment.text == "the customer asked who owns setup"
    assert fake.calls == 1


def test_capture_session_does_not_start_implicitly() -> None:
    """Constructing a session must never open a device."""
    from clearcommit_teams.audio import CaptureSession

    session = CaptureSession("microphone")
    assert session.active is False
    assert session.drain() == []

class RecordingTranscriber:
    """Deterministic transcriber that returns whatever it was told to."""

    name = "recording"

    def __init__(self, texts):
        self.texts = list(texts)
        self.languages = []

    def transcribe(self, wav_bytes, language=None):
        from clearcommit_teams.audio.transcribe import TranscriptSegment

        self.languages.append(language)
        text = self.texts.pop(0) if self.texts else ""
        return TranscriptSegment(text=text)


def _patch_poll_dependencies(monkeypatch, transcriber):
    """Make audio_poll think a session is live with queued chunks."""
    import clearcommit_teams.audio as audio_pkg
    import clearcommit_teams.audio.transcribe as transcribe_mod

    class FakeSession:
        active = True

        def __init__(self, pairs):
            self._pairs = pairs

        def drain_both(self):
            pairs, self._pairs = self._pairs, []
            return pairs

    monkeypatch.setattr(transcribe_mod, "get_transcriber", lambda provider="groq", model=None: transcriber)
    return FakeSession


def test_both_sources_label_you_and_caller(monkeypatch) -> None:
    """Microphone audio is the user; system audio is the other participant."""
    from clearcommit_teams.bridge import Bridge
    from clearcommit_teams.audio.transcribe import TranscriptSegment

    class TurnTranscriber:
        name = "turns"

        def __init__(self):
            self.calls = 0

        def transcribe(self, wav_bytes, language=None):
            self.calls += 1
            if wav_bytes == b"mic":
                return TranscriptSegment(text="Thanks for joining", speaker=None)
            return TranscriptSegment(text="Happy to be here", speaker=None)

    import clearcommit_teams.audio.transcribe as transcribe_mod

    monkeypatch.setattr(
        transcribe_mod, "get_transcriber", lambda provider="groq", model=None: TurnTranscriber()
    )

    bridge = object.__new__(Bridge)
    bridge._capture = type(
        "S", (), {"active": True, "drain_both": lambda self: [("microphone", b"mic"), ("system", b"sys")]}
    )()
    result = bridge._audio_poll({"provider": "groq"})

    assert result["segments"] == 2
    assert result["turns"][0]["speaker"] == "rep"
    assert result["turns"][0]["source"] == "microphone"
    assert result["turns"][1]["speaker"] == "customer"
    assert result["turns"][1]["source"] == "system"
    assert "Thanks for joining" in result["text"]
    assert "Happy to be here" in result["text"]


def test_no_chunks_returns_empty_without_calling_a_provider(monkeypatch) -> None:
    from clearcommit_teams.bridge import Bridge

    called = {"n": 0}

    def boom(provider="groq", model=None):
        called["n"] += 1
        raise AssertionError("a provider must not be called with no audio")

    import clearcommit_teams.audio.transcribe as transcribe_mod

    monkeypatch.setattr(transcribe_mod, "get_transcriber", boom)
    bridge = object.__new__(Bridge)
    bridge._capture = type("S", (), {"active": True, "drain_both": lambda self: []})()

    result = bridge._audio_poll({"provider": "groq"})
    assert result["segments"] == 0
    assert called["n"] == 0


def test_inactive_session_reports_not_active() -> None:
    from clearcommit_teams.bridge import Bridge

    bridge = object.__new__(Bridge)
    bridge._capture = None
    result = bridge._audio_poll({"provider": "groq"})
    assert result["active"] is False

# --- interpretation -------------------------------------------------------

def test_interpretation_status_reports_capability_without_keys(monkeypatch) -> None:
    from clearcommit_teams.audio import interpret

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    state = interpret.status()
    assert state["translation"]["configured"] is False
    assert state["speech"]["configured"] is False
    assert len(state["languages"]) >= 5
    assert "GROQ_API_KEY" in state["translation"]["detail"]


def test_interpretation_status_never_leaks_keys(monkeypatch) -> None:
    from clearcommit_teams.audio import interpret

    monkeypatch.setenv("GROQ_API_KEY", "sk-groq-secret-value")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-secret-value")
    state = interpret.status()
    blob = str(state)
    assert "sk-groq-secret-value" not in blob
    assert "el-secret-value" not in blob


def test_translate_rejects_empty_text() -> None:
    from clearcommit_teams.audio import interpret

    try:
        interpret.translate("   ", "ur")
    except interpret.InterpretationError as exc:
        assert exc.code == "empty_text"
    else:
        raise AssertionError("empty text must be refused")


def test_translate_rejects_unknown_language() -> None:
    from clearcommit_teams.audio import interpret

    try:
        interpret.translate("hello", "klingon")
    except interpret.InterpretationError as exc:
        assert exc.code == "bad_language"
    else:
        raise AssertionError("an unsupported language must be refused")


def test_translate_requires_a_key(monkeypatch) -> None:
    from clearcommit_teams.audio import interpret

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    try:
        interpret.translate("hello", "ur")
    except interpret.InterpretationError as exc:
        assert exc.code == "provider_not_configured"
    else:
        raise AssertionError("translation without a key must be refused")


def test_language_names_cover_the_ui_list() -> None:
    from clearcommit_teams.audio import interpret

    for code, name in interpret.SUPPORTED_LANGUAGES:
        assert interpret.language_name(code) == name


# --- configurable models --------------------------------------------------

def test_stt_model_defaults_to_the_accurate_variant(monkeypatch) -> None:
    from clearcommit_teams.audio import transcribe

    monkeypatch.delenv("CLEARCOMMIT_STT_MODEL_GROQ", raising=False)
    assert transcribe.stt_model("groq") == "whisper-large-v3"
    assert transcribe.DEFAULT_GROQ_STT_MODEL != "whisper-large-v3-turbo"


def test_stt_model_precedence_override_then_env(monkeypatch) -> None:
    from clearcommit_teams.audio import transcribe

    monkeypatch.setenv("CLEARCOMMIT_STT_MODEL_GROQ", "whisper-large-v3-turbo")
    assert transcribe.stt_model("groq") == "whisper-large-v3-turbo"
    # An explicit setting beats the environment.
    assert transcribe.stt_model("groq", "whisper-large-v3") == "whisper-large-v3"


def test_provider_status_reports_the_configured_model(monkeypatch) -> None:
    from clearcommit_teams.audio import transcribe

    monkeypatch.delenv("CLEARCOMMIT_STT_MODEL_GROQ", raising=False)
    state = transcribe.provider_status("whisper-large-v3")
    assert state["model"] == "whisper-large-v3"


def test_tts_settings_override_then_env_then_default(monkeypatch) -> None:
    from clearcommit_teams.audio import interpret

    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("CLEARCOMMIT_TTS_MODEL", raising=False)
    defaults = interpret.tts_settings()
    assert defaults["voice"] == interpret.ELEVENLABS_VOICE
    assert defaults["model"] == interpret.ELEVENLABS_MODEL
    override = interpret.tts_settings("voice-x", "model-y")
    assert override["voice"] == "voice-x"
    assert override["model"] == "model-y"
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env-voice")
    assert interpret.tts_settings()["voice"] == "env-voice"
    # Explicit still wins over the environment.
    assert interpret.tts_settings("explicit")["voice"] == "explicit"
