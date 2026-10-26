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


def _is_output_or_loopback(index: int) -> bool:
    """True when the index can carry system audio (playback or loopback)."""
    try:
        import pyaudiowpatch as pyaudio

        audio = pyaudio.PyAudio()
        try:
            info = audio.get_device_info_by_index(int(index))
        finally:
            audio.terminate()
        return bool(info.get("maxOutputChannels", 0) > 0 or info.get("isLoopbackDevice"))
    except Exception:
        return False


def loopback_devices() -> list[tuple[int, str]]:
    """Every capture endpoint that can record what the machine plays."""
    state = availability()
    if not state.available:
        return []
    try:
        import pyaudiowpatch as pyaudio

        audio = pyaudio.PyAudio()
        try:
            found = []
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info.get("isLoopbackDevice"):
                    found.append((i, str(info["name"]).replace(" [Loopback]", "")))
            return found
        finally:
            audio.terminate()
    except Exception:
        return []


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


def _host_api_name(sd, index: int) -> str:
    try:
        return str(sd.query_hostapis(sd.query_devices(index)["hostapi"])["name"])
    except Exception:
        return ""


def probe_microphones(seconds: float = 0.35) -> list[tuple[int, str, int]]:
    """Measure each input's live level: (index, name, peak).

    A machine commonly has several inputs and the Windows default is often a
    silent one. Measuring a short sample lets the app offer the microphones
    that actually work first, instead of a device that hears nothing.
    """
    _require()
    import numpy as np
    import sounddevice as sd

    measured: list[tuple[int, str, int]] = []
    for index, device in enumerate(sd.query_devices()):
        if device.get("max_input_channels", 0) < 1:
            continue
        # WDM-KS devices can be opened once for a one-shot recording but cannot
        # stream, so they are not usable for live capture. Only consider host
        # APIs that actually support streaming.
        if "WDM-KS" in _host_api_name(sd, index):
            continue
        rate = int(device.get("default_samplerate", 16000) or 16000)
        try:
            recording = sd.rec(
                int(rate * seconds),
                samplerate=rate,
                channels=1,
                dtype="int16",
                device=index,
            )
            sd.wait()
            peak = int(np.abs(recording).max())
        except Exception:
            continue
        measured.append((index, str(device["name"]), peak))
    return measured


def preferred_microphone(threshold: int = 300) -> int | None:
    """The best working physical microphone.

    Virtual devices (VB-Audio, sound mapper, stereo mix) are ranked last: they
    are useful for routing but are not what a person expects to speak into.
    """
    measured = [m for m in probe_microphones() if m[2] >= threshold]
    if not measured:
        return None

    def rank(entry: tuple[int, str, int]) -> tuple[int, int]:
        name = entry[1].lower()
        virtual = any(
            key in name
            for key in ("vb-audio", "cable", "sound mapper", "primary sound", "stereo mix", "point")
        )
        return (1 if virtual else 0, -entry[2])

    return sorted(measured, key=rank)[0][0]


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
    """One active capture, optionally listening to both sides of a call.

    In a one-to-one call the microphone is the person using ClearCommit and the
    system audio is the other participant. Capturing both at once therefore
    labels the speakers by source, which is more reliable than asking a
    diarization model to guess between two channels.
    """

    def __init__(
        self,
        source: str,
        device: Any = None,
        *,
        system_device: Any = None,
        include_system: bool = False,
    ) -> None:
        self.source = source
        self.device = device
        self.system_device = system_device
        self.include_system = include_system
        self._capture = None
        self._system_capture = None
        self._started = False

    def start(self) -> None:
        _require()
        if self._started:
            return

        if self.source == "system" or self.include_system:
            self._system_capture = self._open_system(self.system_device or self.device)
        if self.source == "microphone" or self.include_system:
            self._capture = self._open_mic(self.device if self.source == "microphone" else None)

        started = []
        try:
            if self._capture is not None:
                self._capture.start()
                started.append(self._capture)
            if self._system_capture is not None:
                self._system_capture.start()
                started.append(self._system_capture)
        except Exception as exc:  # PortAudio raises opaque host errors
            for capture in started:
                try:
                    capture.stop()
                except Exception:
                    pass
            self._capture = None
            self._system_capture = None
            raise RuntimeError(
                "The audio device could not be opened. Choose a different device "
                "and make sure it is not in use by another application."
            ) from exc
        self._started = True

    @staticmethod
    def _open_system(device):
        from .loopback import LoopbackCapture

        chosen = device
        if chosen is not None and not _is_output_or_loopback(chosen):
            chosen = None
        return LoopbackCapture(output_device=chosen)

    @staticmethod
    def _open_mic(device):
        from .mic import MicCapture

        return MicCapture(device=device)

    def stop(self) -> None:
        for capture in (self._capture, self._system_capture):
            if capture is not None:
                try:
                    capture.stop()
                except Exception:
                    pass
        self._started = False

    @property
    def active(self) -> bool:
        return self._started

    def utterances(self):
        if self._capture is None:
            return iter(())
        return self._capture.utterances()

    def drain_both(self) -> list[tuple[str, bytes]]:
        """Return (source, wav) pairs ready now, never blocking."""
        chunks: list[tuple[str, bytes]] = []
        for label, capture in (("microphone", self._capture), ("system", self._system_capture)):
            if capture is None:
                continue
            queue_obj = getattr(capture, "_utt_q", None)
            if queue_obj is None:
                continue
            while True:
                try:
                    chunks.append((label, queue_obj.get_nowait()))
                except Exception:
                    break
        return chunks
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
