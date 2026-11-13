"""faster-whisper wrapper: any language per call, switchable between CPU (int8) and GPU (CUDA float16)."""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .config import next_device

BEAM_SIZE = 1  # greedy decoding: lowest latency, fine for short chat phrases
LABELS = {"cpu": "CPU (int8)", "cuda": "GPU (CUDA float16)"}
GPU_LOAD_TIMEOUT_S = 180  # first CUDA start can take ~30 s; beyond this something is stuck
CUDA_LIBS = {"win32": ("cublas64_12.dll", "cudnn64_9.dll"),
             "linux": ("libcublas.so.12", "libcudnn.so.9")}
NO_GPU_LIBS_MESSAGE = ("This installation has no GPU support (the NVIDIA CUDA libraries are missing). "
                       "Use the GPU edition of the installer, or on a source install: "
                       "pip install -r requirements-gpu.txt. Staying on the CPU.")
GPU_HINT = ("GPU needs the NVIDIA CUDA 12 libraries. Installed program: use the GPU edition of the "
            "installer (VoiceChatTool-Setup-...-GPU.exe). From source: pip install -r requirements-gpu.txt")


def cuda_dll_dirs() -> List[Path]:
    """Folders like <site-packages>/nvidia/cublas/bin that hold the pip-installed CUDA DLLs."""
    bases = [Path(p) for p in sys.path if p]
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller bundle
    if meipass:
        bases.append(Path(meipass))
    found: List[Path] = []
    for base in bases:
        root = base / "nvidia"
        if root.is_dir():
            found.extend(d for d in sorted(root.glob("*/bin")) if d.is_dir() and d not in found)
    return found


def add_cuda_dll_dirs() -> None:
    """Make pip-installed CUDA DLLs findable (CTranslate2 loads them lazily via PATH)."""
    for d in cuda_dll_dirs():
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(d))
            except OSError:
                pass


def cuda_libs_loadable(platform: str = sys.platform, loader: Optional[Callable[[str], object]] = None,
                       names: Optional[Sequence[str]] = None) -> bool:
    """True if the CUDA runtime libraries can really be loaded.

    CTranslate2 does not fail cleanly when they are missing: in the installed program the first
    GPU inference blocks forever. So this is checked *before* any CUDA model is built.
    """
    needed = names if names is not None else CUDA_LIBS.get("win32" if platform == "win32" else
                                                           "linux" if platform.startswith("linux") else "", ())
    if not needed:
        return False  # macOS and others: no CUDA
    load = loader or ctypes.CDLL
    try:
        for name in needed:
            load(name)
    except OSError:
        return False
    return True


class Transcriber:
    def __init__(self, cpu_model: str, gpu_model: str, log: Callable[[str], None]):
        self.models: Dict[str, str] = {"cpu": cpu_model, "cuda": gpu_model}
        self.log = log
        self.device = None  # "cpu" | "cuda" once a model is loaded
        self.model = None
        self._cuda_disabled = False  # set when a GPU start-up got stuck: do not try again
        add_cuda_dll_dirs()

    def cuda_available(self) -> bool:
        """A CUDA GPU exists, its libraries are loadable and it did not hang before."""
        if self._cuda_disabled:
            return False
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0 and cuda_libs_loadable()
        except Exception:
            return False

    def gpu_libs_missing(self) -> bool:
        """True if there is a GPU but this installation lacks the CUDA libraries."""
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0 and not cuda_libs_loadable()
        except Exception:
            return False

    def _build_guarded(self, device: str):
        """_build with a time limit for CUDA, so a stuck GPU start can never freeze the engine."""
        if device != "cuda":
            return self._build(device)
        box: Dict[str, object] = {}

        def run() -> None:
            try:
                box["model"] = self._build(device)
            except BaseException as exc:  # reported to the caller below
                box["error"] = exc

        worker = threading.Thread(target=run, name="cuda-load", daemon=True)
        worker.start()
        worker.join(GPU_LOAD_TIMEOUT_S)
        if worker.is_alive():
            self._cuda_disabled = True
            raise TimeoutError(f"the GPU did not respond within {GPU_LOAD_TIMEOUT_S} s")
        if "error" in box:
            raise box["error"]  # type: ignore[misc]
        return box["model"]

    @staticmethod
    def _warm_up(model) -> None:
        """Run one real inference. CUDA library problems only show up here, not at load."""
        import numpy as np

        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="de",
                                       beam_size=1, vad_filter=False)
        list(segments)

    def _build(self, device: str):
        from faster_whisper import WhisperModel

        compute = "float16" if device == "cuda" else "int8"
        model = WhisperModel(self.models[device], device=device, compute_type=compute)
        if device == "cuda":
            self._warm_up(model)
        return model

    def _activate(self, device: str) -> bool:
        """Load the model for `device` and make it current. The old model stays on failure."""
        self.log(f"Loading Whisper model '{self.models[device]}' for {LABELS[device]} "
                 "(first use downloads it; progress bar below)...")
        try:
            model = self._build_guarded(device)
        except Exception as exc:
            self.log(f"Could not use {LABELS[device]}: {exc}")
            if device == "cuda":
                self.log(GPU_HINT)
            return False
        self.model, self.device = model, device
        self.log(f"Whisper active: {LABELS[device]}, model '{self.models[device]}'.")
        return True

    def load(self, preference: str = "auto") -> None:
        """Start-up load. `preference` is 'auto', 'cpu' or 'gpu'. Raises if nothing loads."""
        available = self.cuda_available()
        if preference != "cpu" and available and self._activate("cuda"):
            return
        if preference == "gpu":
            self.log(NO_GPU_LIBS_MESSAGE if not available and self.gpu_libs_missing()
                     else "Falling back to the CPU model.")
        if not self._activate("cpu"):
            raise RuntimeError("could not load the Whisper model on the CPU")

    def toggle(self) -> str:
        """Switch CPU <-> GPU. Returns the active device ('cpu' or 'cuda')."""
        target = next_device(self.device)
        if target == "cuda" and not self.cuda_available():
            self.log(NO_GPU_LIBS_MESSAGE if self.gpu_libs_missing()
                     else "No usable CUDA GPU found; staying on CPU.")
            return self.device
        if not self._activate(target):
            self.log(f"Staying on {LABELS[self.device]}.")
        return self.device

    def set_models(self, cpu_model: str, gpu_model: str) -> bool:
        """Use different models; reloads the active device. False if loading failed
        (the previous model then stays active)."""
        old = dict(self.models)
        self.models = {"cpu": cpu_model, "cuda": gpu_model}
        if self.device is None or self.models[self.device] == old[self.device]:
            return True
        if self._activate(self.device):
            return True
        self.models = old
        return False

    def _run(self, samples, language: str, hotwords: Optional[str]) -> str:
        segments, _info = self.model.transcribe(
            samples, language=language, beam_size=BEAM_SIZE, vad_filter=True,
            hotwords=hotwords or None,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe(self, samples, language: str = "de", hotwords: Optional[str] = None) -> str:
        try:
            return self._run(samples, language, hotwords)
        except Exception as exc:
            if self.device != "cuda":
                raise
            self.log(f"GPU inference failed ({exc}); switching to CPU.")
            if not self._activate("cpu"):
                raise
            return self._run(samples, language, hotwords)
