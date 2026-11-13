"""Microphone capture with sounddevice (16 kHz mono float32)."""
from __future__ import annotations

import threading
from typing import List, Optional, Union

import numpy as np

from .audio_check import SAMPLE_RATE
from .audio_devices import resolve_input_device


class RecorderError(Exception):
    pass


class Recorder:
    def __init__(self, device: Optional[Union[str, int]] = None):
        self.device = device
        self._stream = None
        self._chunks: List[np.ndarray] = []
        self._lock = threading.Lock()

    def _resolve(self) -> Optional[Union[str, int]]:
        """Turn a configured name into one device index (a name can match several interfaces)."""
        if not isinstance(self.device, str):
            return self.device
        import sounddevice as sd

        try:
            default_api = sd.query_devices(kind="input")["hostapi"]
        except Exception:
            default_api = None
        index = resolve_input_device(self.device, sd.query_devices(), default_api)
        if index is None:
            raise RecorderError(f"Microphone {self.device!r} not found")
        return index

    def check_device(self) -> str:
        """Raise RecorderError if no usable input device; return its name."""
        try:
            import sounddevice as sd

            info = sd.query_devices(self._resolve(), "input")
            return str(info["name"])
        except RecorderError:
            raise
        except Exception as exc:
            raise RecorderError(f"No usable microphone ({exc})") from exc

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            try:
                stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                        device=self._resolve(), callback=self._callback)
                stream.start()
            except Exception as exc:
                raise RecorderError(f"Could not open microphone ({exc})") from exc
            self._stream = stream

    def stop(self) -> np.ndarray:
        with self._lock:
            stream, self._stream = self._stream, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
