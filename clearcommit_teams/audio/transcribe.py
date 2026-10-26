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
    speaker: str | None = None


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
    groq = groq_key()
    deepgram = deepgram_key()
    return {
        "provider": "groq-whisper",
        "configured": bool(groq),
        "model": "whisper-large-v3",
        "detail": (
            "Groq Whisper is configured."
            if groq
            else "Set GROQ_API_KEY to enable live transcription."
        ),
        "diarization": {
            "provider": "deepgram-nova",
            "configured": bool(deepgram),
            "model": "nova-3",
            "detail": (
                "Speaker separation is available."
                if deepgram
                else "Set DEEPGRAM_API_KEY to enable speaker separation."
            ),
        },
    }


class GroqTranscriber:
    name = "groq-whisper"

    def __init__(self, api_key: str | None = None, model: str = "whisper-large-v3"):
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


def deepgram_key() -> str | None:
    for name in ("DEEPGRAM_API_KEY", "CLEARCOMMIT_DEEPGRAM_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


class DeepgramTranscriber:
    """Deepgram Nova with speaker diarization.

    Returns one segment per speaker turn, so the caller can label who said
    what. Used when the caller asks for speaker separation; Groq remains the
    faster default when labels are not needed.
    """

    name = "deepgram-nova"

    def __init__(self, api_key: str | None = None, model: str = "nova-3"):
        self.api_key = api_key or deepgram_key()
        self.model = model
        if not self.api_key:
            raise TranscriptionError(
                "Speaker separation needs DEEPGRAM_API_KEY to be set.",
                code="provider_not_configured",
            )

    def transcribe_turns(
        self, wav_bytes: bytes, language: str | None = None
    ) -> list[TranscriptSegment]:
        if not wav_bytes:
            raise TranscriptionError("No audio was captured.", code="empty_audio")
        if len(wav_bytes) > MAX_AUDIO_BYTES:
            raise TranscriptionError(
                "That audio chunk is too large to transcribe.", code="audio_too_large"
            )

        import httpx

        params: list[tuple[str, str]] = [
            ("model", self.model),
            ("smart_format", "true"),
            ("punctuate", "true"),
            ("utterances", "true"),
            ("diarize_model", "latest"),
        ]
        if language:
            params.append(("language", language))

        try:
            response = httpx.post(
                "https://api.deepgram.com/v1/listen",
                params=params,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "audio/wav",
                },
                content=wav_bytes,
                timeout=60.0,
            )
        except httpx.TimeoutException as exc:
            raise TranscriptionError(
                "The transcription provider timed out.", code="provider_timeout", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise TranscriptionError(
                "The transcription provider is unreachable.",
                code="provider_unavailable",
                retryable=True,
            ) from exc

        if response.status_code in (401, 403):
            raise TranscriptionError(
                "The transcription provider rejected the API key.", code="provider_auth"
            )
        if response.status_code == 429:
            raise TranscriptionError(
                "The transcription provider is rate limiting. Try again shortly.",
                code="provider_rate_limit",
                retryable=True,
            )
        if response.status_code >= 400:
            raise TranscriptionError(
                f"The transcription provider returned {response.status_code}.",
                code="provider_error",
                retryable=response.status_code >= 500,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionError(
                "The transcription provider returned an unreadable response.",
                code="provider_error",
            ) from exc

        return parse_deepgram(payload)


def _deepgram_speaker(raw: object) -> str | None:
    """Normalise Deepgram's integer speaker into SPEAKER_00 form."""
    if raw is None:
        return None
    try:
        return f"SPEAKER_{int(raw):02d}"
    except (TypeError, ValueError):
        return None


def parse_deepgram(payload: dict) -> list[TranscriptSegment]:
    """Turn a Deepgram response into speaker-labelled segments."""
    results = (payload or {}).get("results") or {}
    utterances = results.get("utterances") or []
    segments: list[TranscriptSegment] = []
    if utterances:
        for utterance in utterances:
            text = str(utterance.get("transcript") or "").strip()
            if not text:
                continue
            start = float(utterance.get("start") or 0.0)
            end = float(utterance.get("end") or 0.0)
            segments.append(
                TranscriptSegment(
                    text=text,
                    language=None,
                    duration_s=max(0.0, end - start),
                    speaker=_deepgram_speaker(utterance.get("speaker")),
                )
            )
        return segments

    # Fall back to the flat transcript when no utterance breakdown is present.
    channels = results.get("channels") or []
    alternative = (channels[0].get("alternatives") if channels else None) or [{}]
    text = str((alternative[0] or {}).get("transcript") or "").strip()
    if text:
        segments.append(TranscriptSegment(text=text))
    return segments


class DiarizingTranscriber:
    """Adapter exposing turn-based diarization through the single-segment API.

    ``transcribe()`` returns the joined text with the first speaker attached so
    existing callers keep working; ``transcribe_turns()`` returns every turn.
    """

    name = "deepgram-nova"

    def __init__(self, inner: DeepgramTranscriber | None = None):
        self.inner = inner or DeepgramTranscriber()

    def transcribe_turns(self, wav_bytes: bytes, language: str | None = None):
        return self.inner.transcribe_turns(wav_bytes, language)

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> TranscriptSegment:
        turns = self.transcribe_turns(wav_bytes, language)
        if not turns:
            raise TranscriptionError("No speech was recognised in that audio.", code="empty_transcript")
        return TranscriptSegment(
            text=" ".join(turn.text for turn in turns).strip(),
            language=language,
            duration_s=sum(turn.duration_s or 0.0 for turn in turns) or None,
            speaker=turns[0].speaker,
        )


def get_transcriber(provider: str = "groq") -> Transcriber:
    """Return a transcriber. Groq is the default; Deepgram adds speakers."""
    if str(provider).strip().lower() in {"deepgram", "diarize", "speakers"}:
        return DiarizingTranscriber()
    return GroqTranscriber()
