"""Picks the output backend (typing, clipboard, cues) for the current OS."""
from __future__ import annotations

import sys


def load_backend():
    """Module with type_text(text), copy_to_clipboard(text) and play_cue(name)."""
    if sys.platform == "win32":
        from . import winout

        return winout
    from . import unixio

    return unixio


def hotkey_hint() -> str:
    if sys.platform == "darwin":
        return ("macOS: allow the program under System Settings > Privacy & Security > "
                "Accessibility and Input Monitoring.")
    if sys.platform != "win32":
        return "Linux: global hotkeys need root (sudo) or membership in the 'input' group; X11 works best."
    return ""
