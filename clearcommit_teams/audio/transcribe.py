"""Transcription behind a small interface.

The capture layer produces WAV bytes; this module turns them into text. The
provider is replaceable: :class:`GroqTranscriber` is the first adapter, and
tests use a deterministic fake instead of calling any paid API.

Keys are read from the environment only. They are never stored in the
database, returned through the bridge, or written to logs.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Protocol

MAX_AUDIO_BYTES = 24 * 1024 * 1024  # Groq accepts up to 25 MB


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    language: str | None = None
    duration_s: float | None = None


class TranscriptionError(RuntimeError):
    """A provider could not transcribe the audio."""

    def __init__(self, message: str, code: str = "transcription_failed", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Transcriber(Protocol):
    name: str

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> TranscriptSegment:
        ...


def groq_key() -> str | None:
    for name in ("GROQ_API_KEY", "CLEARCOMMIT_GROQ_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def provider_status() -> dict:
    key = groq_key()
    return {
        "provider": "groq-whisper",
        "configured": bool(key),
        "model": "whisper-large-v3-turbo",
        "detail": (
            "Groq Whisper is configured."
            if key
            else "Set GROQ_API_KEY to enable live transcription."
        ),
    }


class GroqTranscriber:
    name = "groq-whisper"

    def __init__(self, api_key: str | None = None, model: str = "whisper-large-v3-turbo"):
        self.api_key = api_key or groq_key()
        self.model = model
        if not self.api_key:
            raise TranscriptionError(
                "Live transcription needs GROQ_API_KEY to be set.",
                code="provider_not_configured",
            )

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> TranscriptSegment:
        if not wav_bytes:
            raise TranscriptionError("No audio was captured.", code="empty_audio")
        if len(wav_bytes) > MAX_AUDIO_BYTES:
            raise TranscriptionError(
                "That audio chunk is too large to transcribe.",
                code="audio_too_large",
            )

        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover - depends on install
            raise TranscriptionError(
                "The 'groq' package is not installed.", code="provider_unavailable"
            ) from exc

        import httpx

        client = Groq(api_key=self.api_key, timeout=httpx.Timeout(30.0, connect=10.0))
        try:
            result = client.audio.transcriptions.create(
                file=("segment.wav", io.BytesIO(wav_bytes), "audio/wav"),
                model=self.model,
                language=language or None,
                response_format="verbose_json",
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            message = str(exc)
            lowered = message.lower()
            if "401" in message or "unauthorized" in lowered:
                raise TranscriptionError(
                    "The transcription provider rejected the API key.",
                    code="provider_auth",
                ) from exc
            if "429" in message or "rate" in lowered:
                raise TranscriptionError(
                    "The transcription provider is rate limiting. Try again shortly.",
                    code="provider_rate_limit",
                    retryable=True,
                ) from exc
            if "timeout" in lowered:
                raise TranscriptionError(
                    "The transcription provider timed out.",
                    code="provider_timeout",
                    retryable=True,
                ) from exc
            raise TranscriptionError(
                "The transcription provider could not process that audio.",
                code="provider_error",
                retryable=True,
            ) from exc

        text = (getattr(result, "text", None) or "").strip()
        if not text:
            raise TranscriptionError("No speech was recognised in that audio.", code="empty_transcript")
        return TranscriptSegment(
            text=text,
            language=getattr(result, "language", None) or language,
            duration_s=getattr(result, "duration", None),
        )


def get_transcriber() -> Transcriber:
    return GroqTranscriber()
