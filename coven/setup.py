"""First-run setup and component readiness state."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import time
from typing import Any

from .configuration import AppConfig
from .paths import bundled_path
from .secrets import SecretStore
from .version import __version__, WINDOWS_CHECKSUM_ASSET, WINDOWS_SETUP_ASSET
from .voice import VoiceService


SETUP_SCHEMA = 1
PROVIDER_SECRET = "provider.openai.api_key"
def _load_runtime_manifest() -> dict[str, Any]:
    try:
        data = json.loads(bundled_path("packaging", "hermes-runtime.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    hermes = data.get("hermes") if isinstance(data.get("hermes"), dict) else {}
    return {
        "repo": hermes.get("repo", "https://github.com/NousResearch/hermes-agent"),
        "tag": hermes.get("tag", "v2026.9.21"),
        "version": hermes.get("version", "0.21.4"),
        "releaseCommit": hermes.get("releaseCommit", "d337b73"),
        "installScript": hermes.get("installScript", "https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.21/scripts/install.ps1"),
        "notes": hermes.get("notes", []),
    }


HERMES_PIN = _load_runtime_manifest()
WEBVIEW2_BOOTSTRAPPER = {
    "name": "Microsoft Edge WebView2 Evergreen Bootstrapper",
    "url": "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
    "command": "MicrosoftEdgeWebview2Setup.exe /silent /install",
}


@dataclass
class SetupManager:
    config: AppConfig
    data_dir: Path
    voice: VoiceService

    def __post_init__(self) -> None:
        self.setup_dir = self.data_dir / "setup"
        self.state_path = self.setup_dir / "setup-state.json"
        self.previous_state_path = self.setup_dir / "setup-state.previous.json"
        self.secret_store = SecretStore(self.setup_dir / "credentials")

    def status(self) -> dict[str, Any]:
        state = self._state()
        provider_ready = self.secret_store.has(PROVIDER_SECRET) or bool(os.environ.get(self.config.providers.openai_key_env))
        workspace = state.get("workspace") if isinstance(state.get("workspace"), dict) else {}
        workspace_path = Path(str(workspace.get("path") or "")) if workspace.get("path") else None
        workspace_ready = bool(workspace_path and workspace_path.exists() and workspace_path.is_dir())
        voice = self.voice.status()
        hermes = self._managed_hermes_status(state)
        steps = [
            self._computer_step(),
            self._webview_step(),
            {
                "id": "hermes",
                "label": "Prepare Hermes",
                "state": hermes["state"],
                "summary": hermes["summary"],
                "details": hermes,
            },
            {
                "id": "provider",
                "label": "Connect AI provider",
                "state": "ready" if provider_ready else "needs_input",
                "summary": "Provider credential is saved." if provider_ready else "Enter your own API credential or choose Explore demo.",
            },
            {
                "id": "workspace",
                "label": "Choose work folder",
                "state": "ready" if workspace_ready else "needs_input",
                "summary": str(workspace_path) if workspace_ready else "Select a writable folder for Coven tasks.",
            },
            {
                "id": "voice",
                "label": "Enable local voice",
                "state": "ready" if voice.get("state") == "ready" else "optional",
                "summary": "Local voice is ready." if voice.get("state") == "ready" else "Optional; text chat can be used now.",
                "details": voice,
            },
            {
                "id": "starterTask",
                "label": "Try first task",
                "state": state.get("starterTask", {}).get("state", "not_run") if isinstance(state.get("starterTask"), dict) else "not_run",
                "summary": state.get("starterTask", {}).get("summary", "Run after Hermes and provider are ready.") if isinstance(state.get("starterTask"), dict) else "Run after Hermes and provider are ready.",
            },
        ]
        setup_complete = bool(state.get("setupComplete")) and provider_ready and workspace_ready
        return {
            "version": __version__,
            "setupComplete": setup_complete,
            "mode": state.get("mode", "live"),
            "steps": steps,
            "release": {
                "installer": WINDOWS_SETUP_ASSET,
                "checksum": WINDOWS_CHECKSUM_ASSET,
                "downloadPage": "https://github.com/UrMom-dev-new/HermesAvatar/releases",
                "visibility": "private repository; testers need repository access until a separate public binary distribution is approved",
            },
            "privacy": "Credentials are stored outside renderer storage. Local voice audio is transcribed locally; transcripts sent to Hermes may reach the configured provider.",
        }

    def choose_mode(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "").strip().lower()
        if mode not in {"live", "demo"}:
            raise ValueError("mode must be live or demo.")
        state = self._state()
        state["mode"] = mode
        if mode == "demo":
            state["setupComplete"] = True
        self._write_state(state)
        return self.status()

    def save_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = str(payload.get("apiKey") or "").strip()
        model = str(payload.get("model") or "").strip()
        if not api_key:
            raise ValueError("API key is required.")
        if not model:
            raise ValueError("Model is required.")
        self.secret_store.put(PROVIDER_SECRET, api_key)
        state = self._state()
        state["provider"] = {
            "type": "openai-compatible",
            "model": model,
            "secretRef": PROVIDER_SECRET,
            "updatedAt": _now(),
        }
        self._write_state(state)
        return self.status()

    def remove_provider(self) -> dict[str, Any]:
        self.secret_store.delete(PROVIDER_SECRET)
        state = self._state()
        state.pop("provider", None)
        state["setupComplete"] = False
        self._write_state(state)
        return self.status()

    def save_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(payload.get("path") or "").strip()
        if not raw_path:
            raise ValueError("Workspace path is required.")
        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_dir():
            raise ValueError("Workspace folder must exist.")
        marker = path / ".coven-write-test"
        try:
            marker.write_text("ok", encoding="utf-8")
            marker.unlink(missing_ok=True)
        except OSError as exc:
            raise ValueError("Workspace folder is not writable.") from exc
        state = self._state()
        state["workspace"] = {"path": str(path.resolve()), "updatedAt": _now()}
        self._write_state(state)
        return self.status()

    def complete(self) -> dict[str, Any]:
        state = self._state()
        state["setupComplete"] = True
        state["completedAt"] = _now()
        self._write_state(state)
        return self.status()

    def repair(self) -> dict[str, Any]:
        state = self._state()
        repairs = state.get("repairs") if isinstance(state.get("repairs"), list) else []
        repairs.append({"at": _now(), "action": "repair_requested", "summary": "Marked app-owned components for verification on next Windows setup run."})
        state["repairs"] = repairs[-20:]
        self._write_state(state)
        return self.status()

    def support_bundle(self) -> dict[str, Any]:
        bundle = {
            "createdAt": _now(),
            "version": __version__,
            "platform": platform.platform(),
            "setup": self.status(),
            "statePath": str(self.state_path),
            "redaction": "No secrets, conversations, raw audio, or business documents are included.",
        }
        output = self.setup_dir / f"support-bundle-{int(time.time())}.json"
        _atomic_write_json(output, bundle)
        return {"path": str(output), "bundle": bundle}

    def workspace_roots(self) -> tuple[Path, ...]:
        state = self._state()
        workspace = state.get("workspace") if isinstance(state.get("workspace"), dict) else {}
        raw_path = workspace.get("path") if isinstance(workspace.get("path"), str) else ""
        if not raw_path:
            return ()
        path = Path(raw_path)
        return (path,) if path.exists() and path.is_dir() else ()

    def _computer_step(self) -> dict[str, Any]:
        arch = platform.machine().lower()
        supported_arch = arch in {"amd64", "x86_64"}
        disk = shutil.disk_usage(str(self.data_dir.parent if self.data_dir.parent.exists() else Path.home()))
        enough_disk = disk.free > 2 * 1024 * 1024 * 1024
        state = "ready" if os.name == "nt" and supported_arch and enough_disk else "unverified" if os.name != "nt" else "needs_attention"
        return {
            "id": "computer",
            "label": "Check this computer",
            "state": state,
            "summary": f"{platform.system() or 'Unknown OS'} {platform.release()} on {platform.machine() or 'unknown CPU'}; {disk.free // (1024 ** 3)} GiB free.",
        }

    def _webview_step(self) -> dict[str, Any]:
        if os.name != "nt":
            return {
                "id": "webview2",
                "label": "WebView2 runtime",
                "state": "unverified",
                "summary": "WebView2 is checked on Windows during desktop startup.",
                "details": WEBVIEW2_BOOTSTRAPPER,
            }
        from .desktop import detect_webview2

        ready, message = detect_webview2()
        return {
            "id": "webview2",
            "label": "WebView2 runtime",
            "state": "ready" if ready else "needs_attention",
            "summary": message,
            "details": WEBVIEW2_BOOTSTRAPPER,
        }

    def _managed_hermes_status(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime_root = self.data_dir / "components" / "hermes-runtime"
        exe = runtime_root / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
        if exe.exists():
            status = "ready"
            summary = "App-owned Hermes executable was found."
        else:
            status = "needs_attention"
            summary = "Hermes runtime is not installed in Coven's app-owned location."
        return {
            "state": status,
            "summary": summary,
            "runtimeRoot": str(runtime_root),
            "expectedExecutable": str(exe),
            "pin": HERMES_PIN,
            "configured": state.get("hermes", {}),
        }

    def _state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema": SETUP_SCHEMA, "mode": "live", "setupComplete": False}
        except (json.JSONDecodeError, OSError):
            return {"schema": SETUP_SCHEMA, "mode": "live", "setupComplete": False, "recoveredFromMalformedState": True}
        return payload if isinstance(payload, dict) else {"schema": SETUP_SCHEMA, "mode": "live", "setupComplete": False}

    def _write_state(self, payload: dict[str, Any]) -> None:
        payload["schema"] = SETUP_SCHEMA
        payload["updatedAt"] = _now()
        if self.state_path.exists():
            self.setup_dir.mkdir(parents=True, exist_ok=True)
            self.previous_state_path.write_text(self.state_path.read_text(encoding="utf-8"), encoding="utf-8")
        _atomic_write_json(self.state_path, payload)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
