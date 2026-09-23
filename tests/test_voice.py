from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest

from coven.configuration import (
    AppConfig,
    CinematicConfig,
    ProviderConfig,
    RuntimeConfig,
    ServerConfig,
    VoiceConfig,
)
from coven.voice import VoiceCommandRouter, VoiceError, VoiceService, _transcript_from_response, inspect_wav


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


def app_config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8765, data_dir=None),
        runtime=RuntimeConfig(
            mode="demo",
            hermes_executable="hermes",
            allow_demo_mode=True,
            hermes_api_base_url="",
            hermes_api_key_env="HERMES_API_SERVER_KEY",
        ),
        providers=ProviderConfig(
            ollama_base_url="http://127.0.0.1:11434/v1",
            ollama_model="",
            openai_key_env="OPENAI_API_KEY",
            openai_model="",
        ),
        cinematics=CinematicConfig(failure_scene=True, reduced_motion_mode="tableau", mute_by_default=False),
        voice=VoiceConfig(enabled=True, max_duration_seconds=60),
    )


class FakeWorker:
    def __init__(self):
        self.jobs = []
        self.results = []

    def submit(self, job):
        self.jobs.append(job)

    def poll(self):
        results = list(self.results)
        self.results.clear()
        return results

    def snapshot(self):
        return {"running": True, "pending": len(self.jobs)}

    def close(self):
        return None


def wav_bytes(duration_seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    frames = int(duration_seconds * sample_rate)
    data = b"\x00\x00" * frames
    header = bytearray()
    header.extend(b"RIFF")
    header.extend(struct.pack("<I", 36 + len(data)))
    header.extend(b"WAVEfmt ")
    header.extend(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    header.extend(b"data")
    header.extend(struct.pack("<I", len(data)))
    return bytes(header) + data


class VoiceTests(unittest.TestCase):
    def profiles(self):
        import json

        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))["witches"]

    def make_service(self, tmp: str, worker: FakeWorker | None = None) -> VoiceService:
        service = VoiceService(app_config(), Path(tmp), PROFILE_PATH, worker=worker or FakeWorker())
        service._runtime_status = lambda: {"available": True, "path": "/bin/echo", "note": "test runtime"}  # type: ignore[method-assign]
        service._model_status = lambda: {  # type: ignore[method-assign]
            "available": True,
            "verified": True,
            "path": str(Path(tmp) / "model.bin"),
            "profile": "base.en-q5_1",
            "label": "base.en Q5_1",
            "note": "test model",
        }
        return service

    def test_router_executes_only_explicit_local_commands(self):
        router = VoiceCommandRouter(self.profiles())

        self.assertEqual(router.route("Select Circe", {"witchId": "morgana"})["action"], "select_witch")
        self.assertEqual(router.route("Open the journal", {"witchId": "morgana"})["view"], "journal")
        self.assertEqual(router.route("Show Circe's tasks", {"witchId": "morgana"})["action"], "show_tasks")
        self.assertEqual(router.route("Stop speaking", {"witchId": "morgana"})["action"], "stop_speaking")
        self.assertEqual(router.route("Please stop adding detail", {"witchId": "morgana"})["action"], "draft_message")

    def test_router_prepares_addressed_and_integration_requests_as_drafts(self):
        router = VoiceCommandRouter(self.profiles())

        addressed = router.route("Circe, draft a compliance matrix from this solicitation", {"witchId": "morgana"})
        self.assertEqual(addressed["action"], "draft_task")
        self.assertEqual(addressed["witchId"], "circe")

        govdash = router.route("Update this document in GovDash", {"witchId": "hecate"})
        self.assertEqual(govdash["action"], "draft_task")
        self.assertEqual(govdash["integration"], "govdash")

    def test_wav_validation_rejects_too_short_audio_at_service_boundary(self):
        with TemporaryDirectory() as tmp:
            service = self.make_service(tmp)
            session = service.start_session({"witchId": "morgana", "inputMode": "message"})["session"]

            with self.assertRaises(VoiceError) as caught:
                service.finish_session_audio(session["id"], generation=session["generation"], audio=wav_bytes(0.05), content_type="audio/wav")

            self.assertEqual(caught.exception.code, "voice_too_short")

    def test_cancel_invalidates_late_audio(self):
        with TemporaryDirectory() as tmp:
            service = self.make_service(tmp)
            session = service.start_session({"witchId": "morgana", "inputMode": "message"})["session"]
            service.cancel_session(session["id"], generation=session["generation"])

            with self.assertRaises(VoiceError) as caught:
                service.finish_session_audio(session["id"], generation=session["generation"], audio=wav_bytes(), content_type="audio/wav")

            self.assertEqual(caught.exception.code, "stale_voice_session")

    def test_stale_worker_results_are_ignored(self):
        with TemporaryDirectory() as tmp:
            worker = FakeWorker()
            service = self.make_service(tmp, worker=worker)
            session = service.start_session({"witchId": "morgana", "inputMode": "message"})["session"]
            service.finish_session_audio(session["id"], generation=session["generation"], audio=wav_bytes(), content_type="audio/wav")

            worker.results.extend(
                [
                    {"ok": True, "sessionId": session["id"], "generation": session["generation"] + 1, "transcript": "Select Circe"},
                    {"ok": True, "sessionId": session["id"], "generation": session["generation"], "transcript": "Select Circe"},
                    {"ok": True, "sessionId": session["id"], "generation": session["generation"], "transcript": "Open settings"},
                ]
            )
            status = service.session_status(session["id"])["session"]

            self.assertEqual(status["state"], "transcript_ready")
            self.assertEqual(status["result"]["command"]["action"], "select_witch")

    def test_inspect_wav_reports_duration(self):
        inspected = inspect_wav(wav_bytes(0.75))

        self.assertEqual(inspected["sampleRate"], 16000)
        self.assertAlmostEqual(inspected["durationSeconds"], 0.75, places=2)

    def test_server_response_parser_accepts_json_and_timestamped_text(self):
        self.assertEqual(_transcript_from_response('{"text": " Select Circe "}'), "Select Circe")
        self.assertEqual(_transcript_from_response("[00:00:00.000 --> 00:00:01.000] Open the journal"), "Open the journal")


if __name__ == "__main__":
    unittest.main()
