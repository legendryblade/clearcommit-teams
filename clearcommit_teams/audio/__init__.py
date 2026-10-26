"""Optional desktop audio capture.

Nothing here runs unless the user explicitly starts a recording. The device
libraries are imported lazily so a machine without them still runs the whole
transcript-import workflow: :func:`availability` reports what is missing
instead of raising at import time.

Capture yields 16 kHz mono WAV chunks from a local voice-activity gate; raw
audio never leaves this machine. Only transcript text is ever sent anywhere,
and only to the configured transcription provider.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

REQUIRED_MODULES = {
    "sounddevice": "microphone capture",
    "pyaudiowpatch": "Windows system-audio capture",
    "numpy": "audio processing",
}


@dataclass(frozen=True)
class Availability:
    available: bool
    missing: tuple[str, ...]
    detail: str


def availability() -> Availability:
    missing = tuple(
        module for module in REQUIRED_MODULES
        if importlib.util.find_spec(module) is None
    )
    if not missing:
        return Availability(True, (), "Audio capture is available.")
    names = ", ".join(REQUIRED_MODULES[m] for m in missing)
    return Availability(
        False,
        missing,
        f"Audio capture needs {names}. Install the audio extras to enable it.",
    )


def _require() -> None:
    state = availability()
    if not state.available:
        raise RuntimeError(state.detail)


def list_microphones() -> list[tuple[int, str]]:
    _require()
    from .mic import list_microphones as _list

    return _list()


def list_output_devices() -> list[tuple[int, str, int, int]]:
    _require()
    from .mic import list_audio_devices as _list

    return _list()


def default_loopback_available() -> bool:
    """True when Windows exposes a WASAPI loopback device."""
    state = availability()
    if not state.available:
        return False
    try:
        from .loopback import LoopbackCapture

        return LoopbackCapture()._find_loopback_device() is not None  # noqa: SLF001
    except Exception:
        return False


class CaptureSession:
    """One active capture at a time, microphone or system audio."""

    def __init__(self, source: str, device: Any = None) -> None:
        self.source = source
        self.device = device
        self._capture = None
        self._started = False

    def start(self) -> None:
        _require()
        if self._started:
            return
        if self.source == "system":
            from .loopback import LoopbackCapture

            self._capture = LoopbackCapture(output_device=self.device)
        else:
            from .mic import MicCapture

            self._capture = MicCapture(device=self.device)
        self._capture.start()
        self._started = True

    def stop(self) -> None:
        if self._capture is not None:
            try:
                self._capture.stop()
            finally:
                self._started = False

    @property
    def active(self) -> bool:
        return self._started

    def utterances(self):
        if self._capture is None:
            return iter(())
        return self._capture.utterances()

    def drain(self) -> list[bytes]:
        """Return completed utterances available *now*, never blocking.

        ``utterances()`` is an endless generator that ends only at stop(), so
        polling it directly would hang. This reads whatever the queue holds and
        returns immediately.
        """
        if self._capture is None:
            return []
        queue_obj = getattr(self._capture, "_utt_q", None)
        if queue_obj is None:
            return []
        chunks: list[bytes] = []
        while True:
            try:
                chunks.append(queue_obj.get_nowait())
            except Exception:
                break
        return chunks
