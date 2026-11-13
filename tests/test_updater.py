import hashlib
from pathlib import Path

import pytest

from vct import updater as U

REPO = "someone/voice-chat-tool"
BASE = f"https://github.com/{REPO}/releases/download/v1.2.0"
PAYLOAD = b"installer-bytes" * 100
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def release_json(tag="v1.2.0", with_sums=True, digest=""):
    assets = [
        {"name": "VoiceChatTool-Setup-1.2.0-CPU.exe", "browser_download_url": f"{BASE}/VoiceChatTool-Setup-1.2.0-CPU.exe", "size": len(PAYLOAD), "digest": digest},
        {"name": "VoiceChatTool-Setup-1.2.0-GPU.exe", "browser_download_url": f"{BASE}/VoiceChatTool-Setup-1.2.0-GPU.exe", "size": 9},
        {"name": "VoiceChatTool-1.2.0-macOS.dmg", "browser_download_url": f"{BASE}/VoiceChatTool-1.2.0-macOS.dmg"},
    ]
    if with_sums:
        assets.append({"name": "SHA256SUMS.txt", "browser_download_url": f"{BASE}/SHA256SUMS.txt"})
    return {"tag_name": tag, "html_url": f"https://github.com/{REPO}/releases/tag/{tag}", "body": "notes", "assets": assets}


@pytest.mark.parametrize("a,b,newer", [
    ("1.0.1", "1.0.0", True), ("v1.10.0", "1.9.9", True), ("1.0.0", "1.0.0", False),
    ("0.9.9", "1.0.0", False), ("2", "1.9.9", True), ("1.2.0-beta", "1.1.9", True),
])
def test_is_newer(a, b, newer):
    assert U.is_newer(a, b) is newer


def test_parse_version_rejects_garbage():
    with pytest.raises(ValueError):
        U.parse_version("latest")


def test_repo_validation():
    assert U.is_valid_repo("a/b") and U.is_valid_repo("My-Org/voice_chat.tool")
    for bad in ("", "abc", "a/b/c", "a b/c", "../x", "https://github.com/a/b"):
        assert not U.is_valid_repo(bad)


def test_parse_release_and_bad_data():
    rel = U.parse_release(release_json())
    assert rel.version == "1.2.0" and rel.tag == "v1.2.0" and len(rel.assets) == 4
    with pytest.raises(U.UpdateError):
        U.parse_release({"tag_name": "nightly"})
    with pytest.raises(U.UpdateError):
        U.parse_release({})


def test_check_for_update_uses_repo_url_and_compares():
    seen = []
    def fake(url):
        seen.append(url)
        return release_json()
    assert U.check_for_update(REPO, "1.0.0", fake).version == "1.2.0"
    assert seen == [f"https://api.github.com/repos/{REPO}/releases/latest"]
    assert U.check_for_update(REPO, "1.2.0", fake) is None
    assert U.check_for_update(REPO, "2.0.0", fake) is None
    with pytest.raises(U.UpdateError):
        U.check_for_update("not a repo", "1.0.0", fake)


def test_pick_installer_matches_edition_and_platform():
    rel = U.parse_release(release_json())
    assert U.pick_installer(rel, "win32", "CPU").name.endswith("-CPU.exe")
    assert U.pick_installer(rel, "win32", "gpu").name.endswith("-GPU.exe")
    assert U.pick_installer(rel, "darwin", "CPU") is None     # no automatic install off Windows
    assert U.pick_installer(U.parse_release({**release_json(), "assets": []}), "win32", "CPU") is None


def test_installed_edition_and_self_update_conditions(tmp_path):
    assert U.installed_edition(tmp_path) == "CPU"
    (tmp_path / "_internal" / "nvidia").mkdir(parents=True)
    assert U.installed_edition(tmp_path) == "GPU"
    assert not U.can_self_update(True, "win32", tmp_path)          # no uninstaller: portable/dev
    (tmp_path / "unins000.exe").write_text("x")
    assert U.can_self_update(True, "win32", tmp_path)
    assert not U.can_self_update(False, "win32", tmp_path)         # running from source
    assert not U.can_self_update(True, "linux", tmp_path)


def test_checksum_parsing_and_expected():
    text = f"{SHA}  VoiceChatTool-Setup-1.2.0-CPU.exe\n{'a' * 64} *other.exe\nnot a line\n"
    assert U.parse_checksums(text) == {"VoiceChatTool-Setup-1.2.0-CPU.exe": SHA, "other.exe": "a" * 64}
    asset = U.Asset("x.exe", "u", digest=f"sha256:{SHA.upper()}")
    assert U.expected_sha256(asset, None) == SHA                   # digest wins, normalised
    assert U.expected_sha256(U.Asset("x.exe", "u"), text) is None


def fake_download(payload):
    def fn(url, dest, progress, expected_size=0):
        dest.write_bytes(payload)
        progress(len(payload), len(payload))
    return fn


def run(tmp_path, payload=PAYLOAD, sums=True, digest="", fetch_text=None):
    rel = U.parse_release(release_json(with_sums=sums, digest=digest))
    asset = U.pick_installer(rel, "win32", "CPU")
    fetch = fetch_text or (lambda url: f"{SHA}  {asset.name}\n")
    return U.download_and_verify(rel, asset, REPO, tmp_path, lambda d, t: None, fetch, fake_download(payload))


def test_download_verified_with_checksum_file(tmp_path):
    path = run(tmp_path)
    assert path.read_bytes() == PAYLOAD and path.name == "VoiceChatTool-Setup-1.2.0-CPU.exe"


def test_download_verified_with_github_digest(tmp_path):
    assert run(tmp_path, sums=False, digest=f"sha256:{SHA}").exists()


def test_tampered_download_is_rejected_and_deleted(tmp_path):
    with pytest.raises(U.UpdateError, match="checksum"):
        run(tmp_path, payload=b"evil")
    assert not (tmp_path / "VoiceChatTool-Setup-1.2.0-CPU.exe").exists()


def test_no_checksum_means_no_automatic_install(tmp_path):
    with pytest.raises(U.UpdateError, match="no checksum"):
        run(tmp_path, sums=False)


def test_foreign_download_url_is_refused(tmp_path):
    rel = U.parse_release(release_json())
    evil = U.Asset("VoiceChatTool-Setup-1.2.0-CPU.exe", "https://evil.example/x.exe", digest=f"sha256:{SHA}")
    with pytest.raises(U.UpdateError, match="not a release"):
        U.download_and_verify(rel, evil, REPO, tmp_path, lambda d, t: None, lambda u: "", fake_download(PAYLOAD))
    other_repo = U.Asset("a.exe", "https://github.com/attacker/repo/releases/download/v1/a.exe", digest=f"sha256:{SHA}")
    with pytest.raises(U.UpdateError):
        U.download_and_verify(rel, other_repo, REPO, tmp_path, lambda d, t: None, lambda u: "", fake_download(PAYLOAD))


def test_installer_command_flags():
    cmd = U.installer_command(Path("C:/t/Setup.exe"))
    assert cmd[1:] == ["/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]


def test_no_release_yet_is_not_an_error():
    def fake(url):
        raise U.NoReleaseError("none")
    assert U.check_for_update(REPO, "1.0.0", fake) is None


def test_other_network_errors_still_raise():
    def fake(url):
        raise U.UpdateError("offline")
    with pytest.raises(U.UpdateError):
        U.check_for_update(REPO, "1.0.0", fake)


def test_download_url_check_ignores_owner_case_but_not_the_repository():
    url = "https://github.com/SomeOne/Voice-Chat-Tool/releases/download/v1/a.exe"
    assert U.trusted_download_url(url, "someone/voice-chat-tool")
    assert not U.trusted_download_url(url, "someone/other-repo")
