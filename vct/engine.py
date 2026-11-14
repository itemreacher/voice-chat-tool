"""Core engine: hotkeys -> record -> transcribe -> translate -> output.

Runs without any UI. The GUI and the console mode both drive this class.
Settings can be changed while running via apply().
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import translator
from .audio_check import check_audio
from .config import device_from_config, model_for_device
from .correction import PySpellBackend, SpellBackend, correct_text, parse_replacements
from .languages import label, needs_translation
from .logic import process_transcript

Log = Callable[[str], None]


@dataclass
class Recording:
    samples: Any
    translate: bool  # recorded with the translate key: always translate


class Engine:
    def __init__(self, cfg: Dict[str, Any], log: Log,
                 on_state: Optional[Callable[[str], None]] = None,
                 on_result: Optional[Callable[[str, str], None]] = None,
                 cuda_dir: Optional[Path] = None):
        self.cfg = dict(cfg)
        self.cuda_dir = cuda_dir
        self.log = log
        self._on_state = on_state or (lambda _s: None)
        self._on_result = on_result or (lambda _h, _r: None)
        self.state = "stopped"  # stopped | loading | ready | recording | processing
        self.transcriber = None
        self.recorder = None
        self._winout = None
        self._translate_fn: Optional[Callable[[str], str]] = None
        self._spell: Optional[SpellBackend] = None
        self._jobs: "queue.Queue" = queue.Queue()
        self._hooks: List[Any] = []
        self._held = threading.Event()
        self._active_kind = "talk"  # which key started the current recording
        self._toggle_held = threading.Event()
        self._worker: Optional[threading.Thread] = None

    # ------------------------------------------------------------ state
    def _set_state(self, state: str) -> None:
        self.state = state
        self._on_state(state)

    @property
    def device(self) -> Optional[str]:
        return self.transcriber.device if self.transcriber else None

    # ------------------------------------------------------------ start / stop
    def start(self) -> bool:
        """Load everything and register the hotkeys. Blocking; call from a thread in the GUI."""
        from .platform_io import load_backend
        from .recorder import Recorder, RecorderError
        from .transcriber import Transcriber

        self._winout = load_backend()
        self._set_state("loading")
        self.recorder = self._open_recorder()
        if self.recorder is None:
            self._set_state("stopped")
            return False

        self.transcriber = Transcriber(model_for_device(self.cfg, "cpu"),
                                       model_for_device(self.cfg, "cuda"), self.log, self.cuda_dir)
        try:
            self.transcriber.load(self.cfg["device"])
        except Exception as exc:
            self.log(f"ERROR: could not load/download the Whisper model: {exc}")
            self.log("Check your internet connection (first run only) and try again.")
            self._set_state("stopped")
            return False

        self._refresh_translator()
        self._refresh_spellcheck()
        self._worker = threading.Thread(target=self._work, name="worker", daemon=True)
        self._worker.start()
        if not self._register_hotkeys():
            self.stop()
            return False
        self._set_state("ready")
        self.log(self.ready_message())
        return True

    def _open_recorder(self):
        """The configured microphone; if that fails, the Windows default. None if neither works."""
        from .recorder import Recorder, RecorderError

        configured = self.cfg["microphone_device"]
        attempts = [device_from_config(configured)]
        if attempts[0] is not None:
            attempts.append(None)  # fall back to the system default microphone
        for n, device in enumerate(attempts):
            recorder = Recorder(device)
            try:
                self.log(f"Microphone: {recorder.check_device()}")
                return recorder
            except RecorderError as exc:
                if n + 1 < len(attempts):
                    self.log(f"Note  : {exc}. Using the default microphone instead.")
                else:
                    self.log(f"ERROR: {exc}. Plug in a microphone or choose one in the settings.")
        return None

    def stop(self) -> None:
        self._unregister_hotkeys()
        if self._worker is not None:
            self._jobs.put(None)
            self._worker = None
        self._set_state("stopped")

    def ready_message(self) -> str:
        c = self.cfg
        pair = f"{label(c['source_language'])} -> {label(c['target_language'])}"
        toggle = f" [{c['device_toggle_hotkey'].upper()}] switches CPU/GPU." if c["device_toggle_hotkey"] else ""
        tkey = f" [{c['translate_hotkey'].upper()}] speaks and always translates." if c["translate_hotkey"] else ""
        return (f"Ready on {(self.device or '?').upper()}. Hold [{c['hotkey'].upper()}] and speak. "
                f"{pair}, mode: {c['translate_mode']}.{tkey}{toggle}")

    # ------------------------------------------------------------ hotkeys
    def _register_hotkeys(self) -> bool:
        import keyboard  # global hooks (Windows)

        try:
            self._hooks = [
                keyboard.on_press_key(self.cfg["hotkey"], lambda _e: self._on_press("talk")),
                keyboard.on_release_key(self.cfg["hotkey"], lambda _e: self._on_release("talk")),
            ]
            tkey = self.cfg["translate_hotkey"]
            if tkey:
                self._hooks += [
                    keyboard.on_press_key(tkey, lambda _e: self._on_press("translate")),
                    keyboard.on_release_key(tkey, lambda _e: self._on_release("translate")),
                ]
            toggle = self.cfg["device_toggle_hotkey"]
            if toggle:
                self._hooks += [
                    keyboard.on_press_key(toggle, self._on_toggle_press),
                    keyboard.on_release_key(toggle, lambda _e: self._toggle_held.clear()),
                ]
        except Exception as exc:
            from .platform_io import hotkey_hint

            self.log(f"ERROR: could not register hotkey: {exc} {hotkey_hint()}")
            self._unregister_hotkeys()
            return False
        return True

    def _unregister_hotkeys(self) -> None:
        if not self._hooks:
            return
        import keyboard

        for hook in self._hooks:
            try:
                keyboard.unhook(hook)
            except Exception:
                pass
        self._hooks = []
        self._held.clear()
        self._toggle_held.clear()

    def _on_press(self, kind: str) -> None:
        from .recorder import RecorderError

        if self._held.is_set() or self.state not in ("ready", "processing"):
            return
        self._held.set()
        self._active_kind = kind
        try:
            self.recorder.start()
        except RecorderError as exc:
            self._held.clear()
            self.log(f"ERROR: {exc}")
            return
        if kind == "translate":
            self._cue("translate")  # the only sound while talking: translation is active
        self._set_state("recording")
        self.log("Recording (translate)..." if kind == "translate" else "Recording...")

    def _on_release(self, kind: str) -> None:
        if not self._held.is_set() or self._active_kind != kind:
            return
        self._held.clear()
        self._set_state("processing")
        # stop() is fast; the transcription happens in the worker
        self._jobs.put(Recording(self.recorder.stop(), kind == "translate"))

    def _on_toggle_press(self, _event) -> None:
        if self._toggle_held.is_set():  # ignore key auto-repeat
            return
        self._toggle_held.set()
        self.toggle_device()

    # ------------------------------------------------------------ live changes
    def toggle_device(self) -> None:
        self.log("Switching CPU/GPU...")
        self._jobs.put(self._do_toggle)

    def apply(self, new_cfg: Dict[str, Any]) -> None:
        """Apply a validated config while running (hotkeys, languages, models, mic, ...)."""
        old, self.cfg = self.cfg, dict(new_cfg)
        if self.state == "stopped":
            return
        if any(old[k] != new_cfg[k] for k in ("hotkey", "translate_hotkey", "device_toggle_hotkey")):
            self._unregister_hotkeys()
            self._register_hotkeys()
        if old["microphone_device"] != new_cfg["microphone_device"]:
            self._jobs.put(self._do_change_microphone)
        if any(old[k] != new_cfg[k] for k in ("whisper_model", "whisper_model_gpu")):
            self._jobs.put(self._do_reload_models)
        if any(old[k] != new_cfg[k] for k in ("source_language", "target_language", "translate_mode")):
            self._jobs.put(self._refresh_translator)
        if any(old[k] != new_cfg[k] for k in ("source_language", "spellcheck")):
            self._jobs.put(self._refresh_spellcheck)

    def _do_toggle(self) -> None:
        self._set_state("loading")
        active = self.transcriber.toggle()
        self._cue("gpu" if active == "cuda" else "cpu")
        self._set_state("ready")

    def _do_reload_models(self) -> None:
        self._set_state("loading")
        self.transcriber.set_models(model_for_device(self.cfg, "cpu"),
                                    model_for_device(self.cfg, "cuda"))
        self._set_state("ready")

    def _do_change_microphone(self) -> None:
        from .recorder import Recorder, RecorderError

        new = Recorder(device_from_config(self.cfg["microphone_device"]))
        try:
            self.log(f"Microphone: {new.check_device()}")
            self.recorder = new
        except RecorderError as exc:
            self.log(f"ERROR: {exc}. Keeping the previous microphone.")

    def _refresh_translator(self) -> None:
        """Make sure the packs for the current pair exist (download if needed)."""
        src, tgt = self.cfg["source_language"], self.cfg["target_language"]
        self._translate_fn = None
        if not needs_translation(src, tgt):
            return
        if translator.ensure(src, tgt, self.log):
            self._translate_fn = translator.make_translate_fn(src, tgt)

    def _refresh_spellcheck(self) -> None:
        """(Re)load the spell-check dictionary for the spoken language, if there is one."""
        self._spell = None
        lang = self.cfg["source_language"]
        if not self.cfg["spellcheck"]:
            return
        try:
            self._spell = PySpellBackend(lang)
        except Exception:
            self.log(f"No spell-check dictionary for '{lang}'; only your replacement list is used.")

    def _correct(self, transcript: str) -> str:
        cfg = self.cfg
        pairs = parse_replacements(cfg["replacements"])
        protected = list(cfg["vocabulary"]) + list(cfg["keywords"]) + [right for _w, right in pairs]
        result = correct_text(transcript, pairs, self._spell, protected)
        for before, after in result.changes:
            self.log(f"Fixed : {before!r} -> {after!r}")
        return result.text

    # ------------------------------------------------------------ worker
    def _cue(self, name: str) -> None:
        if self.cfg["beep"] and self._winout is not None:
            self._winout.play_cue(name)

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                if callable(job):
                    job()
                else:
                    self._handle(job)
            except Exception as exc:  # never let one bad job kill the worker
                self.log(f"ERROR while processing: {exc}")
            if self.state in ("processing", "loading") and self._jobs.empty() and not self._held.is_set():
                self._set_state("ready")

    def _handle(self, rec: Recording) -> None:
        samples = rec.samples
        reason = check_audio(samples)
        if reason:
            self.log(f"Skipped: {reason}.")
            return
        cfg = self.cfg
        hotwords = ", ".join(cfg["vocabulary"]) or None
        heard = self.transcriber.transcribe(samples, cfg["source_language"], hotwords)
        self.log(f"Heard : {heard!r}")
        transcript = self._correct(heard)
        if rec.translate and not needs_translation(cfg["source_language"], cfg["target_language"]):
            self.log("Note  : spoken and output language are the same, nothing to translate.")
        mode = "always" if rec.translate else cfg["translate_mode"]
        outcome = process_transcript(transcript, cfg["keywords"], self._translate_fn, mode)
        if outcome.warning:
            self.log(f"Note  : {outcome.warning}")
        if not outcome.text:
            self.log("Result: (nothing to output)")
            return
        self.log(f"Result: {outcome.text!r}" + ("  [translated]" if outcome.translated else ""))
        self._on_result(transcript, outcome.text)
        try:
            self._winout.copy_to_clipboard(outcome.text)
        except Exception as exc:
            self.log(f"Clipboard error: {exc}")
        if cfg["output_mode"] == "type":
            try:
                self._winout.type_text(outcome.text)
            except Exception as exc:
                self.log(f"Typing error: {exc} (text is on the clipboard: press Ctrl+V)")
        if outcome.translated and not rec.translate:
            self._cue("translate")  # spoken keyword worked: soft confirmation
