import pytest

from vct.audio_devices import resolve_input_device, unique_input_names
from vct.config import parse_config, repair_mojibake

NAME = "Analogue 1 + 2 (Focusrite USB Audio)"
# The situation from a real log: one microphone listed under several Windows audio interfaces.
DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": NAME, "hostapi": 0, "max_input_channels": 2},           # MME (name is cut short in MME, kept for the test)
    {"name": "Speakers (Focusrite)", "hostapi": 1, "max_input_channels": 0},   # output only
    {"name": NAME, "hostapi": 1, "max_input_channels": 2},           # DirectSound
    {"name": NAME, "hostapi": 2, "max_input_channels": 2},           # WASAPI
]


def test_ambiguous_name_resolves_to_one_device_on_the_default_interface():
    assert resolve_input_device(NAME, DEVICES, default_hostapi=2) == 4
    assert resolve_input_device(NAME, DEVICES, default_hostapi=1) == 3
    assert resolve_input_device(NAME, DEVICES, default_hostapi=None) == 1   # lowest index


def test_partial_name_and_case_are_accepted():
    assert resolve_input_device("focusrite usb", DEVICES, default_hostapi=2) == 4


def test_exact_match_beats_partial_match():
    devices = [{"name": "Headset Mic Pro", "hostapi": 0, "max_input_channels": 1},
               {"name": "Headset", "hostapi": 1, "max_input_channels": 1}]
    assert resolve_input_device("Headset", devices, default_hostapi=0) == 1


def test_unknown_name_and_output_only_devices_do_not_match():
    assert resolve_input_device("Nonexistent", DEVICES) is None
    assert resolve_input_device("Speakers", DEVICES) is None          # no input channels


def test_unique_names_lists_each_microphone_once():
    assert unique_input_names(DEVICES, default_hostapi=2) == [NAME, "Microsoft Sound Mapper - Input"]


@pytest.mark.parametrize("broken,fixed", [
    ("Ã¼bersetze", "übersetze"), ("StÃ¶rung", "Störung"), ("Ãœbung", "Übung"),
    ("übersetze", "übersetze"), ("translate", "translate"), ("São Paulo", "São Paulo"), ("Ã", "Ã"),
])
def test_repair_mojibake(broken, fixed):
    assert repair_mojibake(broken) == fixed


def test_config_repairs_keywords_and_vocabulary():
    cfg = parse_config({"keywords": ["translate", "Ã¼bersetze"], "vocabulary": ["GrÃ¼n"],
                        "microphone_device": "MikrofÃ¶n"})
    assert cfg["keywords"] == ["translate", "übersetze"]
    assert cfg["vocabulary"] == ["Grün"] and cfg["microphone_device"] == "Mikrofön"
