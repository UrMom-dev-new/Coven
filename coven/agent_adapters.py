"""Agent runtime adapter boundary for demo fixtures and Hermes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib import error, request

from .configuration import AppConfig
from .store import CovenStore


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
        if not self.available():
            self.store.append_message(witch_id, "user", text, namespace=self.namespace)
            raise AdapterError(
                "Hermes API transport is not configured. Message was saved locally with failed delivery state.",
                code="hermes_api_unconfigured",
            )
        session_id = self._session_for(witch_id)
        payload = self._request("POST", f"/api/sessions/{session_id}/chat", {"input": text})
        self.store.append_message(witch_id, "user", text, namespace=self.namespace)
        assistant_text = self._extract_text(payload)
        if assistant_text:
            messages = self.store.append_message(witch_id, witch_id, assistant_text, namespace=self.namespace)
        else:
            messages = self.store.conversations(witch_id, namespace=self.namespace)
        return AdapterResult(messages=messages, details=payload)

    def create_task(self, body: dict[str, Any]) -> AdapterResult:
        raise AdapterError(
            "The verified Hermes API-server session surface supports chat, but an authoritative task lifecycle endpoint has not been verified for this build.",
            code="hermes_task_interface_unverified",
        )

    def retry_task(self, task_id: str) -> AdapterResult:
        raise AdapterError(
            "Live retry requires verified Hermes task/run identity and side-effect reconciliation.",
            code="hermes_retry_unverified",
        )

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

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise AdapterError("Hermes API base URL is not configured.", code="hermes_api_unconfigured")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AdapterError(f"Hermes API returned HTTP {exc.code}.", code="hermes_http_error", details=detail) from exc
        except OSError as exc:
            raise AdapterError(f"Hermes API request failed: {exc}", code="hermes_connection_error") from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdapterError("Hermes API returned non-JSON data.", code="hermes_bad_json", details=raw[:500]) from exc
        if not isinstance(decoded, dict):
            raise AdapterError("Hermes API returned an unexpected JSON shape.", code="hermes_bad_shape", details=decoded)
        return decoded

    def _extract_text(self, payload: dict[str, Any]) -> str:
        for key in ("content", "message", "text", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        message = payload.get("assistant") or payload.get("response")
        if isinstance(message, dict):
            for key in ("content", "text"):
                value = message.get(key)
                if isinstance(value, str):
                    return value
        return ""


def build_agent_adapter(config: AppConfig, store: CovenStore):
    if config.demo_mode:
        return DemoAdapter(store)
    return HermesAdapter(store, config)
