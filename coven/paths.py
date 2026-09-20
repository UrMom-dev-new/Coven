"""Application path helpers for source and frozen builds."""

from __future__ import annotations

import os
from pathlib import Path
import sys


APP_NAME = "CovenAgentWorkspace"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_path(*parts: str) -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS).joinpath(*parts)  # type: ignore[attr-defined]
    return app_root().joinpath(*parts)


def local_app_data() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


def runtime_dir() -> Path:
    path = local_app_data() / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = local_app_data() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def webview_user_data_dir() -> Path:
    path = local_app_data() / "webview2"
    path.mkdir(parents=True, exist_ok=True)
    return path
