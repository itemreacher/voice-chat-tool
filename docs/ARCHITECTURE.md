# Architecture

Rule of thumb: **pure logic** (testable on any OS, no heavy imports) is kept apart from **OS and
hardware code** (hotkeys, microphone, typing, sound).

```
main.py                 entry point (wraps vct.app.main, shows an error dialog on crashes)
vct/
  app.py                start-up: GUI (default), --console, --selftest; data folder handling
  engine.py             hotkeys -> record -> transcribe -> correct -> translate -> output (no UI)
  gui.py                Tkinter window; talks to the Engine only through callbacks and a queue
  theme.py              colours, fonts, ttk styles (pure colour/contrast maths + Tk setup)
  config.py             defaults, validation, config.toml read/write (pure)
  paths.py              config/log location and bundled resources (pure)
  logic.py              keyword detection, translation modes (pure)
  correction.py         replacement list + conservative spell check (pure, dictionary injected)
  languages.py          language names and which Argos packs a pair needs (pure)
  translator.py         Argos Translate wrapper: install/remove packs, translate
  transcriber.py        faster-whisper wrapper: CPU/GPU switch, CUDA checks and time limit
  audio_check.py        is a recording worth transcribing (pure)
  recorder.py           microphone capture (sounddevice)
  tone.py               soft notification tones as WAV data (pure)
  platform_io.py        picks the OS backend:
  winout.py               Windows: SendInput typing, clipboard, tones (ctypes, winsound)
  unixio.py               macOS/Linux: pbcopy/osascript, xclip/xdotool/wtype, afplay/paplay
  updater.py            GitHub release check, checksum-verified download (pure logic + thin network)
  build_info.py         repository name, written at build time by tools/set_repo.py
tools/                  make_icon.py (logo), set_repo.py, version.py
installer/              Inno Setup script (Windows)
packaging/linux/        install.sh / uninstall.sh for the Linux tarball
build.bat, build_installer.bat, build_macos.sh, build_linux.sh
tests/                  pytest; the OS-specific modules are covered through their pure helpers
```

## Data flow of one recording

1. A global hotkey (`keyboard` library) starts the `Recorder`; releasing it stops it and queues the audio.
2. The worker thread of the `Engine` runs `check_audio` -> `Transcriber.transcribe` (with vocabulary
   hints) -> `correction.correct_text` -> `logic.process_transcript` (translation by `translator`)
   -> clipboard and `type_text` through the OS backend.
3. The GUI never blocks: the engine runs in threads and reports through callbacks that are placed on a queue
   and handled in the Tk main loop.

## Things worth knowing

- **CUDA:** if the NVIDIA libraries are missing, CTranslate2 does not raise an error in the installed
  program, the first GPU inference blocks forever. `cuda_libs_loadable` checks first, and a GPU start has
  a time limit (`GPU_LOAD_TIMEOUT_S`).
- **Typing:** one character per `SendInput` call with a short pause; bigger batches made some
  editors repeat or drop characters.
- **Data folder:** a `config.toml` next to the program wins (portable / source runs); otherwise the per-user
  folder (`%APPDATA%\VoiceChatTool`, `~/Library/Application Support/VoiceChatTool`, `~/.config/VoiceChatTool`).
  `VCT_DATA_DIR` overrides it.
- **Updates:** see `docs/RELEASING.md`.
