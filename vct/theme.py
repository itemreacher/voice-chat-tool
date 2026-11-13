"""Visual theme: a blend of three game worlds.

* Valorant : deep blue-grey ground, coral red signal colour, sharp cut corners
* The Witcher: cold steel and off-white text, serif headings, medallion-like details
* World of Warcraft: warm gold frames and accents

Colours and contrast maths are pure (testable); apply() needs a Tk root.
"""
from __future__ import annotations

from typing import Tuple

# ---- palette --------------------------------------------------------------
BG = "#0F1923"          # window ground (Valorant navy)
PANEL = "#17232F"       # inputs, log, cards
PANEL_HI = "#213242"    # hover / raised
BORDER = "#2E4256"
TEXT = "#ECE8E1"        # warm off-white
MUTED = "#93A1B0"       # steel grey
GOLD = "#C8A15A"        # WoW gold
GOLD_HI = "#E8C985"
RED = "#FF4655"         # Valorant red
RED_HI = "#FF6B78"
TEAL = "#4FD1B5"        # "ready" signal

STATE_COLORS = {
    "stopped": MUTED,
    "loading": GOLD,
    "ready": TEAL,
    "recording": RED,
    "processing": GOLD_HI,
}

FONT_BODY = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_HEAD = ("Georgia", 11, "bold")       # serif: Witcher / WoW flavour
FONT_TITLE = ("Georgia", 20, "bold")
FONT_MONO = ("Consolas", 10)


# ---- contrast (WCAG) ------------------------------------------------------
def _rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def luminance(color: str) -> float:
    def channel(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---- Tk -------------------------------------------------------------------
def style_text(widget) -> None:
    """Dark look for plain tk.Text widgets (ttk styles do not reach them)."""
    widget.configure(bg=PANEL, fg=TEXT, insertbackground=GOLD_HI, selectbackground=GOLD,
                     selectforeground=BG, relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=GOLD, font=FONT_MONO,
                     padx=8, pady=6)


def apply(root) -> None:
    from tkinter import ttk

    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    # drop-down lists of comboboxes are plain tk widgets
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", BG)
    root.option_add("*TCombobox*Listbox.font", FONT_BODY)

    style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=PANEL, focuscolor=GOLD,
                    font=FONT_BODY)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Result.TLabel", foreground=GOLD_HI, font=FONT_BOLD)
    style.configure("Key.TLabel", foreground=GOLD, font=FONT_BOLD)

    style.configure("TLabelframe", background=BG, bordercolor=GOLD, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=GOLD, font=FONT_HEAD)

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
    style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(20, 9),
                    font=FONT_BOLD, borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", PANEL_HI), ("active", PANEL_HI)],
              foreground=[("selected", GOLD_HI), ("active", TEXT)],
              expand=[("selected", (0, 0, 0, 2))])

    style.configure("TButton", background=PANEL_HI, foreground=TEXT, bordercolor=GOLD,
                    padding=(14, 7), font=FONT_BOLD, relief="flat")
    style.map("TButton", background=[("active", GOLD), ("disabled", PANEL)],
              foreground=[("active", BG), ("disabled", MUTED)])
    style.configure("Accent.TButton", background=RED, foreground=BG, bordercolor=RED)
    style.map("Accent.TButton", background=[("active", RED_HI), ("disabled", PANEL)],
              foreground=[("active", BG), ("disabled", MUTED)])

    for name in ("TRadiobutton", "TCheckbutton"):
        style.configure(name, background=BG, foreground=TEXT, indicatorcolor=PANEL,
                        indicatorbackground=PANEL, indicatorforeground=GOLD_HI)
        style.map(name, background=[("active", BG)], foreground=[("active", GOLD_HI)],
                  indicatorcolor=[("selected", GOLD)])

    for name in ("TEntry", "TCombobox"):
        style.configure(name, fieldbackground=PANEL, foreground=TEXT, insertcolor=GOLD_HI,
                        bordercolor=BORDER, padding=5)
        style.map(name, bordercolor=[("focus", GOLD)], fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)])
    style.configure("TCombobox", arrowcolor=GOLD, background=PANEL_HI)

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=27, bordercolor=BORDER, borderwidth=0)
    style.map("Treeview", background=[("selected", GOLD)], foreground=[("selected", BG)])
    style.configure("Treeview.Heading", background=PANEL_HI, foreground=GOLD, font=FONT_HEAD,
                    relief="flat", padding=6)
    style.map("Treeview.Heading", background=[("active", PANEL_HI)])

    style.configure("Vertical.TScrollbar", background=PANEL_HI, troughcolor=PANEL,
                    bordercolor=PANEL, arrowcolor=GOLD)
