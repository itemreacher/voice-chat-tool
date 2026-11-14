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
| **nvidia-cublas-cu12, nvidia-cuda-nvrtc-cu12, nvidia-cudnn-cu12** (GPU installer; or downloaded from PyPI by the program on request) | GPU speed-up | NVIDIA proprietary licences (texts are shipped in `licenses/nvidia/` of the GPU edition and next to the downloaded libraries). The cuBLAS and cuDNN licences allow distributing the runtime libraries as part of an application under conditions (the application must offer substantial functionality of its own, only the application may use the libraries, and the terms must be consistent with NVIDIA's); for cuBLAS only the parts listed in its "Attachment A" may be distributed, which has **not** been checked file by file. The CPU edition does not contain them: the program downloads them from PyPI only if you ask it to. Read the licences before you redistribute the GPU installer. |
| [PyInstaller](https://pyinstaller.org) (build time) | packaging | GPL-2.0 with an exception that allows distributing the built programs |
| [Inno Setup](https://jrsoftware.org/isinfo.php) (build time) | Windows installer | Inno Setup licence (free, also for commercial use) |
| [Pillow](https://python-pillow.org) (build time) | logo generation | MIT-CMU (HPND) |
| [pytest](https://pytest.org) (development) | tests | MIT |

The Windows installers are not code-signed; Windows SmartScreen may warn when you run them for the first time.
