"""Tkinter user interface (stdlib only). All heavy work runs in threads via Engine."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

import os
import sys
import tempfile
import webbrowser

from . import __version__, build_info, cuda_pack, theme, translator, updater
from .audio_devices import unique_input_names
from .config import ConfigError, DEVICES, parse_config, save_config
from .engine import Engine
from .languages import LANGUAGES, PIVOT, code_from_label, label
from .logic import TRANSLATE_MODES
from .paths import cuda_libs_dir, resource_dir

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
STATE_TEXT = {"stopped": "GESTOPPT", "loading": "LÄDT …", "ready": "BEREIT",
              "recording": "● AUFNAHME", "processing": "VERARBEITE …"}
MODE_TEXT = {"keyword": "Per Stichwort (z. B. „translate …“)", "always": "Immer übersetzen",
             "off": "Nie per Stichwort (nur mit Übersetzen-Taste)"}
OUTPUT_TEXT = {"type": "Tippen + Zwischenablage", "clipboard": "Nur Zwischenablage"}
POLL_MS = 100
LOG_FILE_MAX_BYTES = 1_000_000


def microphone_choices() -> List[str]:
    """Input device names for the settings drop-down ('' = Windows default)."""
    try:
        import sounddevice as sd

        try:
            default_api = sd.query_devices(kind="input")["hostapi"]
        except Exception:
            default_api = None
        names = unique_input_names(sd.query_devices(), default_api)
    except Exception:
        names = []
    return [""] + names


class App:
    def __init__(self, root: tk.Tk, cfg: Dict[str, Any], config_path: Path, log_path: Path):
        self.root, self.cfg, self.config_path, self.log_path = root, cfg, config_path, log_path
        self.ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.cuda_dir = cuda_libs_dir(sys.platform, os.environ, Path.home())
        self._gpu_download_running = False
        self.engine = Engine(cfg, self.log, self._state_changed, self._got_result, self.cuda_dir)
        self.installed: set = set()
        self.index_pairs: set = set()
        self._trim_log_file()

        root.title("Voice Chat Tool")
        root.geometry("820x760")
        root.minsize(720, 640)
        root.protocol("WM_DELETE_WINDOW", self.close)
        theme.apply(root)
        self.logo = self._load_logo()
        if self.logo:
            root.iconphoto(True, self.logo)
        self._build_header(root)
        self._build_update_banner(root)
        notebook = ttk.Notebook(root)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._build_main(notebook)
        self._build_languages(notebook)
        self._build_words(notebook)
        self._build_settings(notebook)
        self._poll()
        self.start_engine()
        self.refresh_installed()
        if cfg["update_check"]:
            root.after(4000, lambda: self.check_updates(manual=False))   # not while loading models

    # ------------------------------------------------------------ header
    def _load_logo(self) -> Optional[tk.PhotoImage]:
        base = resource_dir(bool(getattr(sys, "frozen", False)), getattr(sys, "_MEIPASS", None),
                            Path(__file__).resolve().parent.parent)
        try:
            return tk.PhotoImage(file=str(base / "assets" / "logo_64.png"))
        except tk.TclError:
            return None

    def _build_header(self, root: tk.Tk) -> None:
        """Banner: cut-corner steel plate, logo, serif title, gold line with a diamond."""
        height = 92
        bar = tk.Canvas(root, height=height, bg=theme.BG, highlightthickness=0)
        bar.pack(fill="x", padx=14, pady=(14, 8))
        self.header, self.header_height = bar, height
        bar.bind("<Configure>", self._draw_header)

    def _draw_header(self, event) -> None:
        bar, w, h, cut = self.header, event.width, self.header_height, 26
        bar.delete("all")
        bar.create_polygon(0, 0, w, 0, w, h - 10 - cut, w - cut, h - 10, 0, h - 10,
                           fill=theme.PANEL, outline="")
        bar.create_polygon(0, 0, 10, 0, 10, h - 10, 0, h - 10, fill=theme.RED, outline="")  # red edge
        bar.create_line(10, h - 10, w - cut, h - 10, w, h - 10 - cut, fill=theme.GOLD, width=2)
        mid = w // 2
        bar.create_polygon(mid, h - 17, mid + 7, h - 10, mid, h - 3, mid - 7, h - 10,
                           fill=theme.GOLD_HI, outline=theme.BG)                           # diamond
        x = 30
        if self.logo:
            bar.create_image(x, (h - 10) // 2, image=self.logo, anchor="w")
            x += 78
        bar.create_text(x, 30, text="VOICE CHAT TOOL", anchor="w", fill=theme.GOLD_HI,
                        font=theme.FONT_TITLE)
        bar.create_text(x, 62, text="Stimme statt Tastatur", anchor="w", fill=theme.MUTED,
                        font=("Georgia", 11, "italic"))
        bar.create_text(w - 36, 22, text=f"v{__version__}", anchor="e", fill=theme.MUTED,
                        font=theme.FONT_BODY)

    # ------------------------------------------------------------ updates
    def _build_update_banner(self, root: tk.Tk) -> None:
        self.update_banner = tk.Frame(root, bg=theme.PANEL_HI, highlightthickness=1,
                                      highlightbackground=theme.GOLD)
        self.update_text = tk.StringVar()
        tk.Label(self.update_banner, textvariable=self.update_text, bg=theme.PANEL_HI,
                 fg=theme.GOLD_HI, font=theme.FONT_BOLD).pack(side="left", padx=12, pady=8)
        ttk.Button(self.update_banner, text="Später", command=self.update_banner.pack_forget).pack(
            side="right", padx=(0, 10), pady=6)
        ttk.Button(self.update_banner, text="Details", command=self._open_release_page).pack(
            side="right", padx=6, pady=6)
        self.update_btn = ttk.Button(self.update_banner, text="Jetzt aktualisieren",
                                     style="Accent.TButton", command=self.install_update)
        self.update_btn.pack(side="right", padx=6, pady=6)
        self.release: Optional[updater.Release] = None

    def _update_repo(self) -> str:
        return self.cfg["update_repo"] or build_info.REPO

    def check_updates(self, manual: bool) -> None:
        repo = self._update_repo()
        if not updater.is_valid_repo(repo):
            if manual:
                messagebox.showinfo("Updates", "Es ist noch kein GitHub-Repository für Updates "
                                    "eingetragen (Einstellungen → Update-Repository).")
            return

        def work() -> None:
            try:
                release = updater.check_for_update(repo, __version__)
            except updater.UpdateError as exc:
                self.log(f"Update check failed: {exc}")
                if manual:
                    self.ui_queue.put(lambda: messagebox.showwarning("Updates", str(exc)))
                return
            if release is None:
                self.log(f"Up to date (v{__version__}).")
                if manual:
                    self.ui_queue.put(lambda: messagebox.showinfo(
                        "Updates", f"Du hast die neueste Version (v{__version__})."))
                return
            self.log(f"Update available: v{release.version} (installed: v{__version__}).")
            self.ui_queue.put(lambda: self._show_update(release))

        self.in_thread(work)

    def _show_update(self, release: "updater.Release") -> None:
        self.release = release
        self.update_text.set(f"Neue Version v{release.version} verfügbar (installiert: v{__version__})")
        self.update_banner.pack(fill="x", padx=14, pady=(0, 8), before=self.notebook)

    def _open_release_page(self) -> None:
        if self.release and self.release.page_url.startswith("https://github.com/"):
            webbrowser.open(self.release.page_url)

    def install_update(self) -> None:
        release = self.release
        if release is None:
            return
        from .app import app_dir

        frozen = bool(getattr(sys, "frozen", False))
        directory = app_dir()
        asset = updater.pick_installer(release, sys.platform, updater.installed_edition(directory))
        if not (asset and updater.can_self_update(frozen, sys.platform, directory)):
            self.log("Automatic update is only available for the installed Windows program; "
                     "opening the release page.")
            self._open_release_page()
            return
        self.update_btn.configure(state="disabled")
        repo = self._update_repo()
        step = {"next": 10}

        def progress(done: int, total: int) -> None:
            if total and done * 100 // total >= step["next"]:
                self.log(f"Downloading update: {done * 100 // total} %")
                step["next"] += 20

        def work() -> None:
            try:
                path = updater.download_and_verify(
                    release, asset, repo, Path(tempfile.gettempdir()) / "VoiceChatTool-update", progress)
            except updater.UpdateError as exc:
                self.log(f"Update failed: {exc}")
                self.ui_queue.put(lambda: (self.update_btn.configure(state="normal"),
                                           messagebox.showerror("Update fehlgeschlagen", str(exc))))
                return
            self.log("Update downloaded and verified.")
            self.ui_queue.put(lambda: self._run_installer(path, release.version))

        self.log(f"Downloading v{release.version} ({asset.name})...")
        self.in_thread(work)

    def _run_installer(self, path: Path, version: str) -> None:
        if not messagebox.askyesno("Update installieren",
                                   f"Version {version} ist heruntergeladen und geprüft.\n\n"
                                   "Das Programm wird jetzt geschlossen, aktualisiert und danach "
                                   "automatisch neu gestartet. Fortfahren?"):
            self.update_btn.configure(state="normal")
            return
        import subprocess

        try:
            from .app import app_dir

            subprocess.Popen(updater.installer_command(path, app_dir()), close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except OSError as exc:
            self.update_btn.configure(state="normal")
            messagebox.showerror("Update fehlgeschlagen", f"Installer konnte nicht gestartet werden: {exc}")
            return
        self.log("Installer started; closing the program.")
        self.root.after(600, self.close)

    # ------------------------------------------------------------ plumbing
    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        self.ui_queue.put(lambda: self._append_log(line))

    def _trim_log_file(self) -> None:
        try:
            if self.log_path.exists() and self.log_path.stat().st_size > LOG_FILE_MAX_BYTES:
                self.log_path.unlink()
        except OSError:
            pass

    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll)

    def in_thread(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _state_changed(self, state: str) -> None:
        self.ui_queue.put(lambda: self._show_state(state))

    def _got_result(self, heard: str, result: str) -> None:
        self.ui_queue.put(lambda: (self.heard_var.set(heard), self.result_var.set(result)))

    def _show_state(self, state: str) -> None:
        dev = {"cpu": "CPU", "cuda": "GPU"}.get(self.engine.device or "", "–")
        self.state_var.set(f" {STATE_TEXT.get(state, state)} ")
        self.status_label.configure(bg=theme.STATE_COLORS.get(state, theme.MUTED))
        self.device_status_var.set(f"Gerät: {dev}")
        self.start_btn.configure(text="Stoppen" if state != "stopped" else "Starten")
        self.start_btn.configure(state="disabled" if state == "loading" else "normal")

    # ------------------------------------------------------------ tab: speak
    def _build_main(self, notebook: ttk.Notebook) -> None:
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text="Sprechen")
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.state_var = tk.StringVar(value=f" {STATE_TEXT['stopped']} ")
        self.device_status_var = tk.StringVar(value="Gerät: –")
        self.status_label = tk.Label(top, textvariable=self.state_var, bg=theme.MUTED, fg=theme.BG,
                                     font=("Segoe UI Semibold", 12), padx=10, pady=4)
        self.status_label.pack(side="left")
        ttk.Label(top, textvariable=self.device_status_var, style="Muted.TLabel").pack(side="left", padx=12)
        self.start_btn = ttk.Button(top, text="Starten", style="Accent.TButton", command=self.toggle_engine)
        self.start_btn.pack(side="right")
        ttk.Button(top, text="CPU/GPU wechseln", command=self.engine_toggle_device).pack(side="right", padx=6)

        self.keys_var = tk.StringVar()
        ttk.Label(f, textvariable=self.keys_var, style="Key.TLabel").pack(anchor="w", pady=(8, 0))
        self._update_keys_hint()

        langs = ttk.LabelFrame(f, text="Sprachen", padding=8)
        langs.pack(fill="x", pady=8)
        values = [label(c) for c in LANGUAGES]
        self.src_var = tk.StringVar(value=label(self.cfg["source_language"]))
        self.tgt_var = tk.StringVar(value=label(self.cfg["target_language"]))
        ttk.Label(langs, text="Ich spreche:").grid(row=0, column=0, sticky="w")
        ttk.Label(langs, text="Ausgabe in:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        for col, var in ((1, self.src_var), (3, self.tgt_var)):
            box = ttk.Combobox(langs, textvariable=var, values=values, width=22)
            box.grid(row=0, column=col, padx=4)
            box.bind("<<ComboboxSelected>>", lambda _e: self.apply_live())
            box.bind("<Return>", lambda _e: self.apply_live())
        ttk.Button(langs, text="↔", width=3, command=self.swap_languages).grid(row=0, column=4, padx=4)

        modes = ttk.LabelFrame(f, text="Übersetzen", padding=8)
        modes.pack(fill="x")
        self.mode_var = tk.StringVar(value=self.cfg["translate_mode"])
        for key in TRANSLATE_MODES:
            ttk.Radiobutton(modes, text=MODE_TEXT[key], value=key, variable=self.mode_var,
                            command=self.apply_live).pack(anchor="w")
        out = ttk.LabelFrame(f, text="Ausgabe", padding=8)
        out.pack(fill="x", pady=8)
        self.output_var = tk.StringVar(value=self.cfg["output_mode"])
        for key, text in OUTPUT_TEXT.items():
            ttk.Radiobutton(out, text=text, value=key, variable=self.output_var,
                            command=self.apply_live).pack(anchor="w")

        self.heard_var, self.result_var = tk.StringVar(), tk.StringVar()
        for text, var in (("Gehört:", self.heard_var), ("Ergebnis:", self.result_var)):
            row = ttk.Frame(f)
            row.pack(fill="x")
            ttk.Label(row, text=text, width=10, style="Muted.TLabel").pack(side="left")
            ttk.Label(row, textvariable=var, wraplength=620,
                      style="Result.TLabel" if text.startswith("Erg") else "TLabel").pack(side="left", anchor="w")

        self.log_box = tk.Text(f, height=10, state="disabled", wrap="word")
        theme.style_text(self.log_box)
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))

    def _update_keys_hint(self) -> None:
        c = self.cfg
        parts = [f"[{c['hotkey'].upper()}] halten = sprechen"]
        if c["translate_hotkey"]:
            parts.append(f"[{c['translate_hotkey'].upper()}] halten = sprechen + immer übersetzen")
        if c["device_toggle_hotkey"]:
            parts.append(f"[{c['device_toggle_hotkey'].upper()}] = CPU/GPU")
        self.keys_var.set("   ·   ".join(parts))

    def swap_languages(self) -> None:
        src, tgt = self.src_var.get(), self.tgt_var.get()
        self.src_var.set(tgt)
        self.tgt_var.set(src)
        self.apply_live()

    def apply_live(self) -> None:
        """Take the controls on the first tab, validate, save and hand over to the engine."""
        new = dict(self.cfg)
        new.update(source_language=code_from_label(self.src_var.get()),
                   target_language=code_from_label(self.tgt_var.get()),
                   translate_mode=self.mode_var.get(), output_mode=self.output_var.get())
        self._commit(new)

    def _commit(self, new: Dict[str, Any]) -> bool:
        try:
            new = parse_config(new)
            save_config(self.config_path, new)
        except (ConfigError, OSError) as exc:
            messagebox.showerror("Einstellung ungültig", str(exc))
            return False
        self.cfg = new
        self._update_keys_hint()
        self.engine.apply(new)
        return True

    # ------------------------------------------------------------ tab: languages & models
    def _build_languages(self, notebook: ttk.Notebook) -> None:
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text="Sprachen & Modelle")
        ttk.Label(f, text="Übersetzungs-Sprachpakete (offline, je Sprache ↔ Englisch; "
                          "jede Kombination funktioniert über Englisch).",
                  wraplength=700).pack(anchor="w")
        cols = ("name", "code", "to", "from", "status")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12, selectmode="browse")
        for col, text, width in (("name", "Sprache", 180), ("code", "Code", 60),
                                 ("to", "→ Englisch", 100), ("from", "← Englisch", 100),
                                 ("status", "Status", 160)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)

        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Installieren", command=self.install_selected).pack(side="left")
        ttk.Button(row, text="Entfernen", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(row, text="Liste aktualisieren (Internet)", command=self.load_index).pack(side="left")

        models = ttk.LabelFrame(f, text="Whisper-Spracherkennung", padding=8)
        models.pack(fill="x", pady=(10, 0))
        self.cpu_model_var = tk.StringVar(value=self.cfg["whisper_model"])
        self.gpu_model_var = tk.StringVar(value=self.cfg["whisper_model_gpu"])
        ttk.Label(models, text="Modell (CPU):").grid(row=0, column=0, sticky="w")
        ttk.Combobox(models, textvariable=self.cpu_model_var, values=WHISPER_MODELS,
                     width=14).grid(row=0, column=1, padx=6, pady=2)
        ttk.Label(models, text="Modell (GPU, leer = gleich):").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Combobox(models, textvariable=self.gpu_model_var, values=[""] + WHISPER_MODELS,
                     width=14).grid(row=0, column=3, padx=6)
        ttk.Button(models, text="Übernehmen", command=self.apply_models).grid(row=0, column=4, padx=6)
        ttk.Label(models, text="Größere Modelle erkennen besser, laden beim ersten Mal aber "
                               "mehrere 100 MB herunter und sind auf der CPU langsam.",
                  wraplength=700).grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def apply_models(self) -> None:
        new = dict(self.cfg)
        new.update(whisper_model=self.cpu_model_var.get(), whisper_model_gpu=self.gpu_model_var.get())
        if self._commit(new):
            self.log("Whisper models changed; loading (downloads on first use)...")

    def refresh_installed(self) -> None:
        def work() -> None:
            try:
                installed = translator.installed_pairs()
            except Exception as exc:
                self.log(f"Could not read installed language packs: {exc}")
                installed = set()
            self.ui_queue.put(lambda: self._set_installed(installed))

        self.in_thread(work)

    def _set_installed(self, installed: set) -> None:
        self.installed = installed
        codes = set(LANGUAGES) | {c for pair in installed | self.index_pairs for c in pair}
        codes.discard(PIVOT)
        self.tree.delete(*self.tree.get_children())
        for code in sorted(codes, key=lambda c: label(c)):
            to_en, from_en = (code, PIVOT) in installed, (PIVOT, code) in installed
            status = "installiert" if to_en and from_en else ("teilweise" if to_en or from_en else
                     ("verfügbar" if (code, PIVOT) in self.index_pairs else "nicht installiert"))
            self.tree.insert("", "end", iid=code, values=(
                LANGUAGES.get(code, code), code, "✓" if to_en else "–", "✓" if from_en else "–", status))

    def load_index(self) -> None:
        def work() -> None:
            try:
                pairs = {(p.from_code, p.to_code) for p in translator.available_packages(self.log)}
            except Exception as exc:
                self.log(f"Could not load the language list: {exc}")
                return
            self.index_pairs = pairs
            self.log(f"{len(pairs)} language packs available.")
            self.refresh_installed()

        self.in_thread(work)

    def _selected_code(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Sprache wählen", "Bitte zuerst eine Sprache in der Liste auswählen.")
            return None
        return sel[0]

    def install_selected(self) -> None:
        code = self._selected_code()
        if not code:
            return

        def work() -> None:
            try:
                packages = translator.available_packages(self.log)
            except Exception as exc:
                self.log(f"Cannot reach the language index: {exc}")
                return
            for pair in ((code, PIVOT), (PIVOT, code)):
                if pair not in self.installed:
                    translator.install_pair(*pair, self.log, packages)
            self.log(f"Language {label(code)}: done.")
            self.refresh_installed()

        self.in_thread(work)

    def remove_selected(self) -> None:
        code = self._selected_code()
        if not code or not messagebox.askyesno("Entfernen", f"Sprachpakete für {label(code)} löschen?"):
            return

        def work() -> None:
            for pair in ((code, PIVOT), (PIVOT, code)):
                translator.uninstall_pair(*pair, self.log)
            self.refresh_installed()

        self.in_thread(work)

    # ------------------------------------------------------------ tab: words
    def _build_words(self, notebook: ttk.Notebook) -> None:
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text="Wörter")
        self.spell_var = tk.BooleanVar(value=self.cfg["spellcheck"])
        ttk.Checkbutton(f, text="Rechtschreibung automatisch korrigieren (nur eindeutige Fälle, "
                                "vor dem Übersetzen)", variable=self.spell_var,
                        command=self.save_words).pack(anchor="w")

        box = ttk.LabelFrame(f, text="Wortschatz – Namen und Begriffe, die richtig erkannt werden "
                                     "sollen (ein Eintrag pro Zeile)", padding=6)
        box.pack(fill="both", expand=True, pady=6)
        self.vocab_text = tk.Text(box, height=6, wrap="word")
        theme.style_text(self.vocab_text)
        self.vocab_text.pack(fill="both", expand=True)
        self.vocab_text.insert("1.0", chr(10).join(self.cfg["vocabulary"]))

        box = ttk.LabelFrame(f, text="Feste Ersetzungen – falsch = richtig (ein Eintrag pro Zeile, "
                                     "z. B.  wiedora = Valorant)", padding=6)
        box.pack(fill="both", expand=True)
        self.repl_text = tk.Text(box, height=6, wrap="word")
        theme.style_text(self.repl_text)
        self.repl_text.pack(fill="both", expand=True)
        self.repl_text.insert("1.0", chr(10).join(self.cfg["replacements"]))

        ttk.Button(f, text="Speichern", command=self.save_words).pack(anchor="w", pady=8)
        ttk.Label(f, text="Tipp: Im Log steht bei „Gehört“ der Rohtext und bei „Fixed“ jede Korrektur. "
                          "Wird ein Wort falsch erkannt, trage es hier ein.", wraplength=700).pack(anchor="w")

    def save_words(self) -> None:
        lines = lambda box: [ln.strip() for ln in box.get("1.0", "end").splitlines() if ln.strip()]
        new = dict(self.cfg)
        new.update(spellcheck=self.spell_var.get(), vocabulary=lines(self.vocab_text),
                   replacements=lines(self.repl_text))
        if self._commit(new):
            self.log("Word settings saved.")

    # ------------------------------------------------------------ tab: settings
    def _build_settings(self, notebook: ttk.Notebook) -> None:
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text="Einstellungen")
        self.hotkey_var = tk.StringVar(value=self.cfg["hotkey"])
        self.toggle_var = tk.StringVar(value=self.cfg["device_toggle_hotkey"])
        self.translate_key_var = tk.StringVar(value=self.cfg["translate_hotkey"])
        self.mic_var = tk.StringVar(value=str(self.cfg["microphone_device"]))
        self.device_var = tk.StringVar(value=self.cfg["device"])
        self.beep_var = tk.BooleanVar(value=self.cfg["beep"])
        self.keywords_var = tk.StringVar(value=", ".join(self.cfg["keywords"]))
        self.update_check_var = tk.BooleanVar(value=self.cfg["update_check"])
        self.update_repo_var = tk.StringVar(value=self.cfg["update_repo"])

        def row(r: int, text: str, widget: tk.Widget, extra: Optional[tk.Widget] = None) -> None:
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", pady=4)
            widget.grid(row=r, column=1, sticky="w", padx=8)
            if extra:
                extra.grid(row=r, column=2, sticky="w")

        key_btn = lambda var: ttk.Button(f, text="Taste aufnehmen", command=lambda: self.capture_key(var))
        row(0, "Sprechtaste (halten):", ttk.Entry(f, textvariable=self.hotkey_var, width=12), key_btn(self.hotkey_var))
        row(1, "CPU/GPU-Taste (leer = aus):", ttk.Entry(f, textvariable=self.toggle_var, width=12), key_btn(self.toggle_var))
        row(2, "Übersetzen-Taste (halten, leer = aus):", ttk.Entry(f, textvariable=self.translate_key_var, width=12), key_btn(self.translate_key_var))
        row(3, "Mikrofon:", ttk.Combobox(f, textvariable=self.mic_var, values=microphone_choices(), width=40))
        row(4, "Start auf:", ttk.Combobox(f, textvariable=self.device_var, values=list(DEVICES),
                                          state="readonly", width=12))
        row(5, "Stichwörter (Komma):", ttk.Entry(f, textvariable=self.keywords_var, width=40))
        row(6, "Sanfte Töne (Übersetzen, CPU/GPU):", ttk.Checkbutton(f, variable=self.beep_var))
        row(7, "Beim Start nach Updates suchen:", ttk.Checkbutton(f, variable=self.update_check_var),
            ttk.Button(f, text="Jetzt suchen", command=lambda: self.check_updates(manual=True)))
        row(8, "Update-Repository (owner/name):", ttk.Entry(f, textvariable=self.update_repo_var, width=40))
        ttk.Button(f, text="Speichern", command=self.save_settings).grid(row=9, column=1, sticky="w", pady=12, padx=8)
        ttk.Label(f, text="Mikrofon leer = Windows-Standard. „Start auf“ gilt ab dem nächsten Programmstart.\n"
                          "Hinweis: Anti-Cheat (z. B. Vanguard) kann simulierte Eingaben blockieren;\n"
                          "„Nur Zwischenablage“ ist die sichere Variante.", justify="left").grid(
            row=10, column=0, columnspan=3, sticky="w", pady=8)

    def capture_key(self, var: tk.StringVar) -> None:
        var.set("… Taste drücken")

        def work() -> None:
            import keyboard

            name = keyboard.read_key(suppress=False)
            self.ui_queue.put(lambda: var.set(name))

        self.in_thread(work)

    def save_settings(self) -> None:
        new = dict(self.cfg)
        new.update(hotkey=self.hotkey_var.get(), translate_hotkey=self.translate_key_var.get(),
                   device_toggle_hotkey=self.toggle_var.get(),
                   microphone_device=self.mic_var.get(), device=self.device_var.get(),
                   beep=self.beep_var.get(), update_check=self.update_check_var.get(),
                   update_repo=self.update_repo_var.get(),
                   keywords=[k.strip() for k in self.keywords_var.get().split(",") if k.strip()])
        if self._commit(new):
            self.log("Settings saved.")

    # ------------------------------------------------------------ engine control
    def start_engine(self) -> None:
        self.in_thread(self.engine.start)

    def toggle_engine(self) -> None:
        if self.engine.state == "stopped":
            self.start_engine()
        else:
            self.engine.stop()
            self.log("Stopped.")

    def engine_toggle_device(self) -> None:
        if self.engine.state not in ("ready", "processing"):
            return
        tr = self.engine.transcriber
        if self.engine.device == "cpu" and tr is not None and tr.gpu_libs_missing():
            self._offer_gpu_download()
            return
        self.engine.toggle_device()

    def _offer_gpu_download(self) -> None:
        """This installation has no NVIDIA libraries: offer to download them, then switch."""
        if sys.platform != "win32":
            messagebox.showinfo("Keine GPU-Unterstützung",
                                "Die NVIDIA-CUDA-Bibliotheken fehlen. Auf diesem System werden sie nicht "
                                "automatisch geladen (siehe README).")
            return
        if self._gpu_download_running:
            self.log("The NVIDIA libraries are already downloading.")
            return
        if not messagebox.askyesno(
                "GPU-Unterstützung nachladen",
                "Dieses Programm enthält die NVIDIA-CUDA-Bibliotheken nicht, deshalb läuft die "
                "Erkennung auf der CPU.\n\n"
                "Soll es sie jetzt nachladen? Sie kommen direkt von PyPI, wo NVIDIA sie veröffentlicht.\n"
                "• Download ca. 1,3 GB (nur beim ersten Mal), danach ca. 1,9 GB Speicher in\n"
                f"  {self.cuda_dir}\n"
                "• Jede Datei wird per Prüfsumme kontrolliert.\n"
                "• Es gilt die Lizenz von NVIDIA (liegt in den Paketen).\n\n"
                "Danach schaltet das Programm automatisch auf die GPU um."):
            return
        self._gpu_download_running = True
        step = {"pkg": "", "next": 10}

        def progress(package: str, done: int, total: int) -> None:
            if package != step["pkg"]:
                step.update(pkg=package, next=10)
            if total and done * 100 // total >= step["next"]:
                self.log(f"Downloading {package}: {done * 100 // total} %")
                step["next"] += 20

        def work() -> None:
            try:
                cuda_pack.install(self.cuda_dir, Path(tempfile.gettempdir()) / "VoiceChatTool-cuda",
                                  progress, self.log)
            except cuda_pack.CudaPackError as exc:
                self.log(f"GPU libraries could not be installed: {exc}")
                self.ui_queue.put(lambda: messagebox.showerror("GPU-Bibliotheken", str(exc)))
                return
            finally:
                self._gpu_download_running = False
            self.ui_queue.put(self._after_gpu_download)

        self.log("Downloading the NVIDIA CUDA libraries from PyPI...")
        self.in_thread(work)

    def _after_gpu_download(self) -> None:
        tr = self.engine.transcriber
        if tr is None:
            return
        tr.refresh_cuda_dirs()
        self.engine.toggle_device()

    def close(self) -> None:
        self.engine.stop()
        self.root.destroy()


def run_gui(cfg: Dict[str, Any], config_path: Path, log_path: Path) -> int:
    root = tk.Tk()
    App(root, cfg, config_path, log_path)
    root.mainloop()
    return 0
