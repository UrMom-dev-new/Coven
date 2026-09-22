from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from coven.store import CovenStore


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


class StoreTests(unittest.TestCase):
    def make_store(self, tmp_dir: str) -> CovenStore:
        return CovenStore(Path(tmp_dir), PROFILE_PATH)

    def live_payload(self, *, title: str = "Diagnose failure", instructions: str = "Inspect the broken run.") -> dict:
        return {
            "input": f"Coven task: {title}\n\n{instructions}",
            "session_id": "session-1",
            "instructions": "You are Ophelia.",
        }

    def test_demo_failure_is_persisted_before_cinematic(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            task = store.create_task(
                assignee="circe",
                title="Controlled fail fixture",
                instructions="Please fail for test coverage.",
                priority="normal",
            )

            state = store._read()
            state["namespaces"]["demo"]["tasks"][0]["createdAt"] = "2020-01-01T00:00:00+00:00"
            store._write(state)

            updated = store.snapshot(namespace="demo", advance_demo=True)
            failed = next(item for item in updated["tasks"] if item["id"] == task["id"])
            pending = store.pending_failure_events(namespace="demo")

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["evidence"], ["Failure event persisted before presentation."])
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["taskId"], task["id"])

    def test_retry_creates_separate_attempt(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            task = store.create_task(
                assignee="circe",
                title="Controlled fail fixture",
                instructions="fail",
                priority="normal",
            )
            state = store._read()
            state["namespaces"]["demo"]["tasks"][0]["createdAt"] = "2020-01-01T00:00:00+00:00"
            store._write(state)
            store.snapshot(namespace="demo", advance_demo=True)

            retry = store.retry_task(task["id"], namespace="demo")

            self.assertNotEqual(retry["id"], task["id"])
            self.assertEqual(retry["parentTaskId"], task["id"])
            self.assertEqual(retry["status"], "queued")

    def test_retry_requires_failed_task(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            task = store.create_task(
                assignee="morgana",
                title="Normal task",
                instructions="complete normally",
                priority="normal",
            )

            with self.assertRaises(ValueError):
                store.retry_task(task["id"], namespace="demo")

    def test_demo_and_live_state_are_isolated(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.append_message("morgana", "user", "demo note", namespace="demo")
            store.append_message("morgana", "user", "live note", namespace="live")

            self.assertEqual(store.conversations("morgana", namespace="demo")[0]["text"], "Help me plan the next release.")
            self.assertEqual(store.conversations("morgana", namespace="demo")[-1]["text"], "demo note")
            self.assertEqual(store.conversations("morgana", namespace="live")[0]["text"], "live note")
            self.assertEqual(store.snapshot(namespace="live")["tasks"], [])

    def test_seeded_demo_tasks_are_static_reference_fixtures(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            snapshot = store.snapshot(namespace="demo")
            seeded = {task["title"]: task for task in snapshot["tasks"]}

            self.assertEqual(
                list(seeded),
                ["Prepare project brief", "Review research notes", "Organize archive"],
            )
            self.assertEqual(seeded["Prepare project brief"]["status"], "running")
            self.assertEqual(seeded["Review research notes"]["status"], "needs input")
            self.assertEqual(seeded["Organize archive"]["status"], "completed")

            state = store._read()
            state["namespaces"]["demo"]["tasks"][0]["createdAt"] = "2020-01-01T00:00:00+00:00"
            store._write(state)
            advanced = store.snapshot(namespace="demo", advance_demo=True)

            self.assertEqual(advanced["tasks"][0]["status"], "running")

    def test_runtime_sessions_are_namespaced_and_persisted(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.set_runtime_session("morgana", "hermes-live-123", namespace="live")
            store.set_runtime_session("morgana", "hermes-demo-456", namespace="demo")

            reopened = self.make_store(tmp)

            self.assertEqual(reopened.runtime_session("morgana", namespace="live"), "hermes-live-123")
            self.assertEqual(reopened.runtime_session("morgana", namespace="demo"), "hermes-demo-456")
            self.assertIsNone(reopened.runtime_session("morgana", namespace="live", provider="other"))

    def test_live_task_failure_records_one_terminal_event(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            task = store.create_live_task(
                assignee="ophelia",
                title="Diagnose failure",
                instructions="Inspect the broken run.",
                priority="normal",
                idempotency_key="coven-key-1",
                session_id="session-1",
                requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                request_payload=self.live_payload(),
            )
            store.record_live_submission(task["id"], run_id="run-1", remote_status="running", session_id="session-1")

            failed = store.update_live_task_from_run(
                task["id"],
                {
                    "run_id": "run-1",
                    "status": "failed",
                    "error": "terminal failure from runtime",
                    "events": [
                        {"id": "remote-tool-1", "type": "tool.started", "tool": "shell"},
                        {"id": "remote-tool-2", "type": "tool.completed", "tool": "shell"},
                    ],
                },
            )
            store.update_live_task_from_run(
                task["id"],
                {
                    "run_id": "run-1",
                    "status": "failed",
                    "error": "terminal failure from runtime",
                    "events": [{"id": "remote-tool-1", "type": "tool.started", "tool": "shell"}],
                },
            )

            pending = store.pending_failure_events(namespace="live")
            self.assertEqual(failed["status"], "failed")
            self.assertTrue(failed["retryPolicy"]["exhausted"])
            self.assertEqual(
                [item["id"] for item in store.task(task["id"], namespace="live")["timeline"] if item["id"].startswith("remote-tool")],
                ["remote-tool-1", "remote-tool-2"],
            )
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["taskId"], task["id"])

    def test_live_task_idempotency_key_reuses_same_payload(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            payload = self.live_payload(title="Prepare brief", instructions="Draft the brief.")
            first = store.create_live_task(
                assignee="circe",
                title="Prepare brief",
                instructions="Draft the brief.",
                priority="normal",
                idempotency_key="same-key",
                session_id="session-1",
                requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                request_payload=payload,
            )
            second = store.create_live_task(
                assignee="circe",
                title="Prepare brief",
                instructions="Draft the brief.",
                priority="normal",
                idempotency_key="same-key",
                session_id="session-1",
                requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                request_payload=payload,
            )

            self.assertEqual(second["id"], first["id"])
            self.assertEqual(len(store.snapshot(namespace="live")["tasks"]), 1)

    def test_live_task_idempotency_key_rejects_different_payload(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.create_live_task(
                assignee="circe",
                title="Prepare brief",
                instructions="Draft the brief.",
                priority="normal",
                idempotency_key="same-key",
                session_id="session-1",
                requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                request_payload=self.live_payload(title="Prepare brief", instructions="Draft the brief."),
            )

            with self.assertRaises(ValueError):
                store.create_live_task(
                    assignee="circe",
                    title="Prepare brief",
                    instructions="Draft a different brief.",
                    priority="normal",
                    idempotency_key="same-key",
                    session_id="session-1",
                    requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                    request_payload=self.live_payload(title="Prepare brief", instructions="Draft a different brief."),
                )

    def test_terminal_live_task_ignores_late_running_update(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            task = store.create_live_task(
                assignee="ophelia",
                title="Complete once",
                instructions="Finish the work.",
                priority="normal",
                idempotency_key="terminal-key",
                session_id="session-1",
                requested_runtime={"routeMode": "api", "provider": "openai", "model": "gpt-test"},
                request_payload=self.live_payload(title="Complete once", instructions="Finish the work."),
            )
            store.record_live_submission(task["id"], run_id="run-1", remote_status="running", session_id="session-1")
            completed = store.update_live_task_from_run(
                task["id"],
                {"run_id": "run-1", "status": "completed", "output": "Done."},
            )
            stale = store.update_live_task_from_run(
                task["id"],
                {"run_id": "run-1", "status": "running"},
            )

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(stale["status"], "completed")
            self.assertEqual(stale["result"], "Done.")
            self.assertEqual(stale["timeline"][-1]["kind"], "stale_ignored")

    def test_old_state_migrates_to_demo_with_backup(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "tasks": [{"id": "old-task", "status": "completed"}],
                        "conversations": {"morgana": [{"text": "old"}]},
                        "events": [],
                        "cinematics": {"shownEventIds": ["old-event"], "skippedEventIds": []},
                    }
                ),
                encoding="utf-8",
            )

            store = self.make_store(tmp)
            migrated = store.snapshot(namespace="demo")

            self.assertEqual(migrated["tasks"][0]["id"], "old-task")
            self.assertEqual(store.snapshot(namespace="live")["tasks"], [])
            self.assertTrue(list(Path(tmp).glob("state.v1-backup-*.json")))

    def test_preferences_validate_booleans_and_options(self):
        with TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            with self.assertRaises(ValueError):
                store.update_preferences({"mute": "false"})
            with self.assertRaises(ValueError):
                store.update_preferences({"reducedMotionMode": "spin"})
            updated = store.update_preferences({"mute": True, "animationQuality": "low"})
            self.assertTrue(updated["mute"])
            self.assertEqual(updated["animationQuality"], "low")


if __name__ == "__main__":
    unittest.main()
