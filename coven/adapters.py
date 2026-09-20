"""Runtime inspection and adapter status helpers."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _run_capture(command: list[str], timeout: float = 3.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "error": "not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "commandFound": True, "error": "timed out"}
    except OSError as exc:
        return {"available": False, "commandFound": True, "error": str(exc)}

    output = (completed.stdout or completed.stderr or "").strip()
    return {
        "available": completed.returncode == 0,
        "returnCode": completed.returncode,
        "output": output[:1200],
    }


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


def inspect_runtime() -> dict[str, Any]:
    hermes_path = shutil.which("hermes")
    ollama_path = shutil.which("ollama")
    demo_mode = os.environ.get("COVEN_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

    hermes = {"available": bool(hermes_path), "path": hermes_path, "version": None, "notes": []}
    if hermes_path:
        version = _run_capture([hermes_path, "--version"])
        hermes["version"] = version.get("output") or None
        hermes["available"] = bool(version.get("available"))
        if version.get("error"):
            hermes["notes"].append(version["error"])
    else:
        hermes["notes"].append("Hermes CLI was not found on PATH.")

    ollama = {"available": bool(ollama_path), "path": ollama_path, "modelsVisible": False, "notes": []}
    if ollama_path:
        listing = _run_capture([ollama_path, "list"], timeout=2.0)
        ollama["modelsVisible"] = bool(listing.get("available"))
        if listing.get("output"):
            ollama["listOutput"] = listing["output"]
        if listing.get("error") or listing.get("returnCode"):
            ollama["notes"].append(listing.get("error") or "Ollama is installed but its local service did not answer.")
    else:
        ollama["notes"].append("Ollama CLI was not found on PATH.")

    openai = {
        "configured": bool(os.environ.get("OPENAI_API_KEY")),
        "notes": ["API keys are read by the backend process only and are never sent to browser storage."],
    }

    return {
        "mode": "demo" if demo_mode else "live",
        "demoMode": demo_mode,
        "connection": "demo" if demo_mode else ("ready" if hermes["available"] else "disconnected"),
        "hermes": hermes,
        "ollama": ollama,
        "openai": openai,
        "routing": {
            "taskRuntime": "demo-fixture" if demo_mode else "hermes-agent",
            "localModel": "ollama" if ollama["available"] else "unavailable",
            "apiModel": "openai" if openai["configured"] else "unconfigured",
        },
        "hardware": hardware_report(),
    }
