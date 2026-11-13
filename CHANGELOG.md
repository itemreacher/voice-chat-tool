# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com), versions follow
[Semantic Versioning](https://semver.org). A release is created from a tag `vX.Y.Z` (see `docs/RELEASING.md`);
the version in `vct/__init__.py` must match the tag.

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
