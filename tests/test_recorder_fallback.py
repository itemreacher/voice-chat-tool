import pytest

from vct.audio_devices import candidate_input_devices, resolve_input_device, unique_input_names
from vct.recorder import Recorder, RecorderError

FULL = "Analogue 1 + 2 (Focusrite USB Audio)"
CUT = FULL[:31]                       # MME cuts the name: 'Analogue 1 + 2 (Focusrite USB A'
# Device list of a real Windows PC: the same microphone under MME (default), DirectSound and WASAPI.
DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": CUT, "hostapi": 0, "max_input_channels": 4},                  # [1] MME, the system default
    {"name": "Primary Sound Capture Driver", "hostapi": 1, "max_input_channels": 2},
    {"name": FULL, "hostapi": 1, "max_input_channels": 4},                 # [3] DirectSound
    {"name": FULL, "hostapi": 2, "max_input_channels": 2},                 # [4] WASAPI
]


def test_truncated_mme_name_is_recognised_and_default_interface_comes_first():
    assert candidate_input_devices(FULL, DEVICES, default_hostapi=0) == [1, 3, 4]
    assert resolve_input_device(FULL, DEVICES, default_hostapi=0) == 1


def test_without_a_known_default_the_lowest_index_wins():
    assert candidate_input_devices(FULL, DEVICES, default_hostapi=None)[0] == 1


def test_a_different_default_interface_is_respected():
    assert candidate_input_devices(FULL, DEVICES, default_hostapi=1)[0] == 3


def test_short_names_are_not_mistaken_for_truncated_copies():
    devices = [{"name": "Mic", "hostapi": 0, "max_input_channels": 1},
               {"name": "Mic Array (Realtek)", "hostapi": 1, "max_input_channels": 1}]
    assert candidate_input_devices("Mic Array (Realtek)", devices, 0) == [1]


def test_picker_list_hides_the_truncated_duplicate():
    assert unique_input_names(DEVICES, default_hostapi=0) == [
        "Microsoft Sound Mapper - Input", "Primary Sound Capture Driver", FULL]


class FakeRecorder(Recorder):
    """Recorder whose devices and stream opening are scripted."""

    def __init__(self, device, failing=(), candidates=None):
        super().__init__(device)
        self.failing, self._cands, self.tried = set(failing), candidates, []

    def _candidates(self):
        return list(self._cands) if self._cands is not None else super()._candidates()

    def _open_stream(self, device):
        self.tried.append(device)
        if device in self.failing:
            raise OSError(f"DirectSound error on {device}")
        return object()


def test_next_interface_is_tried_when_the_first_cannot_be_opened():
    rec = FakeRecorder(FULL, failing={1}, candidates=[1, 3, 4])
    rec.start()
    assert rec.tried == [1, 3] and rec._stream is not None


def test_the_device_that_worked_is_tried_first_next_time():
    rec = FakeRecorder(FULL, failing={1}, candidates=[1, 3, 4])
    rec.start(); rec.stop()
    rec.tried.clear()
    rec._candidates = lambda: sorted([1, 3, 4], key=lambda i: i != rec._working)  # what the real method does
    rec.start()
    assert rec.tried[0] == 3


def test_all_interfaces_failing_gives_one_clear_error_with_advice():
    rec = FakeRecorder(FULL, failing={1, 3, 4}, candidates=[1, 3, 4])
    with pytest.raises(RecorderError) as err:
        rec.start()
    text = str(err.value)
    assert "[1]" in text and "[3]" in text and "[4]" in text and "exclusively" in text
    assert rec._stream is None                                           # nothing is left half-open


def test_default_device_is_a_single_candidate():
    rec = FakeRecorder(None)
    rec.start()
    assert rec.tried == [None]


def test_start_is_idempotent_while_recording():
    rec = FakeRecorder(None)
    rec.start(); rec.start()
    assert rec.tried == [None]
