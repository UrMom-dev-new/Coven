from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from coven.agent_adapters import AdapterError, DemoAdapter, HermesAdapter
from coven.configuration import AppConfig, CinematicConfig, ProviderConfig, RuntimeConfig, ServerConfig, load_app_config
from coven.store import CovenStore


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


def hermes_config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8765, data_dir=None),
        runtime=RuntimeConfig(
            mode="live",
            hermes_executable="hermes",
            allow_demo_mode=True,
            hermes_api_base_url="http://hermes.test",
            hermes_api_key_env="HERMES_TEST_KEY",
        ),
        providers=ProviderConfig(
            ollama_base_url="http://127.0.0.1:11434/v1",
            ollama_model="",
            openai_key_env="OPENAI_API_KEY",
            openai_model="",
        ),
        cinematics=CinematicConfig(failure_scene=True, reduced_motion_mode="tableau", mute_by_default=False),
    )


class RecordingHermesAdapter(HermesAdapter):
    def __init__(self, store: CovenStore):
        super().__init__(store, hermes_config())
        self.created_sessions = 0

    def _request(self, method: str, path: str, payload=None):
        if path == "/api/sessions":
            self.created_sessions += 1
            return {"id": "hermes-session-1"}
        if path == "/api/sessions/hermes-session-1/chat":
            return {"message": "session reused"}
        raise AssertionError(f"Unexpected Hermes call: {method} {path}")


class AgentAdapterTests(unittest.TestCase):
    def test_demo_adapter_message_and_task(self):
        with TemporaryDirectory() as tmp:
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = DemoAdapter(store)
            result = adapter.send_message("morgana", "hello")
            self.assertEqual(len(result.messages), 2)

            task = adapter.create_task(
                {"assignee": "circe", "title": "demo", "instructions": "do it", "priority": "normal"}
            ).task
            self.assertEqual(task["mode"], "demo")

    def test_hermes_adapter_requires_api_configuration(self):
        with TemporaryDirectory() as tmp:
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = HermesAdapter(store, load_app_config())
            with self.assertRaises(AdapterError) as caught:
                adapter.send_message("morgana", "hello")
            self.assertEqual(caught.exception.code, "hermes_api_unconfigured")

    def test_hermes_adapter_reuses_persisted_session(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            first = RecordingHermesAdapter(store)
            first.send_message("morgana", "hello")

            second = RecordingHermesAdapter(store)
            second.send_message("morgana", "again")

            self.assertEqual(first.created_sessions, 1)
            self.assertEqual(second.created_sessions, 0)


if __name__ == "__main__":
    unittest.main()
