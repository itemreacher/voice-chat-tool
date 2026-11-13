#!/usr/bin/env bash
# Builds installer/Output/VoiceChatTool-<version>-linux.tar.gz (with install.sh). UNTESTED: see README.
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3.11 -m venv .venv || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements-dev.txt
.venv/bin/python tools/make_icon.py

VER=$(.venv/bin/python -c "from vct import __version__ as v; print(v)")
.venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name VoiceChatTool \
    --add-data "assets/logo_64.png:assets" \
    --collect-all faster_whisper --collect-all ctranslate2 --collect-all argostranslate \
    --collect-all sounddevice --collect-all sentencepiece --collect-all spellchecker main.py

OUT="installer/Output/VoiceChatTool-$VER-linux"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -r dist/VoiceChatTool "$OUT/VoiceChatTool"
.venv/bin/python -c "from PIL import Image; Image.open('assets/icon.ico').save('$OUT/icon.png')"
cp packaging/linux/install.sh packaging/linux/uninstall.sh "$OUT/"
chmod +x "$OUT/install.sh" "$OUT/uninstall.sh" "$OUT/VoiceChatTool/VoiceChatTool"
tar -C installer/Output -czf "$OUT.tar.gz" "VoiceChatTool-$VER-linux"
rm -rf "$OUT"   # keep only the .tar.gz in installer/Output (it is what gets published)
echo "Done: $OUT.tar.gz"
