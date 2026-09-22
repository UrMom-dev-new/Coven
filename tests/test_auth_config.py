import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from coven.auth import AuthManager, is_allowed_origin
from coven.configuration import ConfigError, load_app_config, parse_bool


class AuthConfigTests(unittest.TestCase):
    def test_bootstrap_token_creates_one_session(self):
        auth = AuthManager(bootstrap_token="secret")
        session = auth.create_session("secret")

        self.assertTrue(auth.is_valid_cookie(f"coven_session={session}"))
        with self.assertRaises(PermissionError):
            auth.create_session("secret")

    def test_wrong_origin_is_rejected(self):
        self.assertTrue(
            is_allowed_origin(
                host_header="127.0.0.1:8765",
                origin_header="http://127.0.0.1:8765",
                allowed_hosts={"127.0.0.1", "localhost", "::1"},
                server_port=8765,
            )
        )
        self.assertFalse(
            is_allowed_origin(
                host_header="127.0.0.1:8765",
                origin_header="http://evil.example:8765",
                allowed_hosts={"127.0.0.1", "localhost", "::1"},
                server_port=8765,
            )
        )
        self.assertFalse(
            is_allowed_origin(
                host_header="127.0.0.1:9999",
                origin_header="http://127.0.0.1:9999",
                allowed_hosts={"127.0.0.1", "localhost", "::1"},
                server_port=8765,
            )
        )

    def test_bool_parser_does_not_treat_false_string_as_true(self):
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertTrue(parse_bool("true"))
        with self.assertRaises(ConfigError):
            parse_bool("maybe")

    def test_environment_demo_mode_false_is_live(self):
        with mock.patch.dict(os.environ, {"COVEN_DEMO_MODE": "false"}, clear=False):
            self.assertEqual(load_app_config().runtime.mode, "live")
        with mock.patch.dict(os.environ, {"COVEN_DEMO_MODE": "true"}, clear=False):
            self.assertEqual(load_app_config().runtime.mode, "demo")

    def test_integration_config_validation(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "coven.json"
            path.write_text('{"microsoftGraph": {"cloud": "moon"}}', encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_app_config(path)

            path.write_text('{"govdash": {"route": "telepathy"}}', encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_app_config(path)

    def test_workspace_roots_can_include_environment_entries(self):
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"COVEN_ALLOWED_WORKSPACE_ROOTS": tmp}, clear=False):
            roots = load_app_config().workspace.allowed_roots

            self.assertIn(Path(tmp).resolve(), roots)


if __name__ == "__main__":
    unittest.main()
