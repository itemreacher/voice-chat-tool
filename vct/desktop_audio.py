"""Transcribe what the PC plays (desktop audio) while it plays: a video, a stream, a call.

Windows WASAPI loopback (PyAudioWPatch) records the default output device. The audio is converted to 16 kHz
mono, cut at pauses (vct.segmenter) and transcribed chunk by chunk with the shared Whisper model, so the
text appears live. Everything the PC plays is recorded, so the caller should make that visible to the user.

Threads: capture callback (tiny) -> reader (convert + cut) -> worker (Whisper + translation).
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .segmenter import SAMPLE_RATE, Chunk, Segmenter
from .transcript import Line, Spoken, drop_repeats

Log = Callable[[str], None]
NO_SPEECH_PROB = 0.6      # Whisper's own rule: a segment that is probably no speech AND unsure is dropped
LOW_LOGPROB = -1.0


class CaptureError(Exception):
    pass


# ---------------------------------------------------------------- conversion (testable without hardware)
class MonoResampler:
    """Interleaved float32 frames of any rate/channel count -> mono float32 at 16 kHz (streaming)."""

    def __init__(self, rate: int, channels: int, use_av: bool = True):
        self.rate, self.channels = int(rate), max(1, int(channels))
        self._av = None
        if use_av and self.rate != SAMPLE_RATE:
            try:
                import av

                self._av = (av, av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE))
            except Exception:
                self._av = None
        self._carry = np.zeros(0, dtype=np.float32)   # fallback: samples left over between blocks
        self._frac = 0.0                              # fallback: fractional read position

    def process(self, data: bytes) -> np.ndarray:
        raw = np.frombuffer(data[:len(data) // 4 * 4], dtype=np.float32)   # whole float32 values only
        usable = (len(raw) // self.channels) * self.channels
        mono = raw[:usable].reshape(-1, self.channels).mean(axis=1).astype(np.float32, copy=False)
        if self.rate == SAMPLE_RATE or mono.size == 0:
            return mono
        return self._av_resample(mono) if self._av else self._linear_resample(mono)

    def _av_resample(self, mono: np.ndarray) -> np.ndarray:
        av, resampler = self._av
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(mono.reshape(1, -1)), format="flt", layout="mono")
        frame.sample_rate = self.rate
        out = resampler.resample(frame)
        frames = out if isinstance(out, list) else ([out] if out is not None else [])
        parts = [f.to_ndarray().reshape(-1) for f in frames]
        return np.concatenate(parts).astype(np.float32, copy=False) if parts else np.zeros(0, dtype=np.float32)

    def _linear_resample(self, mono: np.ndarray) -> np.ndarray:
        """Fallback without PyAV: average over the step, then interpolate. Good enough for speech."""
        step = self.rate / SAMPLE_RATE
        if self.rate % SAMPLE_RATE == 0:              # 48000, 32000, 96000 ...: exact block averages
            block = int(step)
            data = np.concatenate([self._carry, mono])
            usable = (len(data) // block) * block
            self._carry = data[usable:]
            return data[:usable].reshape(-1, block).mean(axis=1).astype(np.float32, copy=False)
        data = np.concatenate([self._carry, mono])
        positions = np.arange(self._frac, len(data) - 1, step)
        out = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
        consumed = int(positions[-1] + step) if len(positions) else 0
        self._frac = (positions[-1] + step - consumed) if len(positions) else self._frac
        self._carry = data[consumed:]
        return out


def level_percent(rms: float) -> int:
    """0..100 for a level meter: -60 dB is empty, 0 dB is full."""
    if rms <= 1e-6:
        return 0
    return int(max(0.0, min(100.0, (20 * np.log10(rms) + 60) / 60 * 100)))


# ---------------------------------------------------------------- capture
class LoopbackCapture:
    """Records the default output device (Windows only, needs PyAudioWPatch)."""

    def __init__(self) -> None:
        self.name = ""
        self._pa = None
        self._stream = None

    def start(self, on_audio: Callable[[np.ndarray], None]) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as exc:
            raise CaptureError("Desktop audio needs the PyAudioWPatch library (Windows only).") from exc
        try:
            self._pa = pyaudio.PyAudio()
            device = self._pa.get_default_wasapi_loopback()
            self.name = str(device["name"])
            rate, channels = int(device["defaultSampleRate"]), int(device["maxInputChannels"])
            resampler = MonoResampler(rate, channels)

            def callback(in_data, frame_count, time_info, status):
                try:
                    on_audio(resampler.process(in_data))
                except Exception:                      # never raise into the audio thread
                    pass
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                                         frames_per_buffer=rate // 20, input_device_index=device["index"],
                                         stream_callback=callback)
        except Exception as exc:
            self.stop()
            raise CaptureError(f"Could not record the desktop audio: {exc}") from exc

    def stop(self) -> None:
        for closer in (lambda: self._stream and (self._stream.stop_stream(), self._stream.close()),
                       lambda: self._pa and self._pa.terminate()):
            try:
                closer()
            except Exception:
                pass
        self._stream = self._pa = None


# ---------------------------------------------------------------- session
class ArgosTranslation:
    """Offline translation for the transcript: ready() makes sure the language packs exist (downloads
    them on first use), translate() does the work."""

    def __init__(self, log: Log):
        self.log = log

    def ready(self, source: str, target: str) -> bool:
        from . import translator

        return translator.ensure(source, target, self.log)

    def translate(self, text: str, source: str, target: str) -> str:
        from . import translator

        return translator.translate(text, source, target)


class DesktopSession:
    """One capture run. Create, start(), later stop(); lines arrive through on_line."""

    def __init__(self, transcriber, capture, log: Log, language: Optional[str] = None, translate_to: str = "",
                 translation=None,
                 on_line: Optional[Callable[[Line], None]] = None,
                 on_level: Optional[Callable[[float], None]] = None,
                 on_state: Optional[Callable[[str], None]] = None):
        self.transcriber, self.capture, self.log = transcriber, capture, log
        self.language, self.translate_to = language, translate_to
        self._translation = translation     # object with ready(src, tgt) and translate(text, src, tgt)
        self._on_line = on_line or (lambda _l: None)
        self._on_level = on_level or (lambda _r: None)
        self._on_state = on_state or (lambda _s: None)
        self.lines: List[Line] = []
        self.state = "idle"
        self.samples = 0
        self._segmenter = Segmenter()
        self._audio_q: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
        self._chunk_q: "queue.Queue[Optional[Chunk]]" = queue.Queue()
        self._threads: List[threading.Thread] = []
        self._can_translate: Dict[Tuple[str, str], bool] = {}

    @property
    def elapsed(self) -> float:
        return self.samples / SAMPLE_RATE

    @property
    def backlog(self) -> int:
        """Chunks waiting for recognition (grows when the PC is slower than the audio)."""
        return self._chunk_q.qsize()

    def _set(self, state: str) -> None:
        self.state = state
        self._on_state(state)

    def start(self) -> None:
        self._set("starting")
        self._threads = [threading.Thread(target=self._read_loop, name="desktop-reader", daemon=True),
                         threading.Thread(target=self._work_loop, name="desktop-worker", daemon=True)]
        for t in self._threads:
            t.start()
        try:
            self.capture.start(self._audio_q.put)
        except CaptureError as exc:
            self.log(f"ERROR: {exc}")
            self._audio_q.put(None)
            self._set("error")
            raise
        self.log(f"Desktop audio: recording '{getattr(self.capture, 'name', '') or 'default output'}'.")
        self._set("listening")

    def stop(self, timeout: float = 300.0) -> None:
        """Stop recording and finish the text of what was recorded so far."""
        if self.state in ("stopped", "idle"):
            return
        self.capture.stop()
        self._set("finishing")
        self._audio_q.put(None)
        for t in self._threads:
            t.join(timeout)
        self._set("stopped")

    def abort(self) -> None:
        """Stop right away without finishing the text (the window is closing)."""
        if self.state in ("stopped", "idle"):
            return
        self.capture.stop()
        self._audio_q.put(None)
        self._set("stopped")

    # ------------------------------------------------------------ threads
    def _read_loop(self) -> None:
        while True:
            audio = self._audio_q.get()
            if audio is None:
                for chunk in self._segmenter.flush():
                    self._chunk_q.put(chunk)
                self._chunk_q.put(None)
                return
            if audio.size == 0:
                continue
            self.samples += audio.size
            self._on_level(float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))))
            for chunk in self._segmenter.feed(audio):
                self._chunk_q.put(chunk)

    def _work_loop(self) -> None:
        while True:
            chunk = self._chunk_q.get()
            if chunk is None:
                return
            try:
                self._transcribe(chunk)
            except Exception as exc:                    # one bad chunk must not end the session
                self.log(f"ERROR while transcribing a desktop audio chunk: {exc}")

    def _transcribe(self, chunk: Chunk) -> None:
        segments, detected = self.transcriber.transcribe_segments(chunk.audio, self.language)
        language = self.language or detected
        for seg in segments:
            if seg.no_speech_prob > NO_SPEECH_PROB and seg.avg_logprob < LOW_LOGPROB:
                continue                                 # Whisper itself doubts that this is speech
            line = Line(chunk.start + seg.start, chunk.start + seg.end, seg.text, "", language or "")
            if drop_repeats(self.lines, line):
                continue
            translation = self._translate(seg.text, language)
            if translation:
                line = Line(line.start, line.end, line.text, translation, line.language)
            self.lines.append(line)
            self._on_line(line)

    def _translate(self, text: str, source: Optional[str]) -> str:
        target = self.translate_to
        if not target or not source or source == target or self._translation is None:
            return ""
        key = (source, target)
        if key not in self._can_translate:
            try:
                self._can_translate[key] = bool(self._translation.ready(source, target))
            except Exception as exc:
                self.log(f"Translation {source} -> {target} unavailable: {exc}")
                self._can_translate[key] = False
            if not self._can_translate[key]:
                self.log(f"Note: no translation {source} -> {target} (language packs missing); text stays original.")
        if not self._can_translate[key]:
            return ""
        try:
            return (self._translation.translate(text, source, target) or "").strip()
        except Exception as exc:
            self.log(f"Translation failed: {exc}")
            return ""
