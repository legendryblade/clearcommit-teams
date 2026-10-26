"""Live interpretation: translate speech, then speak it in the other language.

Two halves, both optional and both off until the user enables them:

1. translate() — one fast chat-completions call. Text only, no audio.
2. synthesise() — natural-voice TTS (ElevenLabs when configured, Groq Orpheus
   otherwise) returning MP3 bytes.

``speak_to_device`` plays the audio out of a chosen output device, which is how
the translated voice reaches a virtual cable so the other participant hears it.
Nothing here runs on import.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass

# Languages the UI offers. Codes are BCP-47 where the provider expects them.
SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("ur", "Urdu"),
    ("ar", "Arabic"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("hi", "Hindi"),
    ("en", "English"),
)

_LANGUAGE_NAMES = dict(SUPPORTED_LANGUAGES)

TRANSLATION_MODEL = "qwen/qwen3.8-27b"
ELEVENLABS_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah, a premade voice on free plans
ELEVENLABS_MODEL = "eleven_turbo_v2_5"


class InterpretationError(RuntimeError):
    def __init__(self, message: str, code: str = "interpretation_failed", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _groq_key() -> str | None:
    return (os.environ.get("GROQ_API_KEY") or "").strip() or None


def _elevenlabs_key() -> str | None:
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip() or None


def language_name(code: str) -> str:
    return _LANGUAGE_NAMES.get(code, code)


def status() -> dict:
    return {
        "translation": {
            "configured": bool(_groq_key()),
            "model": TRANSLATION_MODEL,
            "detail": "Translation is available." if _groq_key() else "Set GROQ_API_KEY to translate.",
        },
        "speech": {
            "configured": bool(_elevenlabs_key()) or bool(_groq_key()),
            "provider": "elevenlabs" if _elevenlabs_key() else "groq-orpheus",
            "detail": (
                "Natural voice synthesis is available."
                if (_elevenlabs_key() or _groq_key())
                else "Set ELEVENLABS_API_KEY (or GROQ_API_KEY) to speak translations."
            ),
        },
        "languages": [{"code": c, "name": n} for c, n in SUPPORTED_LANGUAGES],
    }


@dataclass(frozen=True)
class Translation:
    text: str
    target: str
    target_name: str


def translate(text: str, target: str, source: str | None = None) -> Translation:
    """Translate ``text`` into ``target``. Returns text only."""
    text = (text or "").strip()
    if not text:
        raise InterpretationError("There is no text to translate.", code="empty_text")
    if target not in _LANGUAGE_NAMES:
        raise InterpretationError(f"Unsupported target language: {target}", code="bad_language")
    key = _groq_key()
    if not key:
        raise InterpretationError(
            "Translation needs GROQ_API_KEY to be set.", code="provider_not_configured"
        )

    import httpx

    instruction = f"Translate the user's text into {language_name(target)}."
    if source:
        instruction += f" The text is in {language_name(source)}."
    instruction += (
        " Reply with the translation only: no notes, no transliteration, no quotes."
    )

    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": TRANSLATION_MODEL,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
                "max_tokens": 500,
            },
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise InterpretationError(
            "The translation service is unreachable.", code="provider_unavailable", retryable=True
        ) from exc

    if response.status_code in (401, 403):
        raise InterpretationError("The translation key was rejected.", code="provider_auth")
    if response.status_code == 429:
        raise InterpretationError(
            "Translation is rate limited. Try again shortly.", code="provider_rate_limit", retryable=True
        )
    if response.status_code >= 400:
        raise InterpretationError(
            f"The translation service returned {response.status_code}.", code="provider_error"
        )

    try:
        payload = response.json()
        translated = payload["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError) as exc:
        raise InterpretationError(
            "The translation service returned an unreadable response.", code="bad_response"
        ) from exc

    if not translated:
        raise InterpretationError("The translation came back empty.", code="empty_text")
    return Translation(text=translated, target=target, target_name=language_name(target))


def synthesise(text: str, target: str = "en") -> bytes:
    """Return spoken audio (MP3) for ``text`` in a natural voice."""
    text = (text or "").strip()
    if not text:
        raise InterpretationError("There is no text to speak.", code="empty_text")

    key = _elevenlabs_key()
    if key:
        return _elevenlabs(text, key)
    groq = _groq_key()
    if groq:
        return _groq_orpheus(text, groq, target)
    raise InterpretationError(
        "Speaking translations needs ELEVENLABS_API_KEY or GROQ_API_KEY.",
        code="provider_not_configured",
    )


def _elevenlabs(text: str, key: str) -> bytes:
    import httpx

    voice = os.environ.get("ELEVENLABS_VOICE_ID") or ELEVENLABS_VOICE
    try:
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={"text": text, "model_id": ELEVENLABS_MODEL},
            timeout=45.0,
        )
    except httpx.HTTPError as exc:
        raise InterpretationError(
            "The speech service is unreachable.", code="provider_unavailable", retryable=True
        ) from exc

    if response.status_code == 401:
        raise InterpretationError("The speech key was rejected.", code="provider_auth")
    if response.status_code == 402:
        raise InterpretationError(
            "This speech voice requires a paid plan. Choose another voice or provider.",
            code="provider_payment_required",
        )
    if response.status_code == 429:
        raise InterpretationError(
            "Speech synthesis is rate limited.", code="provider_rate_limit", retryable=True
        )
    if response.status_code >= 400:
        raise InterpretationError(
            f"The speech service returned {response.status_code}.", code="provider_error"
        )
    if not response.content:
        raise InterpretationError("The speech service returned no audio.", code="empty_audio")
    return response.content


def _groq_orpheus(text: str, key: str, target: str) -> bytes:
    """Fallback synthesis. Only English and Saudi Arabic are available."""
    import httpx

    if target == "ar":
        model, voice = "canopylabs/orpheus-arabic-saudi", "abdullah"
    else:
        model, voice = "canopylabs/orpheus-v1-english", "troy"

    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "input": text, "voice": voice, "response_format": "wav"},
            timeout=45.0,
        )
    except httpx.HTTPError as exc:
        raise InterpretationError(
            "The speech service is unreachable.", code="provider_unavailable", retryable=True
        ) from exc

    if response.status_code >= 400:
        detail = response.text[:160]
        raise InterpretationError(
            "The speech provider refused the request. " + detail, code="provider_error"
        )
    if not response.content:
        raise InterpretationError("The speech service returned no audio.", code="empty_audio")
    return response.content


def output_devices() -> list[tuple[int, str]]:
    """Playback devices the translated voice can be sent to (VB-CABLE etc.)."""
    try:
        import sounddevice as sd
    except Exception:
        return []
    try:
        found = []
        for index, device in enumerate(sd.query_devices()):
            if device.get("max_output_channels", 0) > 0:
                found.append((index, str(device["name"])))
        return found
    except Exception:
        return []


def speak_to_device(audio: bytes, device: int | None = None) -> None:
    """Play ``audio`` out of ``device`` (by default the system default output)."""
    if not audio:
        raise InterpretationError("There is no audio to play.", code="empty_audio")
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        raise InterpretationError(
            "Playback needs the audio extras to be installed.", code="provider_unavailable"
        ) from exc

    try:
        import io as _io

        data, rate = _decode_audio(audio)
    except Exception as exc:
        raise InterpretationError(
            "That audio could not be decoded for playback.", code="bad_audio"
        ) from exc

    try:
        sd.play(data, rate, device=device, blocking=True)
    except Exception as exc:
        raise InterpretationError(
            "The audio output device could not play the translation.", code="playback_failed"
        ) from exc


def _decode_audio(audio: bytes):
    """Decode MP3 or WAV bytes into (float32 mono samples, sample_rate)."""
    import numpy as np

    # WAV: parse the header directly, no extra dependency.
    if audio[:4] == b"RIFF":
        import wave

        with wave.open(io.BytesIO(audio), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
            frames = handle.readframes(handle.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        return samples, rate

    # MP3: use whatever decoder is installed.
    try:
        from pydub import AudioSegment  # type: ignore

        segment = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
        samples = np.array(segment.get_array_of_samples(), dtype=np.float32)
        samples = samples / (32768.0 if segment.sample_width == 2 else 1.0)
        if segment.channels > 1:
            samples = samples.reshape(-1, segment.channels).mean(axis=1)
        return samples, segment.frame_rate
    except Exception:
        pass

    try:
        import miniaudio  # type: ignore

        decoded = miniaudio.decode(audio)
        samples = np.array(decoded.samples, dtype=np.float32) / 32768.0
        if decoded.nchannels > 1:
            samples = samples.reshape(-1, decoded.nchannels).mean(axis=1)
        return samples, decoded.sample_rate
    except Exception as exc:
        raise RuntimeError("no MP3 decoder available") from exc
