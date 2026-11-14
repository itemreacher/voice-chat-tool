import threading
import time

import pytest

from vct import transcriber as T


def make(models=("small", "small")):
    logs = []
    t = T.Transcriber(models[0], models[1], logs.append)
    return t, logs


class Fake(T.Transcriber):
    """Transcriber whose model building is scripted instead of loading Whisper."""
    cuda_behaviour = "ok"   # ok | raise | hang

    def _build(self, device):
        if device == "cuda":
            if self.cuda_behaviour == "raise":
                raise RuntimeError("cublas missing")
            if self.cuda_behaviour == "hang":
                threading.Event().wait(30)   # simulates the native call that never returns
        return f"model-{device}"

    def cuda_available(self):
        return not self._cuda_disabled and self.gpu_present and self.libs_ok

    def gpu_libs_missing(self):
        return self.gpu_present and not self.libs_ok

    gpu_present, libs_ok = True, True


def fake(behaviour="ok", libs_ok=True):
    logs = []
    t = Fake("small", "small", logs.append)
    t.cuda_behaviour, t.libs_ok = behaviour, libs_ok
    return t, logs


def test_cuda_libs_loadable_with_fake_loader():
    assert T.cuda_libs_loadable("win32", loader=lambda n: None)
    def missing(name):
        raise OSError(name)
    assert not T.cuda_libs_loadable("win32", loader=missing)
    assert not T.cuda_libs_loadable("linux", loader=missing)
    assert not T.cuda_libs_loadable("darwin", loader=lambda n: None)   # no CUDA on macOS


def test_cuda_libs_loadable_requires_every_library():
    seen = []
    def loader(name):
        seen.append(name)
        if name.startswith("cudnn"):
            raise OSError(name)
    assert not T.cuda_libs_loadable("win32", loader=loader)
    assert seen == ["cublas64_12.dll", "cudnn64_9.dll"]


def test_hanging_gpu_start_times_out_and_cpu_stays_active(monkeypatch):
    monkeypatch.setattr(T, "GPU_LOAD_TIMEOUT_S", 0.3)
    t, logs = fake("hang")
    t.load("cpu")
    started = time.time()
    assert t.toggle() == "cpu"                       # did not freeze, stayed on the CPU
    assert time.time() - started < 5
    assert t._cuda_disabled and not t.cuda_available()
    assert any("did not respond" in line for line in logs)


def test_failed_gpu_start_keeps_cpu(monkeypatch):
    t, logs = fake("raise")
    t.load("cpu")
    assert t.toggle() == "cpu"
    assert any("Could not use GPU" in line for line in logs)


def test_toggle_without_libs_explains_and_never_builds_cuda():
    t, logs = fake("hang", libs_ok=False)            # would hang if it were attempted
    t.load("cpu")
    started = time.time()
    assert t.toggle() == "cpu"
    assert time.time() - started < 2
    assert any("CUDA libraries are missing" in line for line in logs)


def test_startup_gpu_preference_without_libs_falls_back_quickly():
    t, logs = fake("hang", libs_ok=False)
    t.load("gpu")
    assert t.device == "cpu"
    assert any("CUDA libraries are missing" in line for line in logs)


def test_toggle_works_when_gpu_is_fine():
    t, _ = fake("ok")
    t.load("cpu")
    assert t.toggle() == "cuda" and t.model == "model-cuda"
    assert t.toggle() == "cpu"


def test_auto_prefers_gpu_when_usable_else_cpu():
    t, _ = fake("ok"); t.load("auto"); assert t.device == "cuda"
    t, _ = fake("ok", libs_ok=False); t.load("auto"); assert t.device == "cpu"
