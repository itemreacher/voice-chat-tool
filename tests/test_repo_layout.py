"""Guards for the things a GitHub release depends on."""
from pathlib import Path

from vct import __version__
from vct.config import load_config, parse_config, render_config

ROOT = Path(__file__).resolve().parent.parent


def test_required_repository_files_exist():
    for name in ("README.md", "LICENSE", "THIRD_PARTY_LICENSES.md", "CHANGELOG.md", "CONTRIBUTING.md",
                 ".gitignore", "config.example.toml", "requirements.txt", "requirements-test.txt",
                 ".github/workflows/ci.yml", ".github/workflows/release.yml",
                 "docs/ARCHITECTURE.md", "docs/RELEASING.md", "installer/VoiceChatTool.iss"):
        assert (ROOT / name).is_file(), name


def test_changelog_has_the_current_version():
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_example_config_matches_the_defaults():
    assert load_config(ROOT / "config.example.toml") == parse_config({})
    assert (ROOT / "config.example.toml").read_text(encoding="utf-8") == render_config(parse_config({}))


def test_personal_files_are_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("config.toml", ".venv/", "dist/", "installer/Output/", "*.log"):
        assert pattern in ignore


def test_release_workflow_keeps_the_pieces_the_updater_needs():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for needle in ("SHA256SUMS.txt", "tools/set_repo.py", "build_installer.bat", "gh release create"):
        assert needle in text


def test_installer_script_supports_silent_update_relaunch():
    iss = (ROOT / "installer/VoiceChatTool.iss").read_text(encoding="utf-8")
    assert "RelaunchRequested" in iss and "{param:RELAUNCH" in iss and "AppId=" in iss
