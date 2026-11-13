import pytest

from vct.config import ConfigError, model_for_device, next_device, parse_config, wants_gpu


def test_device_defaults():
    cfg = parse_config({})
    assert cfg["device"] == "auto"
    assert cfg["device_toggle_hotkey"] == "f10"
    assert cfg["whisper_model_gpu"] == ""


def test_device_cuda_alias_and_case():
    assert parse_config({"device": "CUDA"})["device"] == "gpu"
    assert parse_config({"device": " CPU "})["device"] == "cpu"


def test_invalid_device_rejected():
    with pytest.raises(ConfigError):
        parse_config({"device": "tpu"})


def test_toggle_hotkey_rules():
    assert parse_config({"device_toggle_hotkey": ""})["device_toggle_hotkey"] == ""
    with pytest.raises(ConfigError):
        parse_config({"device_toggle_hotkey": "ctrl+f10"})
    with pytest.raises(ConfigError):
        parse_config({"device_toggle_hotkey": "f9"})  # same as push-to-talk


def test_model_for_device_uses_gpu_model_only_on_cuda():
    cfg = parse_config({"whisper_model": "small", "whisper_model_gpu": "medium"})
    assert model_for_device(cfg, "cpu") == "small"
    assert model_for_device(cfg, "cuda") == "medium"


def test_model_for_device_falls_back_to_cpu_model():
    cfg = parse_config({"whisper_model": "base"})
    assert model_for_device(cfg, "cuda") == "base"


@pytest.mark.parametrize("pref,cuda,expected", [
    ("auto", True, True), ("auto", False, False),
    ("gpu", False, True), ("gpu", True, True),
    ("cpu", True, False), ("cpu", False, False),
])
def test_wants_gpu(pref, cuda, expected):
    assert wants_gpu(pref, cuda) is expected


def test_next_device_toggles():
    assert next_device("cuda") == "cpu"
    assert next_device("cpu") == "cuda"
    assert next_device(None) == "cuda"
