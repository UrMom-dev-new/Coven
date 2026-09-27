from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

from coven.configuration import load_app_config
from coven.connection_settings import ConnectionSettings, local_endpoint, selected_executable
from coven.server import build_server, PROFILE_PATH
from coven.voice import VoiceError, VoiceService, VOICE_MODEL_PROFILES


class ConnectionTests(unittest.TestCase):
    def test_loopback_only_and_no_credentials_or_arbitrary_api_paths(self):
        self.assertEqual(local_endpoint("http://127.0.0.1:8642/v1/"), "http://127.0.0.1:8642")
        for address in ["https://example.com", "http://example.com:8642", "http://user:secret@localhost:8642",
                        "http://127.0.0.1:8642/other", "http://localhost:0", "http://localhost:8642?key=secret"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                local_endpoint(address)

    def test_external_paths_and_credentials_survive_reload_without_renderer_secret(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "Separate Hermes installation with spaces"
            exe = external / ".venv" / "Scripts" / "hermes.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"test executable fixture")
            settings = ConnectionSettings(load_app_config(), root / "Coven data")
            settings.save_hermes({"executable": str(external), "home": str(external),
                                  "baseUrl": "http://127.0.0.1:8642", "apiKey": "test-only-private-key"})
            loaded = ConnectionSettings(load_app_config(), root / "Coven data")
            self.assertEqual(loaded.effective_config().runtime.hermes_executable, str(exe.resolve()))
            self.assertEqual(loaded.api_key(), "test-only-private-key")
            self.assertTrue(loaded.status()["hermes"]["keySaved"])
            self.assertNotIn("test-only-private-key", json.dumps(loaded.status()))
            self.assertNotIn("test-only-private-key", loaded.path.read_text())
            with self.assertRaises(ValueError):
                loaded.save_hermes({"baseUrl": "http://127.0.0.1:8643"})

    def test_bad_saved_config_recovers_to_editable_defaults(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "setup").mkdir()
            for saved in [{"voice": {"modelProfile": "invalid"}}, {"hermes": "bad"}, {"voice": {"enabled": "yes"}}]:
                (root / "setup" / "connections.json").write_text(json.dumps(saved))
                settings = ConnectionSettings(load_app_config(), root)
                self.assertTrue(settings.load_error)
                self.assertEqual(settings.effective_config().voice.model_profile, "base.en-q5_1")

    def test_start_uses_explicit_home_and_background_process_without_shell(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "hermes.exe"
            exe.touch()
            settings = ConnectionSettings(load_app_config(), root / "coven")
            settings.save_hermes({"executable": str(exe), "home": str(root), "baseUrl": "http://127.0.0.1:8642"})
            with mock.patch("coven.connection_settings.socket.create_connection", side_effect=OSError), \
                 mock.patch("coven.connection_settings.subprocess.Popen") as popen:
                popen.return_value.poll.return_value = None
                settings.start_hermes()
                args, kwargs = popen.call_args
                self.assertEqual(args[0], [str(exe.resolve()), "gateway"])
                self.assertEqual(kwargs["env"]["HERMES_HOME"], str(root.resolve()))
                self.assertTrue(kwargs["env"]["API_SERVER_KEY"])
                self.assertEqual(kwargs["env"]["API_SERVER_HOST"], "127.0.0.1")
                self.assertNotIn("shell", kwargs)
                if os.name == "nt":
                    self.assertTrue(kwargs["creationflags"])
                settings.close()
                popen.return_value.terminate.assert_called_once()

    def test_model_hash_is_cached_until_file_changes_and_bad_selected_runtime_does_not_fall_back(self):
        with TemporaryDirectory() as tmp:
            service = VoiceService(load_app_config(), Path(tmp), PROFILE_PATH)
            service.model_dir.mkdir(parents=True)
            model = service.model_dir / VOICE_MODEL_PROFILES[service.config.model_profile].filename
            model.write_bytes(b"fixture-a")
            with mock.patch("coven.voice.sha1_file", wraps=lambda path: hashlib.sha1(path.read_bytes()).hexdigest()) as digest:
                first = service._model_status()
                service._model_status()
                self.assertEqual(digest.call_count, 1)
                model.write_bytes(b"fixture-b-longer")
                second = service._model_status()
                self.assertEqual(digest.call_count, 2)
                self.assertNotEqual(first["actualSha1"], second["actualSha1"])
            service.config = replace(service.config, runtime_executable=str(Path(tmp) / "missing.exe"))
            with mock.patch("coven.voice.shutil.which", return_value=str(model)):
                self.assertFalse(service._runtime_status()["available"])
            service.close()


class SettingsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / "config.json"
        self.config.write_text('{"runtime":{"mode":"live"}}')
        self.server = build_server("127.0.0.1", 0, self.root / "data", config_path=self.config, auth_token="settings-test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.cookie = f"coven_session={self.server.auth.create_session('settings-test-token')}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, path, payload=None, authenticated=True, intent=True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Cookie"] = self.cookie
        if intent:
            headers["X-Coven-Intent"] = "ui-action"
        request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def test_settings_routes_require_session_and_write_intent(self):
        self.assertEqual(self.request("/api/setup/connections", authenticated=False)[0], 401)
        self.assertEqual(self.request("/api/setup/voice", {"enabled": False}, intent=False)[0], 403)
        self.assertEqual(self.request("/api/setup/voice/install", {}, authenticated=False)[0], 401)

    def test_save_applies_to_running_adapter_and_checks_real_http_capabilities(self):
        class HermesFixture(BaseHTTPRequestHandler):
            capabilities = True
            def log_message(self, *_args):
                pass
            def do_GET(self):
                authenticated = self.headers.get("Authorization") == "Bearer fixture-private-key"
                payload = {"features": {"run_submission": self.capabilities, "run_status": self.capabilities}} if authenticated else {}
                body = json.dumps(payload).encode()
                self.send_response(200 if authenticated else 401)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        hermes = ThreadingHTTPServer(("127.0.0.1", 0), HermesFixture)
        thread = threading.Thread(target=hermes.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{hermes.server_port}"
            code, result = self.request("/api/setup/hermes", {"baseUrl": endpoint, "apiKey": "fixture-private-key"})
            self.assertEqual(code, 200)
            self.assertEqual(self.server.agent_adapter.base_url, endpoint)
            self.assertEqual(self.server.agent_adapter.api_key, "fixture-private-key")
            self.assertNotIn("fixture-private-key", json.dumps(result))
            code, result = self.request("/api/setup/hermes/test", {})
            self.assertEqual(code, 200)
            self.assertTrue(result["test"]["ready"])
            HermesFixture.capabilities = False
            self.assertFalse(self.request("/api/setup/hermes/test", {})[1]["test"]["ready"])
            reloaded = ConnectionSettings(load_app_config(self.config), self.root / "data")
            self.assertEqual(reloaded.effective_config().runtime.hermes_api_base_url, endpoint)
        finally:
            hermes.shutdown()
            hermes.server_close()
            thread.join(timeout=2)

    def test_pending_live_task_blocks_runtime_switch(self):
        self.server.store.create_live_task(assignee="morgana", title="Pending task", instructions="test", priority="normal",
            idempotency_key="settings-pending-test", session_id=None, requested_runtime={}, request_payload={})
        code, result = self.request("/api/setup/hermes", {"baseUrl": "http://127.0.0.1:8642"})
        self.assertEqual(code, 400)
        self.assertIn("pending live tasks", result["error"])

    def test_voice_changes_apply_without_restart_and_do_not_interrupt_recording(self):
        code, _ = self.request("/api/setup/voice", {"enabled": False, "microphoneId": "test-microphone"})
        self.assertEqual(code, 200)
        self.assertFalse(self.server.voice.config.enabled)
        self.assertEqual(self.server.voice.config.microphone_id, "test-microphone")
        with mock.patch.object(self.server.voice, "require_idle", side_effect=VoiceError("Finish recording")):
            self.assertEqual(self.request("/api/setup/voice", {"enabled": True})[0], 409)
        self.assertFalse(self.server.connections.effective_config().voice.enabled)


if __name__ == "__main__":
    unittest.main()
