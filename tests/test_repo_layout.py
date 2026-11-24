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
    # a mode dialog would block a silent update, so it must not be offered
    assert "PrivilegesRequiredOverridesAllowed=commandline" in iss
    assert "PrivilegesRequiredOverridesAllowed=dialog" not in iss


def test_weekly_routine_is_documented_and_keeps_ideas_local():
    routine = (ROOT / "docs/WEEKLY_ROUTINE.md").read_text(encoding="utf-8")
    for needle in ("untrusted", "never merges", "IDEAS.md", "tools/triage.py", ".github/"):
        assert needle in routine
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("IDEAS.md", "reports/", ".triage_state.json"):
        assert pattern in ignore                     # the maintainer's private review files stay off GitHub
    assert (ROOT / "tools/triage.py").is_file() and (ROOT / ".github/ISSUE_TEMPLATE/idea.md").is_file()


def test_installer_replaces_the_old_version_instead_of_stacking_up():
    iss = (ROOT / "installer/VoiceChatTool.iss").read_text(encoding="utf-8")
    # 1. the program folder is wiped before the new files are copied (Setup never deletes stale files itself)
    assert "[InstallDelete]" in iss
    assert 'Name: "{app}\\_internal"' in iss and 'Name: "{app}\\licenses"' in iss
    # 2. an installation of the other mode (all users <-> this user) is removed, not left next to the new one
    assert "RemoveOtherModeInstall" in iss and "HKLM64" in iss and "'runas'" in iss
    assert "CurStep = ssInstall" in iss
    # 3. tests can use their own id; the real one stays in place
    assert "TestAppId" in iss and "{{6F0B8F4E-3D1A-4C57-9B7E-5A1C2E9D4F10}" in iss


def test_settings_and_downloads_are_not_inside_the_wiped_folders():
    iss = (ROOT / "installer/VoiceChatTool.iss").read_text(encoding="utf-8")
    delete_section = iss.split("[InstallDelete]")[1].split("[Code]")[0]
    for kept in ("AppData", "VoiceChatTool\\cuda", "config.toml"):
        assert kept not in delete_section
