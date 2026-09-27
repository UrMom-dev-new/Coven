"""User-selected local runtimes, saved independently of the app installation."""

from __future__ import annotations

from dataclasses import replace
import json
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import threading
from urllib.parse import urlsplit, urlunsplit

from .processes import background_process_options
from .runtime import RuntimeInspector
from .secrets import SecretStore
from .voice import VOICE_MODEL_PROFILES


HERMES_SECRET = "runtime.hermes.api_key"


def local_endpoint(value):
    if not isinstance(value, str):
        raise ValueError("Enter a local Hermes address.")
    parsed = urlsplit(value.strip())
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") not in {"", "/v1"}):
        raise ValueError("Use a local Hermes address such as http://127.0.0.1:8642.")
    port = parsed.port  # Also validates the port range.
    if not port:
        raise ValueError("Include the Hermes port, normally 8642.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def selected_executable(value, name):
    if not isinstance(value, str) or not value.strip():
        return ""
    path = Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
    if path.is_dir():
        suffix = ".exe" if os.name == "nt" else ""
        candidates = [path / f"{name}{suffix}", path / "Release" / f"{name}{suffix}",
                      path / "bin" / f"{name}{suffix}", path / "Scripts" / f"{name}{suffix}"]
        if name == "hermes":
            for base in (path, path / "hermes-agent"):
                for env in ("venv", ".venv"):
                    candidates += [base / env / "Scripts" / "hermes.exe", base / env / "bin" / "hermes"]
        path = next((item for item in candidates if item.is_file()), path)
    if not path.is_file() or (os.name == "nt" and path.suffix.lower() != ".exe"):
        raise ValueError(f"Select the {name} executable or its installation folder.")
    return str(path.resolve())


class ConnectionSettings:
    def __init__(self, base_config, data_dir):
        self.base_config = base_config
        self.data_dir = data_dir
        self.path = data_dir / "setup" / "connections.json"
        self.secrets = SecretStore(data_dir / "setup" / "credentials")
        self.lock = threading.RLock()
        self._process = None
        self._last_test = None
        self.load_error = ""
        try:
            self.saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.saved, dict):
                raise ValueError("Invalid settings")
            for section in ("hermes", "voice"):
                values = self.saved.get(section, {})
                if not isinstance(values, dict) or any(not isinstance(value, (str, bool)) for value in values.values()):
                    raise ValueError("Invalid settings")
                if any(not isinstance(value, str) for key, value in values.items() if key != "enabled"):
                    raise ValueError("Invalid settings")
            voice = self.saved.get("voice", {})
            if ("enabled" in voice and not isinstance(voice["enabled"], bool)) or voice.get("modelProfile", "base.en-q5_1") not in VOICE_MODEL_PROFILES:
                raise ValueError("Invalid voice settings")
            if self.saved.get("hermes", {}).get("baseUrl"):
                local_endpoint(self.saved["hermes"]["baseUrl"])
        except FileNotFoundError:
            self.saved = {}
        except (ValueError, OSError):
            self.saved = {}
            self.load_error = "Saved connection settings could not be read. Please save them again in Settings."

    def effective_config(self):
        with self.lock:
            h = self.saved.get("hermes", {})
            v = self.saved.get("voice", {})
            runtime = replace(self.base_config.runtime,
                              hermes_executable=h.get("executable") or self.base_config.runtime.hermes_executable,
                              hermes_api_base_url=h.get("baseUrl", self.base_config.runtime.hermes_api_base_url))
            voice = replace(self.base_config.voice, enabled=v.get("enabled", self.base_config.voice.enabled),
                            runtime_executable=v.get("runtimeExecutable", self.base_config.voice.runtime_executable),
                            model_dir=Path(v["modelDir"]) if v.get("modelDir") else self.base_config.voice.model_dir,
                            model_profile=v.get("modelProfile", self.base_config.voice.model_profile),
                            microphone_id=v.get("microphoneId", self.base_config.voice.microphone_id))
            return replace(self.base_config, runtime=runtime, voice=voice)

    def api_key(self):
        if self.secrets.has(HERMES_SECRET):
            return self.secrets.get(HERMES_SECRET)
        return os.environ.get(self.base_config.runtime.hermes_api_key_env, "")

    def connection_id(self):
        with self.lock:
            h = self.saved.get("hermes", {})
            identity = [self.effective_config().runtime.hermes_api_base_url, h.get("home", ""), h.get("executable", "")]
            return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16]

    def status(self):
        config = self.effective_config()
        with self.lock:
            return {"hermes": {"executable": config.runtime.hermes_executable,
                               "home": self.saved.get("hermes", {}).get("home", ""),
                               "baseUrl": config.runtime.hermes_api_base_url or "http://127.0.0.1:8642",
                               "keySaved": bool(self.api_key()), "test": self._last_test,
                               "startedByCoven": self._process is not None and self._process.poll() is None},
                    "voice": {"enabled": config.voice.enabled, "runtimeExecutable": config.voice.runtime_executable,
                              "modelDir": str(config.voice.model_dir or ""), "modelProfile": config.voice.model_profile,
                              "microphoneId": config.voice.microphone_id}, "error": self.load_error}

    def save_hermes(self, payload):
        url = local_endpoint(payload.get("baseUrl", "http://127.0.0.1:8642"))
        raw_exe = payload.get("executable", "")
        # Keep the default PATH choice when no local file has been selected yet.
        executable = "hermes" if raw_exe == "hermes" else selected_executable(raw_exe, "hermes")
        raw_home = str(payload.get("home") or "").strip()
        home = Path(os.path.expandvars(raw_home)).expanduser() if raw_home else None
        if home is not None and not home.is_dir():
            raise ValueError("Choose an existing Hermes data folder, or leave it blank when connecting to a running server.")
        key = payload.get("apiKey", "")
        if not isinstance(key, str) or len(key) > 4096 or any(c in key for c in "\r\n"):
            raise ValueError("Hermes API key is invalid.")
        with self.lock:
            if self._process is not None and self._process.poll() is None:
                raise ValueError("Restart Coven before changing a Hermes process started by this app.")
            old_url = self.effective_config().runtime.hermes_api_base_url
            if old_url != url and self.api_key() and not key.strip():
                raise ValueError("Enter the key for the new Hermes address; an existing key will not be forwarded automatically.")
            if key.strip():
                self.secrets.put(HERMES_SECRET, key.strip())
            self._save("hermes", {"executable": executable, "home": str(home.resolve()) if home else "", "baseUrl": url})
            self._last_test = None

    def save_voice(self, payload):
        current = self.status()["voice"]
        current.update(payload)
        profile = current.get("modelProfile")
        if profile not in VOICE_MODEL_PROFILES or VOICE_MODEL_PROFILES[profile].sha1 is None:
            raise ValueError("Choose the Standard or Lightweight verified model.")
        if not isinstance(current.get("enabled"), bool):
            raise ValueError("Voice enabled must be true or false.")
        runtime = selected_executable(current.get("runtimeExecutable", ""), "whisper-server")
        model_dir = str(current.get("modelDir") or "").strip()
        if model_dir:
            path = Path(os.path.expandvars(model_dir)).expanduser()
            if path.is_file() and path.name == VOICE_MODEL_PROFILES[profile].filename:
                path = path.parent
            if not path.is_dir():
                raise ValueError("Choose the folder containing your Whisper model file.")
            model_dir = str(path.resolve())
        microphone = current.get("microphoneId", "default")
        if not isinstance(microphone, str) or len(microphone) > 512:
            raise ValueError("Select a valid microphone.")
        with self.lock:
            self._save("voice", {"enabled": current["enabled"], "runtimeExecutable": runtime,
                                 "modelDir": model_dir, "modelProfile": profile, "microphoneId": microphone})

    def test_hermes(self):
        probe = RuntimeInspector(self.effective_config(), api_key=self.api_key()).get(force=True)["hermesApi"]
        result = {"ready": probe["taskCapable"], "authenticated": probe["authenticated"],
                  "providerReady": probe["readiness"].get("status") == "ready",
                  "message": "Connected. Hermes supports task submission and status." if probe["taskCapable"] else
                  " ".join(probe["notes"]) or "Hermes connected, but this version does not expose the required Runs API."}
        with self.lock:
            self._last_test = result
        return result

    def start_hermes(self):
        with self.lock:
            if self._process is not None and self._process.poll() is None:
                return {"message": "Hermes is already running under Coven. Test the connection."}
            settings = self.status()["hermes"]
            if not settings["home"]:
                raise ValueError("Choose the Hermes data folder before starting its runtime.")
            executable = selected_executable(shutil.which(settings["executable"]) or settings["executable"], "hermes")
            if not executable:
                raise ValueError("Choose the Hermes executable first.")
            parsed = urlsplit(local_endpoint(settings["baseUrl"]))
            try:
                with socket.create_connection((parsed.hostname, parsed.port), timeout=0.5):
                    raise ValueError("That port is already in use. Use Test connection for an existing Hermes server.")
            except OSError:
                pass
            key = self.api_key()
            if not key:
                key = secrets.token_urlsafe(32)
                self.secrets.put(HERMES_SECRET, key)
            env = dict(os.environ)
            env.update(HERMES_HOME=settings["home"], API_SERVER_ENABLED="true", API_SERVER_HOST=parsed.hostname,
                       API_SERVER_PORT=str(parsed.port), API_SERVER_KEY=key)
            self._process = subprocess.Popen([executable, "gateway"], env=env, cwd=settings["home"],
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             **background_process_options())
            return {"message": "Hermes is starting in the background. Test the connection when it is ready."}

    def close(self):
        with self.lock:
            self._last_test = None
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)

    def _save(self, section, value):
        updated = {**self.saved, section: value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        self.saved = updated
        self.load_error = ""
