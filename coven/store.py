"""Small JSON store for Coven presentation state and demo fixtures."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import event_to_dict, normalize_runtime_event, should_trigger_failure_cinematic


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_profiles(config_path: Path) -> list[dict[str, Any]]:
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data["witches"]


class CovenStore:
    def __init__(self, data_dir: Path, profile_path: Path):
        self.data_dir = data_dir
        self.profile_path = profile_path
        self.state_path = data_dir / "state.json"
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_state()

    def _ensure_state(self) -> None:
        if self.state_path.exists():
            return
        initial = {
            "version": 1,
            "createdAt": utc_now(),
            "tasks": [],
            "conversations": {},
            "events": [],
            "cinematics": {"shownEventIds": [], "skippedEventIds": []},
            "settings": {
                "cinematicsEnabled": True,
                "reducedMotionMode": "tableau",
                "mute": False,
                "animationQuality": "balanced",
            },
        }
        self._write(initial)

    def _read(self) -> dict[str, Any]:
        with self.state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
        tmp.replace(self.state_path)

    def snapshot(self, *, demo_mode: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            if demo_mode:
                changed = self._advance_demo_tasks(state)
                if changed:
                    self._write(state)
            return deepcopy(state)

    def profiles(self) -> list[dict[str, Any]]:
        return load_profiles(self.profile_path)

    def conversations(self, witch_id: str) -> list[dict[str, Any]]:
        with self._lock:
            state = self._read()
            return deepcopy(state["conversations"].get(witch_id, []))

    def append_message(self, witch_id: str, author: str, text: str) -> list[dict[str, Any]]:
        text = text.strip()
        if not text:
            raise ValueError("Message cannot be empty.")
        with self._lock:
            state = self._read()
            thread = state["conversations"].setdefault(witch_id, [])
            thread.append(
                {
                    "id": f"msg-{uuid.uuid4().hex}",
                    "author": author,
                    "text": text,
                    "timestamp": utc_now(),
                }
            )
            self._write(state)
            return deepcopy(thread)

    def create_task(self, *, assignee: str, title: str, instructions: str, priority: str) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Task title is required.")
        now = utc_now()
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        attempt_id = f"{task_id}-attempt-1"
        combined = f"{title}\n{instructions}".lower()
        demo_outcome = "fail" if "fail" in combined or "error fixture" in combined else "complete"
        task = {
            "id": task_id,
            "attemptId": attempt_id,
            "parentTaskId": None,
            "title": title,
            "instructions": instructions.strip(),
            "assignee": assignee,
            "status": "queued",
            "priority": priority or "normal",
            "mode": "demo",
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "completedAt": None,
            "latestUpdate": "Queued in the explicit demo adapter.",
            "dependencies": [],
            "blockers": [],
            "evidence": [],
            "result": None,
            "lastSuccessfulStep": "Task accepted and persisted.",
            "retryPolicy": {"maxRetries": 0, "attempt": 1, "exhausted": False},
            "demoOutcome": demo_outcome,
            "timeline": [
                {
                    "id": f"evt-{uuid.uuid4().hex[:10]}",
                    "kind": "queued",
                    "message": "Task was queued in demo mode.",
                    "timestamp": now,
                }
            ],
        }
        with self._lock:
            state = self._read()
            state["tasks"].insert(0, task)
            self._write(state)
            return deepcopy(task)

    def retry_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            original = next((task for task in state["tasks"] if task["id"] == task_id), None)
            if original is None:
                raise KeyError(task_id)
            if original["status"] != "failed":
                raise ValueError("Only failed tasks can be retried.")
            attempt = int(original["retryPolicy"]["attempt"]) + 1
            now = utc_now()
            new_task = deepcopy(original)
            new_task["id"] = f"task-{uuid.uuid4().hex[:12]}"
            new_task["attemptId"] = f"{new_task['id']}-attempt-{attempt}"
            new_task["parentTaskId"] = original["id"]
            new_task["status"] = "queued"
            new_task["createdAt"] = now
            new_task["updatedAt"] = now
            new_task["startedAt"] = None
            new_task["completedAt"] = None
            new_task["latestUpdate"] = "Retry queued as a separate tracked attempt."
            new_task["result"] = None
            new_task["lastSuccessfulStep"] = "Retry request accepted and persisted."
            new_task["retryPolicy"] = {"maxRetries": 0, "attempt": attempt, "exhausted": False}
            new_task["demoOutcome"] = "complete"
            new_task["timeline"] = [
                {
                    "id": f"evt-{uuid.uuid4().hex[:10]}",
                    "kind": "retry",
                    "message": f"Retry created from {original['id']}.",
                    "timestamp": now,
                }
            ]
            state["tasks"].insert(0, new_task)
            self._write(state)
            return deepcopy(new_task)

    def pending_failure_events(self) -> list[dict[str, Any]]:
        with self._lock:
            state = self._read()
            shown = set(state.get("cinematics", {}).get("shownEventIds", []))
            skipped = set(state.get("cinematics", {}).get("skippedEventIds", []))
            blocked = shown | skipped
            pending = []
            for event in state["events"]:
                if should_trigger_failure_cinematic(event, blocked):
                    pending.append(event_to_dict(normalize_runtime_event(event)))
            return pending

    def mark_cinematic(self, event_id: str, disposition: str) -> dict[str, Any]:
        if disposition not in {"shown", "skipped"}:
            raise ValueError("Disposition must be shown or skipped.")
        key = "shownEventIds" if disposition == "shown" else "skippedEventIds"
        with self._lock:
            state = self._read()
            ids = state.setdefault("cinematics", {}).setdefault(key, [])
            if event_id not in ids:
                ids.append(event_id)
            self._write(state)
            return deepcopy(state["cinematics"])

    def _advance_demo_tasks(self, state: dict[str, Any]) -> bool:
        changed = False
        now_dt = datetime.now(timezone.utc)
        for task in state["tasks"]:
            if task.get("mode") != "demo" or task.get("status") not in {"queued", "running"}:
                continue
            created = datetime.fromisoformat(task["createdAt"])
            age = (now_dt - created).total_seconds()
            if task["status"] == "queued" and age >= 1.0:
                task["status"] = "running"
                task["startedAt"] = utc_now()
                task["updatedAt"] = task["startedAt"]
                task["latestUpdate"] = "Demo worker is recording scoped activity."
                task["timeline"].append(
                    {
                        "id": f"evt-{uuid.uuid4().hex[:10]}",
                        "kind": "running",
                        "message": "Worker claimed the task.",
                        "timestamp": task["updatedAt"],
                    }
                )
                changed = True
            if age >= 4.0 and task["status"] == "running":
                if task.get("demoOutcome") == "fail":
                    self._fail_demo_task(state, task)
                else:
                    self._complete_demo_task(task)
                changed = True
        return changed

    def _complete_demo_task(self, task: dict[str, Any]) -> None:
        now = utc_now()
        task["status"] = "completed"
        task["completedAt"] = now
        task["updatedAt"] = now
        task["latestUpdate"] = "Completed with a recorded demo result and verification note."
        task["result"] = "Demo task completed. In live mode this result must come from Hermes and verified artifacts."
        task["evidence"].append("State transition recorded by the local adapter fixture.")
        task["timeline"].append(
            {
                "id": f"evt-{uuid.uuid4().hex[:10]}",
                "kind": "completed",
                "message": "Completion fixture recorded.",
                "timestamp": now,
            }
        )

    def _fail_demo_task(self, state: dict[str, Any], task: dict[str, Any]) -> None:
        now = utc_now()
        event_id = f"terminal-failure:{task['id']}:{task['attemptId']}"
        task["status"] = "failed"
        task["completedAt"] = now
        task["updatedAt"] = now
        task["latestUpdate"] = "Terminal failure confirmed after permitted retries were exhausted."
        task["retryPolicy"]["exhausted"] = True
        task["blockers"] = ["Controlled terminal failure fixture."]
        task["evidence"].append("Failure event persisted before presentation.")
        task["result"] = None
        task["timeline"].append(
            {
                "id": event_id,
                "kind": "terminal_failure",
                "message": "Terminal failed outcome recorded.",
                "timestamp": now,
            }
        )
        if not any(event.get("id") == event_id for event in state["events"]):
            state["events"].append(
                {
                    "id": event_id,
                    "taskId": task["id"],
                    "attemptId": task["attemptId"],
                    "title": task["title"],
                    "assignee": task["assignee"],
                    "status": "failed",
                    "outcomeKind": "terminal_failure",
                    "terminal": True,
                    "retryPolicyExhausted": True,
                    "error": "Controlled fixture failure after the retry policy was exhausted.",
                    "lastSuccessfulStep": task["lastSuccessfulStep"],
                    "timestamp": now,
                }
            )
