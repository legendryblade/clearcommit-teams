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
