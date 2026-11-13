# Third-party components

Voice Chat Tool itself is MIT licensed (see `LICENSE`). It uses the components below. The licence
names are to the best of my knowledge; **please verify them before redistributing**, especially the
NVIDIA libraries and the downloaded models.

| Component | Used for | Licence |
|---|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2) | speech recognition | MIT |
| OpenAI Whisper model weights (downloaded on first use, not shipped) | speech recognition | MIT |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | offline translation | MIT |
| Argos language packs (downloaded on demand, not shipped) | translation | each pack has its own licence (mostly CC0 / CC-BY / MIT) |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) (+ PortAudio) | microphone | MIT |
| [keyboard](https://github.com/boppreh/keyboard) | global hotkeys | MIT |
| [pyspellchecker](https://github.com/barrust/pyspellchecker) | spelling correction | MIT |
| [NumPy](https://numpy.org) | audio arrays | BSD-3-Clause |
| Tkinter / Python | window, runtime | PSF licence |
| **nvidia-cublas-cu12, nvidia-cudnn-cu12** (GPU installer only) | GPU speed-up | NVIDIA proprietary licence: free to use, redistribution is allowed under NVIDIA's terms; read them before you publish the GPU installer |
| [PyInstaller](https://pyinstaller.org) (build time) | packaging | GPL-2.0 with an exception that allows distributing the built programs |
| [Inno Setup](https://jrsoftware.org/isinfo.php) (build time) | Windows installer | Inno Setup licence (free, also for commercial use) |
| [Pillow](https://python-pillow.org) (build time) | logo generation | MIT-CMU (HPND) |
| [pytest](https://pytest.org) (development) | tests | MIT |

The Windows installers are not code-signed; Windows SmartScreen may warn when you run them for the first time.
