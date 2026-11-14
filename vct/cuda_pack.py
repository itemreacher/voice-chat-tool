"""Download the NVIDIA CUDA runtime libraries on demand (Windows), so the CPU edition can use the GPU.

The libraries are fetched straight from PyPI, where NVIDIA publishes them as wheels, so nothing from
NVIDIA is redistributed by this program. Each wheel is checked against the SHA-256 value PyPI publishes
and only the runtime DLLs are unpacked into a folder of the program's own data directory.

Pure logic (choosing the wheel, safe extraction, completeness check) is separate from the network layer,
which can be replaced in tests.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import updater

PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
TRUSTED_PREFIX = "https://files.pythonhosted.org/"
WHEEL_TAG = "win_amd64"
MARKER = "complete.json"
REQUIRED_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")
_LICENSE_MEMBER = re.compile(r"^([A-Za-z0-9_.\-]+)\.dist-info/licenses/([A-Za-z0-9_.\-]+)$")
_DLL_MEMBER = re.compile(r"^nvidia/([A-Za-z0-9_]+)/bin/([A-Za-z0-9_.\-]+\.dll)$", re.I)

Log = Callable[[str], None]
Progress = Callable[[str, int, int], None]   # (package name, bytes done, bytes total)


class CudaPackError(Exception):
    pass


@dataclass(frozen=True)
class Package:
    name: str
    version: str


# Versions that were tested together with faster-whisper / CTranslate2 (CUDA 12, cuDNN 9).
PACKAGES: Tuple[Package, ...] = (
    Package("nvidia-cuda-nvrtc-cu12", "12.9.86"),
    Package("nvidia-cublas-cu12", "12.9.2.10"),
    Package("nvidia-cudnn-cu12", "9.28.1.4"),
)


@dataclass(frozen=True)
class Wheel:
    filename: str
    url: str
    sha256: str
    size: int


# ---------------------------------------------------------------- pure logic
def pick_wheel(data: Dict, wheel_tag: str = WHEEL_TAG) -> Wheel:
    """The Windows wheel from PyPI's JSON for one release. Raises CudaPackError if there is none."""
    for entry in data.get("urls", []):
        if entry.get("packagetype") == "bdist_wheel" and wheel_tag in entry.get("filename", ""):
            sha = str(entry.get("digests", {}).get("sha256", "")).lower()
            url = str(entry.get("url", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise CudaPackError(f"PyPI lists no checksum for {entry.get('filename')}")
            if not url.startswith(TRUSTED_PREFIX):
                raise CudaPackError("the download address is not on files.pythonhosted.org")
            return Wheel(str(entry["filename"]), url, sha, int(entry.get("size") or 0))
    raise CudaPackError(f"no {wheel_tag} wheel found on PyPI")


def dll_members(names: Sequence[str]) -> List[str]:
    """Archive entries that are runtime DLLs ('nvidia/<pkg>/bin/<name>.dll'); nothing else is unpacked."""
    return [n for n in names if _DLL_MEMBER.match(n)]


def extract_dlls(wheel_path: Path, target: Path) -> List[Path]:
    """Unpack only the runtime DLLs of a wheel below `target`, never outside of it."""
    written: List[Path] = []
    root = target.resolve()
    with zipfile.ZipFile(wheel_path) as archive:
        for member in dll_members(archive.namelist()):
            dest = (target / member).resolve()
            if root not in dest.parents:
                raise CudaPackError(f"unsafe path in the archive: {member}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            written.append(dest)
    return written


def license_members(names: Sequence[str]) -> List[str]:
    return [n for n in names if _LICENSE_MEMBER.match(n)]


def extract_licenses(wheel_path: Path, target: Path) -> List[Path]:
    """Keep NVIDIA's licence texts next to the libraries: <target>/licenses/<package>/<file>."""
    written: List[Path] = []
    root = target.resolve()
    with zipfile.ZipFile(wheel_path) as archive:
        for member in license_members(archive.namelist()):
            match = _LICENSE_MEMBER.match(member)
            dest = (target / "licenses" / match.group(1) / match.group(2)).resolve()
            if root not in dest.parents:
                raise CudaPackError(f"unsafe path in the archive: {member}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(member))
            written.append(dest)
    return written


def is_installed(target: Path) -> bool:
    """All packages were unpacked completely and the key libraries are there."""
    if not (target / MARKER).is_file():
        return False
    return all(any((target / "nvidia").glob(f"*/bin/{dll}")) for dll in REQUIRED_DLLS)


def total_download_mb(sizes: Sequence[int]) -> int:
    return int(sum(sizes) / 1_000_000)


# ---------------------------------------------------------------- network layer
def fetch_wheel_info(package: Package, fetch: Callable[[str], Dict] = updater.fetch_json) -> Wheel:
    try:
        data = fetch(PYPI_JSON.format(name=package.name, version=package.version))
    except updater.UpdateError as exc:
        raise CudaPackError(f"could not reach PyPI: {exc}") from exc
    return pick_wheel(data)


def install(target: Path, tmp_dir: Path, progress: Progress, log: Log,
            fetch: Callable[[str], Dict] = updater.fetch_json,
            download: Callable[..., None] = updater.download_file) -> None:
    """Download, verify and unpack all packages. Raises CudaPackError; leaves no half-finished install
    marked as complete."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER).unlink(missing_ok=True)       # incomplete until the very end
    wheels = [(pkg, fetch_wheel_info(pkg, fetch)) for pkg in PACKAGES]
    log(f"NVIDIA libraries: {total_download_mb([w.size for _, w in wheels])} MB to download from PyPI.")
    for pkg, wheel in wheels:
        dest = tmp_dir / wheel.filename
        log(f"Downloading {pkg.name} {pkg.version} ({wheel.size // 1_000_000} MB)...")
        try:
            download(wheel.url, dest, lambda done, total, n=pkg.name: progress(n, done, total), wheel.size,
                     timeout=60.0)
        except updater.UpdateError as exc:
            raise CudaPackError(str(exc)) from exc
        if updater.sha256_file(dest) != wheel.sha256:
            dest.unlink(missing_ok=True)
            raise CudaPackError(f"{wheel.filename}: checksum mismatch, the download is damaged")
        files = extract_dlls(dest, target)
        extract_licenses(dest, target)
        dest.unlink(missing_ok=True)
        log(f"Unpacked {len(files)} libraries from {pkg.name}.")
    (target / MARKER).write_text(
        json.dumps({p.name: p.version for p in PACKAGES}, indent=2), encoding="utf-8")
    if not is_installed(target):
        raise CudaPackError("the libraries are incomplete after unpacking")
    log("NVIDIA libraries installed.")


def remove(target: Path) -> None:
    """Delete the downloaded libraries (frees about 1.9 GB)."""
    import shutil

    shutil.rmtree(target, ignore_errors=True)
