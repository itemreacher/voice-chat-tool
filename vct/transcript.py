"""A transcript of desktop audio and its export formats (pure, testable anywhere)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class Line:
    start: float                 # seconds from the start of the capture
    end: float
    text: str
    translation: str = ""        # filled when translation is switched on
    language: str = ""           # language Whisper recognised (or was told)


@dataclass(frozen=True)
class Spoken:
    """One phrase as Whisper reports it, relative to the start of the audio it was given."""
    start: float
    end: float
    text: str
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0


def format_timestamp(seconds: float, srt: bool = False) -> str:
    """'00:01:23' for display, '00:01:23,456' for SRT subtitles."""
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    base = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{base},{ms:03d}" if srt else base


def to_text(lines: Iterable[Line], timestamps: bool = False, translated: bool = False) -> str:
    """Plain text, one line per recognised phrase. With translated=True the translation is used if present."""
    out: List[str] = []
    for line in lines:
        text = line.translation if (translated and line.translation) else line.text
        out.append(f"[{format_timestamp(line.start)}] {text}" if timestamps else text)
    return "\n".join(out)


def to_srt(lines: Iterable[Line], translated: bool = False) -> str:
    """SubRip subtitles (numbered blocks with times) that video players can load."""
    blocks: List[str] = []
    for number, line in enumerate(lines, start=1):
        text = line.translation if (translated and line.translation) else line.text
        end = max(line.end, line.start + 0.5)       # a block needs a visible length
        blocks.append(f"{number}\n{format_timestamp(line.start, srt=True)} --> "
                      f"{format_timestamp(end, srt=True)}\n{text}\n")
    return "\n".join(blocks)


def drop_repeats(lines: List[Line], new: Line) -> bool:
    """Whisper sometimes repeats the previous phrase on near-silent stretches; True if `new` is such an echo."""
    return bool(lines) and new.text.strip().lower() == lines[-1].text.strip().lower() and \
        new.start - lines[-1].end < 2.0
