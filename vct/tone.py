"""Soft notification tones as in-memory WAV data (pure stdlib, testable anywhere).

winsound.Beep is a harsh square wave; these are quiet sine tones with a smooth fade
in/out, so they are not annoying.
"""
from __future__ import annotations

import io
import math
import struct
import wave
from typing import Sequence, Tuple

RATE = 22050
VOLUME = 0.12          # 0..1 of full scale: deliberately quiet
FADE = 0.35            # fraction of each note used for fade in and fade out

Note = Tuple[int, int]  # (frequency Hz, duration ms)

# name -> notes. Only these cues exist; normal push-to-talk makes no sound.
CUES = {
    "translate": [(523, 70), (659, 90)],   # gentle rising pair: translation is active
    "gpu": [(784, 110)],
    "cpu": [(392, 110)],
}


def make_tone_wav(notes: Sequence[Note], volume: float = VOLUME, rate: int = RATE) -> bytes:
    """Mono 16-bit WAV with the notes played one after another."""
    samples = []
    for freq, ms in notes:
        count = max(1, int(rate * ms / 1000))
        fade = max(1, int(count * FADE))
        for i in range(count):
            envelope = min(1.0, i / fade, (count - 1 - i) / fade)
            envelope = 0.5 - 0.5 * math.cos(math.pi * max(0.0, envelope))  # raised cosine
            samples.append(int(32767 * volume * envelope * math.sin(2 * math.pi * freq * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()
