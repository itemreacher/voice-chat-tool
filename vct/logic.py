"""Pure logic: keyword detection, text cleanup, translation call.

No OS-specific or heavy imports here, so this module is testable anywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Tuple

_WHITESPACE = re.compile(r"\s+")
# Separators allowed between the keyword and the rest of the sentence.
_SEPARATORS = r"[\s,.:;!?\-–—…]*"


def clean_text(text: Optional[str]) -> str:
    """Collapse all whitespace (incl. newlines) to single spaces and strip."""
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text).strip()


def detect_keyword(transcript: Optional[str], keywords: Iterable[str]) -> Tuple[bool, str]:
    """Return (keyword_found, remainder).

    The keyword must be the first word(s) of the transcript (case-insensitive,
    whole word). Punctuation/whitespace right after it is dropped.
    Without a keyword the cleaned transcript is returned as the remainder.
    """
    text = clean_text(transcript)
    if not text:
        return False, ""
    # Longest keyword first so multi-word keywords win over their prefixes.
    for kw in sorted((k.strip() for k in keywords), key=len, reverse=True):
        if not kw:
            continue
        pattern = r"^\W*" + re.escape(kw) + r"(?!\w)" + _SEPARATORS + r"(.*)$"
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return True, clean_text(match.group(1))
    return False, text


@dataclass
class Outcome:
    text: Optional[str]          # None -> nothing to output
    keyword_used: bool = False
    translated: bool = False
    warning: Optional[str] = None


TRANSLATE_MODES = ("keyword", "always", "off")


def process_transcript(
    transcript: Optional[str],
    keywords: Iterable[str],
    translate_fn: Optional[Callable[[str], str]],
    mode: str = "keyword",
) -> Outcome:
    """Turn a raw transcript into the final chat text.

    mode "keyword": translate only if the transcript starts with a keyword;
    mode "always":  translate everything (a leading keyword is still removed);
    mode "off":     never translate, output the transcript as spoken.
    """
    text = clean_text(transcript)
    if not text:
        return Outcome(None)
    if mode == "off":
        return Outcome(text)

    found, rest = detect_keyword(text, keywords)
    if mode == "keyword" and not found:
        return Outcome(text)
    if found and not rest:
        return Outcome(None, keyword_used=True, warning="Keyword without any text after it.")
    rest = rest if found else text

    if translate_fn is None:
        return Outcome(rest, found, False, "Translation unavailable; using the original text.")
    try:
        translated = clean_text(translate_fn(rest))
    except Exception as exc:  # translation must never crash the tool
        return Outcome(rest, found, False, f"Translation failed ({exc}); using the original text.")
    if not translated:
        return Outcome(rest, found, False, "Translation was empty; using the original text.")
    return Outcome(translated, found, True)
