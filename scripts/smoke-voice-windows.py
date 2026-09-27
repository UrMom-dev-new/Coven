"""Exercise the shipping voice installer and CPU transcription on Windows CI."""
from __future__ import annotations

import multiprocessing
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coven.configuration import load_app_config
from coven.connection_settings import ConnectionSettings
from coven.voice import VoiceService
from coven.voice_install import VoiceInstaller, download_verified


def main():
    with tempfile.TemporaryDirectory(prefix="coven-voice-smoke-") as temporary:
        root = Path(temporary)
        settings = ConnectionSettings(load_app_config(), root)
        installer = VoiceInstaller(root / "installed", settings.save_voice)
        voice = None
        try:
            installer.start("tiny.en-q5_1")
            deadline = time.monotonic() + 300
            previous = ""
            while installer.busy and time.monotonic() < deadline:
                status = installer.status()
                if status["message"] != previous:
                    print(status["message"], flush=True)
                    previous = status["message"]
                threading.Event().wait(0.2)
            if installer.status()["state"] != "completed":
                raise RuntimeError(f"Voice installation failed: {installer.status()}")
            # Public-domain speech fixture, pinned to the same upstream release.
            audio = root / "sample.wav"
            download_verified("https://raw.githubusercontent.com/ggml-org/whisper.cpp/v1.8.3/samples/jfk.wav", audio,
                              "59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e", "sha256",
                              threading.Event(), lambda *_: None, limit=1024 * 1024)
            # Reload saved paths to exercise the next-launch configuration path.
            config = ConnectionSettings(load_app_config(), root).effective_config()
            voice = VoiceService(config, root, ROOT / "config" / "witches.json")
            assert voice.status()["state"] == "ready", voice.status()
            session = voice.start_session({"witchId": "morgana", "inputMode": "dictation"})["session"]
            voice.finish_session_audio(session["id"], generation=session["generation"], audio=audio.read_bytes(), content_type="audio/wav")
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                result = voice.session_status(session["id"])["session"]
                if result["state"] == "error":
                    raise RuntimeError(f"Local transcription failed: {result['error']}")
                if result["state"] == "transcript_ready":
                    transcript = result["result"]["transcript"].lower()
                    assert "country" in transcript and "you" in transcript, transcript
                    print("Verified download, persisted settings, and real CPU transcription passed.", flush=True)
                    return 0
                threading.Event().wait(0.2)
            raise RuntimeError("Timed out waiting for real local transcription.")
        finally:
            installer.close()
            if voice is not None:
                voice.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
