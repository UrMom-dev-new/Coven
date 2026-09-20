from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coven.agent_adapters import AdapterError, DemoAdapter, HermesAdapter
from coven.configuration import load_app_config
from coven.store import CovenStore


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


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


if __name__ == "__main__":
    unittest.main()
