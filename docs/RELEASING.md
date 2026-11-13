# Releasing and updating

## One-time setup

1. Create the GitHub repository and push this folder (see the README, "Put it on GitHub").
2. Nothing to configure for updates: the release workflow writes the repository name
   (`github.repository`) into the build (`tools/set_repo.py`), so installed programs know where to look.
   For local builds run `python tools/set_repo.py owner/name` once before `build_installer.bat`.

## Publishing a new version

1. Change the version in `vct/__init__.py` (for example `1.0.1`) and add a section to `CHANGELOG.md`.
2. Commit, then tag and push:

   ```bash
   git commit -am "release 1.0.1"
   git tag v1.0.1
   git push origin main v1.0.1
   ```

3. The workflow `release` builds the Windows (CPU and GPU), macOS and Linux installers, creates
   `SHA256SUMS.txt` and publishes a GitHub Release `v1.0.1` with all files.
   The tag must equal the version in `vct/__init__.py`, otherwise the build stops.

## What the installed program does

- At start-up (switchable in Settings, `update_check`) it asks `https://api.github.com/repos/<owner>/<name>/releases/latest`
  for the newest release. Nothing about the user is sent.
- If it is newer, a banner offers **Jetzt aktualisieren**. The program downloads the Setup of its own edition
  (CPU or GPU), compares its SHA-256 with the value published in the release (asset digest or
  `SHA256SUMS.txt`), and refuses to install without a matching checksum.
- After a confirmation it starts `Setup.exe /SILENT /CLOSEAPPLICATIONS /RELAUNCH=1`, closes itself, and the
  installer replaces the program in place and starts it again. Settings in the data folder are kept.
- Only an installed Windows program updates itself. Source/portable runs and macOS/Linux open the release page.

## Rules that keep updates working

- Never change the `AppId` in `installer/VoiceChatTool.iss`: it lets a new Setup replace the old installation.
- Keep the asset names `VoiceChatTool-Setup-<version>-CPU.exe` and `...-GPU.exe`; the updater selects them by name.
- Releases must be public and not drafts or pre-releases (the "latest release" endpoint ignores those).
- The Setup is not code-signed. A signing certificate would remove the SmartScreen warning; the checksum check
  protects against corrupted downloads but not against someone who controls your GitHub account.
