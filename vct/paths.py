"""Where config and log live (pure; testable on any OS).

* Development / portable: a config.toml next to the program wins (keeps the folder workflow).
* Installed (frozen, no config.toml next to the program, e.g. under Program Files): the
  per-user data folder, which is always writable.
* VCT_DATA_DIR overrides everything (tests, special setups).
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

APP_NAME = "VoiceChatTool"
CONFIG_NAME = "config.toml"
LOG_NAME = "voice-chat-tool.log"


def user_data_dir(platform: str, env: Mapping[str, str], home: Path) -> Path:
    """Per-user data folder for the platform ('win32', 'darwin', anything else = Linux)."""
    if platform == "win32":
        base = Path(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
        return base / APP_NAME
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else home / ".config"
    return base / APP_NAME


def data_dir(app_dir: Path, frozen: bool, platform: str, env: Mapping[str, str],
             home: Path) -> Path:
    override: Optional[str] = env.get("VCT_DATA_DIR")
    if override:
        return Path(override)
    if not frozen or (app_dir / CONFIG_NAME).exists():
        return app_dir
    return user_data_dir(platform, env, home)


def resource_dir(frozen: bool, meipass: Optional[str], project_dir: Path) -> Path:
    """Folder holding bundled read-only files (assets/...)."""
    return Path(meipass) if frozen and meipass else project_dir
