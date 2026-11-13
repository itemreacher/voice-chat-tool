#!/usr/bin/env bash
set -euo pipefail
rm -rf "$HOME/.local/share/VoiceChatTool" "$HOME/.local/bin/voice-chat-tool" \
       "$HOME/.local/share/applications/voice-chat-tool.desktop"
echo "Removed. Your settings stay in ~/.config/VoiceChatTool (delete it to remove them)."
