"""Gemeinsame Datenpfade für Desktop-Anwendung und eigenständige Werkzeuge."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    override = os.environ.get("PDA_APP_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PersonalDigitalAgent"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "PersonalDigitalAgent"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "PersonalDigitalAgent"
