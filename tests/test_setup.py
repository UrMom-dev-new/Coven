from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from coven.configuration import (
    AppConfig,
    CinematicConfig,
    ProviderConfig,
    RuntimeConfig,
    ServerConfig,
    VoiceConfig,
)
from coven.integrations import IntegrationManager
from coven.setup import HERMES_PIN, PROVIDER_SECRET, SetupManager
from coven.voice import VoiceService


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


def app_config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8765, data_dir=None),
        runtime=RuntimeConfig(
            mode="live",
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
        voice=VoiceConfig(enabled=True),
    )


class SetupTests(unittest.TestCase):
    def make_manager(self, root: Path) -> SetupManager:
        voice = VoiceService(app_config(), root, PROFILE_PATH)
        return SetupManager(app_config(), root, voice)

    def test_provider_secret_is_not_written_to_setup_state_or_bundle(self):
        with TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            manager.save_provider({"apiKey": "sk-test-secret", "model": "gpt-test"})
            state_text = manager.state_path.read_text(encoding="utf-8")
            bundle = manager.support_bundle()

            self.assertNotIn("sk-test-secret", state_text)
            self.assertNotIn("sk-test-secret", json.dumps(bundle))
            self.assertIn(PROVIDER_SECRET, state_text)

    def test_workspace_must_exist_and_be_writable(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            workspace = root / "My Coven Work"
            workspace.mkdir()

            status = manager.save_workspace({"path": str(workspace)})["steps"]

            workspace_step = next(step for step in status if step["id"] == "workspace")
            self.assertEqual(workspace_step["state"], "ready")

    def test_setup_workspace_can_feed_integration_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            workspace = root / "Work"
            workspace.mkdir()
            output = workspace / "result.txt"
            output.write_text("done", encoding="utf-8")
            manager.save_workspace({"path": str(workspace)})
            integrations = IntegrationManager(app_config())
            integrations.set_dynamic_workspace_roots(manager.workspace_roots())

            status = integrations.workspace_status()
            artifacts = integrations.validate_artifact_claims([{"path": str(output)}])

            self.assertTrue(status["operational"])
            self.assertEqual(artifacts[0]["state"], "inspected")

    def test_setup_manifest_pins_hermes_release_tag(self):
        self.assertEqual(HERMES_PIN["tag"], "v2026.9.21")
        self.assertIn("install.ps1", HERMES_PIN["installScript"])


if __name__ == "__main__":
    unittest.main()
