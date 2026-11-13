#!/usr/bin/env bash
# Per-user install: copies the program to ~/.local/share/VoiceChatTool, adds a menu entry.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/.local/share/VoiceChatTool"
rm -rf "$dest"; mkdir -p "$dest" "$HOME/.local/bin" "$HOME/.local/share/applications"
cp -r "$here/VoiceChatTool/." "$dest/"
cp "$here/icon.png" "$dest/icon.png"
ln -sf "$dest/VoiceChatTool" "$HOME/.local/bin/voice-chat-tool"
cat > "$HOME/.local/share/applications/voice-chat-tool.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Voice Chat Tool
Comment=Push-to-talk speech to text with translation
Exec=$dest/VoiceChatTool
Icon=$dest/icon.png
Terminal=false
Categories=Utility;AudioVideo;
DESK
echo "Installed to $dest"
echo
echo "Needed on Linux (install with your package manager if missing):"
echo "  libportaudio2, xclip (or wl-clipboard), xdotool (or wtype), pulseaudio-utils (paplay)"
echo "Global hotkeys read /dev/input: add yourself to the 'input' group, then log in again:"
echo "  sudo usermod -aG input \$USER"
