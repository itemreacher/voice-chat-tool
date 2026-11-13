#!/usr/bin/env bash
# Builds "Voice Chat Tool.app" and a .dmg on macOS. UNTESTED (no Mac was available): see README.
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3.11 -m venv .venv || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements-dev.txt
.venv/bin/python tools/make_icon.py

VER=$(.venv/bin/python -c "from vct import __version__ as v; print(v)")
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name "Voice Chat Tool" \
    --osx-bundle-identifier com.voicechattool.app --icon assets/icon.ico \
    --add-data "assets/logo_64.png:assets" \
    --collect-all faster_whisper --collect-all ctranslate2 --collect-all argostranslate \
    --collect-all sounddevice --collect-all sentencepiece --collect-all spellchecker main.py

APP="dist/Voice Chat Tool.app"
# macOS asks for these permissions only if the bundle explains why.
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 'Voice Chat Tool records your voice for speech recognition.'" "$APP/Contents/Info.plist" || true
codesign --force --deep --sign - "$APP"   # ad-hoc signature (not notarized)

mkdir -p installer/Output
hdiutil create -volname "Voice Chat Tool" -srcfolder "$APP" -ov -format UDZO \
    "installer/Output/VoiceChatTool-$VER-macOS.dmg"
echo "Done: installer/Output/VoiceChatTool-$VER-macOS.dmg"
