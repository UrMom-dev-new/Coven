"""Local voice service boundary for Coven.

The service owns voice session state, cancellation, runtime/model validation,
temporary audio cleanup, and deterministic command routing. Audio capture is
initiated by the authenticated desktop UI and delivered as bounded WAV data;
transcription is local-only through a configured whisper.cpp runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

from .configuration import AppConfig, validate_profiles_file


class VoiceError(RuntimeError):
    def __init__(self, message: str, *, code: str = "voice_error", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class VoiceModelProfile:
    id: str
    label: str
    filename: str
    size_mb: int
    sha1: str | None
    source_url: str
    notes: str


VOICE_MODEL_PROFILES: dict[str, VoiceModelProfile] = {
    "base.en-q5_1": VoiceModelProfile(
        id="base.en-q5_1",
        label="base.en Q5_1",
        filename="ggml-base.en-q5_1.bin",
        size_mb=57,
        sha1="d26d7ce5a1b6e57bea5d0431b9c20ae49423c94a",
        source_url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin",
        notes="Default verified distributed English profile. The official tiny/base set currently publishes Q5_1, not Q5_0.",
    ),
    "tiny.en-q5_1": VoiceModelProfile(
        id="tiny.en-q5_1",
        label="tiny.en Q5_1",
        filename="ggml-tiny.en-q5_1.bin",
        size_mb=31,
        sha1="3fb92ec865cbbc769f08137f22470d6b66e071b6",
        source_url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en-q5_1.bin",
        notes="Verified lower-resource English profile for modest CPUs.",
    ),
    "base.en-q5_0": VoiceModelProfile(
        id="base.en-q5_0",
        label="base.en Q5_0",
        filename="ggml-base.en-q5_0.bin",
        size_mb=57,
        sha1=None,
        source_url="",
        notes="Import-only placeholder: no official distributed base.en Q5_0 file was verified for this branch.",
    ),
    "tiny.en-q5_0": VoiceModelProfile(
        id="tiny.en-q5_0",
        label="tiny.en Q5_0",
        filename="ggml-tiny.en-q5_0.bin",
        size_mb=31,
        sha1=None,
        source_url="",
        notes="Import-only placeholder: no official distributed tiny.en Q5_0 file was verified for this branch.",
    ),
}


TERMINAL_VOICE_STATES = {"transcript_ready", "cancelled", "error"}


@dataclass
class VoiceSession:
    id: str
    generation: int
    witch_id: str
    input_mode: str
    state: str
    created_at: float
    updated_at: float
    context: dict[str, Any]
    audio_path: Path | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "generation": self.generation,
            "witchId": self.witch_id,
            "inputMode": self.input_mode,
            "state": self.state,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "durationSeconds": self.duration_seconds,
        }


class VoiceCommandRouter:
    def __init__(self, profiles: list[dict[str, Any]]):
        self.profiles = profiles
        self.names = {self._normalize(profile["name"]): profile for profile in profiles}
        self.ids = {self._normalize(profile["id"]): profile for profile in profiles}

    def route(self, transcript: str, context: dict[str, Any]) -> dict[str, Any]:
        text = transcript.strip()
        normalized = self._normalize(text)
        if not normalized:
            return {"kind": "empty", "action": "draft_message", "reason": "No speech was transcribed."}

        if normalized.startswith("dictation ") or normalized.startswith("literal "):
            stripped = re.sub(r"^\s*(dictation|literal)\s+", "", text, flags=re.IGNORECASE).strip()
            return {"kind": "dictation", "action": "draft_message", "text": stripped, "reason": "Dictation prefix used."}

        selected = str(context.get("witchId") or "")
        witch = self._profile_for_phrase(normalized)

        if witch and normalized in {f"select {witch['id']}", f"select {self._normalize(witch['name'])}", f"choose {witch['id']}", f"switch to {self._normalize(witch['name'])}"}:
            return {"kind": "command", "action": "select_witch", "witchId": witch["id"], "reason": f"Selected {witch['name']} locally."}

        if normalized in {"open journal", "open the journal", "show journal", "show the journal", "go to journal", "go to the journal"}:
            return {"kind": "command", "action": "open_view", "view": "journal", "reason": "Opened the journal locally."}
        if normalized in {"open sanctuary", "open the sanctuary", "show sanctuary", "show the sanctuary", "go to sanctuary", "go to the sanctuary"}:
            return {"kind": "command", "action": "open_view", "view": "sanctuary", "reason": "Opened the sanctuary locally."}
        if normalized in {"open settings", "open the settings", "show settings", "show the settings", "go to settings", "go to the settings"}:
            return {"kind": "command", "action": "open_view", "view": "settings", "reason": "Opened settings locally."}
        if normalized in {"stop speaking", "stop speech", "stop playback", "cancel speech"}:
            return {"kind": "command", "action": "stop_speaking", "reason": "Stopped local speech playback."}

        task_match = re.match(r"^(show|open)\s+(.+?)'?s?\s+tasks$", normalized)
        if task_match:
            task_witch = self._profile_for_phrase(task_match.group(2))
            if task_witch:
                return {
                    "kind": "command",
                    "action": "show_tasks",
                    "witchId": task_witch["id"],
                    "view": "journal",
                    "reason": f"Opened tasks for {task_witch['name']}.",
                }

        addressed = self._addressed_request(text)
        if addressed:
            return {
                "kind": "request",
                "action": "draft_task",
                "witchId": addressed["witchId"],
                "title": self._title_for_request(addressed["request"]),
                "instructions": addressed["request"],
                "reason": "Prepared an editable task draft; nothing was submitted.",
                "integration": self._integration_hint(addressed["request"]),
            }

        if "govdash" in normalized or "office" in normalized or "document" in normalized or "solicitation" in normalized:
            return {
                "kind": "request",
                "action": "draft_task",
                "witchId": selected,
                "title": self._title_for_request(text),
                "instructions": text,
                "reason": "Prepared an editable task draft because the request mentions external work.",
                "integration": self._integration_hint(text),
            }

        return {"kind": "dictation", "action": "draft_message", "text": text, "reason": "Free-form speech kept as an editable message draft."}

    def supported_commands(self) -> list[dict[str, str]]:
        return [
            {"phrase": "Select Circe", "action": "Selects an existing witch locally."},
            {"phrase": "Show Circe's tasks", "action": "Opens the journal and focuses that witch's tasks locally."},
            {"phrase": "Open the journal", "action": "Opens the existing journal view."},
            {"phrase": "Open settings", "action": "Opens settings."},
            {"phrase": "Stop speaking", "action": "Stops local speech playback only."},
            {"phrase": "Circe, draft a compliance matrix from this solicitation", "action": "Creates an editable task draft; it is not submitted automatically."},
            {"phrase": "Dictation hello there", "action": "Forces literal message draft behavior."},
        ]

    def _addressed_request(self, text: str) -> dict[str, str] | None:
        for profile in self.profiles:
            name = re.escape(profile["name"])
            pid = re.escape(profile["id"])
            match = re.match(rf"^\s*(?:{name}|{pid})\s*[,;:-]\s*(.+)$", text, flags=re.IGNORECASE)
            if match and match.group(1).strip():
                return {"witchId": profile["id"], "request": match.group(1).strip()}
        return None

    def _profile_for_phrase(self, phrase: str) -> dict[str, Any] | None:
        normalized = self._normalize(phrase)
        if normalized in self.names:
            return self.names[normalized]
        if normalized in self.ids:
            return self.ids[normalized]
        for profile in self.profiles:
            if normalized.endswith(f" {self._normalize(profile['name'])}") or normalized.endswith(f" {profile['id']}"):
                return profile
        return None

    def _title_for_request(self, request: str) -> str:
        title = request.strip().rstrip(".")
        if len(title) > 88:
            title = title[:85].rstrip() + "..."
        return title[:1].upper() + title[1:] if title else "Voice task draft"

    def _integration_hint(self, text: str) -> str:
        normalized = self._normalize(text)
        if "govdash" in normalized:
            return "govdash"
        if "office" in normalized or "document" in normalized or "word" in normalized or "excel" in normalized or "powerpoint" in normalized:
            return "office"
        return ""

    def _normalize(self, text: str) -> str:
        normalized = text.lower().replace("’", "'")
        normalized = re.sub(r"[^a-z0-9'\s-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized


class WhisperCppWorker:
    """Persistent owner process for bounded whisper.cpp transcription jobs."""

    def __init__(self):
        self._input: mp.Queue | None = None
        self._output: mp.Queue | None = None
        self._process: mp.Process | None = None
        self._pending = 0
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.is_alive():
                return
            self._input = mp.Queue(maxsize=1)
            self._output = mp.Queue()
            self._process = mp.Process(target=_voice_worker_main, args=(self._input, self._output), daemon=True)
            self._process.start()
            self._pending = 0

    def submit(self, job: dict[str, Any]) -> None:
        self.start()
        assert self._input is not None
        with self._lock:
            if self._pending >= 1:
                raise VoiceError("A transcription is already running.", code="voice_queue_busy")
            try:
                self._input.put_nowait(job)
            except queue.Full as exc:
                raise VoiceError("A transcription is already queued.", code="voice_queue_busy") from exc
            self._pending += 1

    def poll(self) -> list[dict[str, Any]]:
        if self._output is None:
            return []
        results: list[dict[str, Any]] = []
        while True:
            try:
                results.append(self._output.get_nowait())
            except queue.Empty:
                break
        if results:
            with self._lock:
                self._pending = max(0, self._pending - len(results))
        return results

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self._process is not None and self._process.is_alive(),
            "pending": self._pending,
            "mode": "whisper-server",
        }

    def close(self) -> None:
        if self._input is not None:
            try:
                self._input.put_nowait({"type": "shutdown"})
            except Exception:
                pass
        if self._process is not None:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()


class VoiceService:
    def __init__(self, config: AppConfig, data_dir: Path, profile_path: Path, *, worker: WhisperCppWorker | None = None):
        self.config = config.voice
        self.data_dir = data_dir
        self.root = data_dir / "voice"
        self.tmp_dir = self.root / "tmp"
        self.model_dir = self.config.model_dir or (self.root / "models")
        self.runtime_dir = self.config.runtime_dir or (self.root / "runtime")
        self.worker = worker or WhisperCppWorker()
        self.profiles = validate_profiles_file(profile_path)
        self.router = VoiceCommandRouter(self.profiles)
        self._lock = threading.RLock()
        self._session: VoiceSession | None = None
        self._generation = 0
        self._cleanup_startup_tmp()

    def close(self) -> None:
        self.worker.close()
        self._cleanup_terminal_audio()

    def status(self) -> dict[str, Any]:
        self._drain_worker()
        runtime = self._runtime_status()
        model = self._model_status()
        ready = self.config.enabled and runtime["available"] and model["available"] and model["verified"]
        state = "ready" if ready else "setup_required"
        if not self.config.enabled:
            state = "disabled"
        with self._lock:
            session = self._session.to_dict() if self._session else None
        notes = []
        if self.config.allow_api_transcription or self.config.allow_api_speech:
            notes.append("Cloud speech flags are ignored; local-only voice forbids API transcription and API speech.")
        if not runtime["available"]:
            notes.append(runtime["note"])
        if not model["available"] or not model["verified"]:
            notes.append(model["note"])
        notes.append("A transcript explicitly sent to Hermes may leave the device through the configured Hermes/provider route.")
        return {
            "enabled": self.config.enabled,
            "state": state,
            "recording": state if not session else session["state"],
            "transcription": "whisper.cpp server" if ready else state,
            "speech": "local-playback-unverified",
            "engine": self.config.engine,
            "defaultInput": self.config.default_input,
            "language": self.config.language,
            "maxDurationSeconds": self.config.max_duration_seconds,
            "retainAudio": self.config.retain_audio,
            "runtime": runtime,
            "model": model,
            "worker": self.worker.snapshot(),
            "session": session,
            "notes": notes,
        }

    def devices(self) -> dict[str, Any]:
        return {
            "devices": [
                {
                    "id": "default",
                    "label": "Default system microphone",
                    "default": True,
                    "state": "selected" if self.config.microphone_id == "default" else "available",
                }
            ],
            "selected": self.config.microphone_id,
            "notes": [
                "The packaged desktop UI uses the WebView/Windows microphone permission surface for capture.",
                "Native Windows device enumeration must be verified on the target machine.",
            ],
        }

    def commands(self) -> dict[str, Any]:
        return {"commands": self.router.supported_commands()}

    def start_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        readiness = self.status()
        if readiness["state"] != "ready":
            raise VoiceError("Local voice is not ready. Install the whisper.cpp runtime and a verified model first.", code="voice_setup_required", details=readiness)
        witch_id = str(payload.get("witchId") or "").strip()
        if witch_id not in {profile["id"] for profile in self.profiles}:
            raise VoiceError("Voice session witchId must match a configured witch.", code="invalid_voice_context")
        input_mode = str(payload.get("inputMode") or self.config.default_input)
        if input_mode not in {"message", "task", "commands", "dictation", "auto", "push-to-talk", "click-to-toggle"}:
            input_mode = "auto"
        now = time.time()
        with self._lock:
            if self._session is not None and self._session.state not in TERMINAL_VOICE_STATES:
                raise VoiceError("A voice session is already active.", code="voice_session_active")
            self._generation += 1
            session = VoiceSession(
                id=f"voice-{uuid.uuid4().hex[:16]}",
                generation=self._generation,
                witch_id=witch_id,
                input_mode=input_mode,
                state="listening",
                created_at=now,
                updated_at=now,
                context={
                    "witchId": witch_id,
                    "view": str(payload.get("view") or ""),
                    "workspace": payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {},
                    "documents": payload.get("documents") if isinstance(payload.get("documents"), list) else [],
                },
            )
            self._session = session
            return {"session": session.to_dict(), "voice": self.status()}

    def finish_session_audio(self, session_id: str, *, generation: int, audio: bytes, content_type: str) -> dict[str, Any]:
        if content_type and "wav" not in content_type.lower() and "wave" not in content_type.lower():
            raise VoiceError("Voice audio must be WAV PCM for local transcription.", code="unsupported_audio_format")
        if len(audio) > self.config.max_audio_bytes:
            raise VoiceError("Voice audio exceeds the configured size limit.", code="voice_audio_too_large")
        wav = inspect_wav(audio)
        if wav["durationSeconds"] > self.config.max_duration_seconds + 0.5:
            raise VoiceError("Voice recording exceeded the configured duration limit.", code="voice_duration_exceeded", details=wav)
        if wav["durationSeconds"] < 0.25:
            raise VoiceError("Voice recording was too short to transcribe.", code="voice_too_short", details=wav)
        with self._lock:
            session = self._require_session(session_id, generation)
            if session.state != "listening":
                raise VoiceError("Voice session is not accepting audio.", code="stale_voice_session")
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
            audio_path = self.tmp_dir / f"{session.id}-g{session.generation}.wav"
            audio_path.write_bytes(audio)
            session.audio_path = audio_path
            session.duration_seconds = float(wav["durationSeconds"])
            session.state = "transcribing"
            session.updated_at = time.time()
            job = {
                "type": "transcribe",
                "sessionId": session.id,
                "generation": session.generation,
                "audioPath": str(audio_path),
                "runtimeExecutable": self._runtime_status()["path"],
                "modelPath": self._model_status()["path"],
                "threads": self.config.inference_threads,
                "language": self.config.language,
                "durationSeconds": session.duration_seconds,
                "prompt": self._transcription_hint(),
                "timeoutSeconds": max(30, int(session.duration_seconds) + 90),
            }
            self.worker.submit(job)
            return {"session": session.to_dict()}

    def cancel_session(self, session_id: str, *, generation: int | None = None) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id, generation)
            session.state = "cancelled"
            session.updated_at = time.time()
            session.error = {"code": "voice_cancelled", "message": "Voice input was cancelled."}
            self._cleanup_audio(session)
            return {"session": session.to_dict()}

    def session_status(self, session_id: str) -> dict[str, Any]:
        self._drain_worker()
        with self._lock:
            if self._session is None or self._session.id != session_id:
                raise VoiceError("Voice session was not found.", code="voice_session_not_found")
            return {"session": self._session.to_dict()}

    def interpret_transcript(self, payload: dict[str, Any]) -> dict[str, Any]:
        transcript = str(payload.get("transcript") or "")
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        if "witchId" not in context:
            context["witchId"] = str(payload.get("witchId") or "")
        command = self.router.route(transcript, context)
        return {"transcript": transcript, "command": command}

    def _require_session(self, session_id: str, generation: int | None) -> VoiceSession:
        if self._session is None or self._session.id != session_id:
            raise VoiceError("Voice session was not found.", code="voice_session_not_found")
        if generation is not None and self._session.generation != generation:
            raise VoiceError("Voice session generation is stale.", code="stale_voice_session")
        if self._session.state in {"cancelled", "error"}:
            raise VoiceError("Voice session is no longer active.", code="stale_voice_session")
        return self._session

    def _drain_worker(self) -> None:
        for result in self.worker.poll():
            with self._lock:
                session = self._session
                if session is None or session.id != result.get("sessionId") or session.generation != result.get("generation"):
                    self._cleanup_path(Path(str(result.get("audioPath") or "")))
                    continue
                if session.state in TERMINAL_VOICE_STATES:
                    self._cleanup_path(Path(str(result.get("audioPath") or "")))
                    continue
                session.updated_at = time.time()
                if result.get("ok"):
                    transcript = str(result.get("transcript") or "").strip()
                    if not transcript:
                        session.state = "error"
                        session.error = {"code": "voice_empty_transcript", "message": "No speech was recognized."}
                    else:
                        session.state = "transcript_ready"
                        session.result = {
                            "transcript": transcript,
                            "command": self.router.route(transcript, session.context),
                            "engine": self.config.engine,
                            "modelProfile": self.config.model_profile,
                        }
                else:
                    session.state = "error"
                    session.error = {"code": result.get("code") or "voice_transcription_failed", "message": result.get("error") or "Transcription failed."}
                if not self.config.retain_audio:
                    self._cleanup_audio(session)

    def _runtime_status(self) -> dict[str, Any]:
        candidates: list[Path] = []
        if self.config.runtime_executable:
            candidates.append(Path(self.config.runtime_executable).expanduser())
        suffix = ".exe" if os.name == "nt" else ""
        candidates.extend(
            [
                self.runtime_dir / f"whisper-server{suffix}",
                self.runtime_dir / "whisper-server",
                self.runtime_dir / "bin" / f"whisper-server{suffix}",
            ]
        )
        which = shutil.which("whisper-server.exe" if os.name == "nt" else "whisper-server")
        if which:
            candidates.append(Path(which))
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return {"available": True, "path": str(candidate), "note": "whisper.cpp server runtime was found."}
        return {
            "available": False,
            "path": "",
            "note": "whisper.cpp server runtime was not found in the configured voice runtime directory or PATH.",
        }

    def _model_status(self) -> dict[str, Any]:
        profile = VOICE_MODEL_PROFILES[self.config.model_profile]
        path = self.model_dir / profile.filename
        if not path.exists() or not path.is_file():
            return {
                "available": False,
                "verified": False,
                "profile": profile.id,
                "path": str(path),
                "sourceUrl": profile.source_url,
                "expectedSha1": profile.sha1,
                "note": f"Voice model {profile.filename} is not installed.",
            }
        if profile.sha1 is None:
            return {
                "available": True,
                "verified": False,
                "profile": profile.id,
                "path": str(path),
                "sourceUrl": profile.source_url,
                "expectedSha1": None,
                "note": "This model profile has no verified distributed hash; import is blocked until a trusted hash is configured.",
            }
        actual = sha1_file(path)
        verified = actual == profile.sha1
        return {
            "available": True,
            "verified": verified,
            "profile": profile.id,
            "label": profile.label,
            "path": str(path),
            "sourceUrl": profile.source_url,
            "expectedSha1": profile.sha1,
            "actualSha1": actual,
            "sizeMb": profile.size_mb,
            "note": "Voice model hash verified." if verified else "Voice model hash did not match the pinned manifest.",
        }

    def _transcription_hint(self) -> str:
        names = ", ".join(profile["name"] for profile in self.profiles)
        return f"Coven witches: {names}. Terms: Hermes, GovDash, Office, solicitation, compliance matrix."

    def _cleanup_startup_tmp(self) -> None:
        try:
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
            for path in self.tmp_dir.glob("voice-*.wav"):
                self._cleanup_path(path)
        except OSError:
            return

    def _cleanup_terminal_audio(self) -> None:
        with self._lock:
            if self._session is not None and self._session.state in TERMINAL_VOICE_STATES:
                self._cleanup_audio(self._session)

    def _cleanup_audio(self, session: VoiceSession) -> None:
        if session.audio_path is not None:
            self._cleanup_path(session.audio_path)
            if not self.config.retain_audio:
                session.audio_path = None

    def _cleanup_path(self, path: Path) -> None:
        if not str(path):
            return
        try:
            root = self.tmp_dir.resolve()
            resolved = path.resolve()
            resolved.relative_to(root)
            resolved.unlink(missing_ok=True)
        except (OSError, ValueError):
            return


def _voice_worker_main(input_queue: mp.Queue, output_queue: mp.Queue) -> None:
    server: dict[str, Any] | None = None
    while True:
        job = input_queue.get()
        if job.get("type") == "shutdown":
            _stop_whisper_server(server)
            return
        started = time.time()
        audio_path = str(job.get("audioPath") or "")
        try:
            server = _ensure_whisper_server(server, job)
            transcript = _request_whisper_transcript(server, job)
            output_queue.put(
                {
                    "ok": True,
                    "sessionId": job.get("sessionId"),
                    "generation": job.get("generation"),
                    "audioPath": audio_path,
                    "transcript": transcript,
                    "elapsedSeconds": time.time() - started,
                }
            )
        except TimeoutError:
            output_queue.put(
                {
                    "ok": False,
                    "sessionId": job.get("sessionId"),
                    "generation": job.get("generation"),
                    "audioPath": audio_path,
                    "code": "voice_transcription_timeout",
                    "error": "Local transcription timed out.",
                    "elapsedSeconds": time.time() - started,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            if server and server.get("process") is not None and server["process"].poll() is not None:
                server = None
            output_queue.put(
                {
                    "ok": False,
                    "sessionId": job.get("sessionId"),
                    "generation": job.get("generation"),
                    "audioPath": audio_path,
                    "code": "voice_worker_failed",
                    "error": str(exc),
                    "elapsedSeconds": time.time() - started,
                }
            )


def _ensure_whisper_server(server: dict[str, Any] | None, job: dict[str, Any]) -> dict[str, Any]:
    executable = str(job["runtimeExecutable"])
    model_path = str(job["modelPath"])
    threads = int(job.get("threads") or 2)
    language = str(job.get("language") or "en")
    key = (executable, model_path, threads, language)
    if server and server.get("key") == key and server["process"].poll() is None:
        return server
    _stop_whisper_server(server)
    port = _free_loopback_port()
    request_path = f"/coven-voice-{uuid.uuid4().hex}"
    command = [
        executable,
        "-m",
        model_path,
        "-t",
        str(threads),
        "-l",
        language,
        "-nt",
        "-ng",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--request-path",
        request_path,
        "--inference-path",
        "/inference",
    ]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state = {"key": key, "process": process, "baseUrl": f"http://127.0.0.1:{port}{request_path}"}
    deadline = time.time() + 30.0
    health_url = f"{state['baseUrl']}/health"
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("whisper.cpp server exited before becoming ready.")
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if 200 <= response.status < 500:
                    return state
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return state
            time.sleep(0.15)
        except (OSError, urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    _stop_whisper_server(state)
    raise TimeoutError("Timed out waiting for whisper.cpp server to load the selected model.")


def _stop_whisper_server(server: dict[str, Any] | None) -> None:
    if not server:
        return
    process = server.get("process")
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()


def _request_whisper_transcript(server: dict[str, Any], job: dict[str, Any]) -> str:
    audio_path = Path(str(job.get("audioPath") or ""))
    audio = audio_path.read_bytes()
    fields = {
        "response_format": "json",
        "temperature": "0.0",
    }
    prompt = str(job.get("prompt") or "").strip()
    if prompt:
        fields["prompt"] = prompt[:480]
    body, boundary = _multipart_body(fields, "file", audio_path.name or "voice.wav", "audio/wav", audio)
    request = urllib.request.Request(
        f"{server['baseUrl']}/inference",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(job.get("timeoutSeconds") or 120)) as response:
            payload = response.read(1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"whisper.cpp inference failed with HTTP {exc.code}: {detail}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise TimeoutError("Local transcription timed out.") from exc
    return _transcript_from_response(payload)


def _multipart_body(fields: dict[str, str], file_field: str, filename: str, content_type: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = f"coven-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode("ascii"))
    safe_filename = filename.replace('"', "")
    chunks.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_filename}"\r\n'.encode("ascii"))
    chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _transcript_from_response(payload: str) -> str:
    stripped = payload.strip()
    if not stripped:
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return parse_whisper_output(stripped)
    if isinstance(data, dict):
        for key in ("text", "transcription", "result"):
            value = data.get(key)
            if isinstance(value, str):
                return parse_whisper_output(value)
        if isinstance(data.get("segments"), list):
            return parse_whisper_output(" ".join(str(segment.get("text") or "") for segment in data["segments"] if isinstance(segment, dict)))
    return parse_whisper_output(stripped)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_whisper_output(output: str) -> str:
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^\[[0-9:.,\s\->]+\]\s*", "", stripped)
        if stripped:
            lines.append(stripped)
    return " ".join(lines).strip()


def inspect_wav(data: bytes) -> dict[str, Any]:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise VoiceError("Voice audio must be a RIFF/WAVE file.", code="unsupported_audio_format")
    offset = 12
    fmt: dict[str, int] | None = None
    data_size = 0
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        chunk_start = offset + 8
        chunk_end = min(chunk_start + chunk_size, len(data))
        if chunk_id == b"fmt " and chunk_size >= 16:
            audio_format, channels, sample_rate, byte_rate, _block_align, bits = struct.unpack("<HHIIHH", data[chunk_start : chunk_start + 16])
            fmt = {
                "audioFormat": audio_format,
                "channels": channels,
                "sampleRate": sample_rate,
                "byteRate": byte_rate,
                "bitsPerSample": bits,
            }
        elif chunk_id == b"data":
            data_size = chunk_size
        offset = chunk_end + (chunk_size % 2)
    if fmt is None or data_size <= 0:
        raise VoiceError("Voice WAV did not contain usable PCM data.", code="invalid_audio")
    if fmt["audioFormat"] != 1 or fmt["bitsPerSample"] != 16:
        raise VoiceError("Voice WAV must be 16-bit PCM.", code="invalid_audio", details=fmt)
    duration = data_size / max(1, fmt["byteRate"])
    return {**fmt, "dataBytes": data_size, "durationSeconds": duration}


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
