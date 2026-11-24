"""Remove what updates and the GPU download leave behind in the temp folder (pure file handling).

The updater downloads the Setup (200 MB to 1.2 GB) and the GPU download fetches big wheels. Both are only
needed once; without cleanup every update left another few hundred MB behind.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, List, Optional

UPDATE_DIRNAME = "VoiceChatTool-update"      # where the updater puts the downloaded Setup
CUDA_DIRNAME = "VoiceChatTool-cuda"          # where the NVIDIA wheels are downloaded before unpacking


def clear_directory(path: Path, remove_self: bool = False) -> int:
    """Delete everything in `path` that can be deleted; returns the bytes freed.

    A file that is in use (for example a Setup that is still running) is skipped, never an error.
    """
    freed = 0
    if not path.is_dir():
        return 0
    for item in sorted(path.iterdir()):
        try:
            if item.is_dir() and not item.is_symlink():
                freed += clear_directory(item, remove_self=True)
            else:
                size = item.stat().st_size
                item.unlink()
                freed += size
        except OSError:
            continue
    if remove_self:
        try:
            path.rmdir()
        except OSError:
            pass
    return freed


def clean_temp_downloads(temp: Optional[Path] = None, log: Optional[Callable[[str], None]] = None) -> int:
    """Clear the updater's and the GPU download's temp folders. Returns the bytes freed."""
    base = temp if temp is not None else Path(tempfile.gettempdir())
    freed = sum(clear_directory(base / name, remove_self=True) for name in (UPDATE_DIRNAME, CUDA_DIRNAME))
    if freed and log:
        log(f"Cleaned up {freed // 1_000_000} MB of old downloads in the temp folder.")
    return freed


def download_dirs(temp: Optional[Path] = None) -> List[Path]:
    base = temp if temp is not None else Path(tempfile.gettempdir())
    return [base / UPDATE_DIRNAME, base / CUDA_DIRNAME]


def remove_file(path: Path) -> None:
    """Delete one downloaded file (and its folder if that is now empty); errors are ignored."""
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except OSError:
        pass


