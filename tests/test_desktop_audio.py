import threading
import time

import numpy as np
import pytest

from test_segmenter_transcript import quiet, speech  # synthetic signals
from vct.desktop_audio import CaptureError, DesktopSession, MonoResampler, level_percent
from vct.segmenter import SAMPLE_RATE as SR
from vct.transcript import Spoken


# ---------------------------------------------------------------- conversion
def tone(freq, seconds, rate, channels=2, amp=0.5):
    t = np.arange(int(seconds * rate)) / rate
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1).astype(np.float32)


def dominant_frequency(x):
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spectrum) * SR / len(x)


@pytest.mark.parametrize("rate", [16000, 32000, 44100, 48000, 96000])
def test_fallback_resampler_keeps_length_and_pitch(rate):
    r = MonoResampler(rate, 2, use_av=False)
    data = tone(440, 3.0, rate)
    out = np.concatenate([r.process(data[i:i + 1000].tobytes()) for i in range(0, len(data), 1000)])
    assert abs(len(out) - 3 * SR) < 400
    assert dominant_frequency(out[SR // 2: SR // 2 + 16000]) == pytest.approx(440, abs=5)


def test_pyav_resampler_matches_when_available():
    pytest.importorskip("av")
    r = MonoResampler(44100, 2, use_av=True)
    data = tone(440, 3.0, 44100)
    out = np.concatenate([r.process(data[i:i + 2205].tobytes()) for i in range(0, len(data), 2205)])
    assert abs(len(out) - 3 * SR) < 800
    assert dominant_frequency(out[SR: SR * 2]) == pytest.approx(440, abs=5)


def test_resampler_downmixes_channels_and_ignores_partial_frames():
    r = MonoResampler(16000, 2)
    left_right = np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32)
    out = r.process(left_right.tobytes() + b"\x00\x00")      # trailing half sample is ignored
    assert out.tolist() == [0.0, 0.5]
    assert r.process(b"").size == 0


def test_level_meter_scale():
    assert level_percent(0) == 0 and level_percent(1.0) == 100
    assert level_percent(0.001) == 0                          # -60 dB is empty
    assert 40 < level_percent(0.03) < 60


# ---------------------------------------------------------------- session with fakes
class FakeCapture:
    def __init__(self, audio, fail=False):
        self.audio, self.fail, self.name, self.stopped = audio, fail, "Fake speakers", False

    def start(self, on_audio):
        if self.fail:
            raise CaptureError("no loopback device")

        def feed():
            for i in range(0, len(self.audio), 1600):
                on_audio(self.audio[i:i + 1600])
        threading.Thread(target=feed, daemon=True).start()

    def stop(self):
        self.stopped = True


class FakeTranscriber:
    """Returns one phrase per chunk and records which language it was asked for."""

    def __init__(self, texts, language="de"):
        self.texts, self.language, self.calls = list(texts), language, []

    def transcribe_segments(self, audio, language=None):
        self.calls.append((len(audio) / SR, language))
        text = self.texts.pop(0) if self.texts else "..."
        return [Spoken(0.2, len(audio) / SR - 0.1, text, 0.0, -0.2)], language or self.language


class FakeTranslation:
    def __init__(self, ready=True):
        self.is_ready, self.asked = ready, []

    def ready(self, src, tgt):
        self.asked.append((src, tgt))
        return self.is_ready

    def translate(self, text, src, tgt):
        return f"<{tgt}:{text}>"


SIGNAL = np.concatenate([quiet(0.5), speech(2.0), quiet(1.2), speech(1.5), quiet(1.2)])


def run_session(transcriber, translate_to="", translation=None, language=None, signal=None):
    signal = SIGNAL if signal is None else signal
    logs, lines, states = [], [], []
    session = DesktopSession(transcriber, FakeCapture(signal), logs.append, language, translate_to, translation,
                             on_line=lines.append, on_state=states.append)
    session.start()
    deadline = time.time() + 10
    while session.samples < len(signal) and time.time() < deadline:
        time.sleep(0.02)
    session.stop()
    return session, logs, lines, states


def test_two_phrases_become_two_timed_lines_in_order():
    session, logs, lines, states = run_session(FakeTranscriber(["Erster Satz.", "Zweiter Satz."]))
    assert [line.text for line in lines] == ["Erster Satz.", "Zweiter Satz."]
    assert lines[0].start < lines[1].start and lines[1].start == pytest.approx(3.8, abs=0.5)
    assert states[0] == "starting" and "listening" in states and states[-1] == "stopped"
    assert session.capture.stopped and any("Fake speakers" in m for m in logs)
    assert session.elapsed == pytest.approx(len(SIGNAL) / SR, abs=0.2)


def test_auto_language_is_passed_as_none_and_detected_language_is_kept():
    t = FakeTranscriber(["Hello there.", "Next."], language="en")
    _, _, lines, _ = run_session(t, language=None)
    assert all(lang is None for _, lang in t.calls) and {line.language for line in lines} == {"en"}


def test_fixed_language_is_forwarded():
    t = FakeTranscriber(["Hallo.", "Welt."])
    run_session(t, language="de")
    assert all(lang == "de" for _, lang in t.calls)


def test_translation_is_added_once_the_pair_is_ready():
    tr = FakeTranslation()
    _, _, lines, _ = run_session(FakeTranscriber(["Hallo.", "Welt."], "de"), translate_to="en", translation=tr)
    assert [line.translation for line in lines] == ["<en:Hallo.>", "<en:Welt.>"]
    assert tr.asked == [("de", "en")]                       # the pair is prepared only once


def test_missing_language_packs_leave_the_text_untranslated_and_say_so():
    _, logs, lines, _ = run_session(FakeTranscriber(["Hallo.", "Welt."], "de"), "en", FakeTranslation(ready=False))
    assert [line.translation for line in lines] == ["", ""]
    assert any("language packs missing" in m for m in logs)


def test_no_translation_when_source_equals_target():
    tr = FakeTranslation()
    _, _, lines, _ = run_session(FakeTranscriber(["Hello.", "World."], "en"), "en", tr)
    assert tr.asked == [] and all(line.translation == "" for line in lines)


def test_echo_repeats_and_doubtful_segments_are_dropped():
    class Echo(FakeTranscriber):
        def transcribe_segments(self, audio, language=None):      # the phrase fills the chunk, like real output
            return [Spoken(0.2, len(audio) / SR - 0.1, "Danke fürs Zuschauen.", 0.0, -0.2)], "de"
    near = np.concatenate([quiet(0.5), speech(2.0), quiet(0.9), speech(1.5), quiet(1.2)])    # phrases 0.7 s apart
    _, _, lines, _ = run_session(Echo([]), signal=near)
    assert len(lines) == 1                                   # the identical phrase right after is an echo
    far = np.concatenate([quiet(0.5), speech(2.0), quiet(3.5), speech(1.5), quiet(1.2)])     # 3 s apart
    _, _, lines, _ = run_session(Echo([]), signal=far)
    assert len(lines) == 2                                   # the same words much later are kept

    class Doubtful(FakeTranscriber):
        def transcribe_segments(self, audio, language=None):
            return [Spoken(0.1, 1.0, "Untertitel von Fremden", 0.9, -1.5)], "de"
    _, _, lines, _ = run_session(Doubtful([]))
    assert lines == []                                       # probably no speech and unsure: dropped


def test_capture_error_is_reported_and_state_is_error():
    logs, states = [], []
    session = DesktopSession(FakeTranscriber([]), FakeCapture(SIGNAL, fail=True), logs.append,
                             on_state=states.append)
    with pytest.raises(CaptureError):
        session.start()
    assert states[-1] == "error" and any("no loopback device" in m for m in logs)


def test_a_failing_chunk_does_not_end_the_session():
    class Flaky(FakeTranscriber):
        def transcribe_segments(self, audio, language=None):
            if not self.calls:
                self.calls.append(1)
                raise RuntimeError("model hiccup")
            return super().transcribe_segments(audio, language)
    _, logs, lines, _ = run_session(Flaky(["Zweiter Satz."]))
    assert [line.text for line in lines] == ["Zweiter Satz."] and any("model hiccup" in m for m in logs)


def test_stop_twice_is_harmless():
    session, *_ = run_session(FakeTranscriber(["a", "b"]))
    session.stop()
    assert session.state == "stopped"
