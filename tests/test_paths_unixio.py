from pathlib import Path

import pytest

from vct import __version__
from vct.paths import CONFIG_NAME, data_dir, user_data_dir
from vct.unixio import (applescript_string, clipboard_command, play_command, type_command)

HOME = Path("/home/u")


def have(*names):
    return lambda n: f"/usr/bin/{n}" if n in names else None


def test_version_is_semver_like():
    assert len(__version__.split(".")) == 3


def test_user_data_dirs_per_platform():
    assert user_data_dir("win32", {"APPDATA": "C:/Users/u/AppData/Roaming"}, HOME) == Path("C:/Users/u/AppData/Roaming/VoiceChatTool")
    assert user_data_dir("darwin", {}, HOME) == HOME / "Library/Application Support/VoiceChatTool"
    assert user_data_dir("linux", {}, HOME) == HOME / ".config/VoiceChatTool"
    assert user_data_dir("linux", {"XDG_CONFIG_HOME": "/x"}, HOME) == Path("/x/VoiceChatTool")


def test_data_dir_dev_and_portable_use_app_dir(tmp_path):
    assert data_dir(tmp_path, False, "win32", {}, HOME) == tmp_path            # not frozen
    (tmp_path / CONFIG_NAME).write_text("x")
    assert data_dir(tmp_path, True, "win32", {"APPDATA": "/a"}, HOME) == tmp_path  # portable


def test_data_dir_installed_uses_user_folder(tmp_path):
    assert data_dir(tmp_path, True, "linux", {}, HOME) == HOME / ".config/VoiceChatTool"


def test_data_dir_env_override(tmp_path):
    assert data_dir(tmp_path, True, "win32", {"VCT_DATA_DIR": "/o"}, HOME) == Path("/o")


def test_clipboard_commands():
    assert clipboard_command("darwin", {}, have()) == ["pbcopy"]
    assert clipboard_command("linux", {}, have("xclip", "xsel")) == ["xclip", "-selection", "clipboard"]
    assert clipboard_command("linux", {"WAYLAND_DISPLAY": "w"}, have("wl-copy", "xclip")) == ["wl-copy"]
    assert clipboard_command("linux", {}, have("xsel")) == ["xsel", "--clipboard", "--input"]
    with pytest.raises(OSError, match="xclip"):
        clipboard_command("linux", {}, have())


def test_type_commands_no_newlines_never_enter():
    cmd = type_command("linux", {}, have("xdotool"), "hallo\nwelt")
    assert cmd[:2] == ["xdotool", "type"] and cmd[-1] == "hallo welt"
    assert type_command("linux", {"WAYLAND_DISPLAY": "w"}, have("wtype", "xdotool"), "x")[0] == "wtype"
    with pytest.raises(OSError):
        type_command("linux", {}, have(), "x")


def test_macos_type_escapes_quotes_and_backslashes():
    cmd = type_command("darwin", {}, have(), r'sag "hi" \ ok')
    assert cmd[:2] == ["osascript", "-e"]
    assert 'keystroke "sag \\"hi\\" \\\\ ok"' in cmd[2]
    assert applescript_string('a"b') == '"a\\"b"'


def test_play_commands():
    assert play_command("darwin", have(), "/t.wav") == ["afplay", "/t.wav"]
    assert play_command("linux", have("paplay", "aplay"), "/t.wav") == ["paplay", "/t.wav"]
    assert play_command("linux", have("aplay"), "/t.wav") == ["aplay", "-q", "/t.wav"]
