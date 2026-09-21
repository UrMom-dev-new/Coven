"""Agent runtime adapter boundary for demo fixtures and Hermes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
from typing import Any
import uuid
from urllib import error, request

from .configuration import AppConfig, ConfigError, validate_priority
from .store import ASSISTANT_MESSAGE_LIMIT, USER_MESSAGE_LIMIT, CovenStore


class AdapterError(RuntimeError):
    def __init__(self, message: str, *, code: str = "adapter_error", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class AdapterResult:
    messages: list[dict[str, Any]] | None = None
    task: dict[str, Any] | None = None
    code: str = "ok"
    details: Any = None


class DemoAdapter:
    namespace = "demo"

    def __init__(self, store: CovenStore):
        self.store = store

    def send_message(self, witch_id: str, text: str) -> AdapterResult:
        self.store.append_message(witch_id, "user", text, namespace=self.namespace)
        reply = (
            "I recorded this in the durable demo transcript. Use Assign task when you want a tracked demo quest; "
            "include the word fail to exercise the terminal-failure fixture."
        )
        messages = self.store.append_message(witch_id, witch_id, reply, namespace=self.namespace)
        return AdapterResult(messages=messages)

    def create_task(self, body: dict[str, Any]) -> AdapterResult:
        task = self.store.create_task(
            assignee=body.get("assignee"),
            title=body.get("title"),
            instructions=body.get("instructions"),
            priority=body.get("priority", "normal"),
        )
        return AdapterResult(task=task)

    def retry_task(self, task_id: str) -> AdapterResult:
        return AdapterResult(task=self.store.retry_task(task_id, namespace=self.namespace))


class HermesAdapter:
    namespace = "live"

    def __init__(self, store: CovenStore, config: AppConfig):
        self.store = store
        self.config = config
        self.base_url = config.runtime.hermes_api_base_url.rstrip("/")
        self.api_key = os.environ.get(config.runtime.hermes_api_key_env, "")

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def capabilities(self) -> dict[str, Any]:
        if not self.available():
            return {
                "available": False,
                "reason": "Hermes API base URL and API key environment variable are not configured.",
                "keyEnvironmentVariable": self.config.runtime.hermes_api_key_env,
            }
        try:
            return self._request("GET", "/v1/capabilities")
        except AdapterError as exc:
            return {"available": False, "reason": str(exc), "code": exc.code, "details": exc.details}

    def send_message(self, witch_id: str, text: str) -> AdapterResult:
        if not isinstance(text, str) or not text.strip():
            raise AdapterError("Message cannot be empty.", code="invalid_message")
        if len(text) > USER_MESSAGE_LIMIT:
            raise AdapterError(f"Message must be {USER_MESSAGE_LIMIT} characters or fewer.", code="message_too_large")
        message_id = f"msg-{uuid.uuid4().hex}"
        if not self.available():
            self.store.append_message(witch_id, "user", text, namespace=self.namespace, status="failed", message_id=message_id)
            raise AdapterError(
                "Hermes API transport is not configured. Message was saved locally with failed delivery state.",
                code="hermes_api_unconfigured",
            )
        session_id = self._session_for(witch_id)
        self.store.append_message(
            witch_id,
            "user",
            text,
            namespace=self.namespace,
            status="sending",
            message_id=message_id,
            details={"sessionId": session_id},
        )
        try:
            payload = self._request("POST", f"/api/sessions/{session_id}/chat", {"input": text})
        except AdapterError as exc:
            status = "uncertain" if exc.code in {"hermes_timeout", "hermes_connection_error"} else "failed"
            self.store.update_message_delivery(
                witch_id,
                message_id,
                namespace=self.namespace,
                status=status,
                details={"error": str(exc), "code": exc.code},
            )
            raise
        self.store.update_message_delivery(witch_id, message_id, namespace=self.namespace, status="delivered")
        assistant_text = self._extract_text(payload)
        messages = self.store.append_message(
            witch_id,
            witch_id,
            assistant_text,
            namespace=self.namespace,
            max_length=ASSISTANT_MESSAGE_LIMIT,
            details={"runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}},
        )
        return AdapterResult(messages=messages, details=payload)

    def create_task(self, body: dict[str, Any]) -> AdapterResult:
        assignee, title, instructions, priority, idempotency_key = self._validated_task_fields(body)
        if not self.available():
            raise AdapterError("Hermes API transport is not configured.", code="hermes_api_unconfigured")
        capabilities = self.capabilities()
        if not self._feature_enabled(capabilities, "run_submission"):
            raise AdapterError(
                "The configured Hermes API server does not advertise run submission support.",
                code="hermes_run_submission_unavailable",
                details={"capabilities": self._capability_summary(capabilities)},
            )
        session_id = self._session_for(assignee)
        route = self._resolve_route(assignee, body)
        task = self.store.create_live_task(
            assignee=assignee,
            title=title,
            instructions=instructions,
            priority=priority,
            idempotency_key=idempotency_key,
            session_id=session_id,
            requested_runtime=route,
            parent_task_id=body.get("parentTaskId") if isinstance(body.get("parentTaskId"), str) else None,
            attempt=body.get("attempt") if isinstance(body.get("attempt"), int) and body.get("attempt") > 0 else 1,
        )
        payload: dict[str, Any] = {
            "input": self._task_input(task),
            "session_id": session_id,
            "instructions": self._role_instructions(assignee),
        }
        if route.get("provider"):
            payload["provider"] = route["provider"]
        if route.get("model"):
            payload["model"] = route["model"]
        if route.get("modelOptions"):
            payload["model_options"] = route["modelOptions"]
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Hermes-Session-Id": session_id,
            "X-Hermes-Session-Key": self._session_key(assignee),
        }
        try:
            response_headers, run_payload = self._request_with_headers("POST", "/v1/runs", payload, headers=headers, timeout=15)
        except AdapterError as exc:
            self.store.mark_task_dispatch_uncertain(task["id"], reason=str(exc))
            raise
        run_id = str(run_payload.get("run_id") or run_payload.get("id") or "")
        if not run_id:
            self.store.mark_task_dispatch_uncertain(task["id"], reason="Hermes did not return a run_id.")
            raise AdapterError("Hermes did not return a run_id for the submitted task.", code="hermes_run_id_missing", details=run_payload)
        replayed = response_headers.get("Idempotency-Replayed", "").lower() == "true"
        task = self.store.record_live_submission(
            task["id"],
            run_id=run_id,
            remote_status=str(run_payload.get("status") or "running"),
            replayed=replayed,
            session_id=str(run_payload.get("session_id") or session_id),
        )
        try:
            task = self.refresh_task(task)
        except AdapterError:
            pass
        return AdapterResult(task=task, details={"run": run_payload, "replayed": replayed})

    def retry_task(self, task_id: str) -> AdapterResult:
        original = self.store.task(task_id, namespace=self.namespace)
        if original.get("status") != "failed":
            raise AdapterError("Only confirmed failed live tasks can be retried.", code="retry_requires_failed_task")
        retry_body = {
            "assignee": original["assignee"],
            "title": original["title"],
            "instructions": original.get("instructions") or "",
            "priority": original.get("priority") or "normal",
            "parentTaskId": original["id"],
            "attempt": int(original.get("retryPolicy", {}).get("attempt", 1)) + 1,
            "provider": original.get("requestedRuntime", {}).get("provider"),
            "model": original.get("requestedRuntime", {}).get("model"),
            "routeMode": original.get("requestedRuntime", {}).get("routeMode", "auto"),
        }
        return self.create_task(retry_body)

    def refresh_tasks(self) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        if not self.available():
            return updated
        for task in self.store.live_reconcile_candidates():
            try:
                updated.append(self.refresh_task(task))
            except AdapterError as exc:
                self.store.update_live_task(
                    task["id"],
                    status="disconnected",
                    latest_update=f"Could not reconcile Hermes run: {exc}",
                    timeline_kind="disconnected",
                    timeline_message=f"Could not reconcile Hermes run: {exc}",
                )
        return updated

    def refresh_task(self, task: dict[str, Any]) -> dict[str, Any]:
        run_id = task.get("hermes", {}).get("runId")
        if not run_id:
            raise AdapterError("Task has no Hermes run id.", code="hermes_run_id_missing")
        payload = self._request("GET", f"/v1/runs/{run_id}", timeout=8)
        return self.store.update_live_task_from_run(task["id"], payload)

    def stop_task(self, task_id: str) -> AdapterResult:
        task = self.store.task(task_id, namespace=self.namespace)
        run_id = task.get("hermes", {}).get("runId")
        if not run_id:
            raise AdapterError("Task has no Hermes run id to stop.", code="hermes_run_id_missing")
        payload = self._request("POST", f"/v1/runs/{run_id}/stop", {})
        task = self.store.update_live_task(
            task_id,
            status="stopping",
            latest_update="Stop requested. Hermes will settle the run when the agent reaches a safe interruption point.",
            timeline_kind="stopping",
            timeline_message="Stop requested through Hermes.",
        )
        return AdapterResult(task=task, details=payload)

    def resolve_approval(self, task_id: str, decision: str) -> AdapterResult:
        if decision not in {"once", "deny"}:
            raise AdapterError("Approval decision must be once or deny.", code="invalid_approval_decision")
        task = self.store.task(task_id, namespace=self.namespace)
        run_id = task.get("hermes", {}).get("runId")
        if not run_id:
            raise AdapterError("Task has no Hermes run id for approval.", code="hermes_run_id_missing")
        payload = self._request("POST", f"/v1/runs/{run_id}/approval", {"decision": decision})
        task = self.store.update_live_task(
            task_id,
            latest_update=f"Approval decision recorded: {decision}.",
            approval={"state": "resolved", "decision": decision},
            timeline_kind="approval",
            timeline_message=f"Approval decision recorded: {decision}.",
        )
        return AdapterResult(task=task, details=payload)

    def _session_for(self, witch_id: str) -> str:
        existing = self.store.runtime_session(witch_id, namespace=self.namespace)
        if existing:
            return existing
        payload = self._request("POST", "/api/sessions", {"title": f"Coven {witch_id}", "source": "coven"})
        session_id = str(payload.get("id") or payload.get("session_id") or payload.get("sessionId") or "")
        if not session_id:
            raise AdapterError("Hermes did not return a session identifier.", code="hermes_session_missing", details=payload)
        self.store.set_runtime_session(witch_id, session_id, namespace=self.namespace)
        return session_id

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 20,
    ) -> dict[str, Any]:
        _headers, decoded = self._request_with_headers(method, path, payload, headers=headers, timeout=timeout)
        return decoded

    def _request_with_headers(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 20,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        if not self.base_url:
            raise AdapterError("Hermes API base URL is not configured.", code="hermes_api_unconfigured")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request_headers.update(headers or {})
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=request_headers,
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                response_headers = dict(response.headers.items())
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AdapterError(f"Hermes API returned HTTP {exc.code}.", code="hermes_http_error", details=detail) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise AdapterError(f"Hermes API request timed out: {exc}", code="hermes_timeout") from exc
        except OSError as exc:
            raise AdapterError(f"Hermes API request failed: {exc}", code="hermes_connection_error") from exc
        if not raw:
            raise AdapterError("Hermes API returned an empty response.", code="hermes_empty_response")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdapterError("Hermes API returned non-JSON data.", code="hermes_bad_json", details=raw[:500]) from exc
        if not isinstance(decoded, dict):
            raise AdapterError("Hermes API returned an unexpected JSON shape.", code="hermes_bad_shape", details=decoded)
        return response_headers, decoded

    def _extract_text(self, payload: dict[str, Any]) -> str:
        for key in ("content", "message", "text", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
        message = payload.get("assistant") or payload.get("response")
        if isinstance(message, dict):
            for key in ("content", "text"):
                value = message.get(key)
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        return text
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str) and message["content"].strip():
                    return message["content"].strip()
        raise AdapterError("Hermes returned no assistant text for this turn.", code="hermes_empty_response", details=payload)

    def _feature_enabled(self, capabilities: dict[str, Any], feature: str) -> bool:
        features = capabilities.get("features")
        return isinstance(features, dict) and features.get(feature) is True

    def _capability_summary(self, capabilities: dict[str, Any]) -> dict[str, Any]:
        return {
            "available": capabilities.get("available", True),
            "features": capabilities.get("features") if isinstance(capabilities.get("features"), dict) else {},
            "endpoints": capabilities.get("endpoints") if isinstance(capabilities.get("endpoints"), dict) else {},
        }

    def _validated_task_fields(self, body: dict[str, Any]) -> tuple[str, str, str, str, str]:
        assignee = body.get("assignee")
        if not isinstance(assignee, str) or assignee not in self.store.profile_ids:
            raise AdapterError("Task assignee must be one of the configured witches.", code="invalid_task")
        title = body.get("title")
        instructions = body.get("instructions", "")
        if not isinstance(title, str):
            raise AdapterError("Task title must be a string.", code="invalid_task")
        if not isinstance(instructions, str):
            raise AdapterError("Task instructions must be a string.", code="invalid_task")
        title = title.strip()
        instructions = instructions.strip()
        if not title:
            raise AdapterError("Task title is required.", code="invalid_task")
        if len(title) > 160:
            raise AdapterError("Task title must be 160 characters or fewer.", code="invalid_task")
        if len(instructions) > 16_000:
            raise AdapterError("Task instructions must be 16000 characters or fewer.", code="invalid_task")
        try:
            priority = validate_priority(body.get("priority", "normal"))
        except ConfigError as exc:
            raise AdapterError(str(exc), code="invalid_task") from exc
        idempotency_key = str(body.get("idempotencyKey") or f"coven-{uuid.uuid4().hex}")
        if not (1 <= len(idempotency_key) <= 255) or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key):
            raise AdapterError("Idempotency key must be 1-255 visible ASCII characters.", code="invalid_task")
        return assignee, title, instructions, priority, idempotency_key

    def _resolve_route(self, witch_id: str, body: dict[str, Any]) -> dict[str, Any]:
        route_mode = str(body.get("routeMode") or "auto").lower()
        if route_mode not in {"auto", "local", "api"}:
            route_mode = "auto"
        provider = body.get("provider")
        model = body.get("model")
        if not isinstance(provider, str):
            provider = ""
        if not isinstance(model, str):
            model = ""
        provider = provider.strip()
        model = model.strip()
        reason = "Explicit provider/model request." if provider or model else "Auto routing selected by Coven."
        if not provider and route_mode == "local":
            provider = "ollama"
            model = self.config.providers.ollama_model
            reason = "Local route selected; Coven requested the configured Ollama/local model through Hermes."
        elif not provider and route_mode == "api":
            provider = "openai"
            model = self.config.providers.openai_model
            reason = "API route selected; Coven requested the configured API model through Hermes."
        elif not provider and route_mode == "auto":
            if witch_id in {"circe", "hecate"} and self.config.providers.ollama_model:
                provider = "ollama"
                model = self.config.providers.ollama_model
                reason = "Auto chose local for bounded builder/reviewer work because a local model is configured."
            elif self.config.providers.openai_model:
                provider = "openai"
                model = self.config.providers.openai_model
                reason = "Auto chose the configured API model because no suitable local model was configured."
        model_options = body.get("modelOptions") if isinstance(body.get("modelOptions"), dict) else {}
        return {
            "routeMode": route_mode,
            "provider": provider,
            "model": model,
            "modelOptions": model_options,
            "reason": reason,
        }

    def _task_input(self, task: dict[str, Any]) -> str:
        instructions = task.get("instructions") or "(No additional instructions.)"
        return (
            f"Coven task: {task['title']}\n"
            f"Assigned witch: {task['assignee']}\n"
            f"Priority: {task['priority']}\n\n"
            f"Instructions:\n{instructions}\n\n"
            "Return concrete progress, final result, and artifact paths only for files that actually exist."
        )

    def _role_instructions(self, witch_id: str) -> str:
        roles = {
            "morgana": "You are Morgana, coordinator. Plan, assign, track dependencies, and consolidate results. You cannot grant permissions.",
            "sybil": "You are Sybil, researcher. Favor evidence gathering, comparison, and citations. Avoid write actions unless explicitly permitted.",
            "circe": "You are Circe, builder. Create code/artifacts only inside the selected permitted workspace and report checks run.",
            "hecate": "You are Hecate, reviewer. Review diffs, tests, permissions, and completion evidence. Do not approve your own elevation.",
            "selene": "You are Selene, archivist. Maintain project notes and memory in designated locations. Never store credentials.",
            "ophelia": "You are Ophelia, failure analyst. Diagnose failures and propose recovery; do not automatically retry or destroy state.",
        }
        return roles.get(witch_id, roles["morgana"])

    def _session_key(self, witch_id: str) -> str:
        return f"coven:live:{witch_id}:default"


def build_agent_adapter(config: AppConfig, store: CovenStore):
    if config.demo_mode:
        return DemoAdapter(store)
    return HermesAdapter(store, config)
