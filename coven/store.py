"""Small JSON store for Coven presentation state and demo fixtures."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .configuration import (
    VALID_MOTION_MODES,
    VALID_QUALITIES,
    ConfigError,
    validate_identifier,
    validate_priority,
    validate_profiles_file,
)
from .events import event_to_dict, normalize_runtime_event, should_trigger_failure_cinematic


USER_MESSAGE_LIMIT = 4_000
ASSISTANT_MESSAGE_LIMIT = 40_000
TRANSPORT_TEXT_LIMIT = 64_000
TASK_EVENT_LIMIT = 80
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE_TASK_STATUSES = {"queued", "running", "waiting_for_approval", "stopping", "unknown", "disconnected"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CovenStore:
    def __init__(self, data_dir: Path, profile_path: Path):
        self.data_dir = data_dir
        self.profile_path = profile_path
        self.state_path = data_dir / "state.json"
        self._lock = threading.RLock()
        self._profiles = validate_profiles_file(profile_path)
        self.profile_ids = {item["id"] for item in self._profiles}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_state()

    def _ensure_state(self) -> None:
        if not self.state_path.exists():
            self._write(self._new_state())
            return
        existing = self._read_raw()
        migrated = self._migrate_state(existing)
        if migrated is not existing:
            backup = self.state_path.with_suffix(f".v1-backup-{utc_now().replace(':', '')}.json")
            self.state_path.replace(backup)
            self._write(migrated)

    def _new_state(self) -> dict[str, Any]:
        return {
            "version": 3,
            "createdAt": utc_now(),
            "preferences": {
                "cinematicsEnabled": True,
                "reducedMotionMode": "tableau",
                "mute": False,
                "animationQuality": "balanced",
            },
            "namespaces": {
                "demo": self._empty_namespace("demo"),
                "live": self._empty_namespace("live"),
            },
        }

    def _empty_namespace(self, name: str) -> dict[str, Any]:
        if name == "demo":
            return self._seed_demo_namespace()
        return {
            "name": name,
            "tasks": [],
            "conversations": {},
            "runtimeSessions": {},
            "events": [],
            "cinematics": {"shownEventIds": [], "skippedEventIds": []},
        }

    def _seed_demo_namespace(self) -> dict[str, Any]:
        now = utc_now()
        return {
            "name": "demo",
            "tasks": [
                self._demo_task(
                    title="Prepare project brief",
                    instructions="Summarize release goals, risks, verification evidence and next owner actions.",
                    assignee="circe",
                    status="running",
                    priority="high",
                    latest_update="Draft is ready for review.",
                    timeline_kind="running",
                    timeline_message="Circe is assembling the brief from the approved demo workspace.",
                    now=now,
                ),
                self._demo_task(
                    title="Review research notes",
                    instructions="Check the gathered references, flag weak evidence and identify unanswered questions.",
                    assignee="hecate",
                    status="needs input",
                    priority="normal",
                    latest_update="Waiting for a source selection before review continues.",
                    timeline_kind="needs_input",
                    timeline_message="Hecate requested a decision on which notes should be treated as authoritative.",
                    now=now,
                ),
                self._demo_task(
                    title="Organize archive",
                    instructions="Create the durable summary and index the accepted project decisions.",
                    assignee="selene",
                    status="completed",
                    priority="normal",
                    latest_update="Archive summary is complete.",
                    timeline_kind="completed",
                    timeline_message="Selene completed the archive index and summary.",
                    now=now,
                    evidence=["Demo archive summary recorded in the local fixture state."],
                    result="Demo archive organized and ready to inspect.",
                ),
            ],
            "conversations": {
                "morgana": [
                    {
                        "id": f"msg-{uuid.uuid4().hex}",
                        "author": "user",
                        "text": "Help me plan the next release.",
                        "timestamp": now,
                    },
                    {
                        "id": f"msg-{uuid.uuid4().hex}",
                        "author": "morgana",
                        "text": "Let's define the goal, the steps, and the evidence of success.",
                        "timestamp": now,
                    },
                ]
            },
            "runtimeSessions": {},
            "events": [],
            "cinematics": {"shownEventIds": [], "skippedEventIds": []},
        }

    def _demo_task(
        self,
        *,
        title: str,
        instructions: str,
        assignee: str,
        status: str,
        priority: str,
        latest_update: str,
        timeline_kind: str,
        timeline_message: str,
        now: str,
        evidence: list[str] | None = None,
        result: str | None = None,
    ) -> dict[str, Any]:
        task_id = f"task-demo-{validate_identifier(title.lower().replace(' ', '-'), field='demo task id')[:36]}"
        attempt_id = f"{task_id}-attempt-1"
        return {
            "id": task_id,
            "attemptId": attempt_id,
            "parentTaskId": None,
            "title": title,
            "instructions": instructions,
            "assignee": assignee,
            "status": status,
            "priority": priority,
            "mode": "demo",
            "createdAt": now,
            "updatedAt": now,
            "startedAt": now if status in {"running", "needs input", "completed"} else None,
            "completedAt": now if status == "completed" else None,
            "latestUpdate": latest_update,
            "dependencies": [],
            "blockers": ["Awaiting user input in the demo fixture."] if status == "needs input" else [],
            "evidence": evidence or [],
            "result": result,
            "lastSuccessfulStep": "Demo fixture seeded and persisted.",
            "retryPolicy": {"maxRetries": 0, "attempt": 1, "exhausted": False},
            "demoOutcome": "hold",
            "fixtureStatic": True,
            "timeline": [
                {
                    "id": f"evt-{uuid.uuid4().hex[:10]}",
                    "kind": timeline_kind,
                    "message": timeline_message,
                    "timestamp": now,
                }
            ],
        }

    def _migrate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("version") in {2, 3} and isinstance(state.get("namespaces"), dict):
            changed = False
            for namespace in ("demo", "live"):
                if namespace not in state["namespaces"]:
                    state["namespaces"][namespace] = self._empty_namespace(namespace)
                    changed = True
                scope = state["namespaces"][namespace]
                defaults = self._empty_namespace(namespace)
                for key in ("tasks", "conversations", "runtimeSessions", "events", "cinematics"):
                    if key not in scope:
                        scope[key] = deepcopy(defaults[key])
                        changed = True
                for task in scope.get("tasks", []):
                    changed = self._ensure_task_shape(task, namespace=namespace) or changed
                for messages in scope.get("conversations", {}).values():
                    if isinstance(messages, list):
                        for message in messages:
                            if isinstance(message, dict) and "delivery" not in message:
                                message["delivery"] = {"state": "delivered"}
                                changed = True
            if "preferences" not in state:
                state["preferences"] = self._preferences_from(state)
                changed = True
            if state.get("version") != 3:
                state["version"] = 3
                changed = True
            return deepcopy(state) if changed else state

        migrated = self._new_state()
        demo = migrated["namespaces"]["demo"]
        demo["tasks"] = deepcopy(state.get("tasks", []))
        demo["conversations"] = deepcopy(state.get("conversations", {}))
        demo["events"] = deepcopy(state.get("events", []))
        demo["cinematics"] = deepcopy(state.get("cinematics", {"shownEventIds": [], "skippedEventIds": []}))
        migrated["preferences"] = self._preferences_from(state)
        migrated["migratedFromVersion"] = state.get("version", "unknown")
        migrated["migratedAt"] = utc_now()
        return migrated

    def _ensure_task_shape(self, task: dict[str, Any], *, namespace: str) -> bool:
        changed = False
        if "artifacts" not in task:
            task["artifacts"] = []
            changed = True
        if "usage" not in task:
            task["usage"] = None
            changed = True
        if "runtime" not in task:
            task["runtime"] = {}
            changed = True
        if "requestedRuntime" not in task:
            task["requestedRuntime"] = {}
            changed = True
        if "approval" not in task:
            task["approval"] = {"state": "none"}
            changed = True
        if namespace == "live" or task.get("mode") == "live":
            if "hermes" not in task:
                task["hermes"] = {
                    "runId": None,
                    "sessionId": None,
                    "idempotencyKey": None,
                    "lastReconciledAt": None,
                }
                changed = True
        return changed

    def _preferences_from(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("settings", state.get("preferences", {}))
        if not isinstance(raw, dict):
            raw = {}
        motion = raw.get("reducedMotionMode")
        quality = raw.get("animationQuality")
        return {
            "cinematicsEnabled": raw.get("cinematicsEnabled") is not False,
            "reducedMotionMode": motion if motion in VALID_MOTION_MODES else "tableau",
            "mute": raw.get("mute") is True,
            "animationQuality": quality if quality in VALID_QUALITIES else "balanced",
        }

    def _read_raw(self) -> dict[str, Any]:
        with self.state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _read(self) -> dict[str, Any]:
        return self._migrate_state(self._read_raw())

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
        tmp.replace(self.state_path)

    def snapshot(self, *, namespace: str, advance_demo: bool = False) -> dict[str, Any]:
        namespace = self._namespace_name(namespace)
        with self._lock:
            state = self._read()
            scope = state["namespaces"][namespace]
            if namespace == "demo" and advance_demo:
                changed = self._advance_demo_tasks(scope)
                if changed:
                    self._write(state)
            return deepcopy(scope)

    def profiles(self) -> list[dict[str, Any]]:
        return deepcopy(self._profiles)

    def conversations(self, witch_id: str, *, namespace: str) -> list[dict[str, Any]]:
        witch_id = self._profile_id(witch_id)
        namespace = self._namespace_name(namespace)
        with self._lock:
            state = self._read()
            return deepcopy(state["namespaces"][namespace]["conversations"].get(witch_id, []))

    def runtime_session(self, witch_id: str, *, namespace: str, provider: str = "hermes") -> str | None:
        witch_id = self._profile_id(witch_id)
        namespace = self._namespace_name(namespace)
        provider = self._bounded_text(provider, "Provider", max_length=80).strip()
        with self._lock:
            state = self._read()
            record = state["namespaces"][namespace].setdefault("runtimeSessions", {}).get(witch_id)
            if not isinstance(record, dict) or record.get("provider") != provider:
                return None
            session_id = record.get("sessionId")
            return session_id if isinstance(session_id, str) and session_id else None

    def set_runtime_session(self, witch_id: str, session_id: str, *, namespace: str, provider: str = "hermes") -> dict[str, Any]:
        witch_id = self._profile_id(witch_id)
        namespace = self._namespace_name(namespace)
        provider = self._bounded_text(provider, "Provider", max_length=80).strip()
        session_id = self._bounded_text(session_id, "Runtime session id", max_length=512).strip()
        if not provider:
            raise ValueError("Provider is required.")
        if not session_id:
            raise ValueError("Runtime session id is required.")
        record = {"provider": provider, "sessionId": session_id, "updatedAt": utc_now()}
        with self._lock:
            state = self._read()
            state["namespaces"][namespace].setdefault("runtimeSessions", {})[witch_id] = record
            self._write(state)
            return deepcopy(record)

    def append_message(
        self,
        witch_id: str,
        author: str,
        text: str,
        *,
        namespace: str,
        status: str = "delivered",
        max_length: int | None = None,
        message_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        witch_id = self._profile_id(witch_id)
        namespace = self._namespace_name(namespace)
        if author != "user":
            author = self._profile_id(author)
        if status not in {"queued", "sending", "delivered", "failed", "uncertain"}:
            raise ValueError("Message delivery status is invalid.")
        limit = max_length or (USER_MESSAGE_LIMIT if author == "user" else ASSISTANT_MESSAGE_LIMIT)
        text = self._bounded_text(text, "Message", max_length=limit).strip()
        if not text:
            raise ValueError("Message cannot be empty.")
        message_id = message_id or f"msg-{uuid.uuid4().hex}"
        with self._lock:
            state = self._read()
            thread = state["namespaces"][namespace]["conversations"].setdefault(witch_id, [])
            thread.append(
                {
                    "id": message_id,
                    "author": author,
                    "text": text,
                    "timestamp": utc_now(),
                    "delivery": {"state": status, **(details or {})},
                }
            )
            self._write(state)
            return deepcopy(thread)

    def update_message_delivery(
        self,
        witch_id: str,
        message_id: str,
        *,
        namespace: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        witch_id = self._profile_id(witch_id)
        namespace = self._namespace_name(namespace)
        if status not in {"queued", "sending", "delivered", "failed", "uncertain"}:
            raise ValueError("Message delivery status is invalid.")
        with self._lock:
            state = self._read()
            thread = state["namespaces"][namespace]["conversations"].setdefault(witch_id, [])
            message = next((item for item in thread if item.get("id") == message_id), None)
            if message is None:
                raise KeyError(message_id)
            message["delivery"] = {"state": status, **(details or {})}
            message["updatedAt"] = utc_now()
            self._write(state)
            return deepcopy(thread)

    def create_task(self, *, assignee: str, title: str, instructions: str, priority: str) -> dict[str, Any]:
        assignee = self._profile_id(assignee)
        priority = validate_priority(priority)
        title = self._bounded_text(title, "Task title", max_length=160).strip()
        instructions = self._bounded_text(instructions, "Task instructions", max_length=16000).strip()
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
            "instructions": instructions,
            "assignee": assignee,
            "status": "queued",
            "priority": priority,
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
            state["namespaces"]["demo"]["tasks"].insert(0, task)
            self._write(state)
            return deepcopy(task)

    def create_live_task(
        self,
        *,
        assignee: str,
        title: str,
        instructions: str,
        priority: str,
        idempotency_key: str,
        session_id: str | None,
        requested_runtime: dict[str, Any],
        parent_task_id: str | None = None,
        attempt: int = 1,
    ) -> dict[str, Any]:
        assignee = self._profile_id(assignee)
        priority = validate_priority(priority)
        title = self._bounded_text(title, "Task title", max_length=160).strip()
        instructions = self._bounded_text(instructions, "Task instructions", max_length=16_000).strip()
        idempotency_key = self._bounded_text(idempotency_key, "Idempotency key", max_length=255).strip()
        if not title:
            raise ValueError("Task title is required.")
        if not idempotency_key:
            raise ValueError("Idempotency key is required.")

        now = utc_now()
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        task = {
            "id": task_id,
            "attemptId": f"{task_id}-attempt-{attempt}",
            "parentTaskId": parent_task_id,
            "title": title,
            "instructions": instructions,
            "assignee": assignee,
            "status": "queued",
            "priority": priority,
            "mode": "live",
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "completedAt": None,
            "latestUpdate": "Queued for Hermes run submission.",
            "dependencies": [],
            "blockers": [],
            "evidence": [],
            "result": None,
            "lastSuccessfulStep": "Task accepted locally before remote dispatch.",
            "retryPolicy": {"maxRetries": 0, "attempt": attempt, "exhausted": False},
            "requestedRuntime": deepcopy(requested_runtime),
            "runtime": {},
            "usage": None,
            "approval": {"state": "none"},
            "artifacts": [],
            "hermes": {
                "runId": None,
                "sessionId": session_id,
                "idempotencyKey": idempotency_key,
                "lastReconciledAt": None,
            },
            "timeline": [
                {
                    "id": f"evt-{uuid.uuid4().hex[:10]}",
                    "kind": "queued",
                    "message": "Task was persisted locally before Hermes dispatch.",
                    "timestamp": now,
                }
            ],
        }
        with self._lock:
            state = self._read()
            state["namespaces"]["live"]["tasks"].insert(0, task)
            self._write(state)
            return deepcopy(task)

    def task(self, task_id: str, *, namespace: str) -> dict[str, Any]:
        namespace = self._namespace_name(namespace)
        with self._lock:
            state = self._read()
            task = next((item for item in state["namespaces"][namespace]["tasks"] if item.get("id") == task_id), None)
            if task is None:
                raise KeyError(task_id)
            return deepcopy(task)

    def live_reconcile_candidates(self) -> list[dict[str, Any]]:
        with self._lock:
            state = self._read()
            tasks = state["namespaces"]["live"]["tasks"]
            return deepcopy(
                [
                    task
                    for task in tasks
                    if task.get("mode") == "live"
                    and task.get("hermes", {}).get("runId")
                    and task.get("status") not in TERMINAL_TASK_STATUSES
                ]
            )

    def mark_task_dispatch_uncertain(self, task_id: str, *, reason: str) -> dict[str, Any]:
        return self.update_live_task(
            task_id,
            status="unknown",
            latest_update=f"Remote submission outcome is uncertain: {reason}",
            timeline_kind="unknown",
            timeline_message=f"Remote submission outcome is uncertain: {reason}",
        )

    def record_live_submission(
        self,
        task_id: str,
        *,
        run_id: str,
        remote_status: str,
        replayed: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        status = self._map_runtime_status(remote_status)
        return self.update_live_task(
            task_id,
            status=status,
            hermes_updates={"runId": run_id, "sessionId": session_id, "lastReconciledAt": utc_now()},
            latest_update=f"Hermes run {run_id} accepted with status {remote_status}.",
            timeline_kind="submission_replayed" if replayed else "submitted",
            timeline_message=(
                f"Idempotent submission reused Hermes run {run_id}."
                if replayed
                else f"Hermes accepted run {run_id}."
            ),
        )

    def update_live_task_from_run(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        remote_status = str(payload.get("status") or "unknown")
        status = self._map_runtime_status(remote_status)
        output = payload.get("output")
        latest = f"Hermes reports {remote_status}."
        if isinstance(output, str) and output.strip() and status in TERMINAL_TASK_STATUSES:
            latest = "Hermes returned a terminal result."
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        approval = payload.get("approval") if isinstance(payload.get("approval"), dict) else None
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else None
        timeline_events = self._extract_run_timeline(payload)
        return self.update_live_task(
            task_id,
            status=status,
            latest_update=latest,
            result=output if isinstance(output, str) and status == "completed" else None,
            blockers=[str(payload.get("error"))] if status in {"failed", "interrupted"} and payload.get("error") else None,
            evidence=[f"Remote run status polled from Hermes at {utc_now()}."],
            runtime=runtime,
            usage=usage,
            approval=approval,
            artifacts=artifacts,
            hermes_updates={
                "runId": str(payload.get("run_id") or payload.get("id") or ""),
                "sessionId": str(payload.get("session_id") or ""),
                "lastReconciledAt": utc_now(),
            },
            timeline_events=timeline_events,
            timeline_kind=status,
            timeline_message=latest,
        )

    def update_live_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        latest_update: str | None = None,
        result: str | None = None,
        blockers: list[str] | None = None,
        evidence: list[str] | None = None,
        runtime: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        artifacts: list[Any] | None = None,
        hermes_updates: dict[str, Any] | None = None,
        timeline_events: list[dict[str, str]] | None = None,
        timeline_kind: str | None = None,
        timeline_message: str | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in TERMINAL_TASK_STATUSES | ACTIVE_TASK_STATUSES | {"needs_input"}:
            raise ValueError(f"Unsupported task status: {status}")
        with self._lock:
            state = self._read()
            tasks = state["namespaces"]["live"]["tasks"]
            task = next((item for item in tasks if item.get("id") == task_id), None)
            if task is None:
                raise KeyError(task_id)
            now = utc_now()
            previous_status = task.get("status")
            if status is not None:
                task["status"] = status
                if status in {"running", "waiting_for_approval"} and not task.get("startedAt"):
                    task["startedAt"] = now
                if status in TERMINAL_TASK_STATUSES and not task.get("completedAt"):
                    task["completedAt"] = now
            if latest_update is not None:
                task["latestUpdate"] = self._bounded_text(latest_update, "Latest update", max_length=600)
            if result is not None:
                task["result"] = self._bounded_text(result, "Task result", max_length=TRANSPORT_TEXT_LIMIT)
            if blockers is not None:
                task["blockers"] = [self._bounded_text(item, "Blocker", max_length=600) for item in blockers]
            if evidence:
                existing = list(task.get("evidence") or [])
                for item in evidence:
                    text = self._bounded_text(item, "Evidence", max_length=600)
                    if text not in existing:
                        existing.append(text)
                task["evidence"] = existing[-20:]
            if runtime is not None:
                task["runtime"] = deepcopy(runtime)
            if usage is not None:
                task["usage"] = deepcopy(usage)
            if approval is not None:
                task["approval"] = deepcopy(approval)
            if artifacts is not None:
                task["artifacts"] = deepcopy(artifacts[:20])
            if hermes_updates:
                hermes = task.setdefault("hermes", {})
                for key, value in hermes_updates.items():
                    if value not in {None, ""}:
                        hermes[key] = value
            if timeline_events:
                timeline = task.setdefault("timeline", [])
                existing_ids = {item.get("id") for item in timeline if isinstance(item, dict)}
                for event in timeline_events:
                    event_id = event.get("id") or f"evt-{uuid.uuid4().hex[:10]}"
                    if event_id in existing_ids:
                        continue
                    timeline.append(
                        {
                            "id": event_id,
                            "kind": self._bounded_text(event.get("kind", "runtime"), "Timeline event kind", max_length=80),
                            "message": self._bounded_text(event.get("message", "Runtime event recorded."), "Timeline message", max_length=800),
                            "timestamp": event.get("timestamp") or now,
                        }
                    )
                    existing_ids.add(event_id)
                task["timeline"] = timeline[-TASK_EVENT_LIMIT:]
            if timeline_kind and timeline_message:
                timeline = task.setdefault("timeline", [])
                if previous_status != status or not timeline or timeline[-1].get("message") != timeline_message:
                    timeline.append(
                        {
                            "id": f"evt-{uuid.uuid4().hex[:10]}",
                            "kind": timeline_kind,
                            "message": self._bounded_text(timeline_message, "Timeline message", max_length=800),
                            "timestamp": now,
                        }
                    )
                    task["timeline"] = timeline[-TASK_EVENT_LIMIT:]
            task["updatedAt"] = now
            if task.get("status") == "failed":
                task.setdefault("retryPolicy", {})["exhausted"] = True
                self._record_terminal_failure_event(state["namespaces"]["live"], task)
            self._write(state)
            return deepcopy(task)

    def retry_task(self, task_id: str, *, namespace: str) -> dict[str, Any]:
        namespace = self._namespace_name(namespace)
        with self._lock:
            state = self._read()
            tasks = state["namespaces"][namespace]["tasks"]
            original = next((task for task in tasks if task["id"] == task_id), None)
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
            tasks.insert(0, new_task)
            self._write(state)
            return deepcopy(new_task)

    def _map_runtime_status(self, status: str) -> str:
        normalized = str(status or "unknown").strip().lower().replace("-", "_")
        aliases = {
            "started": "running",
            "in_progress": "running",
            "waiting": "waiting_for_approval",
            "needs_input": "waiting_for_approval",
            "needs approval": "waiting_for_approval",
        }
        mapped = aliases.get(normalized, normalized)
        if mapped in TERMINAL_TASK_STATUSES | ACTIVE_TASK_STATUSES | {"needs_input"}:
            return mapped
        return "unknown"

    def _extract_run_timeline(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return []
        timeline: list[dict[str, str]] = []
        for raw in raw_events[-TASK_EVENT_LIMIT:]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("type") or raw.get("event") or raw.get("kind") or "runtime")
            message = self._runtime_event_message(kind, raw)
            timeline.append(
                {
                    "id": str(raw.get("id") or raw.get("event_id") or raw.get("eventId") or f"remote-{uuid.uuid4().hex[:10]}"),
                    "kind": kind,
                    "message": message,
                    "timestamp": str(raw.get("timestamp") or raw.get("created_at") or raw.get("createdAt") or utc_now()),
                }
            )
        return timeline

    def _runtime_event_message(self, kind: str, raw: dict[str, Any]) -> str:
        for key in ("message", "summary", "text", "content"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        tool = raw.get("tool") or raw.get("tool_name") or raw.get("toolName") or raw.get("name")
        if isinstance(tool, str) and tool.strip():
            if kind.endswith("started"):
                return f"{tool.strip()} started."
            if kind.endswith("completed"):
                return f"{tool.strip()} completed."
            return f"{tool.strip()} event: {kind}."
        return f"Hermes event: {kind}."

    def pending_failure_events(self, *, namespace: str) -> list[dict[str, Any]]:
        namespace = self._namespace_name(namespace)
        with self._lock:
            state = self._read()
            scope = state["namespaces"][namespace]
            shown = set(scope.get("cinematics", {}).get("shownEventIds", []))
            skipped = set(scope.get("cinematics", {}).get("skippedEventIds", []))
            blocked = shown | skipped
            pending = []
            for event in scope["events"]:
                if should_trigger_failure_cinematic(event, blocked):
                    pending.append(event_to_dict(normalize_runtime_event(event)))
            return pending

    def mark_cinematic(self, event_id: str, disposition: str, *, namespace: str) -> dict[str, Any]:
        namespace = self._namespace_name(namespace)
        if disposition not in {"shown", "skipped"}:
            raise ValueError("Disposition must be shown or skipped.")
        key = "shownEventIds" if disposition == "shown" else "skippedEventIds"
        with self._lock:
            state = self._read()
            ids = state["namespaces"][namespace].setdefault("cinematics", {}).setdefault(key, [])
            if event_id not in ids:
                ids.append(event_id)
            self._write(state)
            return deepcopy(state["namespaces"][namespace]["cinematics"])

    def preferences(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._read()["preferences"])

    def update_preferences(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {"cinematicsEnabled", "reducedMotionMode", "mute", "animationQuality"}
        unknown = sorted(set(updates) - allowed)
        if unknown:
            raise ValueError(f"Unknown preference field(s): {', '.join(unknown)}.")

        with self._lock:
            state = self._read()
            prefs = state["preferences"]
            if "cinematicsEnabled" in updates:
                if not isinstance(updates["cinematicsEnabled"], bool):
                    raise ValueError("cinematicsEnabled must be a boolean.")
                prefs["cinematicsEnabled"] = updates["cinematicsEnabled"]
            if "mute" in updates:
                if not isinstance(updates["mute"], bool):
                    raise ValueError("mute must be a boolean.")
                prefs["mute"] = updates["mute"]
            if "reducedMotionMode" in updates:
                if updates["reducedMotionMode"] not in VALID_MOTION_MODES:
                    raise ValueError("reducedMotionMode is invalid.")
                prefs["reducedMotionMode"] = updates["reducedMotionMode"]
            if "animationQuality" in updates:
                if updates["animationQuality"] not in VALID_QUALITIES:
                    raise ValueError("animationQuality is invalid.")
                prefs["animationQuality"] = updates["animationQuality"]
            self._write(state)
            return deepcopy(prefs)

    def _advance_demo_tasks(self, state: dict[str, Any]) -> bool:
        changed = False
        now_dt = datetime.now(timezone.utc)
        for task in state["tasks"]:
            if task.get("fixtureStatic"):
                continue
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

    def _record_terminal_failure_event(self, scope: dict[str, Any], task: dict[str, Any]) -> None:
        event_id = f"terminal-failure:{task['id']}:{task['attemptId']}"
        if any(event.get("id") == event_id for event in scope["events"]):
            return
        scope["events"].append(
            {
                "id": event_id,
                "taskId": task["id"],
                "attemptId": task["attemptId"],
                "title": task["title"],
                "assignee": task["assignee"],
                "status": "failed",
                "outcomeKind": "terminal_failure",
                "terminal": True,
                "retryPolicyExhausted": bool(task.get("retryPolicy", {}).get("exhausted")),
                "error": "; ".join(task.get("blockers") or []) or "Hermes reported a terminal failure.",
                "lastSuccessfulStep": task.get("lastSuccessfulStep") or "Remote run was accepted.",
                "timestamp": utc_now(),
            }
        )

    def _namespace_name(self, namespace: str) -> str:
        if namespace not in {"demo", "live"}:
            raise ValueError("Namespace must be demo or live.")
        return namespace

    def _profile_id(self, value: str) -> str:
        try:
            profile_id = validate_identifier(value, field="profile id")
        except ConfigError as exc:
            raise ValueError(str(exc)) from exc
        if profile_id not in self.profile_ids:
            raise ValueError(f"Unknown profile: {profile_id}")
        return profile_id

    def _bounded_text(self, value: Any, field: str, *, max_length: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string.")
        if len(value) > max_length:
            raise ValueError(f"{field} must be {max_length} characters or fewer.")
        return value
