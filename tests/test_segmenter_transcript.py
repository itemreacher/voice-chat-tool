import numpy as np
import pytest

from vct.segmenter import SAMPLE_RATE as SR, Segmenter
from vct.transcript import Line, drop_repeats, format_timestamp, to_srt, to_text

RNG = np.random.default_rng(0)


def speech(seconds, amp=0.25):
    """Speech-like signal: harmonics with a syllable rhythm (about 4 per second, dips between them)."""
    t = np.arange(int(seconds * SR)) / SR
    wobble = 0.15 + 0.85 * np.sin(np.pi * 4 * t) ** 2
    return (amp * wobble * (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 540 * t))).astype(np.float32)


def quiet(seconds, level=0.0005):
    return (level * RNG.standard_normal(int(seconds * SR))).astype(np.float32)


def run(signal, piece=None):
    seg, chunks = Segmenter(), []
    if piece:
        for i in range(0, len(signal), piece):
            chunks += seg.feed(signal[i:i + piece])
    else:
        chunks += seg.feed(signal)
    return chunks + seg.flush()


# ---------------------------------------------------------------- segmenter
def test_two_phrases_with_pauses_become_two_chunks():
    sig = np.concatenate([quiet(1.0), speech(2.0), quiet(1.2), speech(1.5), quiet(1.2)])
    chunks = run(sig)
    assert len(chunks) == 2
    assert chunks[0].start == pytest.approx(0.75, abs=0.05)            # 1.0 s minus the 0.25 s lead-in
    assert chunks[0].duration == pytest.approx(2.55, abs=0.1)
    assert chunks[1].start == pytest.approx(4.0, abs=0.1)


def test_result_does_not_depend_on_how_the_audio_arrives():
    sig = np.concatenate([quiet(0.5), speech(1.5), quiet(1.0), speech(1.0), quiet(1.0)])
    a, b = run(sig), run(sig, piece=777)
    assert [(round(c.start, 3), len(c.audio)) for c in a] == [(round(c.start, 3), len(c.audio)) for c in b]


def test_short_blips_are_ignored():
    sig = np.concatenate([quiet(1.0), speech(0.15), quiet(2.0)])
    assert run(sig) == []


def test_a_final_phrase_without_trailing_silence_is_flushed():
    chunks = run(np.concatenate([quiet(0.5), speech(2.0)]))
    assert len(chunks) == 1 and chunks[0].duration > 2.0


def test_endless_speech_is_cut_into_pieces_without_gaps_or_losses():
    sig = np.concatenate([quiet(0.5), speech(70.0)])
    chunks = run(sig)
    assert len(chunks) >= 3 and all(c.duration <= 26.0 for c in chunks)
    for left, right in zip(chunks, chunks[1:]):
        assert left.start + left.duration == pytest.approx(right.start, abs=1e-6)   # nothing lost or doubled
    assert sum(len(c.audio) for c in chunks) >= 69.5 * SR


def test_forced_cut_lands_on_the_quietest_moment():
    sig = np.concatenate([speech(22.0), quiet(0.2, level=0.0008), speech(10.0)])   # a short dip, below end-of-phrase
    first = run(sig)[0]
    assert first.start + first.duration == pytest.approx(22.1, abs=0.4)


def test_constant_background_noise_is_not_speech():
    noise = (0.01 * RNG.standard_normal(8 * SR)).astype(np.float32)
    sig = np.concatenate([noise, noise[:2 * SR] + speech(2.0), noise])
    chunks = run(sig)
    assert len(chunks) == 1 and 7.0 < chunks[0].start < 8.5


def test_empty_and_silent_input_give_nothing():
    assert run(np.zeros(0, dtype=np.float32)) == []
    assert run(quiet(5.0)) == []


# ---------------------------------------------------------------- transcript
def test_timestamps():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(83.456) == "00:01:23"
    assert format_timestamp(3725.5, srt=True) == "01:02:05,500"
    assert format_timestamp(-4) == "00:00:00"
    assert format_timestamp(59.9996, srt=True) == "00:01:00,000"          # rounding carries over


LINES = [Line(0.0, 2.4, "Hallo zusammen.", "Hello everyone."), Line(3.1, 3.2, "Heute geht es um Whisper.", "")]


def test_plain_text_variants():
    assert to_text(LINES) == "Hallo zusammen.\nHeute geht es um Whisper."
    assert to_text(LINES, timestamps=True).splitlines()[1] == "[00:00:03] Heute geht es um Whisper."
    assert to_text(LINES, translated=True) == "Hello everyone.\nHeute geht es um Whisper."   # untranslated lines stay


def test_srt_is_numbered_and_every_block_has_a_visible_length():
    srt = to_srt(LINES)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,400\nHallo zusammen.\n\n2\n")
    assert "00:00:03,100 --> 00:00:03,600" in srt                       # 0.1 s block stretched to 0.5 s
    assert to_srt([]) == ""


def test_repeated_echo_phrases_are_dropped():
    lines = [Line(0, 2, "Danke fürs Zuschauen.")]
    assert drop_repeats(lines, Line(2.5, 4, "  danke fürs zuschauen. "))
    assert not drop_repeats(lines, Line(30, 32, "Danke fürs Zuschauen."))     # same words much later: keep
    assert not drop_repeats([], Line(0, 1, "x"))
