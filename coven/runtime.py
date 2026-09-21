"""Bounded runtime probes for Hermes, Ollama and provider status."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib import error as urllib_error, request as urllib_request
import json

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
        hermes_api = self._probe_hermes_api()
        hermes_ready = bool(hermes_api["taskCapable"])
        return {
            "mode": "demo" if demo_mode else "live",
            "demoMode": demo_mode,
            "connection": "demo" if demo_mode else ("ready" if hermes_ready else "disconnected"),
            "hermes": hermes,
            "hermesApi": hermes_api,
            "ollama": ollama,
            "openai": openai,
            "routing": {
                "taskRuntime": "demo-fixture" if demo_mode else ("hermes-runs" if hermes_ready else "unavailable"),
                "localModel": self.config.providers.ollama_model or ("ollama" if ollama["installed"] else "unavailable"),
                "apiModel": self.config.providers.openai_model or ("openai" if openai["configured"] else "unconfigured"),
                "autoPolicy": "local for bounded Circe/Hecate when a local model is configured; otherwise configured API model; no silent escalation from explicit local",
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

    def _probe_hermes_api(self) -> dict[str, Any]:
        base_url = self.config.runtime.hermes_api_base_url.rstrip("/")
        key_env = self.config.runtime.hermes_api_key_env
        api_key = os.environ.get(key_env, "")
        probe: dict[str, Any] = {
            "configured": bool(base_url and api_key),
            "baseUrl": base_url or "unconfigured",
            "keyEnvironmentVariable": key_env,
            "reachable": False,
            "authenticated": False,
            "taskCapable": False,
            "runEventsCapable": False,
            "approvalCapable": False,
            "stopCapable": False,
            "modelOptionsAvailable": False,
            "capabilities": {},
            "readiness": {"status": "unavailable"},
            "notes": [],
        }
        if not base_url:
            probe["notes"].append("Hermes API base URL is not configured.")
            return probe
        if not api_key:
            probe["notes"].append(f"Hermes API key environment variable {key_env} is not set.")
            return probe

        health = self._http_json(f"{base_url}/health", api_key, timeout=1.5)
        probe["reachable"] = bool(health.get("ok"))
        if health.get("error"):
            probe["notes"].append(f"Health check failed: {health['error']}")

        capabilities = self._http_json(f"{base_url}/v1/capabilities", api_key, timeout=2.0)
        if capabilities.get("ok") and isinstance(capabilities.get("json"), dict):
            probe["authenticated"] = True
            caps = capabilities["json"]
            features = caps.get("features") if isinstance(caps.get("features"), dict) else {}
            probe["capabilities"] = {
                "model": caps.get("model"),
                "features": features,
                "sessionKeyHeader": caps.get("session_key_header"),
            }
            probe["taskCapable"] = features.get("run_submission") is True and features.get("run_status") is True
            probe["runEventsCapable"] = features.get("run_events_sse") is True
            probe["approvalCapable"] = features.get("run_approval") is True
            probe["stopCapable"] = features.get("run_stop") is True
        else:
            status = capabilities.get("status")
            if status in {401, 403}:
                probe["authenticated"] = False
                probe["notes"].append("Hermes API rejected the configured bearer token.")
            elif capabilities.get("error"):
                probe["notes"].append(f"Capabilities check failed: {capabilities['error']}")

        detailed = self._http_json(f"{base_url}/health/detailed", api_key, timeout=2.0)
        if detailed.get("ok") and isinstance(detailed.get("json"), dict):
            readiness = detailed["json"]
            probe["readiness"] = {
                "status": readiness.get("status", "unknown"),
                "checks": readiness.get("readiness", {}).get("checks", {}) if isinstance(readiness.get("readiness"), dict) else {},
            }

        model_options = self._http_json(f"{base_url}/api/model/options", api_key, timeout=2.0)
        if model_options.get("ok"):
            probe["modelOptionsAvailable"] = True
        return probe

    def _http_json(self, url: str, api_key: str, *, timeout: float) -> dict[str, Any]:
        req = urllib_request.Request(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return {"ok": 200 <= response.status < 300, "status": response.status, "json": payload}
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {"ok": False, "status": exc.code, "error": detail[:240] or f"HTTP {exc.code}"}
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}
