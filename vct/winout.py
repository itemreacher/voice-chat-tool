"""Windows-only output: SendInput Unicode typing, clipboard, soft cues (ctypes/winsound)."""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEY_DELAY_S = 0.008  # pause after each key-down and key-up event

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member; it must be present for the right struct size.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _utf16_units(text: str):
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def type_text(text: str) -> None:
    """Type text into the focused window as Unicode key events. Never presses Enter."""
    text = text.replace("\r", " ").replace("\n", " ")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    # One character per SendInput call, with a short pause after the key-down and
    # after the key-up. Sending big batches made Notepad (Win 11) repeat or drop
    # characters because it could not keep up with the key-state changes.
    for unit in _utf16_units(text):
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            ev = INPUT()
            ev.type = INPUT_KEYBOARD
            ev.ki.wVk = 0
            ev.ki.wScan = unit
            ev.ki.dwFlags = flags
            sent = user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(INPUT))
            if sent != 1:
                raise OSError("SendInput was blocked (another process, UIPI or anti-cheat?)")
            time.sleep(KEY_DELAY_S)


def copy_to_clipboard(text: str) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)

    for _ in range(10):  # another process may hold the clipboard briefly
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("Could not open the clipboard")
    try:
        user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("GlobalAlloc failed")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            raise OSError("GlobalLock failed")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")
        # On success the system owns the handle; do not free it.
    finally:
        user32.CloseClipboard()


def play_cue(name: str) -> None:
    """Play a soft cue from vct.tone.CUES in its own thread (never blocks the caller)."""
    from .tone import CUES, make_tone_wav

    notes = CUES.get(name)
    if not notes:
        return

    def _run() -> None:
        try:
            import winsound

            # SND_MEMORY cannot be combined with SND_ASYNC, so play synchronously here.
            winsound.PlaySound(make_tone_wav(notes), winsound.SND_MEMORY)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
