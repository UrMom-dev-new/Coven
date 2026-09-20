from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from coven.store import CovenStore


PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "witches.json"


class StoreTests(unittest.TestCase):
    def make_store(self, tmp_dir: str) -> CovenStore:
        return CovenStore(Path(tmp_dir), PROFILE_PATH)

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

            self.assertEqual(store.conversations("morgana", namespace="demo")[0]["text"], "demo note")
            self.assertEqual(store.conversations("morgana", namespace="live")[0]["text"], "live note")
            self.assertEqual(store.snapshot(namespace="live")["tasks"], [])

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
