from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from coven.agent_adapters import AdapterError, DemoAdapter, HermesAdapter
from coven.configuration import AppConfig, CinematicConfig, ProviderConfig, RuntimeConfig, ServerConfig, load_app_config
from coven.store import USER_MESSAGE_LIMIT, CovenStore


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

    def _request(self, method: str, path: str, payload=None, **_kwargs):
        if path == "/api/sessions":
            self.created_sessions += 1
            return {"id": "hermes-session-1"}
        if path == "/api/sessions/hermes-session-1/chat":
            return {"message": "session reused"}
        raise AssertionError(f"Unexpected Hermes call: {method} {path}")


class ChatPayloadHermesAdapter(HermesAdapter):
    def __init__(self, store: CovenStore, payload):
        super().__init__(store, hermes_config())
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def _request(self, method: str, path: str, payload=None, **_kwargs):
        self.calls.append((method, path))
        if path == "/api/sessions":
            return {"id": "hermes-session-1"}
        if path == "/api/sessions/hermes-session-1/chat":
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload
        raise AssertionError(f"Unexpected Hermes call: {method} {path}")


class RunSubmissionHermesAdapter(HermesAdapter):
    def __init__(self, store: CovenStore):
        config = hermes_config()
        config = replace(config, providers=replace(config.providers, openai_model="gpt-test"))
        super().__init__(store, config)
        self.submission_payload = None
        self.submission_headers = None

    def _request(self, method: str, path: str, payload=None, **_kwargs):
        if path == "/api/sessions":
            return {"id": "session-task"}
        if path == "/v1/capabilities":
            return {"features": {"run_submission": True, "run_status": True, "run_stop": True, "run_approval": True}}
        if path == "/v1/runs/run-123":
            return {
                "run_id": "run-123",
                "session_id": "session-task",
                "status": "completed",
                "output": "Created the requested artifact.",
                "runtime": {"provider": "openai", "model": "gpt-test"},
                "usage": {"total_tokens": 42},
                "artifacts": [{"path": "C:/CovenTest/out.txt", "exists": True}],
            }
        raise AssertionError(f"Unexpected Hermes call: {method} {path}")

    def _request_with_headers(self, method: str, path: str, payload=None, *, headers=None, timeout=20):
        if method == "POST" and path == "/v1/runs":
            self.submission_payload = payload
            self.submission_headers = headers
            return {"Idempotency-Replayed": "false"}, {"run_id": "run-123", "status": "running", "session_id": "session-task"}
        return {}, self._request(method, path, payload, timeout=timeout)


class AgentAdapterTests(unittest.TestCase):
    def test_demo_adapter_message_and_task(self):
        with TemporaryDirectory() as tmp:
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = DemoAdapter(store)
            result = adapter.send_message("morgana", "hello")
            self.assertEqual(len(result.messages), 4)
            self.assertEqual(result.messages[-2]["text"], "hello")
            self.assertEqual(result.messages[-1]["author"], "morgana")

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

    def test_hermes_empty_chat_response_is_not_success(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = ChatPayloadHermesAdapter(store, {})

            with self.assertRaises(AdapterError) as caught:
                adapter.send_message("morgana", "hello")

            self.assertEqual(caught.exception.code, "hermes_empty_response")

    def test_hermes_long_assistant_reply_is_persisted(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            long_reply = "x" * 9000
            adapter = ChatPayloadHermesAdapter(store, {"message": long_reply})

            result = adapter.send_message("morgana", "hello")

            self.assertEqual(result.messages[-1]["text"], long_reply)

    def test_hermes_rejects_oversized_user_input_before_dispatch(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = ChatPayloadHermesAdapter(store, {"message": "unreachable"})

            with self.assertRaises(AdapterError) as caught:
                adapter.send_message("morgana", "x" * (USER_MESSAGE_LIMIT + 1))

            self.assertEqual(caught.exception.code, "message_too_large")
            self.assertEqual(adapter.calls, [])
            self.assertEqual(store.conversations("morgana", namespace="live"), [])

    def test_hermes_timeout_marks_outgoing_message_uncertain(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = ChatPayloadHermesAdapter(
                store,
                AdapterError("timed out after dispatch", code="hermes_timeout"),
            )

            with self.assertRaises(AdapterError):
                adapter.send_message("morgana", "hello")

            messages = store.conversations("morgana", namespace="live")
            self.assertEqual(messages[-1]["author"], "user")
            self.assertEqual(messages[-1]["delivery"]["state"], "uncertain")
            self.assertEqual(messages[-1]["delivery"]["code"], "hermes_timeout")

    def test_live_task_uses_runs_api_and_records_runtime_evidence(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = RunSubmissionHermesAdapter(store)

            result = adapter.create_task(
                {
                    "assignee": "circe",
                    "title": "Build a fixture",
                    "instructions": "Write a tiny test file.",
                    "priority": "high",
                    "routeMode": "api",
                    "idempotencyKey": "coven-test-key",
                }
            )

            self.assertEqual(result.task["status"], "completed")
            self.assertEqual(result.task["hermes"]["runId"], "run-123")
            self.assertEqual(result.task["requestedRuntime"]["provider"], "openai")
            self.assertEqual(result.task["requestedRuntime"]["model"], "gpt-test")
            self.assertEqual(result.task["runtime"]["provider"], "openai")
            self.assertEqual(result.task["usage"]["total_tokens"], 42)
            self.assertEqual(result.task["artifacts"][0]["path"], "C:/CovenTest/out.txt")
            self.assertEqual(adapter.submission_headers["Idempotency-Key"], "coven-test-key")
            self.assertIn("Coven task: Build a fixture", adapter.submission_payload["input"])
            self.assertIn("You are Circe, builder", adapter.submission_payload["instructions"])

    def test_live_task_validation_happens_before_remote_probe(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"HERMES_TEST_KEY": "secret"}):
            store = CovenStore(Path(tmp), PROFILE_PATH)
            adapter = ChatPayloadHermesAdapter(store, {"message": "unreachable"})

            with self.assertRaises(AdapterError) as caught:
                adapter.create_task({"assignee": "circe", "title": "", "instructions": "", "priority": "normal"})

            self.assertEqual(caught.exception.code, "invalid_task")
            self.assertEqual(adapter.calls, [])
            self.assertEqual(store.snapshot(namespace="live")["tasks"], [])


if __name__ == "__main__":
    unittest.main()
