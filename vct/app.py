"""Entry points: GUI (default), console mode (--console) and build self-test (--selftest)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .config import ConfigError, load_config, model_for_device, save_config
from .paths import CONFIG_NAME, LOG_NAME, data_dir


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller .exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """Folder for config.toml, the log and selftest.log (created if needed)."""
    path = data_dir(app_dir(), bool(getattr(sys, "frozen", False)), sys.platform,
                    os.environ, Path.home())
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_std_streams() -> None:
    """A windowed .exe has no stdout/stderr; libraries that print progress would crash."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def add_frozen_dll_dirs() -> None:
    """In the .exe, wheels keep their DLLs in '<name>.libs' folders that Windows does not search."""
    base = getattr(sys, "_MEIPASS", None)
    if not base or not hasattr(os, "add_dll_directory"):
        return
    for libs in Path(base).glob("*.libs"):
        try:
            os.add_dll_directory(str(libs))
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join([str(p) for p in Path(base).glob("*.libs")]
                                         + [os.environ.get("PATH", "")])


def selftest() -> int:
    """Check that every dependency loads (used to verify the .exe build)."""
    if getattr(sys, "frozen", False):  # windowed .exe has no console: write selftest.log
        sys.stdout = open(user_dir() / "selftest.log", "w", encoding="utf-8", buffering=1)
    import argostranslate.translate  # noqa: F401
    import ctranslate2  # noqa: F401
    import faster_whisper  # noqa: F401
    import keyboard  # noqa: F401
    import sounddevice  # noqa: F401
    import tkinter  # noqa: F401

    from . import translator
    from .correction import PySpellBackend

    if sys.platform == "win32":                      # desktop audio (loopback) must work in the built program too
        from .desktop_audio import CaptureError, LoopbackCapture

        capture = LoopbackCapture()
        try:
            capture.start(lambda _audio: None)
            log(f"Desktop audio OK: can record '{capture.name}'")
        except CaptureError as exc:
            log(f"Desktop audio NOT available here: {exc}")   # e.g. a PC without any output device
        finally:
            capture.stop()

    if not PySpellBackend.supported("de"):
        log("SELFTEST FAILED: spell-check dictionary missing")
        return 1
    log("Spell-check dictionary OK")

    if not translator.ensure("de", "en", log):
        log("SELFTEST FAILED: translator not available")
        return 1
    log(f"Translation OK: 'Hallo Welt' -> {translator.translate('Hallo Welt', 'de', 'en')!r}")

    from .transcriber import Transcriber

    cfg = load_config(user_dir() / CONFIG_NAME)
    transcriber = Transcriber(model_for_device(cfg, "cpu"), model_for_device(cfg, "cuda"), log)
    transcriber.load(cfg["device"])
    log(f"SELFTEST OK: Whisper loaded on {transcriber.device.upper()}")
    return 0


def run_console(cfg) -> int:
    from .engine import Engine

    engine = Engine(cfg, log)
    if not engine.start():
        return 1
    log("Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Bye.")
    finally:
        engine.stop()
    return 0


def main() -> int:
    ensure_std_streams()
    add_frozen_dll_dirs()
    if "--selftest" in sys.argv:
        return selftest()
    config_path = user_dir() / CONFIG_NAME
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        _report_error(f"Config error: {exc}")
        return 1
    if not config_path.exists():
        save_config(config_path, cfg)

    if "--console" in sys.argv:
        return run_console(cfg)
    from .gui import run_gui

    return run_gui(cfg, config_path, user_dir() / LOG_NAME)


def _report_error(message: str) -> None:
    log(message)
    try:  # windowed .exe: the console is invisible, so show a dialog
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Voice Chat Tool", message)
        root.destroy()
    except Exception:
        pass
