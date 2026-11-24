# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com), versions follow
[Semantic Versioning](https://semver.org). A release is created from a tag `vX.Y.Z` (see `docs/RELEASING.md`);
the version in `vct/__init__.py` must match the tag.

## [1.1.0] - 2026-11-24

### Added
- **Desktop audio to text:** the new tab "Desktop-Audio" records what the PC plays (a video, a stream, a call)
  and writes it down live while it plays. The audio is cut at pauses, recognised with the same Whisper model
  (language automatic or fixed), optionally translated, shown with a level meter, copied or saved as text
  or as SRT subtitles. Windows only (WASAPI loopback). The audio itself is not stored.
- New settings `desktop_language`, `desktop_translate_to`, `desktop_timestamps`.

## [1.0.5] - 2026-11-14

### Fixed
- Recording failed with `DirectSound error -2005401480` ("no driver") when the chosen microphone was
  opened through an audio interface that cannot use it at that moment. A named microphone is now tried on
  the interface Windows uses by default first (also recognising Windows' shortened 31-character names) and,
  if that fails, on its other interfaces. The error message lists what was tried and what usually causes it
  (another program holding the microphone exclusively).
- The microphone drop-down no longer lists the shortened duplicate of a name.

## [1.0.4] - 2026-11-14

### Fixed
- Same as 1.0.3 (version 1.0.3 was never published): a unit test compared a Windows path in a way that only
  works on Windows, which stopped the Linux and macOS builds of the release.

## [1.0.3] - 2026-11-14

### Added
- The CPU edition can now use the GPU: the GPU button offers to download the NVIDIA CUDA libraries
  (about 1.3 GB) from PyPI, checks every file against PyPI's SHA-256, unpacks only the runtime DLLs into
  `%LOCALAPPDATA%\VoiceChatTool\cuda` together with NVIDIA's licence texts, and then switches to the GPU.
  The GPU installer (which bundles the libraries) now also ships NVIDIA's licence texts.

## [1.0.2] - 2026-11-13

### Fixed
- A silent update started by the program itself could hang forever on the Setup dialog "Select install mode".
  Setup no longer offers that dialog (per user is the default, `/ALLUSERS` selects all users), and the
  updater states the install mode explicitly.
- Release workflow: the helper list `files.txt` is no longer published as a release file.

## [1.0.1] - 2026-11-13

### Fixed
- The program did not start when the microphone had been chosen by name in the settings and Windows
  listed that microphone under several audio interfaces ("Multiple input devices found"). A name is now
  resolved to exactly one device, and a microphone that cannot be opened falls back to the default one.
- Umlauts in the config that had been damaged by a wrong encoding (`Ã¼bersetze`) are repaired when it is loaded.
- Release workflow: the Linux package no longer drags in CUDA libraries (3 GB), and publishing no longer
  trips over the unpacked folder.

## [1.0.0] - 2026-11-13

### Added
- Push-to-talk speech to text (faster-whisper) with a typed output into the focused window and the clipboard.
- Translation between any language pair, offline (Argos Translate), by spoken keyword or with a
  dedicated translate key.
- Word help: vocabulary hints for Whisper, a replacement list and a conservative spell check.
- CPU/GPU switch (button and hotkey).
- Window with a gaming-inspired design and a "shattered keyboard" logo; language pack manager.
- Windows installers (CPU and GPU editions), per-user, with uninstaller.
- Automatic update check against GitHub Releases with a checksum-verified, one-click update.
- macOS and Linux code paths and build scripts (untested), GitHub Actions for tests and releases.

### Fixed
- Switching to the GPU froze the engine forever in installations without the NVIDIA CUDA libraries.
  The libraries are now checked first, and a GPU start has a time limit.
