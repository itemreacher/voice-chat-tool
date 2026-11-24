from pathlib import Path

import pytest

from vct import cleanup, updater
from vct.cleanup import CUDA_DIRNAME, UPDATE_DIRNAME, clean_temp_downloads, clear_directory, remove_file


def make(path: Path, size: int = 1000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_clear_directory_removes_files_and_subfolders_and_reports_the_size(tmp_path):
    make(tmp_path / "a.exe", 2000)
    make(tmp_path / "sub" / "b.whl", 3000)
    assert clear_directory(tmp_path) == 5000
    assert list(tmp_path.iterdir()) == []
    assert tmp_path.exists()                                   # the folder itself stays unless asked


def test_clear_directory_can_remove_itself_and_tolerates_a_missing_folder(tmp_path):
    make(tmp_path / "d" / "x", 10)
    assert clear_directory(tmp_path / "d", remove_self=True) == 10
    assert not (tmp_path / "d").exists()
    assert clear_directory(tmp_path / "does-not-exist") == 0


def test_a_file_in_use_is_skipped_not_an_error(tmp_path, monkeypatch):
    keep, gone = make(tmp_path / "running-setup.exe"), make(tmp_path / "old.exe")
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.name == "running-setup.exe":
            raise PermissionError("in use")                    # what Windows says for a running program
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)
    assert clear_directory(tmp_path) == 1000
    assert keep.exists() and not gone.exists()


def test_clean_temp_downloads_only_touches_the_two_program_folders(tmp_path):
    make(tmp_path / UPDATE_DIRNAME / "VoiceChatTool-Setup-1.0.5-CPU.exe", 4000)
    make(tmp_path / CUDA_DIRNAME / "nvidia_cublas.whl", 6000)
    other = make(tmp_path / "someone-elses-folder" / "keep.txt")
    messages = []
    assert clean_temp_downloads(tmp_path, messages.append) == 10000
    assert not (tmp_path / UPDATE_DIRNAME).exists() and not (tmp_path / CUDA_DIRNAME).exists()
    assert other.exists()
    assert "Cleaned up" in messages[0]
    assert clean_temp_downloads(tmp_path, messages.append) == 0 and len(messages) == 1   # nothing to say twice


def test_remove_file_deletes_the_download_and_its_empty_folder(tmp_path):
    f = make(tmp_path / UPDATE_DIRNAME / "setup.exe")
    remove_file(f)
    assert not f.exists() and not (tmp_path / UPDATE_DIRNAME).exists()
    remove_file(tmp_path / "never-existed" / "x.exe")           # no error


def test_download_dirs_names():
    assert [p.name for p in cleanup.download_dirs(Path("/t"))] == [UPDATE_DIRNAME, CUDA_DIRNAME]


def test_a_new_download_starts_in_an_empty_folder(tmp_path):
    """Setups of earlier updates must not pile up: the folder is cleared before the next one is fetched."""
    import hashlib

    payload = b"installer" * 50
    sha = hashlib.sha256(payload).hexdigest()
    repo = "o/r"
    asset = updater.Asset("VoiceChatTool-Setup-2.0.0-CPU.exe",
                          f"https://github.com/{repo}/releases/download/v2.0.0/VoiceChatTool-Setup-2.0.0-CPU.exe",
                          len(payload), f"sha256:{sha}")
    release = updater.Release("2.0.0", "v2.0.0", "", "", (asset,))
    old = make(tmp_path / "VoiceChatTool-Setup-1.0.0-CPU.exe", 5000)

    def fake_download(url, dest, progress, expected_size=0, timeout=30.0):
        dest.write_bytes(payload)

    path = updater.download_and_verify(release, asset, repo, tmp_path, lambda d, t: None,
                                       lambda u: "", fake_download)
    assert path.exists() and not old.exists()
    assert [p.name for p in tmp_path.iterdir()] == [asset.name]
