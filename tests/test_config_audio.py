import pytest

from vct.config import ConfigError, DEFAULTS, device_from_config, parse_config


def test_defaults():
    cfg = parse_config({})
    assert cfg["hotkey"] == "f9" and cfg["output_mode"] == "type"
    assert cfg["whisper_model"] == "small"
    assert set(cfg["keywords"]) == set(DEFAULTS["keywords"])


def test_invalid_output_mode():
    with pytest.raises(ConfigError):
        parse_config({"output_mode": "shout"})


def test_hotkey_combo_rejected():
    with pytest.raises(ConfigError):
        parse_config({"hotkey": "ctrl+f9"})


def test_device_mapping():
    assert device_from_config("") is None
    assert device_from_config("3") == 3
    assert device_from_config("Headset") == "Headset"


def test_audio_checks():
    np = pytest.importorskip("numpy")
    from vct.audio_check import SAMPLE_RATE, check_audio

    assert check_audio(np.zeros(0, dtype=np.float32)) is not None            # empty
    assert "shorter" in check_audio(np.full(int(SAMPLE_RATE * 0.2), 0.1, dtype=np.float32))
    assert "silent" in check_audio(np.zeros(SAMPLE_RATE, dtype=np.float32))
    t = np.linspace(0, 1, SAMPLE_RATE, dtype=np.float32)
    assert check_audio(0.2 * np.sin(2 * np.pi * 220 * t)) is None            # usable


def test_load_config_accepts_utf8_bom(tmp_path):
    from vct.config import load_config

    p = tmp_path / "config.toml"
    p.write_bytes(b"\xef\xbb\xbf" + 'hotkey = "f7"\n'.encode("utf-8"))
    assert load_config(p)["hotkey"] == "f7"
