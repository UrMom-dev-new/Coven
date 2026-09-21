from pathlib import Path
from unittest import mock
import unittest

from coven.configuration import AppConfig, CinematicConfig, ProviderConfig, RuntimeConfig, ServerConfig
from coven.runtime import RuntimeInspector


def live_config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8765, data_dir=Path("/tmp/coven-test")),
        runtime=RuntimeConfig(
            mode="live",
            hermes_executable="hermes",
            allow_demo_mode=True,
            hermes_api_base_url="http://hermes.test",
            hermes_api_key_env="HERMES_TEST_KEY",
        ),
        providers=ProviderConfig(
            ollama_base_url="http://127.0.0.1:11434/v1",
            ollama_model="llama-local",
            openai_key_env="OPENAI_API_KEY",
            openai_model="gpt-test",
        ),
        cinematics=CinematicConfig(failure_scene=True, reduced_motion_mode="tableau", mute_by_default=False),
    )


class RuntimeProbeTests(unittest.TestCase):
    def test_hermes_api_probe_requires_runs_capabilities(self):
        inspector = RuntimeInspector(live_config())

        def fake_http(url: str, _api_key: str, *, timeout: float):
            if url.endswith("/health"):
                return {"ok": True, "status": 200, "json": {"ok": True}}
            if url.endswith("/v1/capabilities"):
                return {
                    "ok": True,
                    "status": 200,
                    "json": {
                        "model": "gpt-test",
                        "features": {
                            "run_submission": True,
                            "run_status": True,
                            "run_events_sse": True,
                            "run_stop": True,
                            "run_approval": True,
                        },
                    },
                }
            if url.endswith("/health/detailed"):
                return {"ok": True, "status": 200, "json": {"status": "ready", "readiness": {"checks": {"model": True}}}}
            if url.endswith("/api/model/options"):
                return {"ok": True, "status": 200, "json": {"providers": []}}
            return {"ok": False, "error": "unexpected"}

        with mock.patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            inspector._http_json = fake_http  # type: ignore[method-assign]
            probe = inspector._probe_hermes_api()

        self.assertTrue(probe["configured"])
        self.assertTrue(probe["authenticated"])
        self.assertTrue(probe["taskCapable"])
        self.assertTrue(probe["runEventsCapable"])
        self.assertTrue(probe["approvalCapable"])
        self.assertTrue(probe["stopCapable"])
        self.assertTrue(probe["modelOptionsAvailable"])

    def test_hermes_api_probe_does_not_treat_health_only_as_ready(self):
        inspector = RuntimeInspector(live_config())

        def fake_http(url: str, _api_key: str, *, timeout: float):
            if url.endswith("/health"):
                return {"ok": True, "status": 200, "json": {"ok": True}}
            return {"ok": False, "status": 404, "error": "missing"}

        with mock.patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            inspector._http_json = fake_http  # type: ignore[method-assign]
            probe = inspector._probe_hermes_api()

        self.assertTrue(probe["reachable"])
        self.assertFalse(probe["taskCapable"])
        self.assertIn("Capabilities check failed", " ".join(probe["notes"]))


if __name__ == "__main__":
    unittest.main()
