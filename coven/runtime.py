"""Bounded runtime probes for Hermes, Ollama and provider status."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any

from .adapters import hardware_report
from .configuration import AppConfig


class RuntimeInspector:
    def __init__(self, config: AppConfig, *, ttl_seconds: float = 15.0):
        self.config = config
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._last_probe = 0.0
        self._refreshing = False

    def get(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._snapshot is not None and not force and now - self._last_probe < self.ttl_seconds:
                return dict(self._snapshot)
            if self._refreshing and self._snapshot is not None:
                return dict(self._snapshot)
            self._refreshing = True
        try:
            snapshot = self._probe()
            with self._lock:
                self._snapshot = snapshot
                self._last_probe = time.monotonic()
                return dict(snapshot)
        finally:
            with self._lock:
                self._refreshing = False

    def _probe(self) -> dict[str, Any]:
        hermes = self._probe_executable(self.config.runtime.hermes_executable, ["--version"], timeout=2.0)
        ollama_path = shutil.which("ollama")
        ollama = {
            "installed": bool(ollama_path),
            "path": ollama_path,
            "reachable": False,
            "operational": False,
            "notes": [],
        }
        if ollama_path:
            listing = self._run_capture([ollama_path, "list"], timeout=2.0)
            ollama["reachable"] = bool(listing.get("ok"))
            ollama["operational"] = bool(listing.get("ok"))
            if listing.get("output"):
                ollama["listOutput"] = listing["output"]
            if listing.get("error"):
                ollama["notes"].append(listing["error"])
        else:
            ollama["notes"].append("Ollama CLI was not found on PATH.")

        openai_key = self.config.providers.openai_key_env
        openai = {
            "configured": bool(os.environ.get(openai_key)),
            "keyEnvironmentVariable": openai_key,
            "model": self.config.providers.openai_model or "unconfigured",
            "notes": ["API keys are read by the backend process only and are never sent to browser storage."],
        }

        demo_mode = self.config.demo_mode
        hermes_ready = bool(hermes["installed"] and hermes["operational"])
        return {
            "mode": "demo" if demo_mode else "live",
            "demoMode": demo_mode,
            "connection": "demo" if demo_mode else ("ready" if hermes_ready else "disconnected"),
            "hermes": hermes,
            "hermesApi": {
                "configured": bool(self.config.runtime.hermes_api_base_url and os.environ.get(self.config.runtime.hermes_api_key_env)),
                "baseUrl": self.config.runtime.hermes_api_base_url or "unconfigured",
                "keyEnvironmentVariable": self.config.runtime.hermes_api_key_env,
            },
            "ollama": ollama,
            "openai": openai,
            "routing": {
                "taskRuntime": "demo-fixture" if demo_mode else "hermes-agent",
                "localModel": self.config.providers.ollama_model or ("ollama" if ollama["installed"] else "unavailable"),
                "apiModel": self.config.providers.openai_model or ("openai" if openai["configured"] else "unconfigured"),
            },
            "hardware": hardware_report(),
        }

    def _probe_executable(self, executable: str, args: list[str], *, timeout: float) -> dict[str, Any]:
        path = shutil.which(executable)
        probe = {
            "installed": bool(path),
            "reachable": False,
            "operational": False,
            "path": path,
            "version": None,
            "notes": [],
        }
        if not path:
            probe["notes"].append(f"{executable} was not found on PATH.")
            return probe
        result = self._run_capture([path, *args], timeout=timeout)
        probe["reachable"] = bool(result.get("commandFound", True))
        probe["operational"] = bool(result.get("ok"))
        probe["version"] = result.get("output") or None
        if result.get("error"):
            probe["notes"].append(result["error"])
        return probe

    def _run_capture(self, command: list[str], *, timeout: float) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return {"ok": False, "commandFound": False, "error": "not found"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "commandFound": True, "error": "timed out"}
        except OSError as exc:
            return {"ok": False, "commandFound": True, "error": str(exc)}
        output = (completed.stdout or completed.stderr or "").strip()
        return {
            "ok": completed.returncode == 0,
            "commandFound": True,
            "returnCode": completed.returncode,
            "output": output[:1200],
            "error": "" if completed.returncode == 0 else output[:240] or f"exit {completed.returncode}",
        }
