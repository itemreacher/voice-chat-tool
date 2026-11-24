"""Update check and download from GitHub Releases (stdlib only).

Pure logic (version compare, asset choice, checksums) is separate from the thin network
layer, which can be replaced in tests. Nothing about the user or the PC is sent: a plain
HTTPS GET with a generic User-Agent.

Safety: the installer is only run after its SHA-256 matches the value published in the same
release (asset digest or SHA256SUMS.txt) and only from a github.com release URL of the
configured repository. Without a checksum nothing is installed automatically.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .cleanup import clear_directory

USER_AGENT = "VoiceChatTool-updater"
API = "https://api.github.com/repos/{repo}/releases/latest"
CHECKSUM_ASSET = "SHA256SUMS.txt"
INSTALLER_PATTERN = re.compile(r"^VoiceChatTool-Setup-(?P<ver>[\w.]+)-(?P<edition>CPU|GPU)\.exe$", re.I)
INSTALLER_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]
CHUNK = 1 << 20
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(Exception):
    pass


class NoReleaseError(UpdateError):
    """The repository has no published release yet (GitHub answers 404)."""


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0
    digest: str = ""          # "sha256:<hex>" as provided by GitHub, if present


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    page_url: str
    notes: str = ""
    assets: Tuple[Asset, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- pure logic
def is_valid_repo(repo: str) -> bool:
    if not _REPO.match(repo or ""):
        return False
    return not any(set(part) == {"."} for part in repo.split("/"))  # no '.' / '..' path tricks


def parse_version(text: str) -> Tuple[int, int, int]:
    """'v1.2.3' / '1.2' -> (1, 2, 3). Pre-release suffixes are ignored. ValueError if unparsable."""
    match = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not match:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(g or 0) for g in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def parse_release(data: Dict) -> Release:
    """GitHub 'latest release' JSON -> Release. Raises UpdateError if it is not usable."""
    try:
        tag = str(data["tag_name"])
        parse_version(tag)
        assets = tuple(
            Asset(name=str(a["name"]), url=str(a["browser_download_url"]),
                  size=int(a.get("size") or 0), digest=str(a.get("digest") or ""))
            for a in data.get("assets", []))
        return Release(version=tag.lstrip("vV"), tag=tag, page_url=str(data.get("html_url", "")),
                       notes=str(data.get("body") or ""), assets=assets)
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError(f"unexpected release data: {exc}") from exc


def installed_edition(app_dir: Path) -> str:
    """'GPU' if this installation bundles the NVIDIA libraries, else 'CPU'."""
    return "GPU" if (app_dir / "_internal" / "nvidia").is_dir() else "CPU"


def pick_installer(release: Release, platform: str, edition: str) -> Optional[Asset]:
    """The Setup.exe of the same edition. Automatic installing exists for Windows only."""
    if platform != "win32":
        return None
    for asset in release.assets:
        match = INSTALLER_PATTERN.match(asset.name)
        if match and match.group("edition").upper() == edition.upper():
            return asset
    return None


def can_self_update(frozen: bool, platform: str, app_dir: Path) -> bool:
    """Only a program installed by the Setup (it leaves unins000.exe) updates itself."""
    return frozen and platform == "win32" and (app_dir / "unins000.exe").exists()


def trusted_download_url(url: str, repo: str) -> bool:
    """A release download of this repository. GitHub treats owner/name case-insensitively."""
    return url.lower().startswith(f"https://github.com/{repo}/releases/download/".lower())


def parse_checksums(text: str) -> Dict[str, str]:
    """'sha256sum' output ('<hex>  <name>' or '<hex> *<name>') -> {name: hex}."""
    result: Dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if match:
            result[match.group(2)] = match.group(1).lower()
    return result


def expected_sha256(asset: Asset, checksums_text: Optional[str]) -> Optional[str]:
    if asset.digest.lower().startswith("sha256:"):
        return asset.digest.split(":", 1)[1].lower()
    if checksums_text:
        return parse_checksums(checksums_text).get(asset.name)
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- network layer
def fetch_json(url: str, timeout: float = 10.0) -> Dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NoReleaseError("no release published yet") from exc
        raise UpdateError(f"could not reach GitHub: {exc}") from exc
    except Exception as exc:
        raise UpdateError(f"could not reach GitHub: {exc}") from exc


def fetch_text(url: str, timeout: float = 15.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:
        raise UpdateError(f"could not download {url}: {exc}") from exc


def check_for_update(repo: str, current: str,
                     fetch: Callable[[str], Dict] = fetch_json) -> Optional[Release]:
    """The newest release if it is newer than `current`, else None."""
    if not is_valid_repo(repo):
        raise UpdateError(f"update_repo must look like 'owner/name', got {repo!r}")
    try:
        data = fetch(API.format(repo=repo))
    except NoReleaseError:
        return None  # nothing published yet: nothing newer than what is installed
    release = parse_release(data)
    return release if is_newer(release.version, current) else None


def download_file(url: str, dest: Path, progress: Callable[[int, int], None],
                  expected_size: int = 0, timeout: float = 30.0) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or expected_size or 0)
            done = 0
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                progress(done, total)
    except Exception as exc:
        raise UpdateError(f"download failed: {exc}") from exc


def download_and_verify(release: Release, asset: Asset, repo: str, dest_dir: Path,
                        progress: Callable[[int, int], None],
                        fetch_text_fn: Callable[[str], str] = fetch_text,
                        download_fn: Callable[..., None] = download_file) -> Path:
    """Download the installer and check its SHA-256. Raises UpdateError on any doubt."""
    if not trusted_download_url(asset.url, repo):
        raise UpdateError("the download address is not a release of the configured repository")
    checksums: Optional[str] = None
    if not asset.digest:
        sums = next((a for a in release.assets if a.name == CHECKSUM_ASSET), None)
        if sums and trusted_download_url(sums.url, repo):
            checksums = fetch_text_fn(sums.url)
    expected = expected_sha256(asset, checksums)
    if not expected:
        raise UpdateError("this release publishes no checksum, so it will not be installed "
                          "automatically; download it from the release page")
    clear_directory(dest_dir)                       # Setups of earlier updates are obsolete
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset.name
    download_fn(asset.url, dest, progress, asset.size)
    actual = sha256_file(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise UpdateError("the downloaded file is damaged or was changed (checksum mismatch)")
    return dest


def is_machine_wide_install(app_dir: Path, env: Optional[Dict[str, str]] = None) -> bool:
    """True if the program lives under Program Files (installed 'for all users')."""
    env = env if env is not None else dict(os.environ)
    roots = [env.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    here = str(app_dir).lower().replace("/", "\\")
    return any(r and here.startswith(r.lower().rstrip("\\") + "\\") for r in roots)


def installer_command(installer: Path, app_dir: Optional[Path] = None,
                      env: Optional[Dict[str, str]] = None) -> List[str]:
    """Silent update command. The install mode is always stated, so no dialog can block it:
    per user normally, for all users (Windows asks for permission) if the program is in Program Files."""
    mode = "/ALLUSERS" if app_dir is not None and is_machine_wide_install(app_dir, env) else "/CURRENTUSER"
    return [str(installer), *INSTALLER_ARGS, mode]
