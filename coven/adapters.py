"""Runtime inspection and adapter status helpers."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def default_data_dir() -> Path:
    env_dir = os.environ.get("COVEN_HOME")
    if env_dir:
        return Path(env_dir).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "CovenAgentWorkspace"
    if sys_root := os.environ.get("XDG_DATA_HOME"):
        return Path(sys_root) / "coven-agent-workspace"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CovenAgentWorkspace"
    return Path.home() / ".local" / "share" / "coven-agent-workspace"


def hardware_report() -> dict[str, Any]:
    memory = "unknown"
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            memory = f"{round((pages * page_size) / (1024**3), 1)} GiB"
    except (OSError, ValueError):
        memory = "unknown"

    disk = shutil.disk_usage(Path.home())
    return {
        "machineRole": "development-machine",
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpuCount": os.cpu_count(),
        "memory": memory,
        "homeDiskFree": f"{round(disk.free / (1024**3), 1)} GiB",
        "targetDellVerified": False,
    }
