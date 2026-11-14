"""Microphone capture with sounddevice (16 kHz mono float32)."""
from __future__ import annotations

import threading
from typing import List, Optional, Union

import numpy as np

from .audio_check import SAMPLE_RATE
from .audio_devices import candidate_input_devices

BUSY_HINT = ("Close programs that may hold the microphone exclusively (audio interface control panels, "
              "Discord/game voice with exclusive mode, DAWs), or choose another microphone in the settings.")


class RecorderError(Exception):
    pass


class Recorder:
    def __init__(self, device: Optional[Union[str, int]] = None):
        self.device = device
        self._stream = None
        self._chunks: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._working: Optional[int] = None   # the device that opened last time: tried first

    def _candidates(self) -> List[Optional[int]]:
        """Devices to try, best first. A configured name can match several audio interfaces."""
        if not isinstance(self.device, str):
            return [self.device]                      # None = system default, or an explicit index
        import sounddevice as sd

        try:
            default_api = sd.query_devices(kind="input")["hostapi"]
        except Exception:
            default_api = None
        found = candidate_input_devices(self.device, sd.query_devices(), default_api)
        if not found:
            raise RecorderError(f"Microphone {self.device!r} not found")
        if self._working in found:
            found.remove(self._working)
            found.insert(0, self._working)
        return found

    def check_device(self) -> str:
        """Raise RecorderError if no usable input device; return its name."""
        try:
            import sounddevice as sd

            info = sd.query_devices(self._candidates()[0], "input")
            return str(info["name"])
        except RecorderError:
            raise
        except Exception as exc:
            raise RecorderError(f"No usable microphone ({exc})") from exc

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata[:, 0].copy())

    def _open_stream(self, device: Optional[int]):
        import sounddevice as sd

        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                device=device, callback=self._callback)
        stream.start()
        return stream

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            errors: List[str] = []
            for device in self._candidates():
                try:
                    self._stream = self._open_stream(device)
                except Exception as exc:               # try the same microphone on another interface
                    errors.append(f"[{device}] {exc}")
                    continue
                self._working = device if isinstance(device, int) else None
                return
            raise RecorderError(f"Could not open microphone ({'; '.join(errors)}). {BUSY_HINT}")

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
