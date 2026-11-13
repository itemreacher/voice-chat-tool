import io
import wave

import pytest

from vct.config import ConfigError, parse_config
from vct.tone import CUES, VOLUME, make_tone_wav


def _read(data):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes())


def test_wav_format_and_length():
    ch, width, rate, frames = _read(make_tone_wav([(523, 100)]))
    assert (ch, width) == (1, 2)
    assert len(frames) // 2 == int(rate * 0.1)


def test_notes_are_concatenated():
    one = _read(make_tone_wav([(523, 70)]))[3]
    two = _read(make_tone_wav([(523, 70), (659, 90)]))[3]
    assert len(two) > len(one)


def test_tone_is_quiet_and_fades_in_and_out():
    _, _, _, frames = _read(make_tone_wav([(523, 100)]))
    import struct

    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    assert max(abs(x) for x in samples) <= 32767 * VOLUME + 1   # quiet
    assert abs(samples[0]) < 50 and abs(samples[-1]) < 50        # no click at start/end


def test_all_cues_render():
    assert set(CUES) == {"translate", "gpu", "cpu"}
    for notes in CUES.values():
        assert len(make_tone_wav(notes)) > 44


def test_translate_hotkey_default_and_disable():
    assert parse_config({})["translate_hotkey"] == "f8"
    assert parse_config({"translate_hotkey": ""})["translate_hotkey"] == ""


@pytest.mark.parametrize("bad", [
    {"translate_hotkey": "f9"},                       # same as push-to-talk
    {"translate_hotkey": "f10"},                      # same as device toggle
    {"translate_hotkey": "ctrl+t"},                   # combinations unsupported
    {"hotkey": "f10"},                                # collides with device toggle
])
def test_hotkey_conflicts_rejected(bad):
    with pytest.raises(ConfigError):
        parse_config(bad)


def test_disabled_keys_may_both_be_empty():
    cfg = parse_config({"translate_hotkey": "", "device_toggle_hotkey": ""})
    assert cfg["translate_hotkey"] == cfg["device_toggle_hotkey"] == ""
