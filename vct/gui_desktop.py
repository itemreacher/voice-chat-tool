"""The 'Desktop-Audio' tab: transcribe what the PC plays (video, stream, call) while it plays."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import theme
from .desktop_audio import (ArgosTranslation, CaptureError, DesktopSession, LoopbackCapture, level_percent)
from .languages import LANGUAGES, code_from_label, label
from .transcript import Line, format_timestamp, to_srt, to_text

AUTO_TEXT = "Automatisch erkennen"
NO_TRANSLATION = "Nicht übersetzen"
STATE_TEXT = {"idle": "BEREIT", "starting": "STARTET …", "listening": "● NIMMT AUF", "finishing": "BEENDE …",
              "stopped": "BEENDET", "error": "FEHLER"}
STATE_COLOR = {"idle": theme.MUTED, "starting": theme.GOLD, "listening": theme.RED, "finishing": theme.GOLD_HI,
               "stopped": theme.TEAL, "error": theme.RED}
TICK_MS = 250
PRIVACY_HINT = ("Es wird alles aufgenommen, was dieser PC gerade abspielt, auch Gespräche anderer Personen "
                "(z. B. Sprachchat). Bitte beachte Urheber- und Persönlichkeitsrechte und hole bei Bedarf "
                "Einwilligungen ein. Die Aufnahme selbst wird nicht gespeichert, nur der Text.")


class DesktopTab:
    def __init__(self, app, notebook: ttk.Notebook):
        self.app = app
        self.session: Optional[DesktopSession] = None
        self.lines: List[Line] = []
        self._level = 0.0
        self._build(notebook)

    # ------------------------------------------------------------ layout
    def _build(self, notebook: ttk.Notebook) -> None:
        cfg = self.app.cfg
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text="Desktop-Audio")
        self.frame = f

        top = ttk.Frame(f)
        top.pack(fill="x")
        self.state_var = tk.StringVar(value=f" {STATE_TEXT['idle']} ")
        self.status = tk.Label(top, textvariable=self.state_var, bg=STATE_COLOR["idle"], fg=theme.BG,
                               font=("Segoe UI Semibold", 12), padx=10, pady=4)
        self.status.pack(side="left")
        self.info_var = tk.StringVar()
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="left", padx=12)
        self.start_btn = ttk.Button(top, text="Aufnahme starten", style="Accent.TButton", command=self.toggle)
        self.start_btn.pack(side="right")

        opts = ttk.LabelFrame(f, text="Einstellungen", padding=8)
        opts.pack(fill="x", pady=8)
        codes = list(LANGUAGES)
        self.lang_var = tk.StringVar(value=AUTO_TEXT if cfg["desktop_language"] == "auto"
                                     else label(cfg["desktop_language"]))
        self.target_var = tk.StringVar(value=label(cfg["desktop_translate_to"]) if cfg["desktop_translate_to"]
                                       else NO_TRANSLATION)
        self.times_var = tk.BooleanVar(value=cfg["desktop_timestamps"])
        ttk.Label(opts, text="Sprache im Video:").grid(row=0, column=0, sticky="w")
        lang = ttk.Combobox(opts, textvariable=self.lang_var, width=24,
                            values=[AUTO_TEXT] + [label(c) for c in codes])
        lang.grid(row=0, column=1, padx=6)
        ttk.Label(opts, text="Übersetzen nach:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        target = ttk.Combobox(opts, textvariable=self.target_var, width=24,
                              values=[NO_TRANSLATION] + [label(c) for c in codes])
        target.grid(row=0, column=3, padx=6)
        ttk.Checkbutton(opts, text="Zeitstempel", variable=self.times_var,
                        command=self._options_changed).grid(row=0, column=4, padx=(12, 0))
        for box in (lang, target):
            box.bind("<<ComboboxSelected>>", lambda _e: self._options_changed())
            box.bind("<Return>", lambda _e: self._options_changed())

        meter = ttk.Frame(f)
        meter.pack(fill="x")
        ttk.Label(meter, text="Pegel:", style="Muted.TLabel", width=7).pack(side="left")
        self.meter = ttk.Progressbar(meter, maximum=100, mode="determinate")
        self.meter.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.time_var = tk.StringVar(value="00:00:00")
        ttk.Label(meter, textvariable=self.time_var, style="Key.TLabel", width=9).pack(side="left")

        box = ttk.Frame(f)
        box.pack(fill="both", expand=True, pady=(8, 0))
        self.text = tk.Text(box, wrap="word", state="disabled", height=14)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        theme.style_text(self.text)
        self.text.tag_configure("time", foreground=theme.MUTED)
        self.text.tag_configure("translation", foreground=theme.GOLD_HI)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Kopieren", command=lambda: self.copy(False)).pack(side="left")
        ttk.Button(row, text="Speichern …", command=lambda: self.save(False)).pack(side="left", padx=6)
        self.copy_tr = ttk.Button(row, text="Übersetzung kopieren", command=lambda: self.copy(True))
        self.save_tr = ttk.Button(row, text="Übersetzung speichern …", command=lambda: self.save(True))
        ttk.Button(row, text="Leeren", command=self.clear).pack(side="right")

        ttk.Label(f, text=PRIVACY_HINT, style="Muted.TLabel", wraplength=720).pack(anchor="w", pady=(8, 0))
        if sys.platform != "win32":
            self.start_btn.configure(state="disabled")
            self.info_var.set("Nur unter Windows verfügbar")

    # ------------------------------------------------------------ options
    def language(self) -> Optional[str]:
        text = self.lang_var.get()
        return None if text == AUTO_TEXT else code_from_label(text)

    def translate_to(self) -> str:
        text = self.target_var.get()
        return "" if text == NO_TRANSLATION else code_from_label(text)

    def _options_changed(self) -> None:
        new = dict(self.app.cfg)
        new.update(desktop_language=self.language() or "auto", desktop_translate_to=self.translate_to(),
                   desktop_timestamps=self.times_var.get())
        self.app._commit(new)
        self.render()

    # ------------------------------------------------------------ session control
    def toggle(self) -> None:
        if self.session is not None and self.session.state in ("starting", "listening"):
            self._stop()
        elif self.session is None or self.session.state in ("stopped", "error"):
            self._start()

    def _start(self) -> None:
        transcriber = self.app.engine.transcriber
        if transcriber is None or self.app.engine.state in ("stopped", "loading"):
            messagebox.showinfo("Desktop-Audio", "Das Programm lädt noch die Spracherkennung. "
                                                 "Bitte kurz warten, bis oben „BEREIT“ steht.")
            return
        if self.lines and not messagebox.askyesno(
                "Desktop-Audio", "Der bisherige Text wird beim Start gelöscht (die Zeiten beginnen neu). "
                                 "Hast du ihn gespeichert oder kopiert? Jetzt neu starten?"):
            return
        self._options_changed()
        self.clear()
        self.session = DesktopSession(
            transcriber, LoopbackCapture(), self.app.log, self.language(), self.translate_to(),
            ArgosTranslation(self.app.log), on_line=lambda l: self.app.ui_queue.put(lambda: self._add(l)),
            on_level=self._set_level, on_state=lambda s: self.app.ui_queue.put(lambda: self._show_state(s)))
        session = self.session

        def work() -> None:
            try:
                session.start()
            except CaptureError as exc:
                self.app.ui_queue.put(lambda: messagebox.showerror("Desktop-Audio", str(exc)))

        self.app.in_thread(work)
        self.app.root.after(TICK_MS, self._tick)

    def _stop(self) -> None:
        session = self.session
        self.app.in_thread(session.stop)

    def abort(self) -> None:
        """Window is closing: stop recording without waiting for the last chunk."""
        if self.session is not None:
            self.session.abort()

    # ------------------------------------------------------------ live updates
    def _set_level(self, rms: float) -> None:
        self._level = rms

    def _show_state(self, state: str) -> None:
        self.state_var.set(f" {STATE_TEXT.get(state, state)} ")
        self.status.configure(bg=STATE_COLOR.get(state, theme.MUTED))
        running = state in ("starting", "listening")
        self.start_btn.configure(text="Aufnahme beenden" if running else "Aufnahme starten",
                                 state="disabled" if state == "finishing" else "normal")
        if state in ("stopped", "error"):
            self.meter["value"] = 0

    def _tick(self) -> None:
        session = self.session
        if session is None or session.state in ("stopped", "idle", "error"):
            return
        self.meter["value"] = level_percent(self._level) if session.state == "listening" else 0
        self.time_var.set(format_timestamp(session.elapsed))
        backlog = session.backlog
        self.info_var.set(f"Rückstand: {backlog} Stück(e), die Erkennung ist langsamer als die Wiedergabe"
                          if backlog >= 3 else "")
        self.app.root.after(TICK_MS, self._tick)

    def _add(self, line: Line) -> None:
        self.lines.append(line)
        self._append_text(line)
        if line.translation:
            self.copy_tr.pack(side="left", padx=(12, 0))
            self.save_tr.pack(side="left", padx=6)

    def _append_text(self, line: Line) -> None:
        self.text.configure(state="normal")
        if self.times_var.get():
            self.text.insert("end", f"[{format_timestamp(line.start)}] ", "time")
        self.text.insert("end", line.text + "\n")
        if line.translation:
            self.text.insert("end", f"   → {line.translation}\n", "translation")
        self.text.see("end")
        self.text.configure(state="disabled")

    def render(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        for line in self.lines:
            self._append_text(line)

    # ------------------------------------------------------------ results
    def clear(self) -> None:
        self.lines = []
        if self.session is not None:
            self.session.lines.clear()
        self.render()
        self.copy_tr.pack_forget()
        self.save_tr.pack_forget()

    def copy(self, translated: bool) -> None:
        text = to_text(self.lines, self.times_var.get(), translated)
        if not text:
            messagebox.showinfo("Desktop-Audio", "Es gibt noch keinen Text.")
            return
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        self.app.log(f"Desktop audio: {len(self.lines)} lines copied to the clipboard.")

    def save(self, translated: bool) -> None:
        if not self.lines:
            messagebox.showinfo("Desktop-Audio", "Es gibt noch keinen Text.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.app.root, title="Text speichern", defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Untertitel (SRT)", "*.srt")], initialfile="transkript")
        if not path:
            return
        try:
            content = (to_srt(self.lines, translated) if path.lower().endswith(".srt")
                       else to_text(self.lines, self.times_var.get(), translated))
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content + "\n")
        except OSError as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))
            return
        self.app.log(f"Desktop audio: saved {path}")
