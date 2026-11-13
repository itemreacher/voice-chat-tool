"""Decide whether a recording is worth transcribing (OS independent, needs numpy)."""
from __future__ import annotations

from typing import Optional

import numpy as np

SAMPLE_RATE = 16000
MIN_SECONDS = 0.4
SILENCE_RMS = 0.0008  # about -62 dBFS: only truly dead input; Whisper's VAD handles the rest


def check_audio(samples: Optional[np.ndarray], sample_rate: int = SAMPLE_RATE) -> Optional[str]:
    """Return None if usable, otherwise a short reason to skip it."""
    if samples is None or samples.size == 0:
        return "no audio captured"
    if samples.size / float(sample_rate) < MIN_SECONDS:
        return "recording shorter than 0.4 s"
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms < SILENCE_RMS:
        return f"audio is silent (level {rms:.4f}, need {SILENCE_RMS}); raise the microphone gain"
    return None
