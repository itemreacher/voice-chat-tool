"""Text correction before translation: user replacement list + conservative spell check.

Pure logic; the spell-check dictionary is injected (see SpellBackend) so tests need no
third-party package. `PySpellBackend` is the real one (pyspellchecker, MIT, offline).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Protocol, Tuple

_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
MIN_WORD_LENGTH = 4          # short words are too ambiguous to "fix"
DOMINANCE = 3.0              # best candidate must be this many times more common than the next


@dataclass
class Correction:
    text: str
    changes: List[Tuple[str, str]] = field(default_factory=list)  # (before, after)


def parse_replacements(lines: Iterable[str]) -> List[Tuple[str, str]]:
    """'wrong = right' or 'wrong -> right' lines -> [(wrong, right)]. Bad lines are skipped."""
    pairs: List[Tuple[str, str]] = []
    for line in lines:
        for sep in ("->", "→", "="):
            if sep in line:
                wrong, right = (part.strip() for part in line.split(sep, 1))
                if wrong:
                    pairs.append((wrong, right))
                break
    return pairs


def apply_replacements(text: str, pairs: Iterable[Tuple[str, str]]) -> Correction:
    """Whole-word, case-insensitive replacements; longer phrases first."""
    changes: List[Tuple[str, str]] = []
    for wrong, right in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        pattern = re.compile(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)", re.IGNORECASE)

        def sub(match: "re.Match[str]") -> str:
            if match.group(0) != right:
                changes.append((match.group(0), right))
            return right

        text = pattern.sub(sub, text)
    return Correction(text, changes)


class SpellBackend(Protocol):
    def is_known(self, word: str) -> bool: ...
    def best_fix(self, word: str) -> Optional[str]:
        """Unambiguous correction within edit distance 1, or None."""


class PySpellBackend:
    """pyspellchecker wrapper. `supported(language)` tells whether a dictionary exists."""

    def __init__(self, language: str):
        from spellchecker import SpellChecker

        self._spell = SpellChecker(language=language, distance=1)  # ValueError if unsupported

    @staticmethod
    def supported(language: str) -> bool:
        try:
            from spellchecker import SpellChecker

            SpellChecker(language=language)
            return True
        except Exception:
            return False

    def is_known(self, word: str) -> bool:
        return word.lower() in self._spell

    def best_fix(self, word: str) -> Optional[str]:
        candidates = self._spell.candidates(word.lower()) or set()
        ranked = sorted(candidates, key=self._spell.word_usage_frequency, reverse=True)
        if not ranked:
            return None
        if len(ranked) > 1:
            first, second = (self._spell.word_usage_frequency(w) for w in ranked[:2])
            if first < DOMINANCE * second:
                return None  # too ambiguous: leave the word alone
        return ranked[0]


def _match_case(original: str, fixed: str) -> str:
    return fixed[:1].upper() + fixed[1:] if original[:1].isupper() else fixed


def spell_fix(text: str, backend: SpellBackend, protected: Iterable[str] = ()) -> Correction:
    """Fix unknown words that have one clear nearby dictionary word. Names, acronyms,
    words with digits, short words and anything in `protected` are never touched."""
    skip = {p.lower() for p in protected}
    changes: List[Tuple[str, str]] = []

    def sub(match: "re.Match[str]") -> str:
        word = match.group(0)
        if (len(word) < MIN_WORD_LENGTH or word.isupper() or word.lower() in skip
                or backend.is_known(word)):
            return word
        fixed = backend.best_fix(word)
        if not fixed or fixed.lower() == word.lower():
            return word
        fixed = _match_case(word, fixed)
        changes.append((word, fixed))
        return fixed

    return Correction(_WORD.sub(sub, text), changes)


def correct_text(text: str, replacements: Iterable[Tuple[str, str]],
                 backend: Optional[SpellBackend], protected: Iterable[str] = ()) -> Correction:
    """Replacement list first (your rules win), then the spell check."""
    first = apply_replacements(text, replacements)
    if backend is None:
        return first
    # Words you typed into replacements/vocabulary must survive the spell check.
    second = spell_fix(first.text, backend, protected)
    return Correction(second.text, first.changes + second.changes)
