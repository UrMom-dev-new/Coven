"""Single source for Coven release metadata."""

from __future__ import annotations

from pathlib import Path


def _read_version() -> str:
    root = Path(__file__).resolve().parent.parent
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"


__version__ = _read_version()
APP_DISPLAY_NAME = "Coven"
APP_PUBLISHER = "HermesAvatar"
WINDOWS_SETUP_ASSET = "Coven-Setup-x64.exe"
WINDOWS_CHECKSUM_ASSET = f"{WINDOWS_SETUP_ASSET}.sha256"
