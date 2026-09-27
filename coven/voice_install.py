"""Verified, cancellable installation of the optional local speech components."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import tempfile
import threading
import urllib.request
import uuid
import zipfile

from .voice import VOICE_MODEL_PROFILES


RUNTIME_VERSION = "v1.8.3"
RUNTIME_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.3/whisper-bin-x64.zip"
RUNTIME_SHA256 = "d824b1e37599f882b396e73f1ee0bfd5d0529f700314c48311dcbd00b803321d"
INSTALLABLE_PROFILES = ("base.en-q5_1", "tiny.en-q5_1")


class InstallCancelled(RuntimeError):
    pass


def download_verified(url, destination, expected_hash, algorithm, cancel, progress, *, limit):
    """Only callers' pinned URLs are accepted; no URL is taken from a UI request."""
    digest = hashlib.new(algorithm)
    request = urllib.request.Request(url, headers={"User-Agent": "Coven-Voice-Setup"})
    with urllib.request.urlopen(request, timeout=20) as response, destination.open("wb") as output:
        if not response.geturl().startswith("https://"):
            raise ValueError("Voice downloads must use HTTPS.")
        total = int(response.headers.get("Content-Length", "0"))
        if total > limit:
            raise ValueError("Voice download exceeds its size limit.")
        received = 0
        while True:
            if cancel.is_set():
                raise InstallCancelled("Installation cancelled; previous settings are unchanged.")
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > limit:
                raise ValueError("Voice download exceeds its size limit.")
            digest.update(chunk)
            output.write(chunk)
            progress(received, total)
    if cancel.is_set():
        raise InstallCancelled("Installation cancelled; previous settings are unchanged.")
    if digest.hexdigest() != expected_hash:
        raise ValueError("Downloaded file failed verification. Please retry.")


def extract_runtime(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 256 or sum(item.file_size for item in entries) > 128 * 1024 * 1024:
            raise ValueError("Speech runtime archive is too large.")
        for item in entries:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            mode = item.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or ":" in str(path) or stat.S_ISLNK(mode):
                raise ValueError("Speech runtime archive contains an unsafe path.")
        package.extractall(destination)
    executable = destination / "Release" / "whisper-server.exe"
    if not executable.is_file():
        raise ValueError("Speech package does not contain whisper-server.exe.")
    return executable


class VoiceInstaller:
    def __init__(self, root: Path, activate):
        self.root = root
        self.activate = activate
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = {"state": "idle", "message": "Install local voice, or select an existing whisper.cpp installation."}

    def status(self):
        with self._lock:
            return dict(self._state)

    def start(self, profile: str):
        if profile not in INSTALLABLE_PROFILES:
            raise ValueError("Choose the Standard or Lightweight voice model.")
        if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ValueError("Automatic installation supports Windows x64. Use an existing runtime on this platform.")
        with self._lock:
            if self.busy:
                raise ValueError("Voice installation is already running.")
            self.root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.root).free < 400 * 1024 * 1024:
                raise ValueError("Free at least 400 MB of disk space, then retry.")
            self._cancel.clear()
            self._state = {"state": "downloading", "profile": profile, "message": "Preparing local voice…", "received": 0, "total": 0}
            self._thread = threading.Thread(target=self._install, args=(profile,), name="coven-voice-install", daemon=True)
            self._thread.start()
            return dict(self._state)

    @property
    def busy(self):
        return self._state["state"] in {"downloading", "verifying", "activating"}

    def cancel(self):
        with self._lock:
            if self._state["state"] == "activating":
                return dict(self._state)
            if self.busy:
                self._cancel.set()
                self._state["message"] = "Cancelling download…"
            return dict(self._state)

    def close(self):
        self.cancel()
        if self._thread:
            self._thread.join(timeout=2)

    def _progress(self, message, received=0, total=0):
        with self._lock:
            self._state.update(message=message, received=received, total=total)

    def _install(self, profile):
        installed = None
        try:
            with tempfile.TemporaryDirectory(prefix="download-", dir=self.root) as temporary:
                stage = Path(temporary)
                archive = stage / "runtime.zip"
                self._progress("Downloading whisper.cpp for Windows…")
                download_verified(RUNTIME_URL, archive, RUNTIME_SHA256, "sha256", self._cancel,
                                  lambda n, total: self._progress("Downloading whisper.cpp for Windows…", n, total), limit=16 * 1024 * 1024)
                payload = stage / "package"
                executable = extract_runtime(archive, payload / "runtime")
                model = VOICE_MODEL_PROFILES[profile]
                model_dir = payload / "models"
                model_dir.mkdir()
                download_verified(model.source_url, model_dir / model.filename, model.sha1, "sha1", self._cancel,
                                  lambda n, total: self._progress("Downloading the English voice model…", n, total), limit=100 * 1024 * 1024)
                # Install into a new immutable directory. A failed/cancelled repair
                # must not overwrite a working runtime or a DLL currently in use.
                with self._lock:
                    if self._cancel.is_set():
                        raise InstallCancelled("Installation cancelled; previous settings are unchanged.")
                    self._state.update(state="activating", message="Saving verified voice components…")
                    installed = self.root / f"whisper-{RUNTIME_VERSION}-{uuid.uuid4().hex}"
                    relative_exe = executable.relative_to(payload)
                    payload.rename(installed)
                # Never hold the installer lock while acquiring the server's settings lock.
                self.activate({"enabled": True, "runtimeExecutable": str(installed / relative_exe),
                               "modelDir": str(installed / "models"), "modelProfile": profile})
                with self._lock:
                    self._state.update(state="completed", message="Voice installed. Test your microphone to check transcription.", received=0, total=0)
                    installed = None  # Active files are retained across app updates.
        except InstallCancelled as exc:
            with self._lock:
                self._state.update(state="cancelled", message=str(exc))
        except Exception as exc:
            with self._lock:
                self._state.update(state="error", message=f"Voice setup failed: {exc}. Your previous settings are unchanged.")
        finally:
            if installed is not None:
                shutil.rmtree(installed, ignore_errors=True)
