# voice-chat-tool

Hold a hotkey, speak, release: the text is typed into the focused window
(your Valorant / WoW chat box) and copied to the clipboard. Speak any language and
get the text in any other language (offline translation). Runs fully offline after
the first-run model downloads. Has a small window (Tkinter), no cloud, no telemetry.

The tool **never presses Enter**. Open the chat yourself, speak, check, send.

## Install (finished program)

| System | Installer | Status |
|---|---|---|
| **Windows 10/11** | `installer\Output\VoiceChatTool-Setup-<version>-CPU.exe` (small) or `-GPU.exe` (includes the NVIDIA CUDA libraries, much bigger) | built and tested on Windows 11 |
| **macOS** | `VoiceChatTool-<version>-macOS.dmg` from `build_macos.sh` | **untested** (no Mac available) |
| **Linux** | `VoiceChatTool-<version>-linux.tar.gz` from `build_linux.sh`, then `./install.sh` | **untested** (no Linux machine available) |
| iOS / Android | not supported | see below |

**Windows:** run the Setup. It installs per user (no admin needed; "for all users" is offered),
adds a Start menu entry, an optional desktop icon and an uninstaller. Installing a newer Setup
over an old one updates it in place. Settings (`config.toml`) and the log live in
`%APPDATA%\VoiceChatTool` and survive updates and re-installs; uninstalling keeps them (delete
that folder to remove them). If a `config.toml` sits next to the program (the portable folder
build) it is used instead. Models are downloaded on first start (internet needed once).

Build the installers yourself: `build_installer.bat` (needs `.venv`, see below, and Inno Setup:
`winget install JRSoftware.InnoSetup`). It creates the CPU installer and, if the CUDA libraries are
in the `.venv` (`requirements-gpu.txt`), the GPU installer. The version comes from
`vct/__init__.py`.

**macOS / Linux:** the code has an OS layer (`vct/unixio.py`: `pbcopy`/`osascript`/`afplay` on macOS;
`xclip`|`wl-copy`, `xdotool`|`wtype`, `paplay`|`aplay` on Linux). The command building is unit
tested, but nothing was run on a real Mac or Linux PC. Known requirements and limits:

- macOS: allow the program under Privacy & Security > *Accessibility*, *Input Monitoring* and
  *Microphone*. No GPU support (CPU only). The `.app` is only ad-hoc signed, not notarized, so
  Gatekeeper asks you to confirm opening it.
- Linux: install `libportaudio2`, `xclip` (or `wl-clipboard`), `xdotool` (or `wtype`) and
  `pulseaudio-utils`; global hotkeys need `sudo usermod -aG input $USER` (then log in again). X11
  works best, Wayland restricts global hotkeys and typing. GPU use on Linux needs the CUDA libraries on
  `LD_LIBRARY_PATH` (not bundled).
- `.github/workflows/build.yml` builds all three installers in GitHub Actions (CPU edition). It was
  written but never run.

**iOS / Android:** not possible with this program. These systems do not allow an app to listen for
global hotkeys or to type into other apps (a game chat); it would need a different, separate app
(for example a keyboard or companion app). Not part of this project yet.

## Updates

The installed Windows program checks GitHub for a newer release when it starts (Settings: "Beim Start nach
Updates suchen"). If there is one, a banner offers **Jetzt aktualisieren**: it downloads the Setup of your
edition, verifies its SHA-256 checksum, closes itself, updates in place and starts again. Your settings are
kept. Without a matching checksum nothing is installed automatically. Details: `docs/RELEASING.md`.

## Put it on GitHub

```bash
cd voice-chat-tool
git init -b main
git add .
git commit -m "Voice Chat Tool 1.0.0"
git remote add origin https://github.com/<your-name>/<repository>.git
git push -u origin main
```

Then publish a release by pushing a tag (the workflow builds and uploads all installers):

```bash
git tag v1.0.0
git push origin v1.0.0
```

What the repository contains: `vct/` (code), `tests/`, `tools/`, `installer/` + `build*.{bat,sh}` (packaging),
`.github/` (tests on every push, release workflow, issue/PR templates), `docs/` (architecture, releasing),
`config.example.toml`, `LICENSE` (MIT), `THIRD_PARTY_LICENSES.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.
Personal files (`config.toml`, logs, build output, the venv) are excluded by `.gitignore`.
The version lives in `vct/__init__.py` and must match the tag.

## Windows setup

1. Install **Python 3.11** (64-bit) from <https://www.python.org/downloads/>.
   Tick "Add python.exe to PATH".
2. Open PowerShell in this folder and run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Start it (opens the window; `python main.py --console` runs it without a window):

```powershell
python main.py
```

First run downloads the Whisper model (`small`, roughly 500 MB) and the Argos
de→en language pack, with progress shown in the console. After that no internet
is needed.

Usage: hold **F9**, speak, release. Normal push-to-talk is **silent**. To translate, hold
**F8** instead of F9 (`translate_hotkey`): the text is always translated into the output
language, no keyword needed, and a soft rising tone confirms that translation is active.
Alternatively start with a keyword ("translate …") on F9; a soft tone then confirms the
translation worked. Set `beep = false` for no sounds at all.

## Look and feel

Dark "gaming" theme that blends three worlds: Valorant (deep blue-grey ground, coral-red signal
colour, cut corners), The Witcher (cold steel, serif headings) and World of Warcraft (gold frames).
The logo is a keyboard shattering into shards: the voice replaces the keys. The status field changes
colour (green = ready, red = recording, gold = loading/processing). All colours live in
`vct/theme.py` (checked for readable contrast in the tests). `python tools/make_icon.py` redraws the
logo and icon files in `assets/` (needs Pillow, installed with `requirements-dev.txt`).

## The window

| Tab | What it does |
|---|---|
| **Sprechen** | Status (Bereit / Aufnahme …, CPU or GPU), start/stop, **spoken language**, **output language**, ↔ swap, translation mode, output mode, last heard / result, live log |
| **Sprachen & Modelle** | Install / remove translation language packs, change the Whisper model for CPU and GPU |
| **Einstellungen** | Hotkeys (with "Taste aufnehmen"), microphone, start device, keywords, soft tones |

Changes are applied immediately and saved to `config.toml`. Without a window the log is
in `voice-chat-tool.log` next to the program.

**Translation modes:** *Nur mit Stichwort* (only if you start with a keyword such as
"translate"/"übersetze"), *Immer übersetzen*, *Nie übersetzen*. If spoken and output
language are the same, nothing is translated (e.g. Russian → Russian just types what you said).

**Languages:** Whisper recognises ~100 languages, so any spoken language works without
extra downloads (a bigger Whisper model helps for non-European languages). For translation
each language needs two small Argos packs (language ↔ English, one-time download, tab
"Sprachen & Modelle" → select → *Installieren*; or they are fetched automatically the first
time a pair is used). Argos chains them, so **every combination works**, e.g. ru → de goes
ru → en → de. Quality is best for the direct pairs with English. Not every language is in the
Argos list; *Liste aktualisieren* shows what is available.

## Desktop audio to text

The tab **Desktop-Audio** turns what the PC plays into text while it plays, for example a video, a stream or a
meeting. Start the recording, play the video, stop it; the text appears live, one line per phrase, with times.
Language **automatic** detects it (or choose one); **Übersetzen nach** adds a translation below each line (offline,
the language packs are fetched on first use). Copy it, or save it as `.txt` or as `.srt` subtitles that video
players can load. A level meter shows that sound arrives.

- Windows only (WASAPI loopback of the default output device). Everything the PC plays is recorded, including other
  people's voices in a call: mind copyright and consent. The audio is not saved, only the text.
- It uses the same Whisper model as push-to-talk (CPU or GPU). On a CPU a long video can be transcribed slower than it
  plays; the tab then shows a backlog. A bigger model is more accurate but slower.
- Music, noise and very quiet speech lower the quality. Whisper sometimes invents text on silence; very short
  repeats are filtered and doubtful phrases are dropped.

## Fewer recognition errors (tab "Wörter")

Applied in this order, every change is logged as `Fixed : 'before' -> 'after'` (the raw
recognition stays visible as `Heard`):

1. **Wortschatz** (`vocabulary`): names and game terms are passed to Whisper as hints, so it
   recognises them correctly in the first place (e.g. `Valorant`, `Jett`, `Spike`).
2. **Feste Ersetzungen** (`replacements`): your own `wrong = right` list, whole words,
   case-insensitive. Use it whenever a word keeps coming out wrong.
3. **Rechtschreibung** (`spellcheck`, on by default): unknown words with one clear dictionary
   match are fixed (`Hilfee` → `Hilfe`). It never touches short words (< 4 letters), ALL-CAPS,
   words with digits, your vocabulary, replacement targets or keywords, and it leaves
   ambiguous cases alone. Runs on the spoken language *before* translation. Dictionaries
   exist for de, en, es, fr, it, nl, pt, ru and a few more; other languages only use 1 and 2.

Limits: this fixes typos and words you list. It cannot fix wrongly recognised words that are
valid words themselves ("wieder"/"wider"), and it is no grammar checker. Switch to a bigger
Whisper model for better recognition in general. Rare German compound words are unknown to the
dictionary but are left unchanged unless a clearly dominant near match exists; turn
`spellcheck` off if it ever misfires.

## CPU / GPU switch

Whisper can run on the CPU (int8) or on an NVIDIA GPU (CUDA, float16, much faster,
allows bigger models). Choose at start-up with `device` in `config.toml`
(`"auto"`, `"cpu"`, `"gpu"`) and switch **while running** with **F10**
(`device_toggle_hotkey`). A soft tone confirms: higher = GPU, lower = CPU. The switch
runs in the background; recordings made meanwhile are processed afterwards.

**Installed program:** the GPU edition of the installer already contains the NVIDIA libraries. The CPU edition
does not, but its GPU button offers to download them (about 1.3 GB, from PyPI, checksum-verified) and then
switches. They are stored in `%LOCALAPPDATA%\VoiceChatTool\cuda` together with NVIDIA's licence texts; delete
that folder to remove them. An NVIDIA driver is required in any case.

From source, GPU needs the NVIDIA CUDA 12 libraries (one-time, about 1 GB):

```powershell
pip install -r requirements-gpu.txt
```

Run `build.bat` again afterwards so the exe bundles them. The first switch to the
GPU can take about 30 s (one-time initialisation), later switches about 1 s. If the
GPU cannot be used, the tool says why and stays on the CPU. Set `whisper_model_gpu`
(e.g. `"medium"`) to use a bigger, more accurate model only on the GPU.

## Configuration (`config.toml`)

| Key | Meaning |
|---|---|
| `hotkey` | single push-to-talk key, default `"f9"` |
| `keywords` | translate trigger words, default `["translate", "übersetze"]` |
| `source_language` | language you speak, code like `de`, `en`, `ru`, `fr` |
| `target_language` | language of the output text |
| `translate_mode` | `"keyword"`, `"always"` or `"off"` |
| `vocabulary` | list of names/terms Whisper should recognise |
| `replacements` | list of `"wrong = right"` entries |
| `spellcheck` | `true`/`false`, automatic spelling fix |
| `whisper_model` | `tiny`, `base`, `small`, `medium`, `large-v3` … |
| `whisper_model_gpu` | optional bigger model used only on the GPU, `""` = same as `whisper_model` |
| `device` | start-up device: `"auto"`, `"cpu"` or `"gpu"` |
| `device_toggle_hotkey` | key that switches CPU/GPU while running, default `"f10"`, `""` disables |
| `microphone_device` | `""` = default, a device index, or part of a device name |
| `output_mode` | `"type"` (SendInput + clipboard) or `"clipboard"` (clipboard only) |
| `translate_hotkey` | hold + speak = always translate, default `"f8"`, `""` disables |
| `desktop_language` | desktop audio: `"auto"` or a language code |
| `desktop_translate_to` | desktop audio: translate into this language, `""` = off |
| `desktop_timestamps` | desktop audio: show times in front of each line |
| `beep` | `true` / `false`: soft tones for translation and CPU/GPU switch only (push-to-talk is silent) |

## Tests (any OS, Python 3.11 recommended)

```bash
pip install -r requirements-test.txt   # tests only; requirements-dev.txt also builds the exe
python -m pytest
```

The pure logic (`vct/logic.py`, `vct/config.py`, `vct/audio_check.py`) has no
Windows dependency. Hotkey, microphone and SendInput (`vct/app.py`,
`vct/recorder.py`, `vct/winout.py`) are Windows-only and not covered by tests.

## Start as a normal program (.exe with icon)

Double-click `build.bat` (needs the `.venv` from the setup above). It creates
`dist\VoiceChatTool\VoiceChatTool.exe` with a microphone icon (folder build, fast start,
window only, no console). Then:

- Double-click `Voice Chat Tool.lnk` (copy it to your Desktop if you like), or
  run `dist\VoiceChatTool\VoiceChatTool.exe` directly.
- Change settings in the window. They are saved to `config.toml` (next to the exe in the portable
  folder build, otherwise in the user data folder).
- Check a build with `dist\VoiceChatTool\VoiceChatTool.exe --selftest` (result in `selftest.log`).
- No console window: the log is shown in the window and written to `voice-chat-tool.log`.
  Start-up errors appear as a dialog. Model downloads show no progress bar in the window
  (the log says "Loading/Downloading"); first downloads can take a few minutes.
- Models are stored in the user cache, not inside the exe. Keep the whole
  `dist\VoiceChatTool` folder together.
- After changing the code, run `build.bat` again to update the exe.

## ⚠ Anti-cheat warning

Anti-cheat software (e.g. **Riot Vanguard** for Valorant) may block or flag
simulated keyboard input such as SendInput, and global keyboard hooks may be
looked at too. **The clipboard mode is the safe fallback**: set
`output_mode = "clipboard"` and paste with Ctrl+V yourself. Use this tool at
your own risk; the author is not responsible for bans or other consequences.

## Libraries and licenses (to my knowledge; please verify before redistributing)

| Library | Purpose | License |
|---|---|---|
| faster-whisper (+ CTranslate2) | speech-to-text | MIT |
| OpenAI Whisper model weights | model downloaded by faster-whisper | MIT |
| argostranslate | offline de→en translation | MIT (language packs carry their own licenses) |
| sounddevice | microphone capture | MIT |
| pyspellchecker | spelling correction (offline) | MIT |
| numpy | audio arrays | BSD-3-Clause |
| keyboard | global push-to-talk hotkey | MIT |
| nvidia-cublas-cu12, nvidia-cudnn-cu12 (optional) | CUDA libraries for GPU mode | NVIDIA proprietary license (free to use; check redistribution terms before sharing the exe) |
| Tkinter | window (Python standard library) | PSF license |
| pytest (dev only) | tests | MIT |
| PyInstaller (optional) | .exe build | GPL-2.0 with exception allowing distribution of built apps |

Python standard library only for SendInput, clipboard and the soft tones (`ctypes`, `winsound`, `wave`).
