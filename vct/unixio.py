"""Typing, clipboard and cues for macOS and Linux via the system's own tools.

The command building is pure (testable anywhere); running it needs the real OS.
UNTESTED on real macOS/Linux machines: see README.

macOS: pbcopy, osascript (System Events needs the Accessibility permission), afplay.
Linux: wl-copy/xclip/xsel, wtype/xdotool, paplay/aplay (install what is missing).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from typing import Callable, List, Mapping, Optional, Sequence

KEY_DELAY_MS = 8
Which = Callable[[str], Optional[str]]


def _first(which: Which, names: Sequence[str], purpose: str) -> str:
    for name in names:
        if which(name):
            return name
    raise OSError(f"No tool found to {purpose}. Install one of: {', '.join(names)}")


def applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def clipboard_command(platform: str, env: Mapping[str, str], which: Which) -> List[str]:
    """Command that reads the text from stdin and puts it on the clipboard."""
    if platform == "darwin":
        return ["pbcopy"]
    wayland = bool(env.get("WAYLAND_DISPLAY"))
    order = ["wl-copy", "xclip", "xsel"] if wayland else ["xclip", "xsel", "wl-copy"]
    tool = _first(which, order, "copy to the clipboard")
    return {"wl-copy": ["wl-copy"], "xclip": ["xclip", "-selection", "clipboard"],
            "xsel": ["xsel", "--clipboard", "--input"]}[tool]


def type_command(platform: str, env: Mapping[str, str], which: Which, text: str) -> List[str]:
    """Command that types `text` into the focused window. Never presses Enter."""
    text = text.replace("\r", " ").replace("\n", " ")
    if platform == "darwin":
        script = f'tell application "System Events" to keystroke {applescript_string(text)}'
        return ["osascript", "-e", script]
    wayland = bool(env.get("WAYLAND_DISPLAY"))
    order = ["wtype", "xdotool"] if wayland else ["xdotool", "wtype"]
    tool = _first(which, order, "type into other windows")
    if tool == "wtype":
        return ["wtype", "-d", str(KEY_DELAY_MS), "--", text]
    return ["xdotool", "type", "--delay", str(KEY_DELAY_MS), "--", text]


def play_command(platform: str, which: Which, wav_path: str) -> List[str]:
    if platform == "darwin":
        return ["afplay", wav_path]
    tool = _first(which, ["paplay", "aplay"], "play sounds")
    return [tool, wav_path] if tool == "paplay" else ["aplay", "-q", wav_path]


# ---------------------------------------------------------------- runtime (real OS only)
def _which(name: str) -> Optional[str]:
    import shutil

    return shutil.which(name)


def copy_to_clipboard(text: str) -> None:
    import sys

    cmd = clipboard_command(sys.platform, os.environ, _which)
    subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)


def type_text(text: str) -> None:
    import sys

    subprocess.run(type_command(sys.platform, os.environ, _which, text), check=True, timeout=60)


def play_cue(name: str) -> None:
    """Soft cue from vct.tone.CUES in a thread (never blocks the caller)."""
    import sys

    from .tone import CUES, make_tone_wav

    notes = CUES.get(name)
    if not notes:
        return

    def _run() -> None:
        path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
                fh.write(make_tone_wav(notes))
                path = fh.name
            subprocess.run(play_command(sys.platform, _which, path), check=False, timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    threading.Thread(target=_run, daemon=True).start()
