import unittest

from coven.events import normalize_runtime_event, should_trigger_failure_cinematic


class EventTests(unittest.TestCase):
    def test_terminal_failure_event_triggers_once(self):
        raw = {
            "id": "event-1",
            "taskId": "task-1",
            "attemptId": "attempt-1",
            "status": "failed",
            "outcomeKind": "terminal_failure",
            "terminal": True,
            "retryPolicyExhausted": True,
        }

        self.assertTrue(should_trigger_failure_cinematic(raw, set()))
        self.assertFalse(should_trigger_failure_cinematic(raw, {"event-1"}))

    def test_transient_error_does_not_trigger_cinematic(self):
        raw = {
            "id": "event-2",
            "taskId": "task-2",
            "status": "failed",
            "terminal": False,
            "retryPolicyExhausted": False,
            "reason": "tool_error",
            "message": "A tool failed but the run can continue.",
        }

        event = normalize_runtime_event(raw)
        self.assertEqual(event.outcome_kind, "tool_error")
        self.assertFalse(should_trigger_failure_cinematic(raw, set()))

    def test_string_false_does_not_count_as_boolean_true(self):
        raw = {
            "id": "event-4",
            "taskId": "task-4",
            "status": "failed",
            "outcomeKind": "terminal_failure",
            "terminal": "false",
            "retryPolicyExhausted": "true",
        }

        self.assertFalse(should_trigger_failure_cinematic(raw, set()))

    def test_unknown_failed_event_does_not_trigger(self):
        raw = {
            "id": "event-5",
            "taskId": "task-5",
            "status": "failed",
            "terminal": True,
            "retryPolicyExhausted": True,
        }

        self.assertFalse(should_trigger_failure_cinematic(raw, set()))

    def test_cancelled_task_does_not_trigger_even_if_failed_status(self):
        raw = {
            "id": "event-3",
            "taskId": "task-3",
            "status": "failed",
            "terminal": True,
            "retryPolicyExhausted": True,
            "reason": "cancelled",
        }

        self.assertFalse(should_trigger_failure_cinematic(raw, set()))


if __name__ == "__main__":
    unittest.main()
