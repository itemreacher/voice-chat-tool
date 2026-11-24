"""Cut a continuous audio stream into speech chunks at pauses (pure, numpy only).

Used for desktop audio: the stream never ends, so it is split where the sound gets quiet, and forcibly
after `max_segment_s`, so the text appears while a video is still playing.

The speech decision is a simple energy rule that adapts to the background level (music, noise), because
Whisper's own voice detection runs on every finished chunk anyway; this only has to find sensible cut points.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Chunk:
    start: float            # seconds from the start of the stream (including the lead-in)
    audio: np.ndarray       # float32 mono at SAMPLE_RATE

    @property
    def duration(self) -> float:
        return len(self.audio) / SAMPLE_RATE


class Segmenter:
    def __init__(self, frame_ms: int = 20, min_speech_s: float = 0.5, end_silence_s: float = 0.7,
                 max_segment_s: float = 25.0, lead_in_s: float = 0.25, min_rms: float = 0.004,
                 speech_factor: float = 3.0):
        self.frame = int(SAMPLE_RATE * frame_ms / 1000)
        self.min_speech = int(min_speech_s * SAMPLE_RATE)
        self.end_silence = int(end_silence_s * SAMPLE_RATE)
        self.max_segment = int(max_segment_s * SAMPLE_RATE)
        self.lead_in = int(lead_in_s * SAMPLE_RATE)
        self.min_rms, self.speech_factor = min_rms, speech_factor
        self._pending = np.zeros(0, dtype=np.float32)     # not yet a full frame
        self._pos = 0                                     # samples consumed from the stream so far
        self._levels: Deque[float] = deque(maxlen=int(10 * SAMPLE_RATE / self.frame))  # last ~10 s of frame levels
        self._floor = min_rms / self.speech_factor        # background level (10th percentile of the recent past)
        self._tail = np.zeros(0, dtype=np.float32)        # recent quiet audio kept as lead-in
        self._buf: List[np.ndarray] = []                  # frames of the chunk being built
        self._buf_start = 0
        self._speech = 0                                  # samples of speech in the current chunk
        self._quiet = 0                                   # quiet samples since the last speech

    # ------------------------------------------------------------------ public
    def feed(self, samples: np.ndarray) -> List[Chunk]:
        """Add audio; returns the chunks that are complete now (possibly none)."""
        data = np.concatenate([self._pending, np.asarray(samples, dtype=np.float32).ravel()])
        done: List[Chunk] = []
        usable = (len(data) // self.frame) * self.frame
        for i in range(0, usable, self.frame):
            chunk = self._frame(data[i:i + self.frame])
            if chunk is not None:
                done.append(chunk)
        self._pending = data[usable:]
        return done

    def flush(self) -> List[Chunk]:
        """End of the stream: whatever speech is left becomes a final chunk."""
        out = []
        if self._buf and self._speech >= self.min_speech:
            out.append(self._close(keep_quiet=self._quiet))
        self._reset()
        return out

    # ------------------------------------------------------------------ internals
    def _is_speech(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        speech = rms > max(self.min_rms, self.speech_factor * self._floor)
        self._levels.append(rms)
        if len(self._levels) >= 10:                       # constant music/noise raises the floor, speech stays above it
            self._floor = float(np.percentile(self._levels, 10))
        return speech

    def _frame(self, frame: np.ndarray) -> Optional[Chunk]:
        speech = self._is_speech(frame)
        start_of_frame = self._pos
        self._pos += len(frame)
        if not self._buf:
            if speech:
                lead = self._tail[-self.lead_in:]
                self._buf, self._buf_start = [lead, frame], start_of_frame - len(lead)
                self._speech, self._quiet = len(frame), 0
            else:
                self._tail = np.concatenate([self._tail, frame])[-self.lead_in:]
            return None
        self._buf.append(frame)
        if speech:
            self._speech += len(frame)
            self._quiet = 0
        else:
            self._quiet += len(frame)
        length = sum(len(b) for b in self._buf)
        if self._quiet >= self.end_silence:
            chunk = self._close(keep_quiet=int(0.3 * SAMPLE_RATE)) if self._speech >= self.min_speech else None
            self._reset()
            return chunk
        if length >= self.max_segment:
            return self._force_cut()
        return None

    def _close(self, keep_quiet: int) -> Chunk:
        audio = np.concatenate(self._buf)
        trim = max(0, self._quiet - keep_quiet)
        if trim:
            audio = audio[:len(audio) - trim]
        return Chunk(self._buf_start / SAMPLE_RATE, audio.astype(np.float32, copy=False))

    def _force_cut(self) -> Chunk:
        """Too long without a pause: cut where it is quietest in the last few seconds."""
        audio = np.concatenate(self._buf)
        window = int(4 * SAMPLE_RATE)
        tail = audio[-window:]
        usable = (len(tail) // self.frame) * self.frame
        energies = np.sqrt(np.mean(np.square(tail[:usable].reshape(-1, self.frame), dtype=np.float64), axis=1))
        cut = len(audio) - window + int(np.argmin(energies)) * self.frame + self.frame // 2 if usable else len(audio)
        first, rest = audio[:cut], audio[cut:]
        chunk = Chunk(self._buf_start / SAMPLE_RATE, first.astype(np.float32, copy=False))
        self._buf = [rest]
        self._buf_start += cut
        self._speech, self._quiet = len(rest), 0
        return chunk

    def _reset(self) -> None:
        self._buf, self._speech, self._quiet = [], 0, 0
        self._tail = np.zeros(0, dtype=np.float32)
