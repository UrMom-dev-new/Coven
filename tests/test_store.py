from pathlib import Path
from tempfile import TemporaryDirectory
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

            state = store.snapshot(demo_mode=True)
            state["tasks"][0]["createdAt"] = "2020-01-01T00:00:00+00:00"
            store._write(state)

            updated = store.snapshot(demo_mode=True)
            failed = next(item for item in updated["tasks"] if item["id"] == task["id"])
            pending = store.pending_failure_events()

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
            state = store.snapshot(demo_mode=True)
            state["tasks"][0]["createdAt"] = "2020-01-01T00:00:00+00:00"
            store._write(state)
            store.snapshot(demo_mode=True)

            retry = store.retry_task(task["id"])

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
                store.retry_task(task["id"])


if __name__ == "__main__":
    unittest.main()
