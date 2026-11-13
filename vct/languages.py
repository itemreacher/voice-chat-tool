"""Language names and pure helpers (no heavy imports)."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Whisper understands all of these; Argos offers packs for most of them.
# Unknown codes still work, they just show their code as the name.
LANGUAGES: Dict[str, str] = {
    "de": "Deutsch", "en": "Englisch", "ru": "Russisch", "fr": "Französisch",
    "es": "Spanisch", "it": "Italienisch", "pt": "Portugiesisch", "pl": "Polnisch",
    "tr": "Türkisch", "uk": "Ukrainisch", "nl": "Niederländisch", "cs": "Tschechisch",
    "sv": "Schwedisch", "da": "Dänisch", "fi": "Finnisch", "el": "Griechisch",
    "hu": "Ungarisch", "ro": "Rumänisch", "bg": "Bulgarisch", "ar": "Arabisch",
    "he": "Hebräisch", "hi": "Hindi", "ja": "Japanisch", "ko": "Koreanisch",
    "zh": "Chinesisch", "id": "Indonesisch", "vi": "Vietnamesisch",
}
PIVOT = "en"  # Argos chains X -> en -> Y, so packs to/from English cover every pair
_CODE = re.compile(r"^[a-z]{2,3}$")


def is_valid_code(code: object) -> bool:
    return isinstance(code, str) and bool(_CODE.match(code))


def language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def label(code: str) -> str:
    """'Deutsch (de)' for display in drop-downs."""
    return f"{language_name(code)} ({code})"


def code_from_label(text: str) -> str:
    """Inverse of label(); also accepts a bare code."""
    text = text.strip()
    match = re.search(r"\(([a-z]{2,3})\)\s*$", text)
    return match.group(1) if match else text.lower()


def needs_translation(source: str, target: str) -> bool:
    return source != target


def required_pairs(source: str, target: str) -> List[Tuple[str, str]]:
    """Argos packs needed for source -> target: direct pair, or both hops via English."""
    if source == target:
        return []
    if PIVOT in (source, target):
        return [(source, target)]
    return [(source, PIVOT), (PIVOT, target)]
