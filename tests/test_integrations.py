from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coven.configuration import (
    AppConfig,
    CinematicConfig,
    GovDashConfig,
    MicrosoftGraphConfig,
    OfficeConfig,
    ProviderConfig,
    RuntimeConfig,
    ServerConfig,
    WorkspaceConfig,
)
from coven.integrations import IntegrationManager


def integration_config(**overrides) -> AppConfig:
    config = AppConfig(
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
    for field, value in overrides.items():
        config = replace(config, **{field: value})
    return config


class IntegrationTests(unittest.TestCase):
    def test_default_statuses_are_disabled_or_blocked(self):
        manager = IntegrationManager(integration_config())
        status = manager.status()

        self.assertFalse(status["workspace"]["operational"])
        self.assertFalse(status["office"]["configured"])
        self.assertFalse(status["microsoftGraph"]["operational"])
        self.assertFalse(status["govdash"]["operational"])
        self.assertTrue(any(schema["name"] == "files.validate_artifacts" for schema in status["toolSchemas"]))

    def test_file_validation_operation_uses_workspace_roots(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "artifact.txt"
            target.write_text("ok", encoding="utf-8")
            manager = IntegrationManager(integration_config(workspace=WorkspaceConfig(allowed_roots=(root,))))

            result = manager.execute_office_operation("files.validate_artifacts", {"artifacts": [str(target)]})

            self.assertEqual(result["artifacts"][0]["state"], "inspected")
            self.assertEqual(result["artifacts"][0]["path"], str(target.resolve()))

    def test_govdash_sharepoint_route_requires_selected_root(self):
        manager = IntegrationManager(
            integration_config(govdash=GovDashConfig(enabled=True, route="sharepoint", sharepoint_root=""))
        )

        status = manager.govdash_status()

        self.assertEqual(status["state"], "blocked")
        self.assertIn("SharePoint exchange route", status["notes"][0])

    def test_graph_requires_delegated_runtime_token_configuration(self):
        manager = IntegrationManager(
            integration_config(
                microsoft_graph=MicrosoftGraphConfig(
                    enabled=True,
                    cloud="gcc_high",
                    tenant_id="tenant",
                    client_id="client",
                    token_environment_variable="COVEN_MISSING_TEST_TOKEN",
                )
            )
        )

        status = manager.microsoft_graph_status()

        self.assertEqual(status["endpoint"], "https://graph.microsoft.us")
        self.assertFalse(status["operational"])
        self.assertIn("COVEN_MISSING_TEST_TOKEN", status["notes"][-1])

    def test_office_operation_fails_closed_when_bridge_is_not_operational(self):
        manager = IntegrationManager(integration_config(office=OfficeConfig(enabled=True)))

        with self.assertRaises(RuntimeError):
            manager.execute_office_operation("office.word.inspect_structure", {"path": "proposal.docx"})


if __name__ == "__main__":
    unittest.main()
